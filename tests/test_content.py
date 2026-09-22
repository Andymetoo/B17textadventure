import copy
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest

from app import create_app
from content import TOUR_GOALS, TOUR_LENGTHS, build_briefing, chapter, ground_situation
from game_engine import (RuleError, _mission_consequences, advance, availability,
                         choose_ground, decision_blocker, dispatch, next_event,
                         requisition, set_tour_length, stand_down, start_job)
from models import migrate_campaign, new_campaign
from storage import CampaignStore


class CampaignContentTests(unittest.TestCase):
    def decision(self, kind):
        for seed in range(500):
            state = new_campaign(seed)
            state.update(operation=5, losses=1)
            state['aircraft'][0].update(sorties=6, fatigue=60)
            found = ground_situation(state)
            if found and found['kind'] == kind:
                state['decision'] = found
                return state
        self.fail(f'No eligible situation found for {kind}')

    def test_tour_lengths_and_scaled_goals(self):
        for length in TOUR_LENGTHS:
            state = new_campaign(1, length=length)
            self.assertEqual(state['goal'], TOUR_GOALS[length])
            for _ in range(length):
                stand_down(state, 0)
            self.assertTrue(state['completed'])
            self.assertEqual(len(state['debriefs']), length)
        with self.assertRaises(ValueError):
            new_campaign(length=10000)

    def test_length_locks_after_dispatch(self):
        state = new_campaign(1)
        set_tour_length(state, 28)
        dispatch(state, 'support', ['a1'], 0)
        with self.assertRaises(RuleError):
            set_tour_length(state, 7)

    def test_opening_is_gentler_and_has_no_ground_decisions(self):
        state = new_campaign(1)
        self.assertIsNone(ground_situation(state))
        self.assertTrue(all(m['opening'] for m in build_briefing(state)))
        early = chapter(state)['risk']
        state['operation'] = 20
        self.assertGreater(chapter(state)['risk'], early)

    def test_ground_choices_have_all_eight_contextual_variants(self):
        for kind in ['parts_trade', 'fuel_trade', 'intelligence', 'escort', 'leave', 'training', 'mentoring', 'letters']:
            state = self.decision(kind)
            self.assertIsNone(decision_blocker(state))
            choose_ground(state, state['decision']['id'], 'accept', 1000)
            self.assertIsNone(state['decision'])
            self.assertEqual(state['decision_history'][-1], kind)
            self.assertTrue(state['journal'])

    def test_ground_choice_costs_and_double_submission(self):
        state = self.decision('parts_trade')
        decision = state['decision']['id']
        supplies, parts = state['supplies'], state['parts']
        choose_ground(state, decision, 'accept', 0)
        self.assertEqual(state['supplies'], supplies - 3)
        self.assertEqual(state['parts'], parts + 2)
        with self.assertRaises(RuleError):
            choose_ground(state, decision, 'accept', 0)

    def test_unaffordable_choice_does_not_change_state(self):
        state = self.decision('parts_trade')
        state['supplies'] = 0
        before = copy.deepcopy(state)
        with self.assertRaises(RuleError):
            choose_ground(state, state['decision']['id'], 'accept', 0)
        self.assertEqual(state, before)
        choose_ground(state, state['decision']['id'], 'decline', 0)
        self.assertEqual(state['supplies'], 0)

    def test_leave_has_opportunity_cost_and_returns_next_operation(self):
        state = self.decision('leave')
        plane = next(p for p in state['aircraft'] if p['id'] == state['decision']['plane'])
        choose_ground(state, state['decision']['id'], 'accept', 0)
        self.assertEqual(availability(state, plane), 'Crew on leave')
        with self.assertRaises(RuleError):
            dispatch(state, 'priority', [plane['id']], 0)
        with self.assertRaises(RuleError):
            start_job(state, plane['id'], 'rest', 0)
        advance(state, 10 ** 10)
        self.assertEqual(availability(state, plane), 'Crew on leave')
        stand_down(state, 0)
        self.assertEqual(availability(state, plane), 'Available')

    def test_training_and_mentoring_change_future_capability(self):
        state = self.decision('training')
        plane = next(p for p in state['aircraft'] if p['id'] == state['decision']['plane'])
        skill = plane['skill']
        choose_ground(state, state['decision']['id'], 'accept', 0)
        self.assertAlmostEqual(plane['skill'], skill + .08)
        self.assertEqual(availability(state, plane), 'Crew training')
        state = self.decision('mentoring')
        skills = [p['skill'] for p in state['aircraft']]
        choose_ground(state, state['decision']['id'], 'accept', 0)
        self.assertTrue(any(p['skill'] > old for p, old in zip(state['aircraft'], skills)))

    def test_optional_decision_does_not_expire_with_time_or_require_midair_action(self):
        state = self.decision('intelligence')
        decision = copy.deepcopy(state['decision'])
        advance(state, 10 ** 10)
        self.assertEqual(state['decision'], decision)
        dispatch(state, 'priority', ['a1'], 10 ** 10)
        self.assertIsNone(state['decision'])
        self.assertIn('kept our current arrangements', state['journal'][-1]['text'])

    def test_followup_is_created_by_results_and_expires_by_operation(self):
        state = new_campaign(1)
        flight = {'operation': 1, 'mission': {'name': 'Test junction', 'bonus': 'none', 'effect': 'followup'}}
        _mission_consequences(state, flight, .64)
        self.assertIsNone(state['opportunity'])
        _mission_consequences(state, flight, .65)
        state['operation'] = 2
        self.assertIn('followup', [m['id'] for m in build_briefing(state)])
        dispatch(state, 'followup', ['a1'], 0)
        self.assertIsNone(state['opportunity'])
        state = new_campaign(1)
        _mission_consequences(state, flight, 1)
        state['operation'] = 4
        self.assertNotIn('followup', [m['id'] for m in build_briefing(state)])

    def test_final_operation_never_promises_a_future_advantage(self):
        for effect in ('intel', 'disruption', 'followup'):
            state = new_campaign(1, length=7)
            state['operation'] = 7
            flight = {'operation': 7, 'mission': {'name': 'Last assignment', 'bonus': 'none', 'effect': effect}}
            bonus, text = _mission_consequences(state, flight, 1)
            self.assertFalse(state['effects'])
            self.assertIsNone(state['opportunity'])
            self.assertIn('tour ends', text[0])

    def test_disruption_and_intelligence_have_bounded_future_effects(self):
        state = new_campaign(1)
        state['operation'] = 4
        normal = build_briefing(state)[0]
        state['effects'] = {'disruption': 5, 'intel': 5}
        improved = build_briefing(state)[0]
        self.assertLess(improved['risk'], normal['risk'])
        self.assertTrue(improved['intel'])
        state['operation'] = 6
        self.assertFalse(build_briefing(state)[0]['intel'])

    def test_diversions_medical_outcomes_and_crew_histories_are_reachable(self):
        seen = set()
        for seed in range(180):
            state = new_campaign(seed)
            state['operation'] = 5
            dispatch(state, 'priority', ['a1', 'a2', 'a3', 'a5'], 1000)
            advance(state, state['active']['returns'])
            for result in state['debriefs'][-1]['results']:
                seen.update(result['events'])
                plane = next(p for p in state['aircraft'] if p['id'] == result['id'])
                self.assertTrue(plane['history'])
                if result['diverted']:
                    self.assertEqual(availability(state, plane), 'At another airfield')
                    with self.assertRaises(RuleError):
                        start_job(state, plane['id'], 'repair', 12000)
                if result['medical'] and not result['lost'] and not result['diverted']:
                    self.assertEqual(availability(state, plane), 'Medical leave')
            advance(state, 100000)
            self.assertTrue(all(p['away_until'] is None for p in state['aircraft']))
        self.assertTrue({'diversion', 'forced_landing', 'engine', 'oxygen', 'hung_bombs', 'secondary', 'excellent'} <= seen)

    def test_surviving_crew_keeps_identity_and_leave_when_aircraft_replaced(self):
        state = new_campaign(5)
        plane = state['aircraft'][0]
        plane.update(lost=True, crew_fate='safe', sorties=6, unavailable_until=3, leave_reason='Medical leave')
        original = copy.deepcopy(plane)
        requisition(state, plane['id'], 0)
        plane = state['aircraft'][0]
        for field in ['captain', 'skill', 'sorties', 'unavailable_until']:
            self.assertEqual(plane[field], original[field])
        self.assertFalse(plane['lost'])

    def test_queued_ground_work_runs_serially_while_player_is_away(self):
        state = new_campaign(5)
        start_job(state, 'a5', 'repair', 1000)
        start_job(state, 'a6', 'repair', 1000)
        start_job(state, 'a1', 'rest', 1000)
        start_job(state, 'a4', 'rest', 1000)
        self.assertEqual(state['aircraft'][5]['job']['due'], 6400)
        frequent = copy.deepcopy(state)
        for now in [3700, 6400, 10000]:
            advance(frequent, now)
        advance(state, 10000)
        self.assertEqual(state, frequent)
        self.assertEqual(state['aircraft'][5]['condition'], 100)
        self.assertTrue(all(p['job'] is None for p in state['aircraft']))

    def test_full_offline_catchup_includes_diverted_aircraft(self):
        for seed in range(100):
            state = new_campaign(seed)
            state['operation'] = 6
            dispatch(state, 'priority', ['a1', 'a2', 'a3'], 0)
            offline = copy.deepcopy(state)
            while event := next_event(state):
                advance(state, event[0])
            advance(offline, 100000)
            self.assertEqual(state, offline)
            if any('diversion' in r['events'] for r in state['debriefs'][-1]['results']):
                break
        else:
            self.fail('No diversion exercised')


