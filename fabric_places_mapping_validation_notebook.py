# =========================================================
# 1. Imports
# =========================================================

import math
import re
from typing import Dict

from pyspark.sql import functions as F
from pyspark.sql import types as T


# =========================================================
# 2. Configuration
# =========================================================

CONFIG = {
    "input_table": "SLI_Gold.address_geocode_enriched",
    "validation_table": "SLI_Gold.address_geocode_validation",
    "summary_table": "SLI_Gold.address_geocode_validation_summary",
    "distance_threshold_km": 2.0,
    "far_distance_threshold_km": 5.0,
    "low_confidence_threshold": 0.55,
    "street_weight": 0.35,
    "city_weight": 0.20,
    "state_weight": 0.15,
    "zip_weight": 0.10,
    "granularity_weight": 0.10,
    "distance_weight": 0.10,
    "region_weight": 0.10,
    "write_mode": "overwrite",
    "num_output_partitions": 32,
}

ALLOWED_LOCALITIES = {
    "manhattan", "new york", "brooklyn", "queens", "bronx", "staten island",
    "yonkers", "mount vernon", "new rochelle", "white plains", "peekskill", "rye",
    "harrison", "mamaroneck", "larchmont", "tarrytown", "sleepy hollow", "ossining",
    "dobbs ferry", "irvington", "hastings on hudson", "scarsdale", "greenburgh",
    "eastchester", "pelham", "bronxville", "ardsley", "elmsford", "pleasantville",
    "briarcliff manor", "bedford", "mount kisco", "chappaqua", "cortlandt",
    "croton on hudson", "port chester",
}

ALLOWED_COUNTIES = {
    "new york county", "kings county", "queens county", "bronx county",
    "richmond county", "westchester county",
}

ALLOWED_REGION_BBOX = {
    "min_lat": 40.49,
    "max_lat": 41.35,
    "min_lng": -74.35,
    "max_lng": -73.45,
}

STATE_ABBREVIATIONS = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}

STREET_SUFFIXES = {
    "street": "st", "st": "st", "avenue": "ave", "ave": "ave", "road": "rd", "rd": "rd",
    "boulevard": "blvd", "blvd": "blvd", "drive": "dr", "dr": "dr", "lane": "ln", "ln": "ln",
    "court": "ct", "ct": "ct", "place": "pl", "pl": "pl", "terrace": "ter", "ter": "ter",
    "parkway": "pkwy", "pkwy": "pkwy", "circle": "cir", "cir": "cir", "highway": "hwy", "hwy": "hwy",
}


# =========================================================
# 3. Delta Table DDL Creation
# =========================================================

