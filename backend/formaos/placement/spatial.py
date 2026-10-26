"""Deterministic room-envelope checks and explicit numeric image-model context.

Area screening is a necessary conservative check, not a collision-free floor plan.
"""
from __future__ import annotations
import json
from formaos.contracts import RoomBrief
from formaos.room_state import brief_dimensions_cm

# Rugs can sit beneath furniture; wall/ceiling and countertop objects do not each
# consume a separate floor footprint. These classes must not be added together.
FLOOR_CATEGORIES = frozenset({'sofa', 'loveseat', 'bed', 'cabinet', 'storage', 'table', 'desk', 'chair', 'refrigerator', 'shower', 'vanity', 'toilet', 'bathtub'})
MAX_FLOOR_COVERAGE = .65


def room_capacity_notes(brief: RoomBrief, grounded_slots) -> list[str]:
    dims = brief_dimensions_cm(brief)
    notes = []
    floor_area = 0.0
    for grounded in grounded_slots:
        item = grounded.selected_item
        if item is None:
            continue
        if item.width_cm > dims.width_cm or item.depth_cm > dims.depth_cm:
            notes.append(f'Replace {item.item_id}: actual product footprint exceeds the measured room envelope; do not shrink its dimensions.')
        if dims.height_cm is not None and item.height_cm is not None and item.height_cm > dims.height_cm:
            notes.append(f'Replace {item.item_id}: product height {item.height_cm:g} cm exceeds room height {dims.height_cm:g} cm.')
        if grounded.slot.category in FLOOR_CATEGORIES:
            floor_area += item.width_cm * item.depth_cm * grounded.slot.quantity
    room_area = dims.width_cm * dims.depth_cm
    if floor_area > room_area * MAX_FLOOR_COVERAGE:
        notes.append(f'Reduce floor furniture size or quantity: selected footprints total {floor_area / 10000:.2f} m2, exceeding the {MAX_FLOOR_COVERAGE:.0%} planning allowance ({room_area * MAX_FLOOR_COVERAGE / 10000:.2f} m2). Reserve space for access and circulation.')
    return notes


def spatial_image_context(design: dict | None) -> str:
    if not design or not design.get('room_brief'):
        return ''
    brief = RoomBrief.model_validate(design['room_brief'])
    dims = brief_dimensions_cm(brief)
    items = []
    for grounded in design.get('grounder_output', {}).get('grounded_slots', []):
        item = grounded.get('selected_item')
        if not item:
            continue
        items.append({'item_id': item['item_id'], 'category': grounded['slot']['category'], 'quantity': grounded['slot'].get('quantity', 1), 'width_cm': item['width_cm'], 'depth_cm': item['depth_cm'], 'height_cm': item.get('height_cm'), 'zone': grounded.get('placement_zone')})
    return ('Measured spatial brief (all dimensions in centimetres): ' + json.dumps({'room': dims.model_dump(), 'products': items})
            + '. Use one consistent real-world scale for room and products. Never enlarge the room, alter the camera to imply a larger space, or shrink an ABO product to force a fit. Respect quantities and leave usable circulation, chair pull-out space and access to doors and fixed fixtures. Missing heights are unknown, not zero. This numeric brief is a constraint, not proof of a collision-free layout.')
