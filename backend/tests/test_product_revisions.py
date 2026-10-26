"""Product revision regressions; runnable with unittest without extra dependencies."""
from __future__ import annotations

import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

from starlette.requests import Request
from formaos.agents.product_edits import category_aliases, parse_product_edits
from formaos.api import main as api
from formaos.agents.grounder import ground_design
from formaos.catalogue.index_catalogue import search_items
from formaos.contracts import DesignSlot
from formaos.room_state import InMemoryStateStore, create_room_brief


class ProductRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='.')
        self.addCleanup(self.temp.cleanup)
        self.catalogue = Path(self.temp.name) / 'catalogue.csv'
        self.rows = [
            dict(item_id='sofa-1', normalized_category='sofa', title='Sofa', width_cm=100, depth_cm=60, height_cm=80, price_inr=10000),
            dict(item_id='fan-1', normalized_category='fan', title='Ceiling fan', width_cm=80, depth_cm=80, height_cm=30, price_inr=2000),
            dict(item_id='ac-1', normalized_category='air_conditioner', title='Air conditioner', width_cm=70, depth_cm=25, height_cm=30, price_inr=22000),
            dict(item_id='custom-1', normalized_category='chandelier', title='Chandelier', width_cm=50, depth_cm=50, height_cm=30, price_inr=3000),
        ]
        with self.catalogue.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=self.rows[0].keys())
            writer.writeheader()
            writer.writerows(self.rows)
        self.brief = create_room_brief(width=18, depth=14, budget_inr=200000)
        self.sofa = DesignSlot(slot_id='sofa', category='sofa', target_width_cm=150, target_depth_cm=90, budget_share=1, placement_hint='S')
        self.retrieved = []
        def retrieve(query, category=None, **options):
            self.retrieved.append(category)
            return [dict(row, category=row['normalized_category'], distance=.1) for row in self.rows
                    if row['normalized_category'] == category
                    and row['width_cm'] <= options['max_width_cm']
                    and row['depth_cm'] <= options['max_depth_cm']
                    and row['price_inr'] <= options['max_price_inr']]
        self.lookup = patch('formaos.agents.grounder.search_items', side_effect=retrieve)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)
        with redirect_stdout(io.StringIO()):
            grounded = ground_design(self.brief, [self.sofa], catalogue_path=self.catalogue).model_dump(mode='json')
        self.design = dict(design_id='design', session_id='session', room_brief=self.brief.model_dump(mode='json'),
                           status='passed', designer_output={'slots':[self.sofa.model_dump(mode='json')]},
                           grounder_output=grounded, chat_messages=[])
        self.saved = {'design': self.design}
        self.store = MagicMock()
        self.store.get.side_effect = self.saved.get
        self.store.save.side_effect = lambda key, value: self.saved.__setitem__(key, deepcopy(value))
        for target, value in [('design_store', self.store), ('state_store', InMemoryStateStore()),
                              ('session_users', {}), ('session_projects', {}), ('CATALOGUE_PATH', self.catalogue)]:
            context = patch.object(api, target, value)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(api, 'request_user', return_value=None)
        context.start()
        self.addCleanup(context.stop)
        self.retrieved.clear()

    def revise(self, message):
        with redirect_stdout(io.StringIO()):
            return api.revise_design('design', api.ReviseRequest(message=message), Request({'type':'http', 'headers':[]})).design

    def test_add_and_remove_update_grounding_totals_status_and_saved_slots(self):
        added = self.revise('Add an AC and a ceiling fan')
        self.assertEqual(self.retrieved, ['air_conditioner', 'fan'])
        self.assertEqual(added['grounder_output']['grounded_slots'][0]['selected_item']['item_id'], 'sofa-1')
        self.assertEqual(added['critic_verdict']['total_price_inr'], 34000)
        self.assertEqual(added['critic_verdict']['sourceability']['status'], 'pass')
        self.retrieved.clear()
        removed = self.revise('Remove the sofa and the AC')
        self.assertEqual(self.retrieved, [])
        self.assertEqual([s['category'] for s in removed['designer_output']['slots']], ['fan'])
        self.assertEqual(removed['critic_verdict']['total_price_inr'], 2000)
        self.assertEqual(removed, self.saved['design'])

    def test_unconfigured_catalogue_category_is_sourceable(self):
        result = self.revise('Add a chandelier above the sofa')
        self.assertEqual(self.retrieved, ['chandelier'])
        self.assertEqual(result['critic_verdict']['total_price_inr'], 13000)
        self.assertEqual(result['critic_verdict']['sourceability']['status'], 'pass')
        self.assertEqual(len(result['designer_output']['slots']), 2)

    def test_missing_product_fails_sourceability_then_removal_recovers(self):
        self.rows = [r for r in self.rows if r['normalized_category'] != 'fan']
        missing = self.revise('Add a fan')
        self.assertEqual(missing['status'], 'failed')
        self.assertEqual(missing['critic_verdict']['sourceability']['status'], 'fail')
        fixed = self.revise('Remove the fan')
        self.assertEqual(fixed['status'], 'passed')
        self.assertEqual(fixed['critic_verdict']['sourceability']['status'], 'pass')

    def test_remove_last_item_has_no_stale_products_or_total(self):
        result = self.revise('Remove the sofa')
        self.assertEqual(result['grounder_output']['grounded_slots'], [])
        self.assertEqual(result['critic_verdict']['total_price_inr'], 0)

    def test_visual_edit_preserves_the_shopping_list(self):
        before = deepcopy(self.design['grounder_output'])
        result = self.revise('Make the curtains olive and change nothing else')
        self.assertEqual(result['grounder_output'], before)
        self.assertFalse(result['last_product_update'])
        self.assertEqual(self.retrieved, [])

    def test_multiple_and_negated_additions(self):
        result = self.revise('Do not remove the sofa; add two fans')
        self.assertEqual(len(result['designer_output']['slots']), 3)
        self.assertEqual(result['critic_verdict']['total_price_inr'], 14000)

    def test_parser_preserves_aliases_and_replacements(self):
        aliases = category_aliases(self.catalogue, [self.sofa])
        self.assertEqual([(e.action,e.category) for e in parse_product_edits('Replace the sofa with a fan', aliases)], [('remove','sofa'),('add','fan')])
        self.assertEqual(parse_product_edits('Do not add a fan', aliases), [])
        self.assertEqual([e.category for e in parse_product_edits('Remove the fan but not the sofa', aliases)], ['fan'])
        self.assertEqual([e.category for e in parse_product_edits('Add a fan but keep the sofa', aliases)], ['fan'])

    def test_remove_one_of_multiple_fans(self):
        self.revise('Add two fans')
        result = self.revise('Remove one fan')
        self.assertEqual([s['category'] for s in result['designer_output']['slots']], ['sofa', 'fan'])
        self.assertEqual(result['critic_verdict']['total_price_inr'], 12000)

    def test_unstocked_object_is_not_silently_excluded_from_sourceability(self):
        result = self.revise('Add an easel')
        self.assertIn('easel', self.retrieved)
        self.assertEqual(result['critic_verdict']['sourceability']['status'], 'fail')
        self.assertEqual(result['status'], 'failed')

    def test_catalogue_ac_spelling_retains_friendly_alias(self):
        for row in self.rows:
            if row['normalized_category'] == 'air_conditioner':
                row['normalized_category'] = 'ac'
        with self.catalogue.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=self.rows[0].keys())
            writer.writeheader()
            writer.writerows(self.rows)
        result = self.revise('Add an air conditioner')
        self.assertEqual(self.retrieved, ['ac'])
        self.assertEqual(result['critic_verdict']['sourceability']['status'], 'pass')

    def test_catalogue_category_filter_is_sent_before_candidate_limit(self):
        collection = MagicMock()
        collection.count.return_value = 500
        collection.query.return_value = {'metadatas':[[]], 'distances':[[]]}
        client = MagicMock()
        client.get_or_create_collection.return_value = collection
        with patch('formaos.catalogue.index_catalogue.client_for', return_value=client), redirect_stdout(io.StringIO()):
            search_items('ceiling fan', category='fan')
        self.assertEqual(collection.query.call_args.kwargs['where'], {'category':'fan'})


if __name__ == '__main__':
    unittest.main()
