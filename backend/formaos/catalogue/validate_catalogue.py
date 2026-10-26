from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from formaos.definitions import SUPPORTED_CATEGORIES as ALLOWED_CATEGORIES
from formaos.definitions import PRICE_BANDS
from formaos.definitions import DIMENSION_BANDS


REQUIRED_COLUMNS = {
    "item_id",
    "normalized_category",
    "title",
    "width_cm",
    "depth_cm",
    "height_cm",
    "original_length_value",
    "original_length_unit",
    "original_width_value",
    "original_width_unit",
    "original_height_value",
    "original_height_unit",
    "material",
    "color",
    "image_id",
    "image_path",
    "style_text",
    "price_inr",
    "price_note",
}


def row_identifier(row: dict[str, str]) -> str:
    return row.get("item_id") or row.get("title") or "<unknown>"


def parse_float(row: dict[str, str], field: str, bucket: list[dict[str, str]]) -> float | None:
    try:
        return float(row.get(field, ""))
    except ValueError:
        bucket.append({"item_id": row_identifier(row), "field": field, "value": row.get(field, "")})
        return None


def validate(path: Path) -> dict[str, object]:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    missing_required_columns = sorted(REQUIRED_COLUMNS - set(rows[0].keys())) if rows else sorted(REQUIRED_COLUMNS)
    duplicate_item_ids = [
        item_id for item_id, count in Counter(row.get("item_id", "") for row in rows).items() if count > 1
    ]
    category_counts = Counter(row.get("normalized_category", "") for row in rows)
    invalid_categories = sorted(set(category_counts) - ALLOWED_CATEGORIES)

    missing_required_fields: list[dict[str, str]] = []
    invalid_dimensions: list[dict[str, str]] = []
    dimension_outliers: list[dict[str, object]] = []
    missing_prices: list[str] = []
    missing_price_notes: list[str] = []
    missing_materials: list[str] = []
    missing_colours: list[str] = []
    missing_images: list[str] = []
    price_outliers: list[dict[str, object]] = []
    non_cm_dimensions: list[dict[str, str]] = []

    for row in rows:
        item_id = row_identifier(row)
        for field in REQUIRED_COLUMNS:
            if field == "image_path":
                continue
            if not row.get(field, "").strip():
                missing_required_fields.append({"item_id": item_id, "field": field})

        category = row.get("normalized_category", "")
        width = parse_float(row, "width_cm", invalid_dimensions)
        depth = parse_float(row, "depth_cm", invalid_dimensions)
        height = parse_float(row, "height_cm", invalid_dimensions)
        if width is None or depth is None or height is None or min(width, depth, height) <= 0:
            invalid_dimensions.append({"item_id": item_id, "field": "dimensions", "value": "non-positive"})
        elif category in DIMENSION_BANDS:
            min_w, max_w, min_d, max_d, min_h, max_h = DIMENSION_BANDS[category]
            if not (min_w <= width <= max_w and min_d <= depth <= max_d and min_h <= height <= max_h):
                dimension_outliers.append(
                    {
                        "item_id": item_id,
                        "category": category,
                        "width_cm": width,
                        "depth_cm": depth,
                        "height_cm": height,
                    }
                )

        for value_field, unit_field in (
            ("original_length_value", "original_length_unit"),
            ("original_width_value", "original_width_unit"),
            ("original_height_value", "original_height_unit"),
        ):
            if not row.get(value_field, "").strip() or not row.get(unit_field, "").strip():
                non_cm_dimensions.append({"item_id": item_id, "field": value_field})

        try:
            price = int(row.get("price_inr", ""))
        except ValueError:
            missing_prices.append(item_id)
            price = 0
        if price <= 0:
            missing_prices.append(item_id)
        elif category in PRICE_BANDS:
            low, high = PRICE_BANDS[category]
            if not low <= price <= high:
                price_outliers.append({"item_id": item_id, "category": category, "price_inr": price})

        if not row.get("price_note", "").strip():
            missing_price_notes.append(item_id)
        if not row.get("material", "").strip():
            missing_materials.append(item_id)
        if not row.get("color", "").strip():
            missing_colours.append(item_id)
        if not (row.get("image_id", "").strip() or row.get("image_path", "").strip()):
            missing_images.append(item_id)

    blocking_failures = {
        "row_count_out_of_range": not (150 <= len(rows) <= 300),
        "duplicate_item_ids": duplicate_item_ids,
        "missing_required_columns": missing_required_columns,
        "missing_required_fields": missing_required_fields,
        "invalid_categories": invalid_categories,
        "invalid_dimensions": invalid_dimensions,
        "dimension_outliers": dimension_outliers,
        "missing_prices": sorted(set(missing_prices)),
        "missing_price_notes": sorted(set(missing_price_notes)),
        "missing_materials": sorted(set(missing_materials)),
        "missing_colours": sorted(set(missing_colours)),
        "missing_images": sorted(set(missing_images)),
        "price_outliers": price_outliers,
        "missing_original_dimension_audit": non_cm_dimensions,
    }
    passed = not any(bool(value) for value in blocking_failures.values())

    return {
        "passed": passed,
        "total_rows": len(rows),
        "category_distribution": dict(category_counts),
        "duplicate_item_ids": duplicate_item_ids,
        "missing_required_columns": missing_required_columns,
        "missing_required_fields": missing_required_fields,
        "invalid_categories": invalid_categories,
        "invalid_dimensions": invalid_dimensions,
        "missing_prices": sorted(set(missing_prices)),
        "missing_price_notes": sorted(set(missing_price_notes)),
        "missing_materials": sorted(set(missing_materials)),
        "missing_colours": sorted(set(missing_colours)),
        "missing_images": sorted(set(missing_images)),
        "price_outliers": price_outliers,
        "dimension_outliers": dimension_outliers,
        "missing_original_dimension_audit": non_cm_dimensions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly validate the T5 curated catalogue.")
    parser.add_argument("--catalogue", default="data/curated/abo_mvp_catalogue.csv")
    parser.add_argument("--summary", default="artifacts/metrics/catalogue_validation.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    summary = validate(Path(args.catalogue))
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if args.strict and not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
