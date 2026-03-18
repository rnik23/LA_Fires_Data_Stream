"""Validate Google Places address mapping outputs without external API calls.

This module compares original input address components against Google Places
mapping outputs (formatted address, lat/lng, place_id) and assigns validation
flags plus a confidence score so suspicious mappings can be reviewed or filtered.

Usage example:
    python scripts/validate_places_mappings.py \
        --input mappings.csv \
        --output validated_mappings.csv

The script is intentionally offline-only and does not call any external APIs.
"""

from __future__ import annotations

import argparse
import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd


DEFAULT_CONFIG: Dict[str, object] = {
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
}

ALLOWED_LOCALITIES = {
    "manhattan",
    "new york",
    "brooklyn",
    "queens",
    "bronx",
    "staten island",
    "yonkers",
    "mount vernon",
    "new rochelle",
    "white plains",
    "peekskill",
    "rye",
    "harrison",
    "mamaroneck",
    "larchmont",
    "tarrytown",
    "sleepy hollow",
    "ossining",
    "dobbs ferry",
    "irvington",
    "hastings on hudson",
    "scarsdale",
    "greenburgh",
    "eastchester",
    "pelham",
    "bronxville",
    "ardsley",
    "elmsford",
    "pleasantville",
    "briarcliff manor",
    "bedford",
    "mount kisco",
    "chappaqua",
    "cortlandt",
    "croton on hudson",
    "pleasantville",
    "port chester",
}

ALLOWED_COUNTIES = {
    "new york county",
    "kings county",
    "queens county",
    "bronx county",
    "richmond county",
    "westchester county",
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


@dataclass
class AddressComponents:
    raw: str
    normalized: str
    house_number: Optional[str]
    street: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]


