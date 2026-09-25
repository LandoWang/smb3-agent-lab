from dataclasses import asdict, dataclass, field
import math
from typing import Protocol


class ContractError(ValueError):
    pass


def integer(value, low=1, high=1_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ContractError("invalid_integer")
    return value


@dataclass(frozen=True)
class Segment:
    name: str
    buttons: tuple[str, ...]
    frames: int
    # Checked against current Profile metrics immediately before this phase.
    requires: tuple[tuple[str, str, float | bool], ...] = ()


@dataclass(frozen=True)
class Action:
    id: str
    skill: str
    buttons: tuple[str, ...]
    frames: int
    label: str = ""
    description: str = ""
    segments: tuple[Segment, ...] = ()

    def json(self):
        return asdict(self)

    @classmethod
    def from_json(cls, value):
        return cls(value['id'],value['skill'],tuple(value['buttons']),value['frames'],
            value.get('label',''),value.get('description',''),
            tuple(Segment(s['name'],tuple(s['buttons']),s['frames'],
                tuple(tuple(c) for c in s.get('requires',()))) for s in value.get('segments',())))

    def program(self):
        return self.segments or (Segment(self.skill,self.buttons,self.frames),)

    def phase(self, offset):
        integer(offset,0,self.frames-1)
        for index, part in enumerate(self.program()):
            if offset < part.frames: return index,part,offset
            offset -= part.frames
        raise ContractError('action_program_length')

    def validate(self):
        integer(self.frames,1,120)
        parts=self.program()
        if not 1<=len(parts)<=8 or sum(p.frames for p in parts)!=self.frames or parts[0].buttons!=self.buttons:
            raise ContractError('action_program_length')
        for part in parts:
            integer(part.frames,1,120)
            if not part.name or len(set(part.buttons))!=len(part.buttons):
                raise ContractError('action_segment')
            for metric,op,value in part.requires:
                if not isinstance(metric,str) or op not in ('eq','ge','le') or type(value) not in (int,float,bool) or not math.isfinite(value):
                    raise ContractError('segment_precondition')
        return self


def condition_met(metrics, metric, op, target):
    value=metrics.get(metric)
    if type(value) not in (int,float,bool) or not math.isfinite(value): return False
    if isinstance(target,bool) and not isinstance(value,bool): return False
    return {'eq':value==target,'ge':value>=target,'le':value<=target}[op]


@dataclass
class Sample:
    state: dict
    metrics: dict
    events: list[str] = field(default_factory=list)
    terminal: str | None = None
    image: bytes | None = None
    image_suffix: str = "png"
    memory: bytes | None = None
    memory_interventions: list[dict] = field(default_factory=list)


class Profile(Protocol):
    metadata: dict
    skills: dict
    actions: list[Action]
    metric_names: set[str]
    bootstrap_frames: int

    def observe(self) -> Sample: ...
    def advance(self, buttons: tuple[str, ...]) -> Sample: ...
    def checkpoint(self) -> bytes: ...
    def view(self, sample: Sample, role: str) -> dict: ...
    def eligible(self, action: Action, sample: Sample) -> tuple[bool, str]: ...
    def close(self): ...


PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "objective": {"type": "string"}, "rationale": {"type": "string"},
        "guidance": {"type": "string"},
        "review_after_frames": {"type": "integer"},
        "stages": {"type":"array", "items": {
            "type":"object", "additionalProperties":False,
            "properties": {
                "id":{"type":"string"}, "kind":{"type":"string"},
                "objective":{"type":"string"}, "guidance":{"type":"string"},
                "target":{"type":"string"},
                "region":{"type":["object","null"],"additionalProperties":False,
                    "properties":{k:{"type":"number"} for k in ('x_min','x_max','y_min','y_max')},
                    "required":['x_min','x_max','y_min','y_max']},
                "grounded":{"type":["boolean","null"]}},
            "required":['id','kind','objective','guidance','target','region','grounded']}},
        "milestones": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"id": {"type": "string"},
                "metric": {"type": "string"}, "op": {"type": "string", "enum": ["ge", "le", "eq"]},
                "value": {"type": ["number", "boolean"]}},
            "required": ["id", "metric", "op", "value"]}},
    },
    "required": ["objective", "guidance", "rationale", "review_after_frames", "stages", "milestones"],
}


def validate_plan(value, profile):
    if not isinstance(value, dict) or set(value) != set(PLAN_SCHEMA["required"]):
        raise ContractError("plan_fields")
    if any(not isinstance(value[k], str) or not 0 < len(value[k]) <= 1200 for k in ("objective", "guidance", "rationale")):
        raise ContractError("plan_text")
    integer(value["review_after_frames"])
    stages=value['stages']
    if not isinstance(stages,list) or not 1<=len(stages)<=6: raise ContractError('intent_stages')
    stage_ids=set()
    for stage in stages:
        if not isinstance(stage,dict) or set(stage)!=set(PLAN_SCHEMA['properties']['stages']['items']['required']):
            raise ContractError('intent_stage_fields')
        for key in ('id','kind','objective','guidance','target'):
            if not isinstance(stage[key],str) or not 0<len(stage[key])<=600: raise ContractError('intent_stage_text')
        if stage['id'] in stage_ids: raise ContractError('intent_stage_id')
        stage_ids.add(stage['id'])
        if stage['kind'] not in profile.metadata.get('goal_kinds',[]): raise ContractError('unsupported_goal_kind')
        if stage['grounded'] is not None and type(stage['grounded']) is not bool: raise ContractError('intent_grounded')
        region=stage['region']
        if region is not None:
            if not isinstance(region,dict) or set(region)!={'x_min','x_max','y_min','y_max'}:
                raise ContractError('intent_region')
            if any(type(n) not in (int,float) or not math.isfinite(n) for n in region.values()):
                raise ContractError('intent_region')
            if region['x_min']>region['x_max'] or region['y_min']>region['y_max']: raise ContractError('intent_region')
        if stage['kind']=='reach_region' and region is None: raise ContractError('intent_region_required')
    nodes = value["milestones"]
    if not isinstance(nodes, list) or len(nodes) > 8:
        raise ContractError("milestones")
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or set(node) != {"id", "metric", "op", "value"}:
            raise ContractError("milestone_fields")
        if not isinstance(node["id"], str) or not node["id"] or node["id"] in ids:
            raise ContractError("milestone_id")
        ids.add(node["id"])
        if node["metric"] not in profile.metric_names or node["op"] not in ("ge", "le", "eq"):
            raise ContractError("milestone_contract")
        if type(node["value"]) not in (int, float, bool) or not math.isfinite(node["value"]):
            raise ContractError("milestone_value")
    return value


def progress(plan, metrics):
    result = []
    for node in plan["milestones"]:
        x, target = metrics.get(node["metric"]), node["value"]
        met = condition_met(metrics,node['metric'],node['op'],target)
        result.append({"id": node["id"], "metric": node["metric"], "observed": x, "met": met})
    return result


def offer(profile, sample, plan):
    # Intent is model context only. It never filters legal controller choices.
    kept, excluded = [], []
    seen = set()
    for action in profile.actions:
        action.validate()
        if action.id in seen or action.skill not in profile.skills:
            raise ContractError("profile_action_catalog")
        seen.add(action.id)
        reason = None
        ok, detail = profile.eligible(action, sample)
        if not ok: reason = detail
        (excluded if reason else kept).append({"action": action.json(), "reason": reason} if reason else action)
    return kept, excluded
