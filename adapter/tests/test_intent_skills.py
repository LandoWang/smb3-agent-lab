import copy
import json
from pathlib import Path
import unittest
import test_adapter as fixtures
from session_adapter.backends import Scripted, HTTPBackend
from session_adapter.contracts import Action, Segment, Sample, PLAN_SCHEMA, ContractError, offer, validate_plan
from session_adapter.engine import Schedule
from session_adapter.intent_queue import IntentQueue
from session_adapter.local_context import compact, describe_action
from session_adapter.profiles.fixture import Fixture
from session_adapter.profiles.smb3_skills import ACTIONS, SKILLS, eligible
from session_adapter.recording import verify_links

ROOT=Path(__file__).resolve().parents[1]


def stage(id='near',kind='reach_region',x=5):
    return {'id':id,'kind':kind,'objective':'Reach the next platform' if kind=='reach_region' else kind,
        'guidance':'Survival first; retreat if useful','target':'observed target or explicit synthetic test',
        'region':{'x_min':x,'x_max':x+5,'y_min':-100,'y_max':100} if kind=='reach_region' else None,
        'grounded':False if kind=='reach_region' else None}


def plan(stages=None):
    return {'objective':'Near-to-far goals','guidance':'Avoid enemies throughout; movement choices remain local',
        'rationale':'Synthetic protocol test, not a Mario/model result','review_after_frames':60,
        'stages':stages or [stage(kind='custom')],'milestones':[]}


class FixedBrain(Scripted):
    def __init__(self,p=None): self.plan=p or plan()
    def invoke(self,wire,timeout,emit): return {'value':copy.deepcopy(self.plan)}


class Choose(Scripted):
    def __init__(self,choice): self.choice=choice
    def invoke(self,wire,timeout,emit): return {'value':{'choice':self.choice}}


class MotorFixture(Fixture):
    skills=SKILLS;actions=ACTIONS
    metric_names=Fixture.metric_names|{'a_held_frames'}
    eligible=staticmethod(eligible)
    def _sample(self,events):
        sample=super()._sample(events)
        sample.metrics['a_held_frames']=self.a_held
        sample.state['valid_for_decisions']=not bool(sample.terminal)
        return sample