spark.sql("CREATE SCHEMA IF NOT EXISTS SLI_Gold")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CONFIG['validation_table']} (
    PARENT_PREM_ID STRING,
    PREM_ID STRING,
    canonical_address STRING,
    formatted_address STRING,
    place_id STRING,
    lat DOUBLE,
    lng DOUBLE,
    normalized_input_address STRING,
    normalized_formatted_address STRING,
    input_house_number STRING,
    output_house_number STRING,
    input_street_normalized STRING,
    output_street_normalized STRING,
    input_city_normalized STRING,
    output_city_normalized STRING,
    input_state_normalized STRING,
    output_state_normalized STRING,
    input_zip_normalized STRING,
    output_zip_normalized STRING,
    street_match BOOLEAN,
    house_number_match BOOLEAN,
    city_match BOOLEAN,
    state_match BOOLEAN,
    zip_match BOOLEAN,
    missing_street_in_output BOOLEAN,
    street_present_but_house_missing BOOLEAN,
    component_mismatch_count INT,
    is_city_level_match BOOLEAN,
    is_partial_match BOOLEAN,
    distance_km DOUBLE,
    is_far_distance BOOLEAN,
    is_out_of_region BOOLEAN,
    region_match BOOLEAN,
    confidence_score DOUBLE,
    is_low_confidence BOOLEAN,
    is_suspicious BOOLEAN,
    validation_ts TIMESTAMP
)
USING DELTA
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CONFIG['summary_table']} (
    metric STRING,
    value DOUBLE,
    validation_ts TIMESTAMP
)
USING DELTA
""")


# =========================================================
# 4. Read Input Delta Table
# =========================================================

input_df = spark.table(CONFIG["input_table"])

# The validator supports either split input columns or just canonical_address.
# Optional columns used if present: street, city, state, zip, input_lat, input_lng,
# borough, county.


# =========================================================
# 5. Validation Helper Functions
# =========================================================

validation_schema = T.StructType([
    T.StructField("normalized_input_address", T.StringType(), True),
    T.StructField("normalized_formatted_address", T.StringType(), True),
    T.StructField("input_house_number", T.StringType(), True),
    T.StructField("output_house_number", T.StringType(), True),
    T.StructField("input_street_normalized", T.StringType(), True),
    T.StructField("output_street_normalized", T.StringType(), True),
    T.StructField("input_city_normalized", T.StringType(), True),
    T.StructField("output_city_normalized", T.StringType(), True),
    T.StructField("input_state_normalized", T.StringType(), True),
    T.StructField("output_state_normalized", T.StringType(), True),
    T.StructField("input_zip_normalized", T.StringType(), True),
    T.StructField("output_zip_normalized", T.StringType(), True),
    T.StructField("street_match", T.BooleanType(), True),
    T.StructField("house_number_match", T.BooleanType(), True),
    T.StructField("city_match", T.BooleanType(), True),
    T.StructField("state_match", T.BooleanType(), True),
    T.StructField("zip_match", T.BooleanType(), True),
    T.StructField("missing_street_in_output", T.BooleanType(), True),
    T.StructField("street_present_but_house_missing", T.BooleanType(), True),
    T.StructField("component_mismatch_count", T.IntegerType(), True),
    T.StructField("is_city_level_match", T.BooleanType(), True),
    T.StructField("is_partial_match", T.BooleanType(), True),
    T.StructField("distance_km", T.DoubleType(), True),
    T.StructField("is_far_distance", T.BooleanType(), True),
    T.StructField("is_out_of_region", T.BooleanType(), True),
    T.StructField("region_match", T.BooleanType(), True),
    T.StructField("confidence_score", T.DoubleType(), True),
    T.StructField("is_low_confidence", T.BooleanType(), True),
    T.StructField("is_suspicious", T.BooleanType(), True),
])


def normalize_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_state(value):
    text = normalize_text(value)
    if not text:
        return ""
    if len(text) == 2:
        return text.upper()
    return STATE_ABBREVIATIONS.get(text, text.upper())


def normalize_street(value):
    text = normalize_text(value)
    if not text:
        return ""
    return " ".join(STREET_SUFFIXES.get(token, token) for token in text.split())


def extract_zip(value):
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", str(value or ""))
    return match.group(1) if match else None


def extract_house_number(value):
    match = re.match(r"^\s*(\d+[a-zA-Z\-]?)\b", str(value or ""))
    return match.group(1) if match else None


def tokenize_address(address):
    parts = [part.strip() for part in str(address or "").split(",") if part.strip()]
    street = parts[0] if len(parts) > 0 else ""
    city = parts[1] if len(parts) > 1 else ""
    state_zip = parts[2] if len(parts) > 2 else ""
    country = parts[3] if len(parts) > 3 else ""
    state = ""
    postal_code = extract_zip(state_zip) or extract_zip(country)
    tokens = state_zip.split()
    if tokens:
        state = normalize_state(tokens[0])
    return street, city, state, postal_code or ""


def haversine_km(lat1, lon1, lat2, lon2):
    try:
        lat1_f, lon1_f, lat2_f, lon2_f = map(float, [lat1, lon1, lat2, lon2])
    except (TypeError, ValueError):
        return None
    radius_km = 6371.0088
    dlat = math.radians(lat2_f - lat1_f)
    dlon = math.radians(lon2_f - lon1_f)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1_f)) * math.cos(math.radians(lat2_f)) * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


# =========================================================
# 6. Validation UDF
# =========================================================

@F.udf(returnType=validation_schema)
def validate_mapping_udf(
    canonical_address,
    street,
    city,
    state,
    postal_code,
    borough,
    county,
    formatted_address,
    lat,
    lng,
    input_lat,
    input_lng,
):
    input_street = street or ""
    input_city = city or ""
    input_state = state or ""
    input_zip = postal_code or ""

    if not input_street and canonical_address:
        parsed_street, parsed_city, parsed_state, parsed_zip = tokenize_address(canonical_address)
        input_street = input_street or parsed_street
        input_city = input_city or parsed_city
        input_state = input_state or parsed_state
        input_zip = input_zip or parsed_zip

    output_street, output_city, output_state, output_zip = tokenize_address(formatted_address)

    normalized_input_address = normalize_text(" ".join(filter(None, [input_street, input_city, input_state, input_zip])))
    normalized_formatted_address = normalize_text(formatted_address)
    input_house_number = extract_house_number(input_street)
    output_house_number = extract_house_number(output_street)
    input_street_normalized = normalize_street(input_street)
    output_street_normalized = normalize_street(output_street)
    input_city_normalized = normalize_text(input_city)
    output_city_normalized = normalize_text(output_city)
    input_state_normalized = normalize_state(input_state)
    output_state_normalized = normalize_state(output_state)
    input_zip_normalized = extract_zip(input_zip)
    output_zip_normalized = extract_zip(output_zip)

    street_match = bool(input_street_normalized and output_street_normalized and input_street_normalized == output_street_normalized)
    house_number_match = bool(input_house_number and output_house_number and input_house_number == output_house_number)
    city_match = bool(input_city_normalized and output_city_normalized and input_city_normalized == output_city_normalized)
    state_match = bool(input_state_normalized and output_state_normalized and input_state_normalized == output_state_normalized)
    zip_match = bool(input_zip_normalized and output_zip_normalized and input_zip_normalized == output_zip_normalized)
    missing_street_in_output = bool(input_street_normalized and not output_street_normalized)
    street_present_but_house_missing = bool(input_house_number and not output_house_number)

    component_mismatch_count = sum([
        int(bool(input_street_normalized) and not street_match),
        int(bool(input_city_normalized) and not city_match),
        int(bool(input_state_normalized) and not state_match),
        int(bool(input_zip_normalized) and not zip_match),
    ])

    output_looks_like_city_only = bool(
        output_city_normalized and output_street_normalized and output_street_normalized == output_city_normalized and not output_house_number
    )
    is_city_level_match = bool((input_street_normalized or input_house_number) and ((not output_house_number and output_city_normalized) or output_looks_like_city_only))
    is_partial_match = bool((input_street_normalized or input_house_number) and not is_city_level_match and output_street_normalized and input_house_number and not output_house_number)

    distance_km = haversine_km(input_lat, input_lng, lat, lng)
    is_far_distance = bool(distance_km is not None and distance_km > float(CONFIG["far_distance_threshold_km"]))

    formatted_text = normalize_text(formatted_address)
    locality_candidates = {
        normalize_text(borough),
        normalize_text(county),
        formatted_text,
        input_city_normalized,
        output_city_normalized,
    }
    locality_hits = any(
        locality and (
            locality in ALLOWED_LOCALITIES
            or locality in ALLOWED_COUNTIES
            or any(allowed in locality for allowed in (ALLOWED_LOCALITIES | ALLOWED_COUNTIES))
        )
        for locality in locality_candidates
    )

    coords_in_bbox = False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        coords_in_bbox = (
            ALLOWED_REGION_BBOX["min_lat"] <= lat_f <= ALLOWED_REGION_BBOX["max_lat"]
            and ALLOWED_REGION_BBOX["min_lng"] <= lng_f <= ALLOWED_REGION_BBOX["max_lng"]
        )
    except (TypeError, ValueError):
        coords_in_bbox = False

    state_is_ny = bool(
        output_state_normalized == "NY"
        or re.search(r"\bny\b", formatted_text) is not None
        or "new york" in formatted_text
    )
    is_out_of_region = bool((output_state_normalized and not state_is_ny) or (not locality_hits and not coords_in_bbox))
    region_match = not is_out_of_region

    score = 0.0
    score += CONFIG["street_weight"] * (1.0 if street_match and house_number_match else 0.75 if street_match else 0.0)
    score += CONFIG["city_weight"] * (1.0 if city_match else 0.0)
    score += CONFIG["state_weight"] * (1.0 if state_match else 0.0)
    score += CONFIG["zip_weight"] * (1.0 if zip_match else 0.0)
    score += CONFIG["granularity_weight"] * (0.0 if is_city_level_match else 0.5 if is_partial_match else 1.0)

    if distance_km is None:
        distance_component = 0.5
    elif distance_km <= CONFIG["distance_threshold_km"]:
        distance_component = 1.0
    elif distance_km <= CONFIG["far_distance_threshold_km"]:
        distance_component = 0.5
    else:
        distance_component = 0.0
    score += CONFIG["distance_weight"] * distance_component
    score += CONFIG["region_weight"] * (1.0 if region_match else 0.0)
    confidence_score = round(max(0.0, min(1.0, score)), 4)
    is_low_confidence = confidence_score < CONFIG["low_confidence_threshold"]
    is_suspicious = bool(
        is_low_confidence
        or is_city_level_match
        or is_partial_match
        or is_far_distance
        or is_out_of_region
        or component_mismatch_count >= 2
    )

    return (
        normalized_input_address,
        normalized_formatted_address,
        input_house_number,
        output_house_number,
        input_street_normalized,
        output_street_normalized,
        input_city_normalized,
        output_city_normalized,
        input_state_normalized,
        output_state_normalized,
        input_zip_normalized,
        output_zip_normalized,
        street_match,
        house_number_match,
        city_match,
        state_match,
        zip_match,
        missing_street_in_output,
        street_present_but_house_missing,
        component_mismatch_count,
        is_city_level_match,
        is_partial_match,
        distance_km,
        is_far_distance,
        is_out_of_region,
        region_match,
        confidence_score,
        is_low_confidence,
        is_suspicious,
    )


# =========================================================
# 7. Apply Validation Logic
# =========================================================

validated_df = (
    input_df
    .withColumn(
        "validation",
        validate_mapping_udf(
            F.col("canonical_address"),
            F.coalesce(F.col("street"), F.lit(None).cast("string")),
            F.coalesce(F.col("city"), F.lit(None).cast("string")),
            F.coalesce(F.col("state"), F.lit(None).cast("string")),
            F.coalesce(F.col("zip"), F.col("postal_code"), F.lit(None).cast("string")),
            F.coalesce(F.col("borough"), F.lit(None).cast("string")),
            F.coalesce(F.col("county"), F.lit(None).cast("string")),
            F.col("formatted_address"),
            F.col("lat"),
            F.col("lng"),
            F.coalesce(F.col("input_lat"), F.col("expected_lat"), F.lit(None).cast("double")),
            F.coalesce(F.col("input_lng"), F.col("input_lon"), F.col("expected_lng"), F.col("expected_lon"), F.lit(None).cast("double")),
        )
    )
    .select("*", "validation.*")
    .drop("validation")
    .withColumn("validation_ts", F.current_timestamp())
)


# =========================================================
# 8. Write Validation Delta Table
# =========================================================

(
    validated_df
    .repartition(CONFIG["num_output_partitions"])
    .write
    .format("delta")
    .mode(CONFIG["write_mode"])
    .option("overwriteSchema", "true")
    .saveAsTable(CONFIG["validation_table"])
)


# =========================================================
# 9. Build Summary Metrics
# =========================================================

summary_df = (
    validated_df
    .agg(
        F.count(F.lit(1)).alias("record_count"),
        (F.avg(F.when(F.col("confidence_score") >= 0.85, 1.0).otherwise(0.0)) * 100.0).alias("pct_high_confidence"),
        (F.avg(F.when(F.col("is_low_confidence"), 1.0).otherwise(0.0)) * 100.0).alias("pct_low_confidence"),
        (F.avg(F.when(F.col("is_suspicious"), 1.0).otherwise(0.0)) * 100.0).alias("pct_likely_incorrect"),
        (F.avg(F.when(F.col("is_city_level_match"), 1.0).otherwise(0.0)) * 100.0).alias("pct_city_level_match"),
        (F.avg(F.when(F.col("is_partial_match"), 1.0).otherwise(0.0)) * 100.0).alias("pct_partial_match"),
        (F.avg(F.when(F.col("is_far_distance"), 1.0).otherwise(0.0)) * 100.0).alias("pct_far_distance"),
        (F.avg(F.when(F.col("is_out_of_region"), 1.0).otherwise(0.0)) * 100.0).alias("pct_out_of_region"),
    )
    .select(
        F.array(
            F.struct(F.lit("record_count").alias("metric"), F.col("record_count").cast("double").alias("value")),
            F.struct(F.lit("pct_high_confidence").alias("metric"), F.round(F.col("pct_high_confidence"), 2).alias("value")),
            F.struct(F.lit("pct_low_confidence").alias("metric"), F.round(F.col("pct_low_confidence"), 2).alias("value")),
            F.struct(F.lit("pct_likely_incorrect").alias("metric"), F.round(F.col("pct_likely_incorrect"), 2).alias("value")),
            F.struct(F.lit("pct_city_level_match").alias("metric"), F.round(F.col("pct_city_level_match"), 2).alias("value")),
            F.struct(F.lit("pct_partial_match").alias("metric"), F.round(F.col("pct_partial_match"), 2).alias("value")),
            F.struct(F.lit("pct_far_distance").alias("metric"), F.round(F.col("pct_far_distance"), 2).alias("value")),
            F.struct(F.lit("pct_out_of_region").alias("metric"), F.round(F.col("pct_out_of_region"), 2).alias("value")),
        ).alias("metrics")
    )
    .select(F.explode("metrics").alias("metric_struct"))
    .select(
        F.col("metric_struct.metric").alias("metric"),
        F.col("metric_struct.value").alias("value"),
    )
    .withColumn("validation_ts", F.current_timestamp())
)


# =========================================================
# 10. Write Summary Delta Table
# =========================================================

(
    summary_df
    .write
    .format("delta")
    .mode(CONFIG["write_mode"])
    .option("overwriteSchema", "true")
    .saveAsTable(CONFIG["summary_table"])
)


# =========================================================
# 11. Delta Optimization
# =========================================================

spark.sql(f"OPTIMIZE {CONFIG['validation_table']} ZORDER BY (canonical_address, place_id)")
spark.sql(f"OPTIMIZE {CONFIG['summary_table']} ZORDER BY (metric)")
spark.sql(f"VACUUM {CONFIG['validation_table']} RETAIN 168 HOURS")
spark.sql(f"VACUUM {CONFIG['summary_table']} RETAIN 168 HOURS")


# =========================================================
# 12. Runtime Metrics Summary
# =========================================================

summary_rows = {row['metric']: row['value'] for row in summary_df.collect()}

print("=== Places Mapping Validation Metrics ===")
print(f"Record count: {summary_rows.get('record_count', 0)}")
print(f"% High confidence: {summary_rows.get('pct_high_confidence', 0)}")
print(f"% Low confidence: {summary_rows.get('pct_low_confidence', 0)}")
print(f"% Likely incorrect: {summary_rows.get('pct_likely_incorrect', 0)}")
print(f"% City-level match: {summary_rows.get('pct_city_level_match', 0)}")
print(f"% Partial match: {summary_rows.get('pct_partial_match', 0)}")
print(f"% Far distance: {summary_rows.get('pct_far_distance', 0)}")
print(f"% Out of region: {summary_rows.get('pct_out_of_region', 0)}")
