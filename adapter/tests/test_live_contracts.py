import json
from pathlib import Path
import unittest
from unittest.mock import patch
from session_adapter.backends import HTTPBackend,CodexBackend
from session_adapter.contracts import ContractError
from session_adapter.local_context import compact,messages
from session_adapter.remote_profile import RemoteProfile

ROOT=Path(__file__).resolve().parents[1]

def payload():
    return {'model':'dgemma','state':'{"frame":12}','samples':1,'steps':1,'think':0,'seed':7,
        'questions':{'action':{'type':'choice','instructions':'Survival first',
            'criteria':{'walk':'RIGHT for 6 frames','jump':'RIGHT+A for 12 frames'}}}}

class LiveContracts(unittest.TestCase):
    def test_renderer_fixed_wire_contract(self):
        expected = ('Answer a fixed set of questions about the state the user provides. '
                    'Each question lists its allowed answers; reply with exactly one label '
                    'per question.\n\nQuestion action: Survival first\n'
                    '  A: walk (RIGHT for 6 frames)\n'
                    '  B: jump (RIGHT+A for 12 frames)\n'
                    '\nReply with one line per question, in this order, formatted as "id: label".')
        self.assertEqual(messages(payload()), [
            {'role':'system','content':expected},
            {'role':'user','content':'{"frame":12}'}])

    def test_renderer_candidate_limit_is_fail_closed(self):
        p=payload();p['questions']['action']['criteria']={str(i):'' for i in range(27)}
        with self.assertRaises(ValueError): messages(p)

    def test_projection_is_declared_and_nonmutating(self):
        original={'candidates':[1],'skill_catalog':{},'recent_trajectory':[{'frame':i} for i in range(60)]}
        value=compact(original)
        self.assertEqual(value['recent_trajectory'][-1]['frame'],59)
        self.assertEqual(len(value['recent_trajectory']),4)
        self.assertEqual(value['context_projection']['trajectory_samples_omitted'],56)
        self.assertEqual(len(original['recent_trajectory']),60)

    def test_local_requires_tokenizer_before_inference(self):
        b=HTTPBackend('local_diffusiongemma',endpoint='http://127.0.0.1:1/v1/systemone')
        with self.assertRaises(ContractError): b.invoke(payload(),5,lambda _:None)

    def test_candidate_distribution_must_match_offer(self):
        b=HTTPBackend('local_diffusiongemma',endpoint='http://127.0.0.1:1/v1/systemone')
        b.expected_candidates={'walk','jump'}
        with self.assertRaises(ContractError):
            b.interpret('controller',{'model':'dgemma','answers':{'action':{'choice':'walk','probabilities':{'walk':1}}}})

    def test_remote_nonloopback_is_rejected(self):
        with self.assertRaises(ValueError): RemoteProfile('http://example.com:3090')

    def test_lost_remote_reply_is_not_retried(self):
        class Connection:
            calls=0
            def request(self,*args): self.calls+=1
            def getresponse(self): raise ConnectionError('lost')
        profile=object.__new__(RemoteProfile);profile.connection=Connection();profile.seq=0
        with self.assertRaises(ConnectionError): profile.rpc('advance',{'buttons':['RIGHT']})
        self.assertEqual(profile.connection.calls,1)
        self.assertEqual(profile.seq,1)

    def test_owned_codex_process_disables_tools(self):
        b=CodexBackend('fixture-model',ROOT/'ops/test-not-started')
        for flag in ('features.shell_tool=false','features.apps=false','features.plugins=false',
                     'features.multi_agent=false','features.hooks=false','features.computer_use=false'):
            self.assertIn(flag,b.command)
