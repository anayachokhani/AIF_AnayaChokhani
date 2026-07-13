# Data Sources

## Amazon Berkeley Objects

- Source: https://amazon-berkeley-objects.s3.amazonaws.com/index.html
- Listings archive: https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-listings.tar
- Optional small images archive: https://amazon-berkeley-objects.s3.amazonaws.com/archives/abo-images-small.tar
- License noted in `tasks.tex`: CC BY 4.0.

ABO contains real product metadata and images, but it does not include prices.
For the MVP, `price_inr` values are curated indicative demo prices and must be
labelled that way in the UI and export brief.

Raw downloads should be stored under `data/raw/abo/` and extracted files under
`data/external/abo/`. These directories are ignored by Git.

## Current Local Inventory

Completed on 2026-07-10:

- Downloaded `abo-listings.tar`.
- Extracted listings under `data/external/abo/`.
- Saved source metadata at `data/raw/abo/SOURCE.txt`.
- Saved inventory metrics at `artifacts/metrics/abo_inventory.json`.

Inventory results:

- Total records: 147,702.
- Records with dimensions: 44,647.
- Furniture-like records: 27,190.
- Records with main images: 147,536.

## Current Curated Catalogue

Created `data/curated/abo_mvp_catalogue.csv` with 200 ABO-backed rows:

- 35 sofas.
- 35 chairs.
- 35 tables.
- 30 rugs.
- 25 lighting items.
- 25 storage items.
- 15 beds.

The current `price_inr` values are starter indicative demo prices generated
from category and dimensions. They are usable for development, but should be
manually reviewed before being presented as final curated prices.

Validation artifacts:

- `artifacts/metrics/catalogue_validation.json`.
- `data/curated/price_review_queue.csv`.

## Current Image Mapping Status

Completed on 2026-07-10:

- Downloaded `abo-images-small.tar`.
- Extracted `images/metadata/images.csv.gz` and small product images under
  `data/external/abo/images/`.
- Mapped all curated catalogue `main_image_id` values through
  `images/metadata/images.csv.gz`.
- Copied browser-servable product images to `public/product-images/`.
- Generated the `/image-smoke` sample data with 20 catalogue items.

Current image mapping results:

- Total catalogue rows: 180.
- Mapped product images: 180.
- Placeholder images: 0.
- Image coverage: 100%.
- Broken paths: 0.

- Summary: `artifacts/metrics/image_mapping_summary.json`.
- Output CSV: `data/curated/abo_mvp_catalogue_with_images.csv`.
- UI fallback asset: `public/product-placeholder.svg`.

## Current Retrieval Index

Completed T7 with a local Chroma index:

- Index path: `data/vectorstores/chroma`.
- Collection: `formaos_catalogue_v1`.
- Indexed rows: 180.
- Smoke queries: 10, all returning filtered results.
- Summary: `artifacts/metrics/chroma_index_summary.json`.
- Smoke report: `artifacts/metrics/retrieval_smoke_report.json`.

The current index uses a deterministic local hashing embedding so the MVP can
run without downloading an embedding model. Search still applies hard filters
for category, maximum width, maximum depth, and maximum price after Chroma
retrieval.

## Vastu Rules

The MVP uses a small reviewed JSON rule file rather than a public dataset. Each
rule should include source URLs, rationale, confidence, and severity. Rules are
opt-in guidance only.
