"""The only owner of simulation advancement. Backends never receive an emulator."""
from dataclasses import asdict, dataclass
import copy
import math
import queue
import threading
import time
from .contracts import ContractError, PLAN_SCHEMA, integer, offer, progress, validate_plan, condition_met
from .intent_queue import IntentQueue
from .plan_clock import PlanClock


@dataclass(frozen=True)
class Schedule:
    brain_min_frames: int = 60
    brain_every_frames: int = 120
    decision_every_frames: int = 24
    request_timeout_s: float = 90
    max_frames: int | None = None
    max_decisions: int | None = None
    max_wall_s: float | None = None

    def validate(self):
        integer(self.brain_every_frames)
        integer(self.brain_min_frames,0,self.brain_every_frames)
        integer(self.decision_every_frames, 1, 120)
        if type(self.request_timeout_s) not in (int,float) or not math.isfinite(self.request_timeout_s) or not 0 < self.request_timeout_s <= 600:
            raise ValueError("request_timeout")
        for x in (self.max_frames, self.max_decisions):
            if x is not None: integer(x)
        if self.max_wall_s is not None and (type(self.max_wall_s) not in (int,float) or not math.isfinite(self.max_wall_s) or not 0 < self.max_wall_s):
            raise ValueError("wall_limit")


class Runner:
    def __init__(self, session, profile, brain, controller, schedule=Schedule()):
        schedule.validate()
        self.s, self.p, self.brain, self.controller, self.cfg = session, profile, brain, controller, schedule
        self.calls = {"brain": 0, "controller": 0}
        self.known_cost = 0.0
        self.unknown_cost_calls = 0
        self.last_buttons = ()
        self.last_feedback = {}
        self.history = []
        self.intent_queue = None
        self.frame_advance_uncertain = False
        self.start = time.monotonic()

    def stopping(self):
        if (self.s.root/"STOP").exists(): return "user_stop"
        if self.cfg.max_frames is not None and self.s.frame >= self.cfg.max_frames: return "frame_budget"
        if self.cfg.max_wall_s is not None and time.monotonic()-self.start >= self.cfg.max_wall_s: return "wall_budget"
        return None

    def call(self, role, backend, context, schema, **links):
        self.calls[role] += 1
        cid = f"{role}-{self.calls[role]:05d}"
        wire = backend.prepare(role, copy.deepcopy(context), schema)
        request = self.s.json(f"calls/{cid}/request.json", wire)
        self.s.event("call.started", call_id=cid, role=role, backend=backend.descriptor,
            request=request, **links)
        began = time.monotonic()
        accounted = False
        try:
            timeout = self.cfg.request_timeout_s
            if self.cfg.max_wall_s is not None:
                timeout = min(timeout, max(.001, self.cfg.max_wall_s-(time.monotonic()-self.start)))
            mailbox=queue.Queue(maxsize=4096)
            def dispatch():
                try:
                    value=backend.invoke(wire, timeout, lambda item: mailbox.put(("output",item)))
                    mailbox.put(("result",value))
                except Exception as error:
                    mailbox.put(("error",error))
            threading.Thread(target=dispatch,daemon=True).start()
            while True:
                if self.stopping(): raise InterruptedError("session_stop")
                remaining=timeout-(time.monotonic()-began)
                if remaining <= 0: raise TimeoutError("request_deadline")
                try: kind,value=mailbox.get(timeout=min(.05,remaining))
                except queue.Empty: continue
                if kind=="error": raise value
                if kind=="result": raw=value; break
                self.s.event("call.output",call_id=cid,role=role,item=value,**links)
            response = self.s.json(f"calls/{cid}/response.json", raw)
            self.s.event("call.responded", call_id=cid, role=role, response=response,
                latency_s=time.monotonic()-began, **links)
            result = backend.interpret(role, raw)
            cost = result.get("cost_usd")
            if cost is None:
                self.unknown_cost_calls += 1
            else:
                if type(cost) not in (int,float) or not math.isfinite(cost) or cost < 0:
                    raise ContractError("invalid_cost")
                self.known_cost += cost
            accounted = True
            self.s.event("call.completed", call_id=cid, role=role, model=result.get("model"),
                usage=result.get("usage"), cost_usd=cost, provider_session_id=result.get("provider_session_id"), **links)
            return cid, result["value"]
        except Exception as exc:
            if not accounted: self.unknown_cost_calls += 1
            # Never record exception text, HTTP error bodies, auth headers, or private paths.
            self.s.event("call.failed", call_id=cid, role=role, error_type=type(exc).__name__,
                retry=False, latency_s=time.monotonic()-began, **links)
            raise

    def context(self, sample, role, oid, **extra):
        return {"session_id": self.s.id, "observation_id": oid, "frame": self.s.frame,
            "game_time_s": self.s.frame/self.p.metadata["fps"],
            "planning_window": {"ordinary_replan_min_frames":self.cfg.brain_min_frames,
                "ordinary_replan_max_frames":self.cfg.brain_every_frames,
                "rules":"A plan must cover this game-frame horizon; minor progress updates stay local. Only explicit urgent profile events bypass the minimum. These are NOT button-hold durations."},
            "observation": self.p.view(sample, role),
            "motor_capabilities": {k:v['description'] for k,v in self.p.skills.items()} if role=='brain' else None,
            "goal_kinds":self.p.metadata.get('goal_kinds',[]),
            "goal_verifiers":self.p.metadata.get('goal_verifiers',{}),
            "goal_evidence_note":self.p.metadata.get('goal_evidence_note',''),
            "intent_progress":self.intent_queue.snapshot() if self.intent_queue else None,
            "plan_contract":"Ordered near-to-far goals and persistent guidance, NOT action permissions. All locally executable motor actions stay available.",
            "metric_names": sorted(self.p.metric_names), "previous_buttons": self.last_buttons,
            "recent_trajectory": self.history[-60:], "execution_feedback": self.last_feedback,
            "rules": self.p.metadata.get("instructions", ""), **extra}

    def advance(self, buttons, **links):
        try:
            sample = self.p.advance(buttons)
        except Exception as exc:
            # A profile may fail after stepping but before returning its observation.
            # Never invent a frame or pretend the final checkpoint matches the journal.
            self.frame_advance_uncertain = True
            self.s.event("frame.failed", attempted_frame=self.s.frame+1,
                input_buttons=buttons, emulator_advance_uncertain=True,
                error_type=type(exc).__name__, **links)
            raise
        self.s.frame += 1
        self.last_buttons = buttons
        self.s.sample(sample, input_buttons=buttons, **links)
        self.history.append({"frame": self.s.frame, "metrics": sample.metrics, "buttons": buttons,
            "events": sample.events})
        self.history = self.history[-120:]
        return sample

    def run(self):
        reason, error_type = "unknown", None
        sample = None
        decisions = 0
        singleton_executions = 0
        active_plan = None
        plan_id = None
        plan_clock=PlanClock(self.cfg.brain_min_frames,self.cfg.brain_every_frames)
        latched_milestones = set()
        try:
            sample = self.p.observe()
            self.s.sample(sample, initial=True)
            self.s.checkpoint(self.p.checkpoint(), "initial")
            if sample.terminal:
                reason = sample.terminal
            else:
                for _ in range(self.p.bootstrap_frames):
                    reason = self.stopping()
                    if reason: break
                    sample = self.advance((), execution_id="bootstrap", decision_id=None, plan_id=None,
                        source="profile_bootstrap_not_model")
                    if sample.terminal:
                        reason=sample.terminal; break
            while not sample.terminal and not self.stopping() and reason in (None,"unknown"):
                if self.cfg.max_decisions is not None and decisions >= self.cfg.max_decisions:
                    reason="decision_budget"; break
                oid = self.s.observation(sample)
                if active_plan is None or plan_clock.due(self.s.frame):
                    self.s.checkpoint(self.p.checkpoint(), f"before-brain-{self.calls['brain']+1:05d}")
                    cid, proposal = self.call("brain", self.brain,
                        self.context(sample,"brain",oid, replan_reason=plan_clock.reason, previous_plan=active_plan,
                            previous_plan_id=plan_id), PLAN_SCHEMA, observation_id=oid, previous_plan_id=plan_id)
                    active_plan = copy.deepcopy(validate_plan(proposal,self.p))
                    plan_id = "plan-" + cid
                    self.intent_queue=IntentQueue(active_plan,self.p.metadata,self.intent_queue)
                    initial_verified=self.intent_queue.update(sample,self.s.frame)
                    plan_clock.install(self.s.frame,active_plan['review_after_frames'])
                    latched_milestones = {n["id"] for n in progress(active_plan,sample.metrics) if n["met"]}
                    self.s.event("plan.installed", plan_id=plan_id, call_id=cid, observation_id=oid,
                        plan=active_plan, progress=progress(active_plan,sample.metrics),
                        intent_queue=self.intent_queue.snapshot(), queue_revisions=self.intent_queue.revisions,
                        schedule={'minimum_frames':self.cfg.brain_min_frames,
                            'requested_review_after_frames':active_plan['review_after_frames'],
                            'effective_review_after_frames':plan_clock.remaining(self.s.frame),
                            'next_review_frame':plan_clock.due_frame})
                    for verified in initial_verified:
                        self.s.event('intent.stage_verified',plan_id=plan_id,**verified)
                if self.stopping(): break
                offered, excluded = offer(self.p,sample,active_plan)
                self.s.event("candidates.offered", observation_id=oid, plan_id=plan_id,
                    permission_source='profile_only_NOT_brain_plan',
                    actions=[a.json() for a in offered], excluded=excluded)
                if not offered:
                    reason="empty_action_contract"; break
                self.s.checkpoint(self.p.checkpoint(), f"before-decision-{decisions+1:05d}")
                schema = {"type":"object","additionalProperties":False,
                    "properties":{"choice":{"type":"string","enum":[a.id for a in offered]}}, "required":["choice"]}
                singleton = len(offered) == 1
                if singleton:
                    # No policy choice exists: preserve the plan, never invent a model call.
                    cid, selection = None, {'choice': offered[0].id}
                    singleton_executions += 1
                else:
                    cid, selection = self.call("controller",self.controller,
                        self.context(sample,"controller",oid,plan=active_plan,plan_id=plan_id,
                            plan_schedule={'next_review_frame':plan_clock.due_frame,
                                'review_in_frames':plan_clock.remaining(self.s.frame)},
                            plan_progress=progress(active_plan,sample.metrics), candidates=[a.json() for a in offered]),
                        schema, observation_id=oid, plan_id=plan_id)
                if not isinstance(selection,dict) or set(selection) != {"choice"} or selection["choice"] not in {a.id for a in offered}:
                    raise ContractError("unsupported_model_choice")
                action = next(a for a in offered if a.id == selection["choice"])
                decisions += 1
                did, xid = f"decision-{decisions:05d}",f"execution-{decisions:05d}"
                self.s.event("decision.selected", decision_id=did, call_id=cid, observation_id=oid,
                    plan_id=plan_id, model_choice=None if singleton else action.id, executor_choice=action.id,
                    action_label=action.label or action.skill, intent_progress=self.intent_queue.snapshot(),
                    selection_source="singleton_contract_no_model_choice" if singleton else
                        "model_output" if not self.controller.descriptor.get("scripted") else "scripted_fixture")
                if self.stopping(): break
                frame0 = self.s.frame
                until_brain = plan_clock.remaining(frame0)
                cap = min(action.frames,self.cfg.decision_every_frames,until_brain)
                self.s.event("execution.started", execution_id=xid, decision_id=did, plan_id=plan_id,
                    observation_id=oid, action=action.json(), scheduled_frames=cap,
                    sequence_policy='execute_exact_prefix; discard_unexecuted_tail_on_interrupt; never_auto_resume')
                before_metrics = sample.metrics
                batch_reward=0.0
                interrupt = None
                executed_segments=[]
                for offset in range(cap):
                    interrupt = self.stopping()
                    if interrupt: break
                    segment_index,segment,segment_offset=action.phase(offset)
                    if segment_offset==0:
                        guard=[{'metric':m,'op':op,'value':v,'observed':sample.metrics.get(m),
                            'met':condition_met(sample.metrics,m,op,v)} for m,op,v in segment.requires]
                        if not all(g['met'] for g in guard):
                            interrupt='segment_precondition_failed'
                            self.s.event('execution.segment_guard_failed',execution_id=xid,
                                decision_id=did,plan_id=plan_id,segment_index=segment_index,guard=guard)
                            break
                        executed_segments.append({'index':segment_index,'name':segment.name,
                            'buttons':segment.buttons,'planned_frames':segment.frames,
                            'frame_start':self.s.frame,'executed_frames':0})
                        self.s.event('execution.segment_started',execution_id=xid,decision_id=did,
                            plan_id=plan_id,segment_index=segment_index,name=segment.name,
                            buttons=segment.buttons,planned_frames=segment.frames,guard=guard)
                    sample = self.advance(segment.buttons, execution_id=xid, decision_id=did, plan_id=plan_id,
                        action_frame_offset=offset,segment_index=segment_index,segment_frame_offset=segment_offset,
                        source="singleton_contract_no_model_choice" if singleton else "selected_action")
                    executed_segments[-1]['executed_frames']+=1
                    executed_segments[-1]['frame_end']=self.s.frame
                    reward=sample.metrics.get("reward")
                    if reward is None: batch_reward=None
                    elif batch_reward is not None: batch_reward+=reward
                    if sample.terminal:
                        interrupt=sample.terminal; break
                    verified=self.intent_queue.update(sample,self.s.frame)
                    for item in verified:
                        self.s.event('intent.stage_verified',plan_id=plan_id,**item)
                    if verified: interrupt='intent_stage_boundary'
                    now_met = {n["id"] for n in progress(active_plan,sample.metrics) if n["met"]}
                    if now_met - latched_milestones:
                        latched_milestones |= now_met
                        self.s.event('replan.requested',plan_id=plan_id,
                            **plan_clock.request(self.s.frame,'milestone_reached'))
                        interrupt="milestone_boundary"
                    if 'urgent_replan' in sample.events:
                        self.s.event('replan.requested',plan_id=plan_id,
                            trigger_events=sample.events,
                            **plan_clock.request(self.s.frame,'urgent_profile_event',urgent=True))
                        interrupt='urgent_profile_event';break
                    if "replan" in sample.events:
                        self.s.event('replan.requested',plan_id=plan_id,
                            trigger_events=sample.events,
                            **plan_clock.request(self.s.frame,'profile_event'))
                        interrupt="profile_event"; break
                    if interrupt: break
                    if "observe" in sample.events:
                        interrupt="observation_boundary"; break
                if interrupt is None and cap < action.frames:
                    interrupt="brain_cadence" if cap==until_brain else "controller_cadence"
                self.last_feedback = {"execution_id":xid,"decision_id":did,"plan_id":plan_id,
                    "frame_start":frame0,"frame_end":self.s.frame,"requested_frames":action.frames,
                    "executed_frames":self.s.frame-frame0,"buttons":action.buttons if not action.segments else None,
                    "executed_segments":executed_segments,
                    "discarded_remaining_frames":action.frames-(self.s.frame-frame0),
                    "intent_progress":self.intent_queue.snapshot(),
                    "interruption":interrupt,"terminal":sample.terminal,"before":before_metrics,
                    "after":sample.metrics,"milestone_status":progress(active_plan,sample.metrics),
                    "reward":batch_reward,"reward_source":self.p.metadata.get("reward_source")}
                self.last_feedback['next_brain_review_frame']=plan_clock.due_frame
                self.last_feedback['selection_source']='singleton_contract_no_model_choice' if singleton else 'controller_choice'
                self.s.event("execution.completed", **self.last_feedback)
            reason = sample.terminal or self.stopping() or reason or "stopped"
        except KeyboardInterrupt:
            reason="user_interrupt"
        except Exception as exc:
            reason=self.stopping() or ("contract_error" if isinstance(exc,ContractError) else
                "request_timeout" if isinstance(exc,TimeoutError) else "runtime_error")
            error_type=type(exc).__name__
            self.s.event("session.error", error_type=error_type, recovery="none")
        finally:
            try:
                self.s.checkpoint(self.p.checkpoint(), "final")
            except Exception as exc:
                self.s.event("checkpoint.failed", error_type=type(exc).__name__)
            for component in (self.brain,self.controller,self.p):
                try: component.close()
                except Exception as exc: self.s.event("component.close_failed",error_type=type(exc).__name__)
            self.s.finish(reason, calls=self.calls, decisions=decisions, error_type=error_type,
                singleton_contract_executions=singleton_executions,
                cost={"known_api_cost_usd":self.known_cost,"calls_without_price":self.unknown_cost_calls,
                    "compute_cost_usd":None,"total_cost_usd":None},
                death_count=1 if sample is not None and sample.terminal=="death" else 0,
                frame_advance_uncertain=self.frame_advance_uncertain,
                completion_claim=sample is not None and sample.terminal=="complete")
        return self.s.root