class IntentTests(unittest.TestCase):
    def test_schema_is_strict_and_has_no_motor_permissions(self):
        def visit(node):
            if isinstance(node,dict):
                if node.get('type')=='object' or node.get('type')==['object','null']:
                    self.assertFalse(node['additionalProperties'])
                    self.assertEqual(set(node['properties']),set(node['required']))
                for value in node.values(): visit(value)
            elif isinstance(node,list):
                for value in node: visit(value)
        visit(PLAN_SCHEMA)
        self.assertNotIn('allowed_skills',PLAN_SCHEMA['properties'])
        self.assertNotIn('max_frames',PLAN_SCHEMA['properties'])

    def test_queue_keeps_order_and_unknown_events_unverified(self):
        p=plan([stage('block','hit_block'),stage('item','collect_item'),stage('far',x=10)])
        q=IntentQueue(p,Fixture().metadata)
        sample=Sample({}, {'x':12,'y':0,'airborne':True})
        self.assertEqual(q.update(sample,40),[])
        state=q.snapshot()
        self.assertEqual(state['current']['id'],'block')
        self.assertEqual([s['id'] for s in state['upcoming']],['item','far'])
        self.assertEqual(state['stages'][0]['status'],'unverified')
        self.assertEqual(state['stages'][2]['status'],'queued')

    def test_region_verification_advances_only_current_stage(self):
        q=IntentQueue(plan([stage('near',x=5),stage('item','collect_item')]),Fixture().metadata)
        sample=Sample({}, {'x':7,'y':0,'airborne':True})
        self.assertEqual(q.update(sample,3)[0]['stage_id'],'near')
        self.assertEqual(q.snapshot()['current']['id'],'item')
        self.assertFalse(q.snapshot()['all_stages_verified'])

    def test_removing_unverified_goal_is_not_completion(self):
        old=IntentQueue(plan([stage('block','hit_block')]),Fixture().metadata)
        new=IntentQueue(plan([stage('far',x=10)]),Fixture().metadata,old)
        self.assertEqual(new.revisions[0]['prior_status'],'unverified')
        self.assertFalse(new.completed)

    def test_same_verified_stage_keeps_evidence_across_replan(self):
        p=plan([stage('near',x=5),stage('item','collect_item')]);meta=Fixture().metadata
        old=IntentQueue(p,meta);old.update(Sample({}, {'x':7,'y':0,'airborne':True}),3)
        new=IntentQueue(p,meta,old)
        new.update(Sample({}, {'x':90,'y':0,'airborne':True}),60)
        self.assertEqual(new.snapshot()['current']['id'],'item')
        self.assertEqual(new.completed['near']['frame'],3)

    def test_unknown_kind_and_bad_region_rejected(self):
        p=plan([stage(kind='teleport')])
        with self.assertRaises(ContractError): validate_plan(p,Fixture())
        p=plan([stage()]);p['stages'][0]['region']['x_max']=-10
        with self.assertRaises(ContractError): validate_plan(p,Fixture())

    def test_goals_and_words_cannot_remove_left_actions(self):
        profile=MotorFixture();sample=profile.observe()
        a,_=offer(profile,sample,plan())
        adversarial=plan();adversarial.update(allowed_skills=['run_right'],max_frames=1)
        adversarial['guidance']='Only go right, never go left'
        b,_=offer(profile,sample,adversarial)
        self.assertEqual(a,b)
        self.assertIn('run_left_12',[x.id for x in b])

    def test_grounded_held_jump_keeps_release_and_recovery_candidates(self):
        # Synthetic equivalent of the held-A eligibility condition, not a RAM replay.
        sample=Sample({'valid_for_decisions':True}, {'airborne':False,'a_held_frames':59})
        profile=MotorFixture()
        offered,excluded=offer(profile,sample,plan())
        names={a.id for a in offered}
        self.assertTrue({'run_left_6','run_right_6','release_6','runup_jump_right_24'}<=names)
        self.assertNotIn('running_jump_right_6',names)
        self.assertTrue(all(e['reason']!='brain_skill_contract' for e in excluded))

    def test_all_action_sequences_roundtrip_and_fit_frontend(self):
        self.assertEqual(len(ACTIONS),22)
        self.assertLessEqual(len(ACTIONS),26)
        for a in ACTIONS:
            self.assertEqual(Action.from_json(json.loads(json.dumps(a.json()))).validate(),a)
            text=describe_action(a.json())
            for part in a.program(): self.assertIn(f'{part.frames}f',text)

    def test_airborne_candidates_retain_corrections_and_release(self):
        profile=MotorFixture();sample=profile.observe();sample.metrics['airborne']=True
        offered,_=offer(profile,sample,plan())
        names={a.id for a in offered}
        self.assertTrue({'move_left_6','move_right_6','release_6','jump_left_12','run_left_12'}<=names)
        self.assertNotIn('runup_jump_right_24',names)

    def test_bad_program_is_rejected(self):
        with self.assertRaises(ContractError):
            Action('bad','x',(),12,segments=(Segment('x',(),6),)).validate()

    def test_initial_unknown_jump_hold_does_not_break_claim(self):
        profile=MotorFixture();sample=profile.observe();sample.metrics['a_held_frames']=None
        offered,excluded=offer(profile,sample,plan())
        self.assertIn('release_6',[a.id for a in offered])
        self.assertNotIn('jump_up_6',[a.id for a in offered])
        self.assertTrue(excluded)

    def test_compact_controller_keeps_current_future_and_global_guidance(self):
        p=plan([stage('block','hit_block'),stage('item','collect_item'),stage('far',x=100)])
        q=IntentQueue(p,Fixture().metadata)
        c={'plan':p,'intent_progress':q.snapshot(),'recent_trajectory':[]}
        out=compact(c)
        self.assertEqual(out['plan']['guidance'],p['guidance'])
        self.assertEqual(out['intent_progress']['current']['id'],'block')
        self.assertEqual([s['id'] for s in out['intent_progress']['upcoming']],['item','far'])
        self.assertNotIn('rationale',out['plan'])
        self.assertIn('rationale',c['plan'])


