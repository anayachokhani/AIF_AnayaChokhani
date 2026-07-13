# FormaOS Final Demo Script

## Setup

From a clean terminal at the repository root:

```bash
export PATH="$PWD/.tools/node/bin:$PWD/.tools/bin:$PATH"
export UV_CACHE_DIR="$PWD/.uv-cache"
export PYTHONPATH=backend
```

Start the backend in deterministic demo mode:

```bash
FORMAOS_DEMO_PLANNER=1 uv run uvicorn formaos.api.main:app --app-dir backend --reload
```

Start the frontend in a second terminal:

```bash
npm run dev
```

Optional evidence capture with headless Chrome running on port 9222:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless=new \
  --remote-debugging-port=9222 \
  --user-data-dir=/private/tmp/formaos-demo-chrome \
  --no-first-run \
  --disable-gpu \
  http://localhost:3000/workspace
```

Run the acceptance evidence script:

```bash
npm run demo:acceptance
```

## Demo Brief

- Room: 10 ft by 12 ft living room.
- Budget: Rs 85,000.
- Style: warm wood.
- Need: kid-friendly layout with extra storage.
- Vastu: enabled, north-facing compass/main-door setup.

## Walkthrough

1. Open `http://localhost:3000/workspace`.
2. Show the two-panel workspace: room/chat setup on the left, design workspace on the right.
3. Submit the demo brief.
4. Show progress states: planning, designing, grounding, checking, revising, passed/failed/error.
5. Show the first backend design result and attempt log state from `artifacts/demo/acceptance_run.json`.
6. Show grounded product cards with real item IDs, product photos, dimensions, prices, fit notes, Vastu badge, and alternatives.
7. Open the Vastu tab and show the 3 by 3 grid, item chips, score/status, rules, notes, and palette guidance.
8. Open the Shopping List tab and show selected items, exact total, user budget, and budget status.
9. Open the generated `/design/{id}/brief` route from the workspace.
10. Show the export brief with room summary, requirements, images, selected products, prices, budget summary, fit notes, Vastu summary, design ID, generation time, ABO attribution, and indicative pricing disclaimer.
11. Print/export the brief to PDF.
12. Open `artifacts/metrics/eval_summary_table.md` and show FormaOS versus baseline metrics.

## Evidence Files

- `artifacts/demo/acceptance_run.json`
- `artifacts/demo/workspace.png`
- `artifacts/demo/export_brief.png`
- `artifacts/demo/export_brief.pdf`
- `artifacts/metrics/eval_summary.json`
- `artifacts/metrics/eval_summary_table.md`

## Acceptance Criteria

The final demo passes when:

- The app starts using README commands.
- A backend session is created.
- The full brief to checked design journey completes.
- Grounded catalogue items, prices, dimensions, budget status, Vastu status, and export brief are visible without developer tools.
- Metrics evidence is available under `artifacts/metrics/`.
- `artifacts/demo/acceptance_run.json` reports `status: PASS`.
