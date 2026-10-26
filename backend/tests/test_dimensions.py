"""Room minimums, units, envelope and combined-footprint regression tests."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch
from pydantic import ValidationError
from formaos.contracts import RoomBrief, DesignSlot, CatalogueItem
from formaos.room_state import create_room_brief, brief_dimensions_cm
from formaos.room_dimensions import ROOM_DIMENSION_POLICY
from formaos.agents.grounder import GrounderOutput, GroundedSlot, SlotConstraints
from formaos.agents.critic import critique_design
from formaos.catalogue.index_catalogue import metadata_passes, search_items
from formaos.placement.spatial import room_capacity_notes, spatial_image_context


class DimensionTests(unittest.TestCase):
    def test_room_limits_in_every_unit_and_rotation(self):
        for room, limits in ROOM_DIMENSION_POLICY['rooms'].items():
            width = limits['minSideCm']
            depth = limits['minAreaM2'] * 10000 / width
            for units, factor in [('cm',1), ('m',100), ('ft',30.48)]:
                with self.subTest(room=room, units=units):
                    brief = create_room_brief(room_type=room, width=width/factor, depth=depth/factor, height=limits['minHeightCm']/factor, units=units)
                    create_room_brief(room_type=room, width=depth/factor, depth=width/factor, units=units)
                    self.assertAlmostEqual(brief_dimensions_cm(brief).width_cm, width, places=1)
                    with self.assertRaises(ValidationError):
                        create_room_brief(room_type=room, width=(width-1)/factor, depth=depth/factor, units=units)
                    with self.assertRaises(ValidationError):
                        create_room_brief(room_type=room, width=width/factor, depth=(depth-1)/factor, units=units)
                    with self.assertRaises(ValidationError):
                        create_room_brief(room_type=room, width=width/factor, depth=depth/factor, height=(limits['minHeightCm']-1)/factor, units=units)

    def test_defaults_and_unit_consistent_upper_bound(self):
        for room in ROOM_DIMENSION_POLICY['rooms']:
            create_room_brief(room_type=room)
        for units, size in [('ft',81), ('m',25), ('cm',2500)]:
            with self.assertRaises(ValidationError):
                create_room_brief(width=size, depth=size, units=units)

    def grounded(self, quantity=1, height=100, category='chair'):
        return GroundedSlot(slot=DesignSlot(slot_id='chairs', category=category, quantity=quantity, budget_share=1), placement_zone='C', constraints=SlotConstraints(max_width_cm=200,max_depth_cm=200,max_price_inr=100000), selected_item=CatalogueItem(item_id='chair',title='Chair',product_type=category,width_cm=100,depth_cm=100,height_cm=height,price_inr=2000,placement_zone='C'))

    def test_quantity_can_fail_combined_fit_when_every_item_fits(self):
        brief=create_room_brief(room_type='dining_room',width=3,depth=3.2,units='m')
        self.assertEqual(room_capacity_notes(brief,[self.grounded(quantity=4)]),[])
        self.assertTrue(any('quantity' in note for note in room_capacity_notes(brief,[self.grounded(quantity=8)])))
        self.assertEqual(room_capacity_notes(brief,[self.grounded(quantity=8, category='rug')]),[])

    def test_tall_product_and_numeric_image_context(self):
        brief=create_room_brief(height=9.1)
        grounded=self.grounded(height=300)
        self.assertTrue(any('height' in note for note in room_capacity_notes(brief,[grounded])))
        context=spatial_image_context({'room_brief':brief.model_dump(mode='json'),'grounder_output':{'grounded_slots':[grounded.model_dump(mode='json')]}})
        self.assertIn('"height_cm": 277.4',context)
        self.assertIn('"height_cm": 300',context)
        self.assertIn('Never enlarge the room',context)

    def test_height_filter_rejects_oversized_or_unknown_products(self):
        item=dict(category='cabinet',width_cm=80,depth_cm=40,height_cm=300,price_inr=10000)
        self.assertFalse(metadata_passes(item,'cabinet',100,100,20000,max_height_cm=275))
        item['height_cm']=200
        self.assertTrue(metadata_passes(item,'cabinet',100,100,20000,max_height_cm=275))
        item['height_cm']=None
        self.assertFalse(metadata_passes(item,'cabinet',100,100,20000,max_height_cm=275))

    def test_capacity_failure_reaches_critic_fit_status(self):
        import tempfile
        from pathlib import Path
        brief = create_room_brief(room_type='dining_room', width=3, depth=3.2, units='m')
        with tempfile.TemporaryDirectory(dir='.') as directory:
            catalogue = Path(directory) / 'ids.csv'
            catalogue.write_text('item_id\nchair\n', encoding='utf-8')
            with redirect_stdout(io.StringIO()):
                verdict = critique_design(brief, GrounderOutput(grounded_slots=[self.grounded(quantity=8)]), catalogue_path=catalogue)
            self.assertEqual(verdict.fit.status.value, 'fail')
            self.assertEqual(verdict.sourceability.status.value, 'pass')
            self.assertFalse(verdict.passed)

    def test_image_generation_is_blocked_for_a_known_nonfitting_plan(self):
        import asyncio
        from unittest.mock import AsyncMock
        from starlette.requests import Request
        from fastapi import HTTPException
        from formaos.api import main as api
        design = {'design_id':'blocked', 'room_brief':create_room_brief().model_dump(mode='json'), 'critic_verdict':{'fit':{'status':'fail'}}}
        store = MagicMock()
        store.get.return_value = design
        image_generator = AsyncMock()
        with patch.object(api, 'design_store', store), patch.object(api, 'request_user', return_value=None), patch.object(api, 'project_concept_history', return_value=([], [])), patch.object(api, 'generate_openai_image', image_generator):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(api.create_concept_image(api.ConceptImageRequest(design_id='blocked', project_type='new_space', room_type='living_room'), Request({'type':'http', 'headers':[]})))
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.detail['code'], 'room_fit_failed')
            image_generator.assert_not_called()

    def test_all_numeric_filters_precede_vector_candidate_limit(self):
        client=MagicMock();collection=client.get_or_create_collection.return_value
        collection.count.return_value=500;collection.query.return_value={'metadatas':[[]],'distances':[[]]}
        with patch('formaos.catalogue.index_catalogue.client_for',return_value=client), redirect_stdout(io.StringIO()):
            search_items('cabinet',category='cabinet',max_width_cm=100,max_depth_cm=60,max_height_cm=275,max_price_inr=20000)
        filters=collection.query.call_args.kwargs['where']['$and']
        self.assertIn({'height_cm':{'$lte':275}},filters)
        self.assertIn({'width_cm':{'$lte':100}},filters)


if __name__=='__main__':
    unittest.main()
