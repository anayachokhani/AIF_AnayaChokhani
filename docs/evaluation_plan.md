# FormaOS Evaluation Plan

This evaluation set is frozen before final metrics are run. T21 must use the files under `data/eval/` as written here and must not tune briefs or metrics after seeing results.

## Frozen Inputs

- `data/eval/test_briefs.json`: 10 room briefs covering living rooms, bedrooms, studies, small budgets, large budgets, Vastu on/off, metric units, and impossible constraints.
- `data/eval/baseline_definition.json`: ungrounded baseline definition.
- `data/eval/output_schema.json`: common output shape for FormaOS and baseline outputs.
- `data/eval/metric_definitions.json`: metric definitions for fit, budget, sourceability, and Vastu.

## Baseline

The baseline is an ungrounded LLM-style item list. It may propose plausible furniture in prose, but it cannot use catalogue lookup, ABO item IDs, Chroma retrieval, product images, hard dimension filtering, hard price filtering, or the deterministic Vastu rule engine.

## Metrics

- Fit rate: selected items whose dimensions satisfy room or slot constraints.
- Budget accuracy: designs whose total selected item price is within budget.
- Sourceability: selected items that exist in the curated catalogue.
- Optional Vastu compliance: deterministic Vastu checks for briefs where Vastu is enabled.

## Common Output Format

FormaOS and baseline outputs must be converted into `data/eval/output_schema.json` before scoring. Baseline item IDs and image paths must remain null because baseline outputs are not sourceable catalogue selections.
