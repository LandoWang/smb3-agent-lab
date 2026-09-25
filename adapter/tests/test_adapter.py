import copy
from dataclasses import asdict
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import zipfile

from session_adapter.backends import CodexBackend, HTTPBackend, Scripted
from session_adapter.contracts import ContractError, PLAN_SCHEMA, offer, progress, validate_plan
from session_adapter.engine import Runner, Schedule
from session_adapter.profiles.fixture import Fixture
from session_adapter.recording import Redactor, Session, pack, verify, verify_links

ROOT=Path(__file__).resolve().parent.parent
TMP=ROOT/"test-tmp"
TMP.mkdir(exist_ok=True)


class Override(Scripted):
    def __init__(self,callback): self.callback=callback
    def invoke(self,wire,timeout,emit):
        return self.callback(wire,super().invoke(wire,timeout,emit))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TMP)
        self.root=Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def attempt(self,profile=None,brain=None,controller=None,schedule=None,redactor=None):
        p=profile or Fixture();cfg=schedule or Schedule(brain_min_frames=0,brain_every_frames=60,decision_every_frames=24)
        s=Session(self.root,{"profile":p.metadata,"seed":1,"schedule":asdict(cfg)},redactor)
        Runner(s,p,brain or Scripted(),controller or Scripted(),cfg).run()
        verify(s.root)
        return s

    def test_frame_coverage_and_links(self):
        s=self.attempt()
        self.assertEqual([r["frame"] for r in s.events if r["kind"]=="frame.executed"],list(range(1,97)))
        calls={r["call_id"]:r for r in s.events if r["kind"]=="call.started"}
        for r in s.events:
            if r["kind"]=="call.responded": self.assertEqual(r["frame"],calls[r["call_id"]]["frame"])
            if r["kind"]=="decision.selected":
                self.assertEqual(r["executor_choice"],r["model_choice"])
                self.assertTrue(any(p.get("plan_id")==r["plan_id"] and p["kind"]=="plan.installed" for p in s.events))

    def test_feedback_flows_back_to_brain(self):
        s=self.attempt()
        request=json.loads((s.root/"calls/brain-00002/request.json").read_text())
        feedback=request["context"]["execution_feedback"]
        self.assertEqual(feedback["frame_end"],30)
        self.assertEqual(feedback["executed_frames"],6)
        self.assertEqual(feedback["requested_frames"],24)

    def test_plan_reaches_controller(self):
        s=self.attempt()
        request=json.loads((s.root/"calls/controller-00001/request.json").read_text())["context"]
        self.assertEqual(request["plan_id"],"plan-brain-00001")
        self.assertEqual(request["frame"],0)
        self.assertIn("right_24",[a["id"] for a in request["candidates"]])

    def test_hazard_event_pauses_and_replans(self):
        s=self.attempt()
        x=next(r for r in s.events if r["kind"]=="execution.completed" and r["frame_end"]==40)
        self.assertEqual(x["interruption"],"profile_event")
        self.assertTrue(any(r["kind"]=="plan.installed" and r["frame"]==40 for r in s.events))

    def test_actual_reward_is_batch_sum(self):
        s=self.attempt()
        first=next(r for r in s.events if r["kind"]=="execution.completed")
        self.assertEqual(first["reward"],first["executed_frames"])

    def test_first_death_stops_without_restore(self):
        s=self.attempt(Fixture(death_at=15))
        self.assertEqual(s.metadata["stop_reason"],"death")
        self.assertEqual(s.frame,15)
        self.assertEqual(s.metadata["death_count"],1)
        self.assertFalse(s.metadata["completion_claim"])

    def test_initial_death_has_no_model_calls(self):
        s=self.attempt(Fixture(death_at=0))
        self.assertEqual(s.frame,0)
        self.assertEqual(s.metadata["calls"],{"brain":0,"controller":0})

    def test_invalid_choice_never_advances(self):
        bad=Override(lambda wire,raw:{"value":{"choice":"teleport"}})
        s=self.attempt(controller=bad)
        self.assertEqual(s.frame,0)
        self.assertEqual(s.metadata["stop_reason"],"contract_error")
        self.assertTrue((s.root/"calls/controller-00001/response.json").exists())

    def test_unsupported_plan_fails_closed(self):
        def bad(wire,raw): raw["value"]["allowed_skills"]=["teleport"];return raw
        s=self.attempt(brain=Override(bad))
        self.assertEqual(s.frame,0)
        self.assertEqual(s.metadata["calls"]["controller"],0)

    def test_intent_cannot_remove_executable_candidates(self):
        p=Fixture();plan=Scripted().invoke({"role":"brain","context":{"skill_catalog":p.skills,"observation":p.observe().state}},5,lambda _:None)["value"]
        plan["allowed_skills"]=["right"];plan["max_frames"]=12
        kept,excluded=offer(p,p.observe(),plan)
        self.assertEqual([a.id for a in kept],[a.id for a in p.actions])
        self.assertFalse(excluded)
        with self.assertRaises(ContractError): validate_plan(plan,p)

    def test_brain_cadence_is_emulated_frames(self):
        def brain(w,raw): raw["value"]["milestones"]=[];raw["value"]["review_after_frames"]=100;return raw
        s=self.attempt(Fixture(goal=31,hazard_at=999),Override(brain),schedule=Schedule(brain_min_frames=0,brain_every_frames=10))
        self.assertEqual([e["frame"] for e in s.events if e["kind"]=="plan.installed"],[0,10,20,30])

    def test_frame_budget_truncation(self):
        s=self.attempt(schedule=Schedule(max_frames=7))
        self.assertEqual(s.frame,7)
        self.assertEqual(s.metadata["stop_reason"],"frame_budget")
        x=next(e for e in s.events if e["kind"]=="execution.completed")
        self.assertEqual((x["requested_frames"],x["executed_frames"]),(24,7))

    def test_decision_budget(self):
        s=self.attempt(schedule=Schedule(max_decisions=1))
        self.assertEqual(s.metadata["decisions"],1)
        self.assertEqual(s.metadata["stop_reason"],"decision_budget")

    def test_hard_request_timeout_no_late_execution(self):
        def slow(w,r): time.sleep(.2);return r
        s=self.attempt(brain=Override(slow),schedule=Schedule(request_timeout_s=.02))
        self.assertEqual(s.frame,0)
        self.assertEqual(s.metadata["error_type"],"TimeoutError")
        self.assertEqual(s.metadata["cost"]["calls_without_price"],1)
        time.sleep(.23)
        self.assertEqual(s.frame,0);verify(s.root)

    def test_user_stop_during_request(self):
        p=Fixture();s=Session(self.root,{"profile":p.metadata})
        def stop(w,r): (s.root/"STOP").touch();time.sleep(.1);return r
        Runner(s,p,Override(stop),Scripted()).run()
        self.assertEqual(s.metadata["stop_reason"],"user_stop")
        self.assertEqual(s.frame,0)
        time.sleep(.12)

    def test_pause_does_not_release_a(self):
        p=Fixture(goal=1000,hazard_at=999)
        p.advance(("RIGHT","A"));first=p.observe().state["a_held_frames"]
        p.observe();p.observe();self.assertEqual(p.observe().state["a_held_frames"],first)
        p.advance(("RIGHT","A"));self.assertEqual(p.observe().state["a_held_frames"],2)
        p.advance(());self.assertEqual(p.observe().state["a_held_frames"],0)

    def test_session_ids_cannot_overwrite(self):
        s=Session(self.root,{},session_id="one");s.finish("test")
        with self.assertRaises(FileExistsError): Session(self.root,{},session_id="one")
        with self.assertRaises(ValueError): Session(self.root,{},session_id="../unsafe")

    def test_checksums_detect_tampering(self):
        s=self.attempt();(s.root/"states/initial.state").write_bytes(b"tampered")
        with self.assertRaises(ValueError): verify(s.root)

    def test_cross_timeline_links_are_validated(self):
        s=self.attempt()
        manifest=json.loads((s.root/"checksums.json").read_text())
        rows=json.loads((s.root/"timeline.json").read_text())["events"]
        next(r for r in rows if r["kind"]=="decision.selected")["call_id"]="brain-00001"
        with self.assertRaises(ValueError): verify_links(rows,s.metadata,manifest)

    def test_partial_step_failure_is_explicit_uncertainty(self):
        class Broken(Fixture):
            def advance(self,buttons):
                super().advance(buttons)
                raise RuntimeError("after_emulator_step")
        s=self.attempt(profile=Broken())
        self.assertEqual(s.frame,0)
        self.assertTrue(s.metadata["frame_advance_uncertain"])
        self.assertEqual(s.metadata["stop_reason"],"runtime_error")
        event=next(r for r in s.events if r["kind"]=="frame.failed")
        self.assertEqual(event["attempted_frame"],1)

    def test_pack_is_portable_and_excludes_unregistered_files(self):
        s=self.attempt();(s.root/"private.env").write_text("API_KEY=not_for_archive")
        path=self.root/"bundle.zip";pack(s.root,path)
        with zipfile.ZipFile(path) as z:
            names=z.namelist();self.assertFalse(any("private.env" in n for n in names))
            self.assertIn(s.id+"/index.html",names)
            dest=self.root/"unpacked";z.extractall(dest)
        verify(dest/s.id)
        with self.assertRaises(FileExistsError): pack(s.root,path)

    def test_redaction_in_requests_responses_and_events(self):
        secret="fixture-secret-very-private"
        def echo(w,r): r["value"]["rationale"]=secret;return r
        s=self.attempt(brain=Override(echo),redactor=Redactor([secret]))
        for p in s.root.rglob("*"):
            if p.is_file(): self.assertNotIn(secret.encode(),p.read_bytes())

    def test_error_text_never_logged(self):
        def fail(w,r): raise ValueError("TOP_SECRET_HEADER")
        s=self.attempt(brain=Override(fail))
        self.assertNotIn("TOP_SECRET_HEADER",(s.root/"events.jsonl").read_text())

    def test_viewer_escapes_untrusted_response_html(self):
        def evil(w,r): r["value"]["rationale"]="</script><script>alert(1)</script>";return r
        s=self.attempt(brain=Override(evil))
        page=(s.root/"index.html").read_text()
        self.assertNotIn("</script><script>alert",page)
        self.assertIn("\\u003c/script>",page)

    def test_invalid_metric_and_duplicate_milestone(self):
        p=Fixture();plan=Scripted().invoke({"role":"brain","context":{"skill_catalog":p.skills,"observation":p.observe().state}},5,lambda _:None)["value"]
        plan["milestones"][0]["metric"]="fake"
        with self.assertRaises(ContractError): validate_plan(plan,p)
        plan["milestones"][0]["metric"]="x";plan["milestones"]*=2
        with self.assertRaises(ContractError): validate_plan(plan,p)

    def test_unknown_metric_is_not_goal_success(self):
        node={"milestones":[{"id":"n","metric":"missing","op":"ge","value":3}]}
        self.assertFalse(progress(node,{})[0]["met"])

    def test_codex_protocol_persistent_thread_and_safe_transcript(self):
        backend=CodexBackend("fixture-model",self.root/"codex",[sys.executable,str(ROOT/"tests/fake_codex.py")])
        emitted=[]
        try:
            wire=backend.prepare("brain",{"frame":0},PLAN_SCHEMA)
            first=backend.invoke(wire,5,emitted.append)
            second=backend.invoke(wire,5,emitted.append)
            self.assertEqual(first["thread_id"],second["thread_id"])
            self.assertNotEqual(first["turn_id"],second["turn_id"])
            result=backend.interpret("brain",second)
            self.assertEqual(result["usage"]["outputTokens"],20)
            self.assertNotIn("PRIVATE_REASONING",json.dumps(emitted))
        finally: backend.close()

    def test_new_codex_backend_does_not_inherit_thread(self):
        a=CodexBackend("m",self.root);b=CodexBackend("m",self.root)
        a.thread_id="old";self.assertIsNone(b.thread_id)

    def test_http_jev_payload_is_actual_decisions_contract(self):
        config=self.root/"private.env";config.write_text("OPENROUTER_API_KEY=test-not-a-key\n")
        b=HTTPBackend("openrouter_jev",private_config=config)
        context={"session_id":"test","candidates":[{"id":"right_6","buttons":["RIGHT"],"frames":6}]}
        wire=b.prepare("controller",context,{})
        self.assertEqual(wire["model"],"typesafe/jev-1.13")
        self.assertEqual(list(wire["questions"]["action"]["criteria"]),["right_6"])
        self.assertNotIn("test-not-a-key",json.dumps(wire))

    def test_http_rejects_bad_model_and_probabilities(self):
        b=HTTPBackend("local_diffusiongemma",endpoint="http://localhost:1/decisions")
        with self.assertRaises(ContractError): b.interpret("controller",{"model":"other"})
        with self.assertRaises(ContractError): b.interpret("controller",{"model":"dgemma","answers":{"action":{"choice":"a","probabilities":{"a":float('nan')}}}})

    def test_schedule_rejects_invalid_frames(self):
        for value in (0,True,-1,121):
            with self.assertRaises(ValueError): Schedule(decision_every_frames=value).validate()

    def test_schedule_rejects_nonfinite_clocks(self):
        for value in (float('nan'),float('inf'),True,0):
            with self.assertRaises(ValueError): Schedule(max_wall_s=value).validate()
            with self.assertRaises(ValueError): Schedule(request_timeout_s=value).validate()


if __name__=="__main__": unittest.main()
