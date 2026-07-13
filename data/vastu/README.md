# Vastu Rules

FormaOS treats Vastu as opt-in traditional guidance only. It is not a
scientific guarantee, architectural certification, safety review, legal advice,
or a promise of any outcome. The application must not apply these rules unless
the user explicitly enables Vastu guidance in the room brief.

The MVP target file is:

```text
data/vastu/vastu_rules_v1.json
```

The editable seed source is:

```text
data/vastu/seeds.csv
```

Rules are manually curated seed guidance. Each rule includes:

- `rule_id`
- `perspective`
- `room_type`
- `object_class`
- `preferred_zones`
- `avoided_zones`
- `preferred_colors`
- `avoided_colors`
- `severity`
- `rationale`
- `source_urls`
- `confidence`

Regenerate the JSON file from the seed CSV with:

```bash
PYTHONPATH=backend uv run python backend/formaos/vastu/schema.py \
  --seeds data/vastu/seeds.csv \
  --output data/vastu/vastu_rules_v1.json
```