class MigrationTests(unittest.TestCase):
    def fixture(self):
        return json.loads((Path(__file__).parent / 'fixtures/schema1_midflight.json').read_text())

    def test_original_flight_finishes_with_original_outcomes(self):
        data = self.fixture()
        state = data['saved']
        migrate_campaign(state)
        self.assertEqual(state['length'], 12)
        self.assertEqual(state['goal'], 60)
        advance(state, 4000)
        self.assertEqual(state['debriefs'], data['expected']['debriefs'])
        for plane, expected in zip(state['aircraft'], data['expected']['aircraft']):
            for key, value in expected.items():
                self.assertEqual(plane[key], value, key)
        for key in ['supplies', 'parts', 'score', 'operation', 'messages']:
            self.assertEqual(state[key], data['expected'][key], key)
        migrated = copy.deepcopy(state)
        migrate_campaign(state)
        self.assertEqual(state, migrated)

    def test_store_upgrades_save_and_rejects_old_form(self):
        with tempfile.TemporaryDirectory() as temp:
            store = CampaignStore(temp + '/test.db')
            fixture = self.fixture()['saved']
            with store.connect() as db:
                db.execute('INSERT INTO campaigns VALUES (?, ?)', ('old', json.dumps(fixture)))
            with self.assertRaises(RuleError):
                store.transact('old', 1030, lambda s, n: requisition(s, None, n), 0)
            state = store.transact('old', 1030)
            self.assertEqual(state['schema'], 2)
            self.assertEqual(state['revision'], 1)
            self.assertEqual(len(state['aircraft']), 6)

    def test_unknown_schema_is_not_silently_overwritten(self):
        state = new_campaign(1)
        state['schema'] = 999
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            migrate_campaign(state)
        self.assertEqual(before, state)