class MotorExecutionTests(unittest.TestCase):
    setUp=fixtures.AdapterTests.setUp
    tearDown=fixtures.AdapterTests.tearDown
    attempt=fixtures.AdapterTests.attempt

    def run_macro(self,profile=None,brain=None,schedule=None):
        return self.attempt(profile or MotorFixture(goal=999,hazard_at=999),brain or FixedBrain(),
            Choose('runup_jump_right_24'),schedule or Schedule(brain_min_frames=60,brain_every_frames=60,max_decisions=1))

    def test_macro_executes_exact_three_phase_inputs(self):
        s=self.run_macro()
        frames=[r for r in s.events if r['kind']=='frame.executed']
        self.assertEqual([r['input_buttons'] for r in frames],
            [['RIGHT','B']]*6+[['RIGHT','A','B']]*12+[['RIGHT','B']]*6)
        x=next(e for e in s.events if e['kind']=='execution.completed')
        self.assertEqual([p['executed_frames'] for p in x['executed_segments']],[6,12,6])
        self.assertEqual(x['discarded_remaining_frames'],0)
        self.assertIsNone(x['buttons'])

    def test_takeoff_guard_rechecks_after_runup(self):
        class Falling(MotorFixture):
            def advance(self,buttons):
                sample=super().advance(buttons)
                if self.frame>=5: sample.metrics['airborne']=True
                return sample
        s=self.run_macro(Falling(goal=999,hazard_at=999))
        x=next(e for e in s.events if e['kind']=='execution.completed')
        self.assertEqual(s.frame,6)
        self.assertEqual(x['interruption'],'segment_precondition_failed')
        self.assertEqual(x['discarded_remaining_frames'],18)
        self.assertTrue(all('A' not in e['input_buttons'] for e in s.events if e['kind']=='frame.executed'))

    def test_death_interrupts_without_executing_tail(self):
        s=self.run_macro(MotorFixture(death_at=9,hazard_at=999))
        self.assertEqual(s.frame,9)
        self.assertEqual(s.metadata['stop_reason'],'death')
        x=next(e for e in s.events if e['kind']=='execution.completed')
        self.assertEqual(x['discarded_remaining_frames'],15)

    def test_cadence_can_cut_macro_before_jump(self):
        s=self.run_macro(schedule=Schedule(brain_min_frames=5,brain_every_frames=5,max_decisions=1))
        x=next(e for e in s.events if e['kind']=='execution.completed')
        self.assertEqual(s.frame,5);self.assertEqual(x['interruption'],'brain_cadence')
        self.assertEqual(x['discarded_remaining_frames'],19)

    def test_stage_transition_returns_to_controller_not_brain(self):
        target=stage('near',x=3);target['grounded']=True
        p=plan([target,stage('block','hit_block')])
        s=self.run_macro(brain=FixedBrain(p),schedule=Schedule(brain_min_frames=60,brain_every_frames=60,max_decisions=2))
        xs=[e for e in s.events if e['kind']=='execution.completed']
        self.assertEqual(xs[0]['frame_end'],3)
        self.assertEqual(xs[0]['interruption'],'intent_stage_boundary')
        self.assertEqual(s.metadata['calls']['brain'],1)
        request=json.loads((s.root/'calls/controller-00002/request.json').read_text())
        self.assertEqual(request['context']['intent_progress']['current']['id'],'block')

    def test_segment_tampering_rejected_by_audit(self):
        s=self.run_macro();rows=copy.deepcopy(s.events)
        next(e for e in rows if e['kind']=='frame.executed' and e['frame']==7)['input_buttons']=['RIGHT','B']
        with self.assertRaisesRegex(ValueError,'executed_input_link'):
            verify_links(rows,s.metadata,json.loads((s.root/'checksums.json').read_text()))
