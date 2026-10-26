from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from pathlib import Path
from typing import Any
from formaos.definitions import CATEGORIES
from formaos.definitions import PRICE_BANDS, DIMENSION_BANDS, PRICE_MULTIPLIERS
from formaos.definitions import COMPARABLES


ALLOWED_CATEGORIES = tuple(CATEGORIES)
TARGET_COUNTS = {category: 15 for category in ALLOWED_CATEGORIES}


def iter_records(root: Path):
    for path in sorted(root.rglob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            output.extend(values(item))
        return output
    if isinstance(value, dict):
        if "value" in value:
            return values(value["value"])
        if "normalized_value" in value:
            return values(value["normalized_value"])
        return []
    return [str(value)]


def english_value(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("language_tag") == "en_US":
                return str(item.get("value", "")).strip()
        for item in value:
            text = english_value(item)
            if text:
                return text
    if isinstance(value, dict):
        return str(value.get("value", "")).strip()
    return str(value or "").strip()


def normalize_text(text: str) -> str:
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", text).strip()


def product_types(record: dict[str, Any]) -> list[str]:
    return [item.upper() for item in values(record.get("product_type"))]


def text_blob(record: dict[str, Any]) -> str:
    return normalize_text(
        " ".join(
            [
                english_value(record.get("item_name")),
                english_value(record.get("bullet_point")),
                english_value(record.get("node")),
                english_value(record.get("item_keywords")),
                english_value(record.get("style")),
                " ".join(product_types(record)),
            ]
        )
    ).lower()


def original_dimension(record: dict[str, Any], key: str) -> tuple[float | None, str]:
    dims = record.get("item_dimensions") or {}
    raw = dims.get(key)
    if not isinstance(raw, dict):
        return None, ""
    try:
        value = float(raw["value"])
    except (KeyError, TypeError, ValueError):
        return None, ""
    return value, str(raw.get("unit", ""))


def dimension_cm(record: dict[str, Any], key: str) -> float | None:
    raw_value, raw_unit = original_dimension(record, key)
    if raw_value is None:
        return None
    unit = raw_unit.lower()
    if "inch" in unit:
        return round(raw_value * 2.54, 1)
    if unit in {"centimeters", "centimeter", "cm"}:
        return round(raw_value, 1)
    if unit in {"meters", "meter", "m"}:
        return round(raw_value * 100, 1)
    return None


def infer_category(record: dict[str, Any]) -> str | None:
    types = set(product_types(record))
    text = text_blob(record)
    title = normalize_text(english_value(record.get("item_name"))).lower()

    if "PLANTER" in types or "planter" in title or "flower pot" in title:
        return "planter"
    if "RUG" in types or "/rugs" in text or " area rug" in title:
        return "rug"
    if "LIGHT_FIXTURE" in types and any(
        word in title for word in ("lamp", "sconce", "chandelier", "light", "lantern")
    ):
        return "lamp"
    if "mirror" in title and ("HOME" in types or "BATHROOM_FIXTURE" in types):
        return "mirror"
    if "BED_FRAME" in types or title.startswith("bed ") or " bed frame" in title:
        return "bed"
    if "CHAIR" in types and not any(word in title for word in ("wheelchair", "chair mat")):
        return "chair"
    if "SOFA" in types:
        if "loveseat" in title or "love seat" in title or "2-seater" in title or "2 seater" in title:
            return "loveseat"
        return "sofa"
    if "TABLE" in types:
        if "desk" in title or "writing table" in title or "computer table" in title:
            return "desk"
        if "cabinet" in title or "bookcase" in title:
            return "cabinet"
        if "storage" in title or "shelf" in title:
            return "storage"
        return "table"
    if any(word in title for word in ("cabinet", "bookcase", "sideboard", "wardrobe")):
        return "cabinet"
    if any(word in title for word in ("storage", "shelf", "organizer", "organiser", "cart")):
        return "storage"
    if "desk" in title:
        return "desk"
    return None


def plausible_dimensions(category: str, width: float, depth: float, height: float) -> bool:
    if min(width, depth, height) <= 0:
        return False
    limits = DIMENSION_BANDS[category]
    min_w, max_w, min_d, max_d, min_h, max_h = limits
    return min_w <= width <= max_w and min_d <= depth <= max_d and min_h <= height <= max_h


def material_text(record: dict[str, Any]) -> str:
    text = normalize_text(english_value(record.get("material")))
    if text:
        return text
    blob = text_blob(record)
    for material in ("wood", "metal", "fabric", "polyester", "cotton", "ceramic", "glass", "plastic"):
        if material in blob:
            return material.title()
    return ""


def price_for(category: str, width_cm: float, depth_cm: float, height_cm: float, material: str) -> int:
    footprint = max(width_cm * depth_cm / 10000, 0.1)
    volume = max(width_cm * depth_cm * max(height_cm, 1) / 1000000, 0.1)
    low, high = PRICE_BANDS[category]
    if category in {"rug", "table", "desk", "mirror"}:
        scale = footprint
    elif category in {"lamp", "planter"}:
        scale = max(height_cm / 100, footprint)
    else:
        scale = volume
    material_factor = 1.0
    material_lower = material.lower()
    if any(word in material_lower for word in ("wood", "teak", "oak", "sheesham", "metal", "leather")):
        material_factor = 1.18
    if any(word in material_lower for word in ("plastic", "fabric", "polyester")):
        material_factor = 0.92
    category_multiplier = PRICE_MULTIPLIERS[category]
    price = low + category_multiplier * scale * material_factor
    price = min(max(price, low), high)
    return int(round(price / 100) * 100)


def price_note_for(
    category: str, width_cm: float, depth_cm: float, height_cm: float, material: str
) -> str:
    material_part = f", {material}" if material else ""
    return (
        f"Indicative INR manual review: {COMPARABLES[category]}; "
        f"adjusted for {round(width_cm)} x {round(depth_cm)} x {round(height_cm)} cm{material_part}."
    )


def to_row(record: dict[str, Any]) -> dict[str, str] | None:
    category = infer_category(record)
    if category not in ALLOWED_CATEGORIES:
        return None

    width = dimension_cm(record, "length")
    depth = dimension_cm(record, "width")
    height = dimension_cm(record, "height")
    if width is None or depth is None or height is None:
        return None
    if not plausible_dimensions(category, width, depth, height):
        return None

    original_length, original_length_unit = original_dimension(record, "length")
    original_width, original_width_unit = original_dimension(record, "width")
    original_height, original_height_unit = original_dimension(record, "height")
    title = normalize_text(english_value(record.get("item_name")))
    material = material_text(record)
    color = normalize_text(english_value(record.get("color")))
    image_id = str(record.get("main_image_id") or "")
    if not title or not material or not color or not image_id:
        return None

    style = normalize_text(text_blob(record)[:300])
    price = price_for(category, width, depth, height, material)

    return {
        "item_id": str(record.get("item_id") or ""),
        "normalized_category": category,
        "title": title,
        "width_cm": f"{width:.1f}",
        "depth_cm": f"{depth:.1f}",
        "height_cm": f"{height:.1f}",
        "original_length_value": f"{original_length:.3f}" if original_length is not None else "",
        "original_length_unit": original_length_unit,
        "original_width_value": f"{original_width:.3f}" if original_width is not None else "",
        "original_width_unit": original_width_unit,
        "original_height_value": f"{original_height:.3f}" if original_height is not None else "",
        "original_height_unit": original_height_unit,
        "material": material,
        "color": color,
        "image_id": image_id,
        "image_path": "",
        "style_text": style,
        "price_inr": str(price),
        "price_note": price_note_for(category, width, depth, height, material),
        "source_dataset": "ABO",
    }


def curate(input_root: Path, limit: int) -> list[dict[str, str]]:
    buckets: dict[str, list[dict[str, str]]] = {category: [] for category in ALLOWED_CATEGORIES}
    seen: set[str] = set()
    for record in iter_records(input_root):
        row = to_row(record)
        if not row or row["item_id"] in seen:
            continue
        category = row["normalized_category"]
        if len(buckets[category]) >= TARGET_COUNTS[category]:
            continue
        buckets[category].append(row)
        seen.add(row["item_id"])
        if sum(len(rows) for rows in buckets.values()) >= limit:
            break
    return [row for category in ALLOWED_CATEGORIES for row in buckets[category]][:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate a production-ready MVP furniture subset.")
    parser.add_argument("--input", default="data/external/abo")
    parser.add_argument("--output", default="data/curated/abo_mvp_catalogue.csv")
    parser.add_argument("--limit", type=int, default=180)
    args = parser.parse_args()

    rows = curate(Path(args.input), args.limit)
    if len(rows) < 150:
        raise SystemExit(f"Only curated {len(rows)} rows; T5 requires at least 150.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "row_count": len(rows),
        "category_counts": {
            category: sum(1 for row in rows if row["normalized_category"] == category)
            for category in ALLOWED_CATEGORIES
        },
        "output": str(output),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
