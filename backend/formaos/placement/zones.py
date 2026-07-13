from __future__ import annotations

from formaos.contracts import Direction, DesignSlot


ZONES: tuple[Direction, ...] = ("NW", "N", "NE", "W", "C", "E", "SW", "S", "SE")

DEFAULT_CATEGORY_ZONES: dict[str, tuple[Direction, ...]] = {
    "bed": ("SW",),
    "wardrobe": ("SW", "S", "W"),
    "cabinet": ("SW", "S", "W"),
    "storage": ("SW", "S", "W"),
    "sofa": ("S", "W"),
    "loveseat": ("S", "W"),
    "mirror": ("N", "E"),
    "stove": ("SE",),
    "lamp": ("SE", "S"),
    "table": ("C",),
    "rug": ("C",),
    "desk": ("E", "N"),
    "chair": ("E", "N"),
    "planter": ("NE", "N", "E"),
}


class PlacementZoneError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "placement_zone_validation_failed"


def is_valid_zone(zone: str | None) -> bool:
    return zone in ZONES


def map_placement_hint_to_zone(placement_hint: str) -> Direction:
    if placement_hint not in ZONES:
        raise PlacementZoneError(f"invalid placement hint: {placement_hint}")
    return placement_hint


def map_user_chip_location(chip_location: str | None) -> Direction | None:
    if chip_location is None:
        return None
    normalized = chip_location.strip().upper().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {
        "NORTHWEST": "NW",
        "NORTH": "N",
        "NORTHEAST": "NE",
        "WEST": "W",
        "CENTER": "C",
        "CENTRE": "C",
        "EAST": "E",
        "SOUTHWEST": "SW",
        "SOUTH": "S",
        "SOUTHEAST": "SE",
    }
    return aliases.get(normalized, normalized) if is_valid_zone(aliases.get(normalized, normalized)) else None


def default_zones_for_category(category: str) -> tuple[Direction, ...]:
    return DEFAULT_CATEGORY_ZONES.get(category.strip().lower(), ("C",))


def assign_zone_for_slot(slot: DesignSlot, user_chip_location: str | None = None) -> Direction:
    chip_zone = map_user_chip_location(user_chip_location)
    if chip_zone is not None:
        return chip_zone
    if slot.placement_hint is not None:
        return map_placement_hint_to_zone(slot.placement_hint)
    return default_zones_for_category(slot.category)[0]
