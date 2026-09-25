"""Synchronous one-step RPC to an owned emulator, reachable only through SSH."""
import base64
import http.client
import json
from urllib.parse import urlsplit
from .contracts import Action, Sample


class RemoteProfile:
    def __init__(self,url):
        u=urlsplit(url)
        if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost') or u.path not in ('','/'):
            raise ValueError('loopback_ssh_tunnel_required')
        self.connection=http.client.HTTPConnection(u.hostname,u.port,timeout=20)
        self.seq=0
        info=self.rpc('claim',{})
        self.metadata=info['metadata']
        if (self.metadata.get('action_program_contract')!='segments-v1' or
                self.metadata.get('intent_contract')!='ordered-goals-v1'):
            self.connection.close()
            raise ValueError('remote_profile_contract_mismatch')
        self.metadata['transport']='owned_emulator_over_ssh_loopback_rpc'
        self.skills=info['skills'];self.metric_names=set(info['metric_names'])
        self.actions=[Action.from_json(a).validate() for a in info['actions']]
        self.bootstrap_frames=info['bootstrap_frames']
        self.set_sample(info['sample'])

    def rpc(self,method,params):
        # Deliberately no reconnect/retry: a lost step reply is uncertain execution.
        seq=self.seq;self.seq+=1
        body=json.dumps({'seq':seq,'method':method,'params':params}).encode()
        self.connection.request('POST','/rpc',body,{'Content-Type':'application/json'})
        response=self.connection.getresponse();data=response.read(4_000_001)
        if response.status!=200 or len(data)>4_000_000: raise RuntimeError('emulator_rpc_failed')
        result=json.loads(data)
        if result['seq']!=seq: raise RuntimeError('emulator_sequence_mismatch')
        return result['result']

    def set_sample(self,data):
        self.views=data.pop('views');self.eligibility=data.pop('eligibility')
        for k in ('image','memory'):
            if data.get(k) is not None: data[k]=base64.b64decode(data[k],validate=True)
        self.current=Sample(**data)
        return self.current

    def observe(self): return self.current
    def advance(self,buttons): return self.set_sample(self.rpc('advance',{'buttons':list(buttons)}))
    def checkpoint(self): return base64.b64decode(self.rpc('checkpoint',{})['data'],validate=True)
    def view(self,sample,role): return self.views[role]
    def eligible(self,action,sample): return tuple(self.eligibility[action.id])
    def close(self):
        try: self.rpc('close',{})
        finally: self.connection.close()
