import copy
import json
import unittest
import test_adapter as fixtures
from session_adapter.backends import Scripted
from session_adapter.engine import Schedule
from session_adapter.profiles.fixture import Fixture
from session_adapter.recording import verify_links


def singleton_plan(wire, raw):
    raw['value'].update(review_after_frames=6)
    return raw


class NeverCalled(Scripted):
    def prepare(self, *args):
        raise AssertionError('singleton must not call a controller')


class SingletonTests(unittest.TestCase):
    setUp = fixtures.AdapterTests.setUp
    tearDown = fixtures.AdapterTests.tearDown
    attempt = fixtures.AdapterTests.attempt

    def run_singleton(self, profile=None):
        profile=profile or Fixture(goal=121,hazard_at=999)
        profile.actions=[a for a in profile.actions if a.id=='right_6']
        return self.attempt(profile,
            brain=fixtures.Override(singleton_plan),controller=NeverCalled(),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=60))

    def test_singleton_never_claims_a_model_choice(self):
        s=self.run_singleton()
        self.assertEqual(s.metadata['calls']['controller'],0)
        self.assertEqual(s.metadata['stop_reason'],'complete')
        self.assertEqual([e['frame'] for e in s.events if e['kind']=='plan.installed'],[0,60,120])
        ds=[e for e in s.events if e['kind']=='decision.selected']
        self.assertEqual(s.metadata['singleton_contract_executions'],len(ds))
        for d in ds:
            self.assertIsNone(d['model_choice']);self.assertIsNone(d['call_id'])
            self.assertEqual(d['selection_source'],'singleton_contract_no_model_choice')
            self.assertEqual(d['executor_choice'],'right_6')
        self.assertFalse((s.root/'calls/controller-00001').exists())

    def test_singleton_still_stops_on_first_death(self):
        s=self.run_singleton(Fixture(death_at=15))
        self.assertEqual(s.frame,15)
        self.assertEqual(s.metadata['stop_reason'],'death')

    def test_singleton_audit_rejects_fake_choice(self):
        s=self.run_singleton(Fixture(goal=7))
        rows=copy.deepcopy(s.events)
        next(e for e in rows if e['kind']=='decision.selected')['executor_choice']='left_6'
        with self.assertRaisesRegex(ValueError,'invalid_singleton_contract_selection'):
            verify_links(rows,s.metadata,json.loads((s.root/'checksums.json').read_text()))

    def test_multicandidate_still_calls_controller(self):
        s=self.attempt(Fixture(goal=31,hazard_at=999),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=60))
        self.assertGreater(s.metadata['calls']['controller'],0)
        self.assertEqual(s.metadata['singleton_contract_executions'],0)
