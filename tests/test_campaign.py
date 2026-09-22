import copy
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest

from app import create_app
from game_engine import (RuleError, advance, availability, dispatch, effectiveness,
                         next_event, requisition, stand_down, start_job)
from models import briefing, new_campaign
from storage import CampaignStore


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.state = new_campaign(1234)

    def fly(self, state=None, planes=None):
        state = self.state if state is None else state
        dispatch(state, 'priority', planes or ['a1', 'a2', 'a3'], 1000)
        advance(state, state['active']['returns'])

    def test_six_aircraft_can_expand_to_eight(self):
        self.assertEqual(len(self.state['aircraft']), 6)
        requisition(self.state, None, 0)
        requisition(self.state, None, 0)
        self.assertEqual(len(self.state['aircraft']), 8)
        self.state['parts'] = 20
        with self.assertRaises(RuleError):
            requisition(self.state, None, 0)

    def test_duplicate_aircraft_rejected_without_spending(self):
        before = copy.deepcopy(self.state)
        with self.assertRaises(RuleError):
            dispatch(self.state, 'priority', ['a1', 'a1'], 0)
        self.assertEqual(before, self.state)

    def test_unaffordable_and_unknown_orders_rejected(self):
        self.state['supplies'] = 0
        for target, planes in [('priority', ['a1']), ('bad', ['a1']), ('priority', ['bad'])]:
            with self.assertRaises(RuleError):
                dispatch(self.state, target, planes, 0)

    def test_no_double_dispatch_or_midair_maintenance(self):
        dispatch(self.state, 'priority', ['a1'], 0)
        for action in [lambda: dispatch(self.state, 'support', ['a2'], 1),
                       lambda: start_job(self.state, 'a1', 'repair', 1),
                       lambda: start_job(self.state, 'a1', 'rest', 1),
                       lambda: stand_down(self.state, 1)]:
            with self.assertRaises(RuleError):
                action()

    def test_grounded_aircraft_and_exhausted_crews_cannot_dispatch(self):
        for condition, fatigue in [(54, 0), (100, 85)]:
            self.state['aircraft'][0].update(condition=condition, fatigue=fatigue)
            with self.assertRaises(RuleError):
                dispatch(self.state, 'priority', ['a1'], 0)

    def test_frequent_checks_equal_offline_catchup_with_ground_work(self):
        start_job(self.state, 'a5', 'repair', 1000)
        start_job(self.state, 'a6', 'rest', 1000)
        self.state['operation'] = 2
        dispatch(self.state, 'priority', ['a1', 'a2', 'a3'], 1000)
        frequent = copy.deepcopy(self.state)
        for now in range(1000, 20000, 13):
            advance(frequent, now)
        advance(self.state, 20000)
        advance(frequent, 20000)
        self.assertEqual(self.state, frequent)

    def test_completed_mission_is_idempotent(self):
        self.fly()
        before = copy.deepcopy(self.state)
        advance(self.state, 10 ** 10)
        self.assertEqual(self.state, before)

    def test_maintenance_has_capacity_cost_and_duration(self):
        start_job(self.state, 'a5', 'repair', 0)
        self.assertEqual(self.state['parts'], 6)
        start_job(self.state, 'a2', 'repair', 1)
        self.assertEqual(self.state['aircraft'][1]['job']['starts'], 2700)
        self.assertEqual(self.state['aircraft'][1]['job']['due'], 5400)
        advance(self.state, 2699)
        self.assertEqual(self.state['aircraft'][4]['condition'], 62)
        advance(self.state, 2700)
        self.assertEqual(self.state['aircraft'][4]['condition'], 100)
        self.assertIsNone(self.state['aircraft'][4]['job'])

    def test_waiting_does_not_create_resources_or_clear_unassigned_fatigue(self):
        before = copy.deepcopy(self.state)
        advance(self.state, 10 ** 10)
        self.assertEqual(before, self.state)
        self.assertEqual(briefing(self.state), briefing(before))

    def test_crew_recovery_is_explicit(self):
        start_job(self.state, 'a6', 'rest', 0)
        self.assertEqual(self.state['supplies'], 17)
        advance(self.state, 2700)
        self.assertEqual(self.state['aircraft'][5]['fatigue'], 5)

    def test_unused_crews_recover_and_mission_carries_consequences(self):
        self.fly()
        self.assertEqual(self.state['aircraft'][3]['fatigue'], 23)
        self.assertGreater(self.state['aircraft'][0]['fatigue'], 22)
        self.assertLess(self.state['aircraft'][0]['condition'], 100)
        self.assertEqual(len(self.state['debriefs']), 1)

    def test_cloud_and_fatigue_change_formation_strength(self):
        target = briefing(self.state)[0]
        plane = self.state['aircraft'][0]
        target['weather'] = 'Clear'
        clear = effectiveness(plane, target)
        target['weather'] = 'Overcast'
        self.assertLess(effectiveness(plane, target), clear)
        original = effectiveness(plane, target)
        plane['fatigue'] = 80
        self.assertLess(effectiveness(plane, target), original)

    def test_autonomous_abort_occurs_without_a_command(self):
        found = False
        for seed in range(100):
            state = new_campaign(seed)
            state['aircraft'][0].update(condition=55, fatigue=60)
            self.fly(state, ['a1'])
            result = state['debriefs'][-1]['results'][0]
            if result['aborted']:
                self.assertEqual(result['status'], 'Returned early')
                self.assertEqual(result['contribution'], 0)
                found = True
                break
        self.assertTrue(found)

    def test_stand_down_is_a_finite_recovery_path(self):
        self.state['supplies'] = 0
        stand_down(self.state, 0)
        self.assertEqual(self.state['supplies'], 4)
        self.assertEqual(self.state['operation'], 2)
        self.assertEqual(self.state['score'], 0)
        for _ in range(self.state["length"] - 1):
            stand_down(self.state, 1)
        self.assertTrue(self.state['completed'])
        with self.assertRaises(RuleError):
            stand_down(self.state, 2)
        with self.assertRaises(RuleError):
            dispatch(self.state, 'support', ['a1'], 2)

    def test_replacement_keeps_slot_and_historical_report(self):
        self.fly()
        report = copy.deepcopy(self.state['debriefs'])
        self.state['aircraft'][0]['lost'] = True
        self.state['aircraft'][0]['crew_fate'] = 'missing'
        requisition(self.state, 'a1', 2000)
        self.assertEqual(len(self.state['aircraft']), 6)
        self.assertFalse(self.state['aircraft'][0]['lost'])
        self.assertEqual(self.state['aircraft'][0]['skill'], .65)
        self.assertEqual(self.state['debriefs'], report)


class PersistenceAndHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.config = {'TESTING': True, 'SECRET_KEY': 'unit-test-key',
                       'DATABASE': self.temp.name + '/state.db', 'NOW': lambda: self.now}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.client.get('/')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
            self.identity = session['campaign_id']

    def tearDown(self):
        self.temp.cleanup()

    def state(self):
        return self.app.extensions['campaign_store'].transact(self.identity, self.now)

    def post(self, command, **data):
        data.setdefault('revision', self.state()['revision'])
        return self.client.post('/command/' + command, data={'csrf': self.csrf, **data}, follow_redirects=True)

    def test_home_renders_six_aircraft_and_operational_choices(self):
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Lucky Penny', page.data)
        self.assertIn(b'Old Reliable', page.data)
        self.assertIn(b'Prototype', page.data.replace(b'PROTOTYPE', b'Prototype'))
        self.assertNotIn(b'EXECUTE TURN', page.data)

    def test_full_dispatch_report_debrief_loop(self):
        page = self.post('dispatch', mission='priority', aircraft=['a1', 'a2', 'a3'])
        self.assertIn(b'FORMATION AIRBORNE', page.data)
        self.assertNotIn(b'id="dispatch-form"', page.data)
        self.assertIsNotNone(self.state()['active'])
        for _ in range(3):
            page = self.post('advance')
        self.assertIsNone(self.state()['active'])
        self.assertEqual(self.state()['operation'], 2)
        self.assertIn(b'LATEST DEBRIEF', page.data)
        self.assertIn(b'id="dispatch-form"', page.data)
        self.assertIn(b'Read the crew reports', page.data)

    def test_restart_preserves_save_and_same_browser_identity(self):
        self.post('dispatch', mission='support', aircraft=['a1', 'a2'])
        cookie = self.client.get_cookie('session')
        self.now += 200
        restarted = create_app(self.config).test_client()
        restarted.set_cookie('session', cookie.value)
        page = restarted.get('/')
        self.assertIn(b'LATEST DEBRIEF', page.data)
        self.assertEqual(self.state()['operation'], 2)

    def test_stale_and_duplicate_post_cannot_dispatch_twice(self):
        revision = self.state()['revision']
        self.post('dispatch', mission='priority', aircraft=['a1'], revision=revision)
        before = self.state()
        page = self.post('dispatch', mission='priority', aircraft=['a2'], revision=revision)
        self.assertEqual(self.state(), before)
        self.assertIn(b'airfield has changed', page.data)

    def test_concurrent_dispatch_only_spends_once(self):
        store = self.app.extensions['campaign_store']
        revision = self.state()['revision']
        def submit(pid):
            try:
                store.transact(self.identity, self.now, lambda s, n: dispatch(s, 'priority', [pid], n), revision)
                return True
            except RuleError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ['a1', 'a2']))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.state()['supplies'], 16)

    def test_failed_command_rolls_back_transaction(self):
        store = self.app.extensions['campaign_store']
        before = self.state()
        def fail(state, now):
            state['supplies'] = 0
            raise RuleError('failure')
        with self.assertRaises(RuleError):
            store.transact(self.identity, self.now, fail, before['revision'])
        self.assertEqual(self.state(), before)

    def test_csrf_and_get_cannot_mutate(self):
        before = self.state()
        self.assertEqual(self.client.post('/command/reset', data={'csrf': 'wrong'}).status_code, 400)
        self.assertEqual(self.client.get('/command/reset').status_code, 405)
        self.assertEqual(self.state(), before)

    def test_clients_have_separate_campaigns(self):
        other = self.app.test_client()
        other.get('/')
        with other.session_transaction() as session:
            self.assertNotEqual(session['campaign_id'], self.identity)
        self.post('requisition')
        self.assertEqual(len(self.state()['aircraft']), 7)
        self.assertNotIn(b'Extra Trouble', other.get('/').data)

    def test_disabled_fast_forward_cannot_be_bypassed(self):
        self.app.config['ALLOW_FAST_FORWARD'] = False
        self.post('dispatch', mission='priority', aircraft=['a1'])
        before = self.state()
        page = self.post('advance')
        self.assertEqual(self.state(), before)
        self.assertIn(b'Fast-forward is disabled', page.data)

    def test_reset_invalidates_old_forms(self):
        old_revision = self.state()['revision']
        self.post('reset')
        page = self.post('requisition', revision=old_revision)
        self.assertIn(b'airfield has changed', page.data)
        self.assertEqual(len(self.state()['aircraft']), 6)

    def test_completed_tour_renders_and_retains_archive(self):
        for _ in range(self.state()["length"]):
            page = self.post('stand-down')
        self.assertIn(b'The tour is complete', page.data)
        self.assertNotIn(b'id="dispatch-form"', page.data)
        self.assertEqual(len(self.state()['debriefs']), self.state()['length'])


if __name__ == '__main__':
    unittest.main()