class ContentHTTPTests(unittest.TestCase):
    def test_length_choices_ground_decision_and_histories_render(self):
        with tempfile.TemporaryDirectory() as temp:
            app = create_app({'TESTING': True, 'SECRET_KEY': 'test', 'DATABASE': temp + '/test.db', 'NOW': lambda: 1000})
            client = app.test_client()
            self.assertEqual(client.get('/').status_code, 200)
            with client.session_transaction() as session:
                identity, csrf = session['campaign_id'], session['csrf']
            page = client.post('/command/tour-length', data={'csrf': csrf, 'revision': 0, 'length': 7}, follow_redirects=True)
            self.assertIn(b'/ 35 goal', page.data)
            store = app.extensions['campaign_store']
            state = store.transact(identity, 1000)
            def seed(s, now):
                s['operation'] = 5
                for n in range(100):
                    s['seed'] = n
                    s['decision'] = ground_situation(s)
                    if s['decision']:
                        break
                s['aircraft'][0]['history'] = [{'operation': 3, 'text': 'Three sorties home.'}]
            state = store.transact(identity, 1000, seed, state['revision'])
            page = client.get('/')
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'AT THE AIRFIELD', page.data)
            self.assertIn(b'Crew service record', page.data)
            page = client.post('/command/ground-choice', data={'csrf': csrf, 'revision': state['revision'], 'decision': state['decision']['id'], 'choice': 'decline'}, follow_redirects=True)
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'Decisions that shaped this tour', page.data)


if __name__ == '__main__':
    unittest.main()
