"""Ordered intentions; only declared Profile evidence can complete a stage.

The model may revise an unsupported stage at a later plan, but removing it is
recorded as a revision, NEVER retroactively relabeled verified completion.
"""
import copy


class IntentQueue:
    def __init__(self, plan, metadata, previous=None):
        self.stages=copy.deepcopy(plan['stages'])
        self.verifiers=metadata.get('goal_verifiers',{})
        self.completed={}
        self.revisions=[]
        if previous:
            for old in previous.stages:
                matching=next((s for s in self.stages if s==old),None)
                if matching and old['id'] in previous.completed:
                    self.completed[old['id']]=copy.deepcopy(previous.completed[old['id']])
                elif not matching:
                    self.revisions.append({'id':old['id'],'prior_status':
                        'verified' if old['id'] in previous.completed else 'unverified',
                        'change':'planner_removed_or_revised_NOT_completion'})
        self.latest={}

    def evidence(self, stage, sample):
        spec=self.verifiers.get(stage['kind'])
        if not spec or spec.get('method')!='metric_region':
            return {'status':'unverified','reason':'profile_has_no_verified_completion_signal',
                'kind':stage['kind'],'completion_claim':False}
        # Do not let proximity stand in for collecting an item or hitting a block.
        if stage['kind']!='reach_region':
            return {'status':'unverified','reason':'unsupported_verifier_semantics','completion_claim':False}
        region=stage['region'];m=sample.metrics
        x,y=m.get(spec['x_metric']),m.get(spec['y_metric'])
        if type(x) not in (int,float) or type(y) not in (int,float):
            return {'status':'unverified','reason':'missing_position_metrics','completion_claim':False}
        met=region['x_min']<=x<=region['x_max'] and region['y_min']<=y<=region['y_max']
        ground=None
        if stage['grounded'] is not None:
            airborne=m.get(spec['airborne_metric'])
            if type(airborne) is not bool:
                return {'status':'unverified','reason':'missing_airborne_metric','completion_claim':False}
            ground=not airborne
            met=met and ground==stage['grounded']
        return {'status':'verified' if met else 'pending','completion_claim':met,
            'reason':'measured_anchor_in_region_NOT_collision_or_item_verification',
            'observed':{'x':x,'y':y,'grounded':ground},'region':region}

    def update(self, sample, frame):
        events=[]
        if sample.terminal: return events
        for stage in self.stages:
            if stage['id'] in self.completed: continue
            proof=self.evidence(stage,sample)
            self.latest[stage['id']]=proof
            if proof['status']!='verified': break
            proof={**proof,'frame':frame}
            self.completed[stage['id']]=proof
            events.append({'stage_id':stage['id'],'objective':stage['objective'],'evidence':proof})
        return events

    def snapshot(self):
        pending=[s for s in self.stages if s['id'] not in self.completed]
        current=pending[0] if pending else None
        return {'current':copy.deepcopy(current),'upcoming':copy.deepcopy(pending[1:]),
            'stages':[{'id':s['id'],'objective':s['objective'],
                'status':'verified' if s['id'] in self.completed else
                    self.latest.get(s['id'],{}).get('status','pending' if s==current else 'queued'),
                'evidence':copy.deepcopy(self.completed.get(s['id'],self.latest.get(s['id'])))} for s in self.stages],
            'all_stages_verified':not pending,
            'semantics':'intent queue only; all locally executable actions remain available; unverified stages never auto-complete'}
