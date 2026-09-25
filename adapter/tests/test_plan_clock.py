import json
import unittest
from unittest.mock import patch
from session_adapter.engine import Schedule
from session_adapter.plan_clock import PlanClock
from session_adapter.profiles.fixture import Fixture
import test_adapter as fixtures
Override=fixtures.Override


def short_plan(wire,raw):
    raw['value']['review_after_frames']=6
    return raw


class CadenceTests(unittest.TestCase):
    setUp=fixtures.AdapterTests.setUp
    tearDown=fixtures.AdapterTests.tearDown
    attempt=fixtures.AdapterTests.attempt
    def test_model_cannot_force_six_frame_replans(self):
        s=self.attempt(Fixture(goal=121,hazard_at=999),brain=Override(short_plan),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=120))
        plans=[r for r in s.events if r['kind']=='plan.installed']
        self.assertEqual([r['frame'] for r in plans],[0,60,120])
        self.assertEqual(plans[0]['plan']['review_after_frames'],6)
        self.assertEqual(plans[0]['schedule']['effective_review_after_frames'],60)
        deferred=[r for r in s.events if r['kind']=='replan.requested' and r['deferred']]
        self.assertTrue(deferred)
        self.assertGreater(s.metadata['calls']['controller'],3)

    def test_ordinary_profile_event_waits_for_minimum(self):
        s=self.attempt(Fixture(goal=70,hazard_at=20),brain=Override(short_plan),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=120))
        self.assertEqual([r['frame'] for r in s.events if r['kind']=='plan.installed'],[0,60])
        event=next(r for r in s.events if r['kind']=='replan.requested' and r['reason']=='profile_event')
        self.assertEqual(event['effective_frame'],60)
        self.assertFalse(event['minimum_bypassed'])

    def test_urgent_event_bypasses_and_restarts_clock(self):
        class Urgent(Fixture):
            def advance(self,buttons):
                sample=super().advance(buttons)
                if self.frame==20: sample.events=['observe','urgent_replan','fixture_urgent_test']
                return sample
        s=self.attempt(Urgent(goal=100,hazard_at=999),brain=Override(short_plan),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=120))
        self.assertEqual([r['frame'] for r in s.events if r['kind']=='plan.installed'],[0,20,80])
        event=next(r for r in s.events if r['kind']=='replan.requested' and r['urgent'])
        self.assertTrue(event['minimum_bypassed'])
        self.assertEqual(event['effective_frame'],20)
        self.assertIn('fixture_urgent_test',event['trigger_events'])

    def test_no_extra_frames_after_death_for_cadence(self):
        s=self.attempt(Fixture(death_at=15),brain=Override(short_plan),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=120))
        self.assertEqual(s.frame,15)
        self.assertEqual(s.metadata['calls']['brain'],1)
        self.assertEqual(s.metadata['stop_reason'],'death')

    def test_interval_config_validation(self):
        for value in (-1,True,121):
            with self.assertRaises(ValueError): Schedule(brain_min_frames=value,brain_every_frames=120).validate()
        Schedule(brain_min_frames=0).validate()

    def test_invalid_interval_rejected_before_emulator_claim(self):
        from session_adapter.__main__ import run
        config={'profile':{'kind':'remote_smb3','endpoint_env':'NOT_ACCESSED'},
            'brain':{'kind':'scripted_fixture'},'controller':{'kind':'scripted_fixture'},
            'schedule':{'brain_min_frames':121,'brain_every_frames':120}}
        with patch('session_adapter.__main__.env_path',side_effect=AssertionError('must not touch endpoint')):
            with self.assertRaises(ValueError): run(config,self.root,allow_live=True)

    def test_maximum_period_and_exact_fixed_period(self):
        clock=PlanClock(60,120);clock.install(10,999)
        self.assertEqual(clock.due_frame,130)
        clock=PlanClock(90,90);clock.install(10,6)
        self.assertEqual(clock.due_frame,100)
        self.assertFalse(clock.due(99));self.assertTrue(clock.due(100))

    def test_controller_receives_effective_deadline(self):
        s=self.attempt(Fixture(goal=61,hazard_at=999),brain=Override(short_plan),
            schedule=Schedule(brain_min_frames=60,brain_every_frames=120))
        request=json.loads((s.root/'calls/controller-00001/request.json').read_text())
        self.assertEqual(request['context']['plan_schedule']['next_review_frame'],60)
