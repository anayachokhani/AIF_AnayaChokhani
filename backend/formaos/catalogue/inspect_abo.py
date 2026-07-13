from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any


FURNITURE_HINTS = (
    "sofa",
    "loveseat",
    "chair",
    "table",
    "desk",
    "cabinet",
    "storage",
    "shelf",
    "rug",
    "lamp",
    "mirror",
    "bed",
    "dresser",
    "wardrobe",
)


def iter_json_records(root: Path):
    for path in root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        if isinstance(payload, list):
            for record in payload:
                if isinstance(record, dict):
                    yield record
        elif isinstance(payload, dict):
            yield payload

    for path in root.rglob("*.jsonl"):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record

    for path in root.rglob("*.json.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record


def text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(text_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(text_value(item) for item in value.values())
    return str(value)


def has_dimensions(record: dict[str, Any]) -> bool:
    text = json.dumps(record).lower()
    return "dimension" in text or ("width" in text and "height" in text)


def has_main_image(record: dict[str, Any]) -> bool:
    text = json.dumps(record).lower()
    return "main_image" in text or "mainimage" in text or "image_id" in text


def product_type(record: dict[str, Any]) -> str:
    for key in ("product_type", "productType", "type", "category"):
        if key in record:
            return text_value(record[key]).strip()
    return "unknown"


def is_furniture_like(record: dict[str, Any]) -> bool:
    searchable = " ".join(
        [
            product_type(record),
            text_value(record.get("item_name")),
            text_value(record.get("title")),
            text_value(record.get("bullet_point")),
            text_value(record.get("product_description")),
        ]
    ).lower()
    return any(hint in searchable for hint in FURNITURE_HINTS)


def inspect(root: Path) -> dict[str, Any]:
    records = list(iter_json_records(root))
    type_counts = Counter(product_type(record) or "unknown" for record in records)
    dimension_count = sum(1 for record in records if has_dimensions(record))
    furniture_count = sum(1 for record in records if is_furniture_like(record))
    image_count = sum(1 for record in records if has_main_image(record))

    return {
        "record_count": len(records),
        "records_with_dimensions": dimension_count,
        "furniture_like_records": furniture_count,
        "records_with_main_images": image_count,
        "top_product_types": type_counts.most_common(30),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inventory extracted ABO listing files.")
    parser.add_argument("--input", default="data/external/abo", help="Extracted ABO directory")
    parser.add_argument(
        "--output",
        default="artifacts/metrics/abo_inventory.json",
        help="Inventory JSON output path",
    )
    args = parser.parse_args()

    root = Path(args.input)
    if not root.exists():
        raise SystemExit(f"ABO input directory not found: {root}")

    summary = inspect(root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
