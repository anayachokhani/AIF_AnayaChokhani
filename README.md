# FormaOS MVP App

Multi-page prototype for a grounded interior-design assistant. Each top-level
navigation item is implemented as its own route:

- `/` - Overview
- `/workspace` - full frontend-to-backend design journey
- `/planner` - interactive room and budget planner
- `/catalogue` - sample furniture catalogue
- `/image-smoke` - product image mapping smoke page
- `/validation` - fit, budget, sourceability, and Vastu checks
- `/design/{id}/brief` - shareable export brief for a saved backend design
- `/research` - measurable research comparison
- `/evaluation` - frozen evaluation plan and metrics
- `/roadmap` - implementation phases

## Prerequisites

- Node.js `>=22.13.0`
- npm
- Python `>=3.11`
- uv

This workspace includes local tool installs under `.tools/`. Use this command
from the repository root before running app commands:

```bash
export PATH="$PWD/.tools/node/bin:$PWD/.tools/bin:$PATH"
export UV_CACHE_DIR="$PWD/.uv-cache"
export PYTHONPATH=backend
```

## Frontend

```bash
npm install
npm run dev
```

Then open the local URL printed by the development server.

## Backend

```bash
uv sync
uvicorn formaos.api.main:app --app-dir backend --reload
```

For the deterministic local demo flow without OpenRouter/API spend:

```bash
FORMAOS_DEMO_PLANNER=1 uv run uvicorn formaos.api.main:app --app-dir backend --reload
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Core API routes:

- `GET /api/health`
- `POST /api/session`
- `POST /api/chat`
- `GET /api/design/{id}`
- `POST /api/design/{id}/revise`
- `GET /api/catalogue/search`
- `GET /api/export/{id}`

## Validate

```bash
npm run build
npm test
uv run python -c "from formaos.contracts import RoomBrief; print(RoomBrief(room_type='living_room', width=10, depth=12, units='ft', budget_inr=85000).room_type)"
uv run pytest backend/tests/test_room_state.py
```

Run the frozen evaluation and final acceptance check:

```bash
uv run python backend/formaos/eval/run_eval.py
npm run demo:acceptance
```

## Dataset Commands

Inventory extracted ABO listings:

```bash
uv run python backend/formaos/catalogue/inspect_abo.py \
  --input data/external/abo \
  --output artifacts/metrics/abo_inventory.json
```

Create the starter curated catalogue:

```bash
uv run python backend/formaos/catalogue/curate_abo_subset.py \
  --input data/external/abo \
  --output data/curated/abo_mvp_catalogue.csv \
  --limit 200
```

Validate the curated catalogue and create a price review queue:

```bash
uv run python backend/formaos/catalogue/validate_catalogue.py \
  --catalogue data/curated/abo_mvp_catalogue.csv \
  --summary artifacts/metrics/catalogue_validation.json \
  --price-review data/curated/price_review_queue.csv
```

Map ABO product images after `abo-images-small.tar` has been downloaded and
extracted:

```bash
uv run python backend/formaos/catalogue/map_images.py \
  --catalogue data/curated/abo_mvp_catalogue.csv \
  --abo-root data/external/abo \
  --images-root data/external/abo/images \
  --output data/curated/abo_mvp_catalogue_with_images.csv \
  --summary artifacts/metrics/image_mapping_summary.json \
  --strict
```

Build and smoke test the local Chroma retrieval index:

```bash
uv run python backend/formaos/catalogue/index_catalogue.py \
  --catalogue data/curated/abo_mvp_catalogue_with_images.csv \
  --chroma-path data/vectorstores/chroma \
  --summary artifacts/metrics/chroma_index_summary.json \
  --smoke-report artifacts/metrics/retrieval_smoke_report.json \
  --strict
```

## Main files

- `app/layout.tsx` - shared app shell and navigation
- `app/globals.css` - visual system and responsive layout
- `app/data.ts` - nav items, sample catalogue, metrics, and helpers
- `app/components/PlannerTool.tsx` - interactive MVP planner
- `app/components/ZoneGrid.tsx` - 3 by 3 placement grid for Vastu zone chips
- `app/*/page.tsx` - distinct route pages
- `docs/product_scope.md` - MVP scope and deferred list
- `docs/contracts.md` - shared frontend/backend contracts
- `backend/formaos/contracts.py` - Pydantic state and API models
- `backend/formaos/api/main.py` - initial FastAPI surface
- `backend/formaos/agents/planner.py` - OpenRouter-backed Planner node with strict JSON validation
- `backend/formaos/agents/designer.py` - Designer node that turns planner needs into validated retrieval slots
- `backend/formaos/agents/grounder.py` - Grounder node that retrieves real ABO catalogue items or typed no-fit failures
- `backend/formaos/agents/critic.py` - Critic node for fit, budget, sourceability, and opt-in Vastu checks
- `backend/formaos/agents/reviser.py` - deterministic Reviser that edits slots from Critic repair notes
- `backend/formaos/agents/graph_loop.py` - bounded LangGraph Planner to Designer to Grounder to Critic retry loop
- `backend/formaos/agents/pipeline.py` - typed Planner to Designer pipeline helper
- `backend/formaos/placement/zones.py` - 3 by 3 zone model and automatic placement defaults
- `backend/formaos/catalogue/*.py` - ABO inventory, curation, validation, and image mapping scripts
- `backend/formaos/vastu/schema.py` - Pydantic schema and generator for opt-in Vastu seed rules
- `backend/formaos/vastu/checker.py` - deterministic Vastu scorer with per-item badges and repair notes
- `data/vastu/seeds.csv` and `data/vastu/vastu_rules_v1.json` - manually curated Vastu MVP seed rules
