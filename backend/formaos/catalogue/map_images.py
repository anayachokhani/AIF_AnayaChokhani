from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
PLACEHOLDER_ASSET = "public/product-placeholder.svg"
PLACEHOLDER_SRC = "/product-placeholder.svg"
SMOKE_COUNT = 20


def read_catalogue(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_catalogue(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    for extra in ("image_available", "image_source_path"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def open_metadata(path: Path) -> Iterable[dict[str, str]]:
    if not path.exists():
        return []
    if path.suffix == ".gz":
        handle = gzip.open(path, "rt", newline="", encoding="utf-8")
    else:
        handle = path.open(newline="", encoding="utf-8")
    with handle:
        yield from csv.DictReader(handle)


def build_metadata_index(metadata_path: Path, wanted_ids: set[str]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    if not metadata_path.exists():
        return index
    for row in open_metadata(metadata_path):
        image_id = row.get("image_id", "").strip()
        if image_id in wanted_ids:
            index[image_id] = row
    return index


def build_stem_index(images_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not images_root.exists():
        return index
    for path in images_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            index.setdefault(path.stem, path)
    return index


def candidate_metadata_paths(abo_root: Path, images_root: Path, metadata: Path | None) -> list[Path]:
    paths: list[Path] = []
    if metadata:
        paths.append(metadata)
    paths.extend(
        [
            images_root / "metadata" / "images.csv.gz",
            images_root.parent / "metadata" / "images.csv.gz",
            abo_root / "images" / "metadata" / "images.csv.gz",
            abo_root / "metadata" / "images.csv.gz",
        ]
    )
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def find_metadata_path(abo_root: Path, images_root: Path, metadata: Path | None) -> Path | None:
    for path in candidate_metadata_paths(abo_root, images_root, metadata):
        if path.exists():
            return path
    return None


def resolve_metadata_image(row: dict[str, str], abo_root: Path, images_root: Path) -> Path | None:
    keys = (
        "path",
        "image_path",
        "file_path",
        "relative_path",
        "location",
        "small_path",
        "large_path",
    )
    for key in keys:
        raw_value = row.get(key, "").strip()
        if not raw_value:
            continue
        raw_path = Path(raw_value)
        candidates = []
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.extend(
                [
                    abo_root / raw_path,
                    images_root / "small" / raw_path,
                    images_root / raw_path,
                    images_root.parent / raw_path,
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return candidate
    image_id = row.get("image_id", "").strip()
    for key in ("height", "width"):
        _ = row.get(key)
    if image_id:
        prefix = image_id[:2]
        for suffix in IMAGE_EXTENSIONS:
            for candidate in (
                images_root / "small" / prefix / f"{image_id}{suffix}",
                images_root / prefix / f"{image_id}{suffix}",
                images_root / f"{image_id}{suffix}",
            ):
                if candidate.exists():
                    return candidate
    return None


def is_openable_image(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return False
    if header.startswith(b"\xff\xd8\xff"):
        return True
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return True
    if path.suffix.lower() == ".svg" and header.startswith(b"<"):
        return True
    return False


def safe_filename(*parts: str, suffix: str) -> str:
    base = "-".join(part for part in parts if part)
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in base)
    return f"{cleaned[:140]}{suffix.lower()}"


def copy_public_image(source: Path, row: dict[str, str], public_dir: Path) -> Path:
    public_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(row.get("item_id", ""), row.get("image_id", ""), suffix=source.suffix)
    destination = public_dir / filename
    shutil.copy2(source, destination)
    return destination


def to_web_src(public_path: Path) -> str:
    parts = public_path.parts
    if "public" in parts:
        public_index = parts.index("public")
        return "/" + "/".join(parts[public_index + 1 :])
    return str(public_path)


def smoke_sort_key(row: dict[str, str]) -> str:
    seed = "|".join([row.get("item_id", ""), row.get("image_id", ""), row.get("title", "")])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def build_smoke_items(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    sorted_rows = sorted(rows, key=smoke_sort_key)
    selected = sorted_rows[:SMOKE_COUNT]
    return [
        {
            "itemId": row["item_id"],
            "title": row["title"],
            "category": row["normalized_category"],
            "dimensions": f'{row["width_cm"]} x {row["depth_cm"]} x {row["height_cm"]} cm',
            "price": f'INR {int(float(row["price_inr"])):,}',
            "imageSrc": row["image_path"] if row["image_path"].startswith("/") else to_web_src(Path(row["image_path"])),
            "imageAvailable": row["image_available"] == "true",
        }
        for row in selected
    ]


def write_smoke_data(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    items = build_smoke_items(rows)
    source = (
        "export type ImageSmokeItem = {\n"
        "  itemId: string;\n"
        "  title: string;\n"
        "  category: string;\n"
        "  dimensions: string;\n"
        "  price: string;\n"
        "  imageSrc: string;\n"
        "  imageAvailable: boolean;\n"
        "};\n\n"
        f"export const imageSmokeItems: ImageSmokeItem[] = {json.dumps(items, indent=2)};\n"
    )
    path.write_text(source, encoding="utf-8")


def validate_rows(rows: list[dict[str, str]], project_root: Path, placeholder_asset: Path) -> dict[str, object]:
    image_paths = [row.get("image_path", "") for row in rows]
    duplicates = sorted(path for path, count in Counter(image_paths).items() if path and path != PLACEHOLDER_SRC and count > 1)
    broken_paths: list[str] = []
    invalid_references: list[str] = []
    missing_image_paths: list[str] = []
    missing_image_ids: list[str] = []
    for row in rows:
        image_id = row.get("image_id", "").strip()
        image_path = row.get("image_path", "").strip()
        available = row.get("image_available") == "true"
        if not image_id:
            missing_image_ids.append(row.get("item_id", ""))
        if not image_path:
            missing_image_paths.append(row.get("item_id", ""))
            continue
        path = project_root / image_path if not image_path.startswith("/") else project_root / "public" / image_path.lstrip("/")
        if available:
            if not path.exists():
                broken_paths.append(image_path)
            elif not is_openable_image(path):
                invalid_references.append(image_path)
        elif image_path != PLACEHOLDER_SRC:
            invalid_references.append(image_path)
    placeholder_exists = placeholder_asset.exists() and is_openable_image(placeholder_asset)
    return {
        "broken_paths": broken_paths,
        "duplicate_mappings": duplicates,
        "missing_image_ids": missing_image_ids,
        "missing_image_paths": missing_image_paths,
        "invalid_image_references": invalid_references,
        "placeholder_asset_exists": placeholder_exists,
    }


def map_images(
    catalogue: Path,
    abo_root: Path,
    images_root: Path,
    metadata_path: Path | None,
    output: Path,
    summary_path: Path,
    public_image_dir: Path,
    smoke_data_path: Path,
    placeholder_asset: Path,
    min_coverage: float,
) -> dict[str, object]:
    rows = read_catalogue(catalogue)
    wanted_ids = {row.get("image_id", "").strip() for row in rows if row.get("image_id", "").strip()}
    resolved_metadata_path = find_metadata_path(abo_root, images_root, metadata_path)
    metadata_index = build_metadata_index(resolved_metadata_path, wanted_ids) if resolved_metadata_path else {}
    stem_index = build_stem_index(images_root)

    mapped_count = 0
    missing_metadata_ids: list[str] = []
    missing_source_files: list[str] = []
    unreadable_source_files: list[str] = []

    for row in rows:
        image_id = row.get("image_id", "").strip()
        row["image_available"] = "false"
        row["image_source_path"] = ""
        row["image_path"] = PLACEHOLDER_SRC
        source_path: Path | None = None
        metadata_row = metadata_index.get(image_id)
        if metadata_row:
            source_path = resolve_metadata_image(metadata_row, abo_root, images_root)
        elif image_id:
            missing_metadata_ids.append(image_id)
            source_path = stem_index.get(image_id)
        if not source_path:
            if image_id:
                missing_source_files.append(image_id)
            continue
        if not is_openable_image(source_path):
            unreadable_source_files.append(str(source_path))
            continue
        public_path = copy_public_image(source_path, row, public_image_dir)
        row["image_source_path"] = str(source_path)
        row["image_path"] = to_web_src(public_path)
        row["image_available"] = "true"
        mapped_count += 1

    write_catalogue(output, rows)
    write_smoke_data(smoke_data_path, rows)

    validation = validate_rows(rows, output.parents[2], placeholder_asset)
    total_rows = len(rows)
    placeholder_count = total_rows - mapped_count
    coverage = mapped_count / total_rows if total_rows else 0
    passed = (
        total_rows > 0
        and coverage >= min_coverage
        and not validation["broken_paths"]
        and not validation["missing_image_paths"]
        and not validation["invalid_image_references"]
        and validation["placeholder_asset_exists"]
        and len(build_smoke_items(rows)) >= SMOKE_COUNT
    )
    summary: dict[str, object] = {
        "total_catalogue_rows": total_rows,
        "mapped_images": mapped_count,
        "placeholder_count": placeholder_count,
        "image_coverage_percent": round(coverage * 100, 2),
        "coverage_threshold_percent": round(min_coverage * 100, 2),
        "metadata_path": str(resolved_metadata_path) if resolved_metadata_path else "",
        "images_root": str(images_root),
        "output_csv": str(output),
        "smoke_data": str(smoke_data_path),
        "broken_paths": validation["broken_paths"],
        "duplicate_mappings": validation["duplicate_mappings"],
        "missing_image_ids": validation["missing_image_ids"],
        "missing_image_paths": validation["missing_image_paths"],
        "missing_metadata_ids": sorted(set(missing_metadata_ids)),
        "missing_source_files": sorted(set(missing_source_files)),
        "unreadable_source_files": sorted(set(unreadable_source_files)),
        "invalid_image_references": validation["invalid_image_references"],
        "placeholder_asset_exists": validation["placeholder_asset_exists"],
        "validation_status": "PASS" if passed else "FAIL",
        "passed": passed,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Map curated ABO furniture items to local product images.")
    parser.add_argument("--catalogue", default="data/curated/abo_mvp_catalogue.csv")
    parser.add_argument("--abo-root", default="data/external/abo")
    parser.add_argument("--images-root", default="data/external/abo/images")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--output", default="data/curated/abo_mvp_catalogue_with_images.csv")
    parser.add_argument("--summary", default="artifacts/metrics/image_mapping_summary.json")
    parser.add_argument("--public-image-dir", default="public/product-images")
    parser.add_argument("--smoke-data", default="app/image-smoke/smoke-items.ts")
    parser.add_argument("--placeholder", default=PLACEHOLDER_ASSET)
    parser.add_argument("--min-coverage", type=float, default=0.70)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    metadata = Path(args.metadata) if args.metadata else None
    summary = map_images(
        catalogue=Path(args.catalogue),
        abo_root=Path(args.abo_root),
        images_root=Path(args.images_root),
        metadata_path=metadata,
        output=Path(args.output),
        summary_path=Path(args.summary),
        public_image_dir=Path(args.public_image_dir),
        smoke_data_path=Path(args.smoke_data),
        placeholder_asset=Path(args.placeholder),
        min_coverage=args.min_coverage,
    )
    print(json.dumps(summary, indent=2))
    if args.strict and not summary["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
