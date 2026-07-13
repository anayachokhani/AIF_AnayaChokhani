from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

import chromadb
from chromadb import EmbeddingFunction, Embeddings


COLLECTION_NAME = "formaos_catalogue_v1"
VECTOR_SIZE = 384
SMOKE_QUERY_COUNT = 10
SEMANTIC_CANDIDATE_LIMIT = 100


class HashingEmbeddingFunction(EmbeddingFunction):
    """Small local embedding function for repeatable MVP retrieval.

    This avoids model downloads while keeping the Chroma interface intact. It is
    adequate for smoke tests and hard-filtered catalogue retrieval; a production
    version can swap in a stronger embedding model without changing callers.
    """

    def __init__(self) -> None:
        pass

    def __call__(self, input: list[str]) -> Embeddings:
        return [hashing_embedding(text) for text in input]


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def hashing_embedding(text: str) -> list[float]:
    vector = [0.0] * VECTOR_SIZE
    for token in tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % VECTOR_SIZE
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def load_catalogue(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def searchable_text(row: dict[str, str]) -> str:
    return " ".join(
        [
            row.get("title", ""),
            row.get("normalized_category", ""),
            row.get("material", ""),
            row.get("color", ""),
            row.get("style_text", ""),
            row.get("pattern", ""),
            row.get("description", ""),
        ]
    )


def numeric_metadata(row: dict[str, str]) -> dict[str, str | int | float | bool]:
    return {
        "item_id": row["item_id"],
        "title": row["title"],
        "category": row["normalized_category"],
        "width_cm": float(row["width_cm"]),
        "depth_cm": float(row["depth_cm"]),
        "height_cm": float(row["height_cm"]),
        "price_inr": int(row["price_inr"]),
        "material": row.get("material", ""),
        "color": row.get("color", ""),
        "image_id": row.get("image_id", ""),
        "image_path": row.get("image_path", ""),
        "image_available": row.get("image_available") == "true",
    }


def client_for(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def build_index(catalogue_path: Path, chroma_path: Path) -> dict[str, object]:
    rows = load_catalogue(catalogue_path)
    client = client_for(chroma_path)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        COLLECTION_NAME,
        embedding_function=HashingEmbeddingFunction(),
        metadata={"description": "FormaOS curated ABO MVP catalogue"},
    )

    collection.add(
        ids=[row["item_id"] for row in rows],
        documents=[searchable_text(row) for row in rows],
        metadatas=[numeric_metadata(row) for row in rows],
    )

    indexed_count = collection.count()
    return {
        "catalogue_path": str(catalogue_path),
        "chroma_path": str(chroma_path),
        "collection": COLLECTION_NAME,
        "input_rows": len(rows),
        "indexed_count": indexed_count,
        "embedding": "local_hashing_embedding_v1",
        "searchable_fields": ["title", "category", "material", "color", "style_text", "pattern", "description"],
    }


def metadata_passes(
    item: dict[str, object],
    category: str | None,
    max_width_cm: float | None,
    max_depth_cm: float | None,
    max_price_inr: int | None,
) -> bool:
    if category and item.get("category") != category:
        return False
    if max_width_cm is not None and float(item.get("width_cm", 0)) > max_width_cm:
        return False
    if max_depth_cm is not None and float(item.get("depth_cm", 0)) > max_depth_cm:
        return False
    if max_price_inr is not None and int(item.get("price_inr", 0)) > max_price_inr:
        return False
    return True


def search_items(
    query: str,
    category: str | None = None,
    max_width_cm: float | None = None,
    max_depth_cm: float | None = None,
    max_price_inr: int | None = None,
    k: int = 5,
    chroma_path: Path = Path("data/vectorstores/chroma"),
) -> list[dict[str, object]]:
    client = client_for(chroma_path)
    collection = client.get_collection(COLLECTION_NAME, embedding_function=HashingEmbeddingFunction())
    candidate_count = min(collection.count(), max(SEMANTIC_CANDIDATE_LIMIT, k * 8, k))
    results = collection.query(query_texts=[query], n_results=candidate_count)
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    output: list[dict[str, object]] = []
    for metadata, distance in zip(metadatas, distances):
        if metadata_passes(metadata, category, max_width_cm, max_depth_cm, max_price_inr):
            output.append({**metadata, "distance": distance})
        if len(output) >= k:
            break
    return output


def smoke_queries(chroma_path: Path) -> list[dict[str, object]]:
    examples = [
        {
            "query": "warm wooden sofa",
            "category": "sofa",
            "max_width_cm": 240,
            "max_depth_cm": 110,
            "max_price_inr": 50000,
        },
        {
            "query": "compact storage cabinet",
            "category": "storage",
            "max_width_cm": 180,
            "max_depth_cm": 80,
            "max_price_inr": 45000,
        },
        {
            "query": "soft neutral rug",
            "category": "rug",
            "max_width_cm": 300,
            "max_depth_cm": 300,
            "max_price_inr": 25000,
        },
        {
            "query": "modern dining or coffee table",
            "category": "table",
            "max_width_cm": 180,
            "max_depth_cm": 120,
            "max_price_inr": 35000,
        },
        {
            "query": "floor lamp warm light",
            "category": "lamp",
            "max_width_cm": 90,
            "max_depth_cm": 90,
            "max_price_inr": 20000,
        },
        {
            "query": "small work desk",
            "category": "desk",
            "max_width_cm": 160,
            "max_depth_cm": 90,
            "max_price_inr": 30000,
        },
        {
            "query": "comfortable accent chair",
            "category": "chair",
            "max_width_cm": 110,
            "max_depth_cm": 120,
            "max_price_inr": 35000,
        },
        {
            "query": "full size wooden bed",
            "category": "bed",
            "max_width_cm": 230,
            "max_depth_cm": 240,
            "max_price_inr": 100000,
        },
        {
            "query": "wall mirror natural frame",
            "category": "mirror",
            "max_width_cm": 120,
            "max_depth_cm": 20,
            "max_price_inr": 15000,
        },
        {
            "query": "simple indoor planter",
            "category": "planter",
            "max_width_cm": 80,
            "max_depth_cm": 80,
            "max_price_inr": 10000,
        },
    ]
    report = []
    for example in examples:
        results = search_items(chroma_path=chroma_path, k=5, **example)
        report.append({**example, "result_count": len(results), "results": results})
    return report


def validate_smoke_report(report: list[dict[str, object]], expected_count: int = SMOKE_QUERY_COUNT) -> dict[str, object]:
    failures: list[dict[str, object]] = []
    if len(report) != expected_count:
        failures.append({"type": "query_count", "expected": expected_count, "actual": len(report)})
    for example in report:
        results = example.get("results", [])
        if not results:
            failures.append({"type": "empty_results", "query": example.get("query")})
            continue
        for result in results:
            if result.get("category") != example.get("category"):
                failures.append(
                    {
                        "type": "category_filter",
                        "query": example.get("query"),
                        "item_id": result.get("item_id"),
                        "expected": example.get("category"),
                        "actual": result.get("category"),
                    }
                )
            if float(result.get("width_cm", 0)) > float(example.get("max_width_cm", 0)):
                failures.append({"type": "width_filter", "query": example.get("query"), "item_id": result.get("item_id")})
            if float(result.get("depth_cm", 0)) > float(example.get("max_depth_cm", 0)):
                failures.append({"type": "depth_filter", "query": example.get("query"), "item_id": result.get("item_id")})
            if int(result.get("price_inr", 0)) > int(example.get("max_price_inr", 0)):
                failures.append({"type": "price_filter", "query": example.get("query"), "item_id": result.get("item_id")})
    return {
        "smoke_query_count": len(report),
        "queries_with_results": sum(1 for example in report if example.get("result_count", 0) > 0),
        "filter_failures": failures,
        "passed": not failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and smoke test the FormaOS Chroma index.")
    parser.add_argument("--catalogue", default="data/curated/abo_mvp_catalogue_with_images.csv")
    parser.add_argument("--chroma-path", default="data/vectorstores/chroma")
    parser.add_argument("--summary", default="artifacts/metrics/chroma_index_summary.json")
    parser.add_argument("--smoke-report", default="artifacts/metrics/retrieval_smoke_report.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    chroma_path = Path(args.chroma_path)
    summary = build_index(Path(args.catalogue), chroma_path)
    report = smoke_queries(chroma_path)
    validation = validate_smoke_report(report)
    summary = {
        **summary,
        "smoke_report": args.smoke_report,
        "validation_status": "PASS" if validation["passed"] else "FAIL",
        "validation": validation,
    }

    summary_path = Path(args.summary)
    report_path = Path(args.smoke_report)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    if args.strict and not validation["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
