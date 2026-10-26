"""Apply explicit product additions/removals before catalogue matching.

Recognize categories from the shared registry, the actual catalogue, and saved
slots. Catalogue-only categories do not require a new room default dictionary.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from formaos.contracts import DesignSlot, RoomBrief
from formaos.definitions import CATEGORIES, CATEGORY_TERMS, ROOM_FOOTPRINT_OVERRIDES
from formaos.room_state import brief_dimensions_cm


@dataclass(frozen=True)
class ProductEdit:
    action: str
    category: str
    quantity: int = 0


def words(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def category_aliases(catalogue_path: Path, slots: list[DesignSlot]) -> dict[str, set[str]]:
    aliases = {category: {words(category), *(words(term) for term in terms)}
               for category, terms in CATEGORY_TERMS.items()}
    # Revision aliases describe products, rather than broader seating/lighting concepts.
    aliases.setdefault("sofa", set()).discard("loveseat")
    catalogue_categories = set()
    if catalogue_path.exists():
        with catalogue_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                category = row.get("normalized_category", "").strip()
                if category:
                    catalogue_categories.add(category)
                    aliases.setdefault(category, set()).add(words(category))
    for category in list(catalogue_categories):
        for registered, terms in list(aliases.items()):
            if registered != category and words(category) in terms and registered not in catalogue_categories:
                aliases[category].update(terms)
                aliases.pop(registered, None)
    for slot in slots:
        aliases.setdefault(slot.category, set()).add(words(slot.category))
    return aliases


def mentioned_categories(text: str, aliases: dict[str, set[str]]) -> list[tuple[int, int, str]]:
    normalized = words(text)
    matches = []
    for category, terms in aliases.items():
        for term in terms:
            pattern = r"\b" + re.escape(term) + r"(?:s|es)?\b"
            matches.extend((m.start(), m.end(), category) for m in re.finditer(pattern, normalized))
    # A specific catalogue category (ceiling fan) wins over an overlapping alias (fan).
    chosen = []
    for match in sorted(matches, key=lambda m: (-(m[1] - m[0]), m[0])):
        if not any(match[0] < other[1] and match[1] > other[0] for other in chosen):
            chosen.append(match)
    return sorted(chosen)


def parse_product_edits(message: str, aliases: dict[str, set[str]]) -> list[ProductEdit]:
    normalized = words(message)
    action_pattern = re.compile(r"\b(add|include|install|put|remove|delete|discard|eliminate|omit|replace|swap|change|refresh|update|make|keep|leave)\b|\btake out\b|get rid of")
    actions = list(action_pattern.finditer(normalized))
    edits = []
    for index, action in enumerate(actions):
        # Do not interpret explicit negative instructions as product edits.
        prefix = normalized[max(0, action.start() - 18):action.start()]
        if re.search(r"(?:do not|don t|dont|never|not)\s+$", prefix):
            continue
        clause = normalized[action.end():actions[index + 1].start() if index + 1 < len(actions) else len(normalized)]
        clause = words(clause)
        verb = action.group()
        if verb in {"change", "refresh", "update", "make", "keep", "leave"}:
            continue
        operation = "add" if verb in {"add", "include", "install", "put"} else "remove"
        if verb in {"replace", "swap"}:
            parts = re.split(r"\b(?:with|for)\b", clause, maxsplit=1)
            if len(parts) != 2:
                continue
            old = mentioned_categories(parts[0], aliases)
            new = mentioned_categories(parts[1], aliases)
            # Same-category replacements use the ordinary refresh path.
            if {m[2] for m in old} == {m[2] for m in new}:
                continue
            edits.extend(ProductEdit("remove", m[2]) for m in old)
            clause = words(parts[1])
            operation = "add"
        clause = re.split(r"\b(?:above|below|beside|near|behind|under|over|onto|on|next to|in front of|but not|except|without|but keep|while keeping|and keep|keep|leave|preserve)\b", clause, maxsplit=1)[0].strip()
        matches = mentioned_categories(clause, aliases)
        if operation == "remove" and re.search(r"\b(?:all furniture|all products|everything)\b", clause):
            matches = [(0, 0, category) for category in aliases]
        if not matches and operation == "add":
            # Preserve explicit requests for unstocked objects in sourceability too.
            # A category that has no catalogue match stays an unavailable slot.
            for phrase in re.split(r"\band\b", clause):
                object_match = re.fullmatch(r"\s*(?:a|an|the|one)\s+([a-z][a-z ]{1,60})\s*", phrase)
                if object_match:
                    category = object_match.group(1).strip().replace(" ", "_")
                    matches.append((0, 0, category))
        for start, end, category in matches:
            before = clause[:start]
            quantity_match = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight)\s+(?:(?:new|more|additional)\s+)?$", before)
            value = quantity_match.group(1) if quantity_match else "1"
            number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
            quantity = int(value) if value.isdigit() else number_words[value]
            count = max(1, min(quantity, 8)) if operation == "add" or quantity_match else 0
            edits.append(ProductEdit(operation, category, count))
    return edits


def apply_product_edits(brief: RoomBrief, slots: list[DesignSlot], edits: list[ProductEdit], message: str) -> tuple[list[DesignSlot], set[str]]:
    updated = [slot.model_copy(deep=True) for slot in slots]
    changed_ids = set()
    dims = brief_dimensions_cm(brief)
    for edit in edits:
        if edit.action == "remove":
            remaining = edit.quantity
            kept = []
            for slot in updated:
                if slot.category != edit.category:
                    kept.append(slot)
                elif edit.quantity and remaining <= 0:
                    kept.append(slot)
                elif edit.quantity:
                    remaining -= slot.quantity
                    if remaining < 0:
                        kept.append(slot.model_copy(update={"quantity": -remaining}))
            updated = kept
            continue
        definition = CATEGORIES.get(edit.category)
        if definition is None:
            definition = next((entry for entry in CATEGORIES.values()
                               if words(edit.category) in {words(term) for term in entry.terms}), None)
        # Unknown catalogue categories use room-bounded retrieval limits, not a furniture allowlist.
        width, depth = (definition.footprint(dims.width_cm, dims.depth_cm) if definition else (dims.width_cm * .75, dims.depth_cm * .6))
        override = ROOM_FOOTPRINT_OVERRIDES.get((brief.room_type, edit.category))
        if override:
            width, depth = override(dims.width_cm, dims.depth_cm)
        slot = DesignSlot(
            slot_id=f"slot_{uuid4().hex[:12]}_{edit.category}", category=edit.category,
            quantity=1, target_width_cm=width, target_depth_cm=depth,
            budget_share=max(.15, min(.6, definition.price_band[0] * 2 / brief.budget_inr)) if definition else .15, style_text=" ".join([*brief.style_words, message]),
            must_have_constraints=brief.constraints,
            placement_hint=definition.placement if definition else "C",
        )
        for _ in range(max(1, edit.quantity)):
            added = slot.model_copy(update={"slot_id": f"slot_{uuid4().hex[:12]}_{edit.category}", "quantity": 1})
            updated.append(added)
            changed_ids.add(added.slot_id)
    if updated:
        total = sum(slot.budget_share for slot in updated)
        for slot in updated:
            slot.budget_share = slot.budget_share / total if total else 1 / len(updated)
    return updated, changed_ids
