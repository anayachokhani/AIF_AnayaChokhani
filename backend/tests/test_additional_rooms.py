"""Bathroom/dining planning, revisions, quantities and Vastu schema regressions."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from formaos.api.main import DemoPlannerClient, ConceptImageRequest, build_concept_prompt, selected_product_snapshots, selected_item_lines
from formaos.agents.designer import design_slots, planner_need_from_default
from formaos.agents.planner import PlannerOutput, build_planner_prompt
from formaos.agents.grounder import compute_slot_budget_inr
from formaos.agents.critic import critique_design
from formaos.agents.product_edits import category_aliases, parse_product_edits, apply_product_edits
from formaos.definitions import DEFAULT_ROOM_TYPES, ROOM_DEFAULT_NEEDS, ROOM_CATEGORIES, CATEGORIES
from formaos.room_state import create_room_brief, normalize_room_type, parse_room_brief_text, brief_dimensions_cm
from formaos.vastu.schema import VastuRule, load_rule_set


class AdditionalRoomTests(unittest.TestCase):
    def test_new_room_aliases_and_text(self):
        for alias, canonical in [('bathroom', 'bathroom'), ('washroom', 'bathroom'), ('bath room', 'bathroom'), ('Dining room', 'dining_room'), ('dining', 'dining_room'), ('dining area', 'dining_room')]:
            with self.subTest(alias=alias):
                self.assertEqual(normalize_room_type(alias), canonical)
                self.assertEqual(parse_room_brief_text(f'Design my {alias}')['room_type'], canonical)
                self.assertEqual(create_room_brief(room_type=alias).room_type, canonical)

    def test_all_rooms_and_budgets_generate_valid_slots(self):
        for room in ROOM_DEFAULT_NEEDS:
            for budget in [70000, 150000, 200000]:
                with self.subTest(room=room, budget=budget):
                    brief = create_room_brief(room_type=room, budget_inr=budget)
                    dims = brief_dimensions_cm(brief)
                    planner = PlannerOutput(room_facts=dict(room_type=room, width_cm=dims.width_cm, depth_cm=dims.depth_cm, budget_inr=budget, style_words=brief.style_words), needs_list=[planner_need_from_default(n, brief) for n in ROOM_DEFAULT_NEEDS[room][:2]])
                    output = design_slots(brief, planner, include_concept_prompt=True)
                    self.assertAlmostEqual(sum(slot.budget_share for slot in output.slots), 1, places=3)
                    self.assertTrue(all(slot.target_width_cm > 0 and slot.target_depth_cm > 0 and slot.placement_hint for slot in output.slots))
                    if room == 'bathroom':
                        self.assertTrue({'toilet','basin','shower','vanity'} <= {s.category for s in output.slots})
                    if room == 'dining_room':
                        self.assertEqual(next(s.quantity for s in output.slots if s.category == 'chair'), 4)

    def test_demo_and_model_prompts_use_room_specific_needs(self):
        for room, keyword in [('bathroom', 'plumbing'), ('dining_room', 'pull-out')]:
            brief = create_room_brief(room_type=room)
            planner = PlannerOutput.model_validate(json.loads(DemoPlannerClient(brief).complete([])))
            self.assertEqual({n.category for n in planner.needs_list}, set(ROOM_CATEGORIES[room]))
            self.assertIn(keyword, build_planner_prompt(brief)[0]['content'])
            image_prompt = build_concept_prompt(ConceptImageRequest(project_type='renovation', room_type=room))
            self.assertIn(keyword, image_prompt)
        self.assertEqual(next(n.quantity for n in planner.needs_list if n.category == 'chair'), 4)

    def test_new_room_types_and_fixtures_are_valid_vastu_rule_inputs(self):
        template = load_rule_set(Path('data/vastu/vastu_rules_v1.json')).rules[0].model_dump(mode='json')
        for room, category in [('bathroom','toilet'), ('dining_room','table')]:
            rule = VastuRule.model_validate({**template, 'room_type':room, 'object_class':category})
            self.assertEqual(rule.room_type, room)

    def test_bathroom_and_dining_revisions_use_shared_categories(self):
        for room, message, category in [('bathroom','Add a towel rail','towel_rack'), ('dining_room','Add two dining chairs','chair')]:
            brief = create_room_brief(room_type=room)
            aliases = category_aliases(Path('data/curated/abo_mvp_catalogue_with_images.csv'), [])
            edits = parse_product_edits(message, aliases)
            slots, ids = apply_product_edits(brief, [], edits, message)
            self.assertTrue(slots)
            self.assertEqual({s.category for s in slots}, {category})
            self.assertEqual(len(slots), 2 if room == 'dining_room' else 1)

    def test_dining_quantity_budget_snapshots_and_prompt(self):
        from backend.tests.test_product_revisions import ProductRevisionTests
        fixture = ProductRevisionTests(methodName='test_visual_edit_preserves_the_shopping_list')
        fixture.setUp()
        try:
            brief = create_room_brief(room_type='dining_room', budget_inr=150000)
            grounded = fixture.design['grounder_output']
            grounded['grounded_slots'][0]['slot']['quantity'] = 4
            with redirect_stdout(io.StringIO()):
                verdict = critique_design(brief, grounded, catalogue_path=fixture.catalogue)
            self.assertEqual(verdict.total_price_inr, 40000)
            slot = planner_need_from_default(ROOM_DEFAULT_NEEDS['dining_room'][1], brief)
            from formaos.contracts import DesignSlot
            chair = DesignSlot(slot_id='chairs', category='chair', quantity=4, budget_share=.28)
            self.assertEqual(compute_slot_budget_inr(brief, chair), 10500)
            design = {'grounder_output':grounded}
            self.assertEqual(selected_product_snapshots(design)[0]['quantity'], 4)
            self.assertTrue(selected_item_lines(design)[0].startswith('4 '))
        finally:
            fixture.doCleanups()

    def test_registry_is_complete(self):
        self.assertEqual(set(DEFAULT_ROOM_TYPES), set(ROOM_CATEGORIES))
        for room, needs in ROOM_DEFAULT_NEEDS.items():
            self.assertTrue(set(ROOM_CATEGORIES[room]) <= CATEGORIES.keys())


if __name__ == '__main__':
    unittest.main()
