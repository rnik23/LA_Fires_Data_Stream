# =========================================================
# 1. Imports
# =========================================================

import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from pyspark.sql import functions as F
from pyspark.sql import types as T


# =========================================================
# 2. Configuration
# =========================================================

# Runtime knobs for distributed geocoding behavior.
CONFIG = {
    "num_partitions": 128,
    "max_workers_per_partition": 8,
    "qps_per_partition": 20,
    "max_retries": 5,
    "base_delay": 0.5,
    "jitter": 0.25,
    "provider": "google_places_legacy_find_place",
    "enable_place_details_fallback": False,
}

TABLE_SILVER_INPUT = "SLI_Silver.sli_silver_address_strandardization"
TABLE_CACHE = "SLI_Silver.address_geocode_cache"
TABLE_FAILURES = "SLI_Silver.address_geocode_failures"
TABLE_GOLD = "SLI_Gold.address_geocode_enriched"

PLACES_FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
PLACES_BASIC_FIELDS = "place_id,formatted_address,geometry,name"

API_KEY = dbutils.secrets.get(
    scope="fabric-secrets",
    key="google-geocode-api-key"
)


# =========================================================
# 3. Delta Table DDL Creation
# =========================================================

spark.sql("CREATE SCHEMA IF NOT EXISTS SLI_Silver")
spark.sql("CREATE SCHEMA IF NOT EXISTS SLI_Gold")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TABLE_CACHE} (
    canonical_address STRING,
    formatted_address STRING,
    place_id STRING,
    lat DOUBLE,
    lng DOUBLE,
    provider STRING,
    geocode_ts TIMESTAMP
)
USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TABLE_FAILURES} (
    canonical_address STRING,
    http_status INT,
    error_type STRING,
    error_message STRING,
    response_snippet STRING,
    attempt_ts TIMESTAMP
)
USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {TABLE_GOLD} (
    PARENT_PREM_ID STRING,
    PREM_ID STRING,
    canonical_address STRING,
    formatted_address STRING,
    place_id STRING,
    lat DOUBLE,
    lng DOUBLE
)
USING DELTA
""")


# =========================================================
# 4. Read Silver Table
# =========================================================

silver_df = (
    spark.table(TABLE_SILVER_INPUT)
    .select("PARENT_PREM_ID", "PREM_ID", "canonical_address")
    .filter(F.col("canonical_address").isNotNull())
    .filter(F.length(F.trim(F.col("canonical_address"))) > 0)
)


# =========================================================
# 5. Address Deduplication
# =========================================================

distinct_addresses_df = (
    silver_df
    .select(F.trim(F.col("canonical_address")).alias("canonical_address"))
    .dropDuplicates(["canonical_address"])
)


# =========================================================
# 6. Cache Lookup (Left Anti Join)
# =========================================================

cache_df = spark.table(TABLE_CACHE).select("canonical_address").dropDuplicates(["canonical_address"])

cache_miss_df = (
    distinct_addresses_df.alias("d")
    .join(cache_df.alias("c"), on="canonical_address", how="left_anti")
    .repartition(CONFIG["num_partitions"], "canonical_address")
)

cache_miss_count = cache_miss_df.count()


# =========================================================
# 7. Distributed Geocoding Engine (mapPartitions + ThreadPoolExecutor)
# =========================================================

result_schema = T.StructType([
    T.StructField("canonical_address", T.StringType(), False),
    T.StructField("formatted_address", T.StringType(), True),
    T.StructField("place_id", T.StringType(), True),
    T.StructField("lat", T.DoubleType(), True),
    T.StructField("lng", T.DoubleType(), True),
    T.StructField("provider", T.StringType(), True),
    T.StructField("geocode_ts", T.TimestampType(), True),
    T.StructField("http_status", T.IntegerType(), True),
    T.StructField("error_type", T.StringType(), True),
    T.StructField("error_message", T.StringType(), True),
    T.StructField("response_snippet", T.StringType(), True),
    T.StructField("attempt_ts", T.TimestampType(), True),
    T.StructField("is_success", T.BooleanType(), False),
])


def geocode_partition(partition_iter):
    """
    Runs inside each Spark partition:
    - Uses a shared requests.Session for connection reuse.
    - Uses ThreadPoolExecutor for concurrent API calls per partition.
    - Applies partition-local rate limiting and retry/backoff with jitter.
    """
    addresses = [row["canonical_address"] for row in partition_iter]
    if not addresses:
        return iter([])

    session = requests.Session()
    min_interval = 1.0 / max(1, CONFIG["qps_per_partition"])

    # Shared mutable timestamp for rate-limiting across partition threads.
    last_call = {"ts": 0.0}

    def call_places_details(place_id):
        response = session.get(
            PLACES_DETAILS_URL,
            params={
                "place_id": place_id,
                "fields": PLACES_BASIC_FIELDS,
                "key": API_KEY,
            },
            timeout=20,
        )
        payload = response.json() if response.text else {}
        return response.status_code, payload, response.text

    def call_api(canonical_address):
        retries = 0
        while retries <= CONFIG["max_retries"]:
            try:
                # Partition-local QPS throttle.
                now = time.time()
                elapsed = now - last_call["ts"]
                if elapsed < min_interval:
                    time.sleep(min_interval - elapsed)
                last_call["ts"] = time.time()

                response = session.get(
                    PLACES_FIND_PLACE_URL,
                    params={
                        "input": canonical_address,
                        "inputtype": "textquery",
                        "fields": PLACES_BASIC_FIELDS,
                        "key": API_KEY,
                    },
                    timeout=20,
                )
                http_status = response.status_code
                payload = response.json() if response.text else {}
                api_status = payload.get("status")

                if http_status == 200 and api_status == "OK":
                    first = payload.get("candidates", [{}])[0]
                    place_id = first.get("place_id")
                    formatted_address = first.get("formatted_address")
                    location = first.get("geometry", {}).get("location", {})

                    if (
                        CONFIG.get("enable_place_details_fallback", False)
                        and place_id
                        and (
                            formatted_address is None
                            or location.get("lat") is None
                            or location.get("lng") is None
                        )
                    ):
                        details_http_status, details_payload, _ = call_places_details(place_id)
                        if details_http_status == 200 and details_payload.get("status") == "OK":
                            details_result = details_payload.get("result", {})
                            formatted_address = details_result.get("formatted_address") or formatted_address
                            location = details_result.get("geometry", {}).get("location", location)

                    return {
                        "canonical_address": canonical_address,
                        "formatted_address": formatted_address,
                        "place_id": place_id,
                        "lat": float(location.get("lat")) if location.get("lat") is not None else None,
                        "lng": float(location.get("lng")) if location.get("lng") is not None else None,
                        "provider": CONFIG["provider"],
                        "geocode_ts": datetime.utcnow(),
                        "http_status": None,
                        "error_type": None,
                        "error_message": None,
                        "response_snippet": None,
                        "attempt_ts": datetime.utcnow(),
                        "is_success": True,
                    }

                if http_status == 200 and api_status == "ZERO_RESULTS":
                    return {
                        "canonical_address": canonical_address,
                        "formatted_address": None,
                        "place_id": None,
                        "lat": None,
                        "lng": None,
                        "provider": None,
                        "geocode_ts": None,
                        "http_status": 200,
                        "error_type": "ZERO_RESULTS",
                        "error_message": "No geocoding match found.",
                        "response_snippet": json.dumps(payload)[:1000],
                        "attempt_ts": datetime.utcnow(),
                        "is_success": False,
                    }

                retriable = (
                    (http_status == 429)
                    or (500 <= http_status <= 599)
                    or (api_status in {"OVER_QUERY_LIMIT", "UNKNOWN_ERROR"})
                )
                if retriable and retries < CONFIG["max_retries"]:
                    sleep_s = (CONFIG["base_delay"] * (2 ** retries)) + random.uniform(0, CONFIG["jitter"])
                    time.sleep(sleep_s)
                    retries += 1
                    continue

                return {
                    "canonical_address": canonical_address,
                    "formatted_address": None,
                    "place_id": None,
                    "lat": None,
                    "lng": None,
                    "provider": None,
                    "geocode_ts": None,
                    "http_status": http_status,
                    "error_type": api_status or "HTTP_ERROR",
                    "error_message": f"Geocode request failed after retries={retries}",
                    "response_snippet": response.text[:1000] if response.text else None,
                    "attempt_ts": datetime.utcnow(),
                    "is_success": False,
                }

            except Exception as ex:
                if retries < CONFIG["max_retries"]:
                    sleep_s = (CONFIG["base_delay"] * (2 ** retries)) + random.uniform(0, CONFIG["jitter"])
                    time.sleep(sleep_s)
                    retries += 1
                    continue
                return {
                    "canonical_address": canonical_address,
                    "formatted_address": None,
                    "place_id": None,
                    "lat": None,
                    "lng": None,
                    "provider": None,
                    "geocode_ts": None,
                    "http_status": None,
                    "error_type": "NETWORK_EXCEPTION",
                    "error_message": f"Max retry exceeded: {str(ex)[:400]}",
                    "response_snippet": None,
                    "attempt_ts": datetime.utcnow(),
                    "is_success": False,
                }

        return {
            "canonical_address": canonical_address,
            "formatted_address": None,
            "place_id": None,
            "lat": None,
            "lng": None,
            "provider": None,
            "geocode_ts": None,
            "http_status": None,
            "error_type": "MAX_RETRY_EXCEEDED",
            "error_message": "Retry loop exited unexpectedly.",
            "response_snippet": None,
            "attempt_ts": datetime.utcnow(),
            "is_success": False,
        }

    max_workers = max(1, CONFIG["max_workers_per_partition"])
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(call_api, addr) for addr in addresses]
        for future in as_completed(futures):
            results.append(future.result())

    return iter(results)


# =========================================================
# 8. Execute Geocoding Job
# =========================================================

geocode_result_df = spark.createDataFrame(
    cache_miss_df.rdd.mapPartitions(geocode_partition),
    schema=result_schema,
)


# =========================================================
# 9. Split Success vs Failures
# =========================================================

success_df = (
    geocode_result_df
    .filter(F.col("is_success") == True)
    .select(
        "canonical_address",
        "formatted_address",
        "place_id",
        "lat",
        "lng",
        "provider",
        "geocode_ts",
    )
)

failure_df = (
    geocode_result_df
    .filter(F.col("is_success") == False)
    .select(
        "canonical_address",
        "http_status",
        "error_type",
        "error_message",
        "response_snippet",
        "attempt_ts",
    )
)

success_count = success_df.count()
failure_count = failure_df.count()


# =========================================================
# 10. Write Failures (Dead Letter Table)
# =========================================================

if failure_count > 0:
    (
        failure_df
        .repartition(max(1, CONFIG["num_partitions"] // 4), "canonical_address")
        .write
        .format("delta")
        .mode("append")
        .saveAsTable(TABLE_FAILURES)
    )


# =========================================================
# 11. Upsert Cache Table
# =========================================================

if success_count > 0:
    upsert_src_df = success_df.repartition(max(1, CONFIG["num_partitions"] // 4), "canonical_address")
    upsert_src_df.createOrReplaceTempView("tmp_geocode_success")

    spark.sql(f"""
    MERGE INTO {TABLE_CACHE} AS tgt
    USING tmp_geocode_success AS src
    ON tgt.canonical_address = src.canonical_address
    WHEN MATCHED THEN UPDATE SET
      tgt.formatted_address = src.formatted_address,
      tgt.place_id = src.place_id,
      tgt.lat = src.lat,
      tgt.lng = src.lng,
      tgt.provider = src.provider,
      tgt.geocode_ts = src.geocode_ts
    WHEN NOT MATCHED THEN INSERT (
      canonical_address,
      formatted_address,
      place_id,
      lat,
      lng,
      provider,
      geocode_ts
    ) VALUES (
      src.canonical_address,
      src.formatted_address,
      src.place_id,
      src.lat,
      src.lng,
      src.provider,
      src.geocode_ts
    )
    """)


# =========================================================
# 12. Join Cache Back to Original Dataset
# =========================================================

cache_latest_df = spark.table(TABLE_CACHE).select(
    "canonical_address",
    "formatted_address",
    "place_id",
    "lat",
    "lng",
)

enriched_df = (
    silver_df.alias("s")
    .join(cache_latest_df.alias("c"), on="canonical_address", how="left")
    .select(
        "s.PARENT_PREM_ID",
        "s.PREM_ID",
        "s.canonical_address",
        "c.formatted_address",
        "c.place_id",
        "c.lat",
        "c.lng",
    )
)


# =========================================================
# 13. Write Gold Table
# =========================================================

(
    enriched_df
    .repartition(CONFIG["num_partitions"], "canonical_address")
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(TABLE_GOLD)
)


# =========================================================
# 14. Delta Optimization (OPTIMIZE + ZORDER + VACUUM)
# =========================================================

spark.sql(f"OPTIMIZE {TABLE_CACHE} ZORDER BY (canonical_address)")
spark.sql(f"OPTIMIZE {TABLE_GOLD} ZORDER BY (canonical_address)")
spark.sql(f"VACUUM {TABLE_CACHE} RETAIN 168 HOURS")
spark.sql(f"VACUUM {TABLE_GOLD} RETAIN 168 HOURS")
spark.sql(f"VACUUM {TABLE_FAILURES} RETAIN 168 HOURS")


# =========================================================
# 15. Runtime Metrics Summary
# =========================================================

cache_size_after_merge = spark.table(TABLE_CACHE).count()

print("=== Geocoding Pipeline Metrics ===")
print(f"Cache misses geocoded this run: {cache_miss_count}")
print(f"Successful geocodes: {success_count}")
print(f"Failed geocodes: {failure_count}")
print(f"Cache size after merge: {cache_size_after_merge}")
