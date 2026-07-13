# FormaOS Contracts

These contracts define the shared field names used by the frontend, backend,
catalogue, agent loop, and tests.

## RoomBrief

```json
{
  "room_type": "living_room",
  "width": 10,
  "depth": 12,
  "units": "ft",
  "budget_inr": 85000,
  "style_words": ["warm", "modern", "wood", "family"],
  "constraints": ["kid-friendly", "extra storage"],
  "vastu_enabled": true,
  "main_door_direction": "N",
  "compass_direction": "N"
}
```

Required fields: `room_type`, `width`, `depth`, `units`, `budget_inr`,
`style_words`, and `vastu_enabled`.

Backend helpers normalize partial room input into this contract:

- `create_room_brief(...)` applies defaults for common room types.
- `brief_dimensions_cm(...)` converts `ft`, `m`, or `cm` into centimeters.
- `create_initial_state(...)` stores the validated brief and normalized
  dimensions in the graph state object.

## DesignSlot

```json
{
  "slot_id": "slot_sofa_1",
  "category": "sofa",
  "quantity": 1,
  "target_width_cm": 210,
  "target_depth_cm": 95,
  "style_text": "warm modern compact family sofa",
  "budget_share": 0.38,
  "must_have_constraints": ["kid-friendly"],
  "placement_hint": "S"
}
```

## CatalogueItem

```json
{
  "item_id": "SOF-101",
  "title": "Kavya compact three-seat sofa",
  "product_type": "sofa",
  "width_cm": 208,
  "depth_cm": 88,
  "height_cm": 82,
  "material": "woven fabric",
  "color": "moss grey",
  "style_text": "warm modern family minimal",
  "price_inr": 32000,
  "image_path": null,
  "image_available": false,
  "source_url": null,
  "source_dataset": "demo_catalogue",
  "price_note": "curated indicative demo price"
}
```

## GroundedDesign

```json
{
  "design_id": "demo-living-room-001",
  "brief": {},
  "slots": [],
  "selected_items": [],
  "alternatives": {},
  "total_price_inr": 78900,
  "fit_status": "pass",
  "budget_status": "pass",
  "sourceability_status": "pass",
  "vastu_status": "warn",
  "fit_notes": [],
  "vastu_notes": [],
  "attempt_log": []
}
```

## Frontend Response States

- `waiting`
- `planning`
- `designing`
- `grounding`
- `checking`
- `revising`
- `passed`
- `failed`
- `error`

## FormaOSState

```json
{
  "session_id": "local-demo-session",
  "response_state": "waiting",
  "brief": {},
  "brief_cm": {
    "width_cm": 304.8,
    "depth_cm": 365.8
  },
  "current_design": null,
  "messages": [],
  "attempt_log": []
}
```

## Stable API Error Codes

- `missing_api_key`
- `invalid_brief`
- `no_catalogue_results`
- `graph_failure`
- `retry_exhausted`
- `not_found`