def normalize_text(value: object) -> str:
    """Lowercase and normalize whitespace/punctuation for text comparison."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_state(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    if len(text) == 2:
        return text.upper()
    return STATE_ABBREVIATIONS.get(text, text.upper())


def normalize_street(street: object) -> str:
    text = normalize_text(street)
    if not text:
        return ""
    parts = [STREET_SUFFIXES.get(token, token) for token in text.split()]
    return " ".join(parts)


def extract_zip(value: object) -> Optional[str]:
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", str(value or ""))
    return match.group(1) if match else None


def extract_house_number(value: object) -> Optional[str]:
    match = re.match(r"^\s*(\d+[a-zA-Z\-]?)\b", str(value or ""))
    return match.group(1) if match else None


def tokenize_address(formatted_address: object) -> Tuple[str, str, str, str]:
    parts = [part.strip() for part in str(formatted_address or "").split(",") if part.strip()]
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


def parse_address_components(row: pd.Series) -> Tuple[AddressComponents, AddressComponents]:
    """Create comparable component objects for input and Google output addresses."""
    input_street = row.get("street") or row.get("input_street") or row.get("address_line_1") or ""
    input_city = row.get("city") or row.get("input_city") or ""
    input_state = row.get("state") or row.get("input_state") or ""
    input_zip = row.get("zip") or row.get("zipcode") or row.get("postal_code") or row.get("input_zip") or ""

    if not input_street and row.get("canonical_address"):
        street, city, state, postal_code = tokenize_address(row.get("canonical_address"))
        input_street = input_street or street
        input_city = input_city or city
        input_state = input_state or state
        input_zip = input_zip or postal_code

    output_formatted = row.get("formatted_address") or row.get("google_formatted_address") or ""
    output_street, output_city, output_state, output_zip = tokenize_address(output_formatted)

    input_components = AddressComponents(
        raw=" ".join(filter(None, [str(input_street), str(input_city), str(input_state), str(input_zip)])),
        normalized=normalize_text(" ".join(filter(None, [input_street, input_city, input_state, input_zip]))),
        house_number=extract_house_number(input_street),
        street=normalize_street(input_street),
        city=normalize_text(input_city),
        state=normalize_state(input_state),
        postal_code=extract_zip(input_zip) or None,
    )
    output_components = AddressComponents(
        raw=str(output_formatted),
        normalized=normalize_text(output_formatted),
        house_number=extract_house_number(output_street),
        street=normalize_street(output_street),
        city=normalize_text(output_city),
        state=normalize_state(output_state),
        postal_code=extract_zip(output_zip) or None,
    )
    return input_components, output_components


def compare_components(input_addr: AddressComponents, output_addr: AddressComponents) -> Dict[str, object]:
    street_match = bool(input_addr.street and output_addr.street and input_addr.street == output_addr.street)
    house_number_match = bool(
        input_addr.house_number and output_addr.house_number and input_addr.house_number == output_addr.house_number
    )
    city_match = bool(input_addr.city and output_addr.city and input_addr.city == output_addr.city)
    state_match = bool(input_addr.state and output_addr.state and input_addr.state == output_addr.state)
    zip_match = bool(input_addr.postal_code and output_addr.postal_code and input_addr.postal_code == output_addr.postal_code)

    missing_street_in_output = bool(input_addr.street and not output_addr.street)
    street_present_but_house_missing = bool(input_addr.house_number and not output_addr.house_number)
    component_mismatch_count = sum([
        int(bool(input_addr.street) and not street_match),
        int(bool(input_addr.city) and not city_match),
        int(bool(input_addr.state) and not state_match),
        int(bool(input_addr.postal_code) and not zip_match),
    ])

    return {
        "street_match": street_match,
        "house_number_match": house_number_match,
        "city_match": city_match,
        "state_match": state_match,
        "zip_match": zip_match,
        "missing_street_in_output": missing_street_in_output,
        "street_present_but_house_missing": street_present_but_house_missing,
        "component_mismatch_count": component_mismatch_count,
    }


def detect_granularity_mismatch(input_addr: AddressComponents, output_addr: AddressComponents) -> Dict[str, bool]:
    input_has_street_level = bool(input_addr.street or input_addr.house_number)
    output_has_street_level = bool(output_addr.house_number)
    output_looks_like_city_only = bool(
        output_addr.city
        and output_addr.street
        and output_addr.street == output_addr.city
        and not output_addr.house_number
    )
    is_city_level_match = bool(
        input_has_street_level
        and (
            (not output_has_street_level and output_addr.city)
            or output_looks_like_city_only
        )
    )
    is_partial_match = bool(
        input_has_street_level
        and not is_city_level_match
        and bool(output_addr.street)
        and input_addr.house_number
        and not output_addr.house_number
    )
    return {
        "is_city_level_match": is_city_level_match,
        "is_partial_match": is_partial_match,
    }


def haversine_km(lat1: object, lon1: object, lat2: object, lon2: object) -> Optional[float]:
    try:
        lat1_f, lon1_f, lat2_f, lon2_f = map(float, [lat1, lon1, lat2, lon2])
    except (TypeError, ValueError):
        return None

    radius_km = 6371.0088
    dlat = math.radians(lat2_f - lat1_f)
    dlon = math.radians(lon2_f - lon1_f)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1_f))
        * math.cos(math.radians(lat2_f))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


def distance_validation(row: pd.Series, config: Dict[str, object]) -> Dict[str, object]:
    expected_lat = row.get("input_lat") or row.get("expected_lat")
    expected_lng = row.get("input_lng") or row.get("input_lon") or row.get("expected_lng") or row.get("expected_lon")
    returned_lat = row.get("lat")
    returned_lng = row.get("lng")

    distance_km = haversine_km(expected_lat, expected_lng, returned_lat, returned_lng)
    is_far_distance = bool(distance_km is not None and distance_km > float(config["far_distance_threshold_km"]))
    return {
        "distance_km": distance_km,
        "is_far_distance": is_far_distance,
    }


def region_validation(row: pd.Series, input_addr: AddressComponents, output_addr: AddressComponents) -> Dict[str, object]:
    """Flag mappings that fall outside NYC boroughs or Westchester County."""
    formatted_text = normalize_text(row.get("formatted_address") or row.get("google_formatted_address"))
    locality_candidates = {
        normalize_text(row.get("borough")),
        normalize_text(row.get("county")),
        formatted_text,
        input_addr.city,
        output_addr.city,
    }
    locality_hits = any(
        locality and (
            locality in ALLOWED_LOCALITIES
            or locality in ALLOWED_COUNTIES
            or any(allowed in locality for allowed in ALLOWED_LOCALITIES | ALLOWED_COUNTIES)
        )
        for locality in locality_candidates
    )

    returned_lat = row.get("lat")
    returned_lng = row.get("lng")
    coords_in_bbox = False
    try:
        lat = float(returned_lat)
        lng = float(returned_lng)
        coords_in_bbox = (
            ALLOWED_REGION_BBOX["min_lat"] <= lat <= ALLOWED_REGION_BBOX["max_lat"]
            and ALLOWED_REGION_BBOX["min_lng"] <= lng <= ALLOWED_REGION_BBOX["max_lng"]
        )
    except (TypeError, ValueError):
        coords_in_bbox = False

    state_is_ny = bool(
        output_addr.state == "NY"
        or re.search(r"\bny\b", formatted_text) is not None
        or "new york" in formatted_text
    )
    is_out_of_region = bool((output_addr.state and not state_is_ny) or (not locality_hits and not coords_in_bbox))
    return {
        "is_out_of_region": is_out_of_region,
        "region_match": not is_out_of_region,
    }


def score_mapping(
    component_results: Dict[str, object],
    granularity_results: Dict[str, bool],
    distance_results: Dict[str, object],
    region_results: Dict[str, object],
    config: Dict[str, object],
) -> float:
    score = 0.0
    score += float(config["street_weight"]) * (
        1.0 if component_results["street_match"] and component_results["house_number_match"]
        else 0.75 if component_results["street_match"]
        else 0.0
    )
    score += float(config["city_weight"]) * (1.0 if component_results["city_match"] else 0.0)
    score += float(config["state_weight"]) * (1.0 if component_results["state_match"] else 0.0)
    score += float(config["zip_weight"]) * (1.0 if component_results["zip_match"] else 0.0)
    score += float(config["granularity_weight"]) * (
        0.0 if granularity_results["is_city_level_match"] else 0.5 if granularity_results["is_partial_match"] else 1.0
    )

    distance_km = distance_results["distance_km"]
    if distance_km is None:
        distance_component = 0.5
    elif distance_km <= float(config["distance_threshold_km"]):
        distance_component = 1.0
    elif distance_km <= float(config["far_distance_threshold_km"]):
        distance_component = 0.5
    else:
        distance_component = 0.0
    score += float(config["distance_weight"]) * distance_component
    score += float(config["region_weight"]) * (1.0 if region_results["region_match"] else 0.0)

    return round(max(0.0, min(1.0, score)), 4)


def validate_mapping_row(row: pd.Series, config: Dict[str, object]) -> pd.Series:
    input_addr, output_addr = parse_address_components(row)
    component_results = compare_components(input_addr, output_addr)
    granularity_results = detect_granularity_mismatch(input_addr, output_addr)
    distance_results = distance_validation(row, config)
    region_results = region_validation(row, input_addr, output_addr)
    confidence_score = score_mapping(component_results, granularity_results, distance_results, region_results, config)
    is_low_confidence = confidence_score < float(config["low_confidence_threshold"])

    result = {
        "normalized_input_address": input_addr.normalized,
        "normalized_formatted_address": output_addr.normalized,
        "input_house_number": input_addr.house_number,
        "output_house_number": output_addr.house_number,
        "input_street_normalized": input_addr.street,
        "output_street_normalized": output_addr.street,
        "input_city_normalized": input_addr.city,
        "output_city_normalized": output_addr.city,
        "input_state_normalized": input_addr.state,
        "output_state_normalized": output_addr.state,
        "input_zip_normalized": input_addr.postal_code,
        "output_zip_normalized": output_addr.postal_code,
        **component_results,
        **granularity_results,
        **distance_results,
        **region_results,
        "confidence_score": confidence_score,
        "is_low_confidence": is_low_confidence,
        "is_suspicious": bool(
            is_low_confidence
            or granularity_results["is_city_level_match"]
            or granularity_results["is_partial_match"]
            or distance_results["is_far_distance"]
            or region_results["is_out_of_region"]
            or component_results["component_mismatch_count"] >= 2
        ),
    }
    return pd.Series(result)


def validate_mappings(df: pd.DataFrame, config: Optional[Dict[str, object]] = None) -> pd.DataFrame:
    config = {**DEFAULT_CONFIG, **(config or {})}
    validation_df = df.apply(lambda row: validate_mapping_row(row, config), axis=1)
    return pd.concat([df, validation_df], axis=1)


def summarize_validation(validated_df: pd.DataFrame, config: Optional[Dict[str, object]] = None) -> pd.DataFrame:
    config = {**DEFAULT_CONFIG, **(config or {})}
    total = len(validated_df)
    if total == 0:
        return pd.DataFrame([
            {"metric": "record_count", "value": 0}
        ])

    summary = [
        {"metric": "record_count", "value": total},
        {"metric": "pct_high_confidence", "value": round((validated_df["confidence_score"] >= 0.85).mean() * 100, 2)},
        {"metric": "pct_low_confidence", "value": round((validated_df["confidence_score"] < float(config["low_confidence_threshold"])) .mean() * 100, 2)},
        {"metric": "pct_likely_incorrect", "value": round(validated_df["is_suspicious"].mean() * 100, 2)},
        {"metric": "pct_city_level_match", "value": round(validated_df["is_city_level_match"].mean() * 100, 2)},
        {"metric": "pct_partial_match", "value": round(validated_df["is_partial_match"].mean() * 100, 2)},
        {"metric": "pct_far_distance", "value": round(validated_df["is_far_distance"].fillna(False).mean() * 100, 2)},
        {"metric": "pct_out_of_region", "value": round(validated_df["is_out_of_region"].fillna(False).mean() * 100, 2)},
    ]
    return pd.DataFrame(summary)


def read_input_dataset(path: str) -> pd.DataFrame:
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    if path.endswith(".json"):
        return pd.read_json(path, lines=True)
    return pd.read_csv(path)


def write_output_dataset(df: pd.DataFrame, path: str) -> None:
    if path.endswith(".parquet"):
        df.to_parquet(path, index=False)
    elif path.endswith(".json"):
        df.to_json(path, orient="records", lines=True)
    else:
        df.to_csv(path, index=False)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Google Places mapping outputs without API calls.")
    parser.add_argument("--input", required=True, help="Input dataset path (.csv, .json, .parquet).")
    parser.add_argument("--output", required=True, help="Validated output dataset path (.csv, .json, .parquet).")
    parser.add_argument("--summary-output", help="Optional summary output path (.csv, .json, .parquet).")
    parser.add_argument("--distance-threshold-km", type=float, default=DEFAULT_CONFIG["distance_threshold_km"])
    parser.add_argument("--far-distance-threshold-km", type=float, default=DEFAULT_CONFIG["far_distance_threshold_km"])
    parser.add_argument("--low-confidence-threshold", type=float, default=DEFAULT_CONFIG["low_confidence_threshold"])
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    config = {
        "distance_threshold_km": args.distance_threshold_km,
        "far_distance_threshold_km": args.far_distance_threshold_km,
        "low_confidence_threshold": args.low_confidence_threshold,
    }

    df = read_input_dataset(args.input)
    validated_df = validate_mappings(df, config)
    summary_df = summarize_validation(validated_df, config)

    write_output_dataset(validated_df, args.output)
    if args.summary_output:
        write_output_dataset(summary_df, args.summary_output)

    print("=== Mapping Validation Summary ===")
    print(summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
