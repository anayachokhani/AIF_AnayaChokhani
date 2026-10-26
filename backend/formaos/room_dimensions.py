"""Room input policy shared verbatim with both frontend planners."""
from __future__ import annotations
import json
import math
from pathlib import Path

ROOM_DIMENSION_POLICY = json.loads((Path(__file__).resolve().parents[2] / 'shared' / 'room-dimensions.json').read_text(encoding='utf-8'))
UNIT_FACTORS = {'ft': 30.48, 'm': 100.0, 'cm': 1.0}


def validate_room_dimensions(room_type: str, width: float, depth: float, units: str, height: float | None = None) -> None:
    factor = UNIT_FACTORS[units]
    sides = (width * factor, depth * factor)
    if not all(math.isfinite(side) and side > 0 for side in sides):
        raise ValueError('Room dimensions must be positive finite numbers.')
    if max(sides) > ROOM_DIMENSION_POLICY['maxSideCm'] + 1e-6:
        raise ValueError('Room sides must not exceed 24.384 m (80 ft).')
    limits = ROOM_DIMENSION_POLICY['rooms'].get(room_type)
    if limits is None:
        raise ValueError(f'Unsupported room type: {room_type}')
    if min(sides) + 1e-6 < limits['minSideCm'] or sides[0] * sides[1] / 10000 + 1e-6 < limits['minAreaM2']:
        raise ValueError(f"{room_type.replace('_', ' ').title()} requires both sides at least {limits['minSideCm'] / 100:g} m and floor area at least {limits['minAreaM2']:g} m2.")
    if height is not None and (not math.isfinite(height) or height * factor + 1e-6 < limits['minHeightCm']):
        raise ValueError(f"{room_type.replace('_', ' ').title()} requires clear height at least {limits['minHeightCm'] / 100:g} m.")
