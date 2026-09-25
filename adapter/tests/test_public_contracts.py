"""Public packaging/context regressions: synthetic inputs, no services."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from session_adapter.__main__ import run
from session_adapter.backends import HTTPBackend
from session_adapter.contracts import ContractError
from session_adapter.local_context import trim_audit_fields
from session_adapter.profiles.fixture import Fixture
from session_adapter.recording import verify


class PublicContracts(unittest.TestCase):
    def test_trim_preserves_decision_fields_without_mutating_input(self):
        value = {'session_id':'synthetic', 'observation_id':'o1', 'frame':12,
            'observation':{'player':{'vx':2.5}, 'hazards':[{'x':64}]},
            'plan':{'objective':'Land safely', 'guidance':'Brake before edge'},
            'intent_progress':{'current':{'id':'near'}, 'upcoming':[{'id':'far'}], 'stages':[{'id':'done'}]},
            'recent_trajectory':[{'frame':11,'x':20}], 'previous_buttons':['RIGHT','A'],
            'plan_schedule':{'next_review_frame':60},
            'execution_feedback':{'executed_segments':[{'buttons':['RIGHT','A'],'executed_frames':6}],
                                  'interruption':None, 'after':{'x':24}, 'reward':6}}
        before=copy.deepcopy(value);out=trim_audit_fields(value)
        self.assertEqual(value,before)
        for field in ('frame','observation','plan','recent_trajectory','previous_buttons','plan_schedule'):
            self.assertEqual(out[field],value[field])
        for field in ('current','upcoming'):
            self.assertEqual(out['intent_progress'][field],value['intent_progress'][field])
        self.assertEqual(out['execution_feedback']['executed_segments'],value['execution_feedback']['executed_segments'])
        self.assertNotIn('session_id',out)
        self.assertNotIn('after',out['execution_feedback'])

    def test_jev_and_local_keep_same_action_criteria(self):
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'provider.txt'
            config.write_text('OPENROUTER_API_KEY=synthetic-not-a-real-key\n')
            jev=HTTPBackend('openrouter_jev',private_config=config)
            local=HTTPBackend('local_diffusiongemma',endpoint='http://localhost:1/v1/systemone')
            context={'session_id':'synthetic','recent_trajectory':[],'candidates':[
                {'id':'left','buttons':['LEFT'],'frames':6,'description':'Brake to left'},
                {'id':'release','buttons':[],'frames':6,'description':'Release A; inertia remains'}]}
            a,b=jev.prepare('controller',context,{}),local.prepare('controller',context,{})
            self.assertEqual(a['questions'],b['questions'])
            self.assertEqual(set(a['questions']['action']['criteria']),{'left','release'})
            self.assertNotIn('samples',a)
            self.assertIn('session_id',a)

    def test_oversized_local_request_never_reaches_inference(self):
        backend=HTTPBackend('local_diffusiongemma',endpoint='http://localhost:1/v1/systemone',
                            token_endpoint='http://localhost:2/tokenize',reserve_tokens=16)
        requests=[]
        class Opener:
            def open(self,request,timeout):
                requests.append(request if isinstance(request,str) else request.full_url)
                if len(requests)==1:
                    value={'backend':'local_diffusiongemma','model_revision':'synthetic-revision'}
                elif len(requests)==2: value={'count':120,'max_model_len':128}
                else: raise AssertionError('Inference must not be called')
                return io.BytesIO(json.dumps(value).encode())
        wire={'state':'synthetic','questions':{'action':{'type':'choice','instructions':'Choose',
            'criteria':{'left':'LEFT 6f','release':'RELEASE 6f'}}}}
        with patch('session_adapter.backends.urllib.request.build_opener',return_value=Opener()):
            with self.assertRaises(ContractError): backend.invoke(wire,5,lambda _:None)
        self.assertEqual(len(requests),2)

    def test_remote_cli_has_no_private_sibling_source_dependency(self):
        config={'profile':{'kind':'remote','endpoint_env':'TEST_ADAPTER_ENDPOINT'},
                'brain':{'kind':'scripted_fixture'},'controller':{'kind':'scripted_fixture'},
                'schedule':{'max_frames':12}}
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'TEST_ADAPTER_ENDPOINT':'http://127.0.0.1:1'}):
                with patch('session_adapter.remote_profile.RemoteProfile',return_value=Fixture()) as remote:
                    root=run(config,Path(folder).resolve(),allow_live=True)
            self.assertEqual(verify(root)['frames'],12)
            remote.assert_called_once_with('http://127.0.0.1:1')
            self.assertFalse((root/'code/pinned_legacy').exists())

    def test_live_opt_in_required_before_remote_claim(self):
        config={'profile':{'kind':'remote','endpoint_env':'TEST_ADAPTER_ENDPOINT'},
                'brain':{'kind':'scripted_fixture'},'controller':{'kind':'scripted_fixture'}}
        with patch('session_adapter.remote_profile.RemoteProfile') as remote:
            with self.assertRaisesRegex(ValueError,'live_requires_explicit_flag'):
                run(config,'unused-not-created')
        remote.assert_not_called()

    def test_service_limit_and_model_alias_are_used_without_upstream_url_logging(self):
        backend=HTTPBackend('local_diffusiongemma',model='synthetic-alias',
            endpoint='http://localhost:1/v1/systemone',token_endpoint='http://localhost:2/tokenize',
            reserve_tokens=16,expected_revision='synthetic-revision')
        requests=[];events=[]
        class Opener:
            def open(self,request,timeout):
                requests.append(request)
                if len(requests)==1:
                    value={'backend':'local_diffusiongemma','model_revision':'synthetic-revision',
                           'vllm_base':'https://example.invalid/private-upstream'}
                elif len(requests)==2:
                    assert json.loads(request.data)['model']=='synthetic-alias'
                    value={'count':200,'max_model_len':256}
                else: value={'model':'synthetic-alias','answers':{}}
                return io.BytesIO(json.dumps(value).encode())
        wire={'state':'synthetic','questions':{'action':{'type':'choice','instructions':'Choose',
            'criteria':{'left':'LEFT 6f','release':'RELEASE 6f'}}}}
        with patch('session_adapter.backends.urllib.request.build_opener',return_value=Opener()):
            result=backend.invoke(wire,5,events.append)
        self.assertEqual(len(requests),3)
        self.assertEqual(result['model'],'synthetic-alias')
        self.assertNotIn('private-upstream',json.dumps(events))
        self.assertEqual(events[-1]['max_model_len'],256)

    def test_optional_revision_mismatch_stops_before_tokenizer_or_inference(self):
        backend=HTTPBackend('local_diffusiongemma',endpoint='http://localhost:1/v1/systemone',
            token_endpoint='http://localhost:2/tokenize',expected_revision='expected-synthetic')
        class Opener:
            def open(self,request,timeout):
                if not isinstance(request,str): raise AssertionError('Must fail at provenance')
                return io.BytesIO(b'{"backend":"local_diffusiongemma","model_revision":"different"}')
        with patch('session_adapter.backends.urllib.request.build_opener',return_value=Opener()):
            with self.assertRaisesRegex(ContractError,'local_provenance_mismatch'):
                backend.invoke({},5,lambda _:None)
