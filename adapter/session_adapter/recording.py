"""One append-only source of truth; derived timelines are rebuildable."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
import uuid
import zipfile
from . import VERSION, FORMAT_VERSION
from .contracts import Action


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Redactor:
    def __init__(self, secrets=()):
        self.secrets = [s for s in secrets if isinstance(s, str) and len(s) >= 6]

    def clean(self, value):
        if isinstance(value, dict):
            return {str(k): ("[REDACTED]" if re.search(r"(?i)^(api[-_]?key|authorization|password|secret|access_token|refresh_token)$", str(k)) else self.clean(v)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)
            return re.sub(r"(?i)Bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED]", value)
        return value


class Session:
    def __init__(self, parent, metadata, redactor=None, clock=time.monotonic_ns, session_id=None):
        self.id = session_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", self.id):
            raise ValueError("unsafe_session_id")
        self.root = Path(parent) / self.id
        self.root.mkdir(parents=True, exist_ok=False)
        self.clock, self.started = clock, clock()
        self.redactor = redactor or Redactor()
        self.events, self.assets = [], {}
        self.log = (self.root / "events.jsonl").open("xb")
        self.frame = 0
        self.metadata = {"format_version": FORMAT_VERSION, "adapter_version": VERSION,
            "session_id": self.id, "created_utc": self.utc(), "status": "running",
            "indices": {"journal":"events.jsonl", "timeline":"timeline.json",
                "offline_viewer":"index.html", "integrity_manifest":"checksums.json"},
            "clock_contract": {"frame": "completed emulator steps since session start; initial snapshot is frame 0",
                "wall_ns": "monotonic elapsed nanoseconds; includes model waiting",
                "utc": "display/correlation only; never schedules simulation",
                "video": "frame-N image is post-step; video time (N-1)/fps, initial frame 0 excluded"},
            "privacy": "private_debug_bundle; ROMs, secrets, core binaries and private configuration excluded",
            **metadata}
        self.json("metadata.json", self.metadata)
        self.event("session.started", metadata_file="metadata.json")

    @staticmethod
    def utc():
        return datetime.now(timezone.utc).isoformat()

    def path(self, name):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("unsafe_asset_path")
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in [target, *target.parents] if p != self.root.parent):
            raise ValueError("symlink_asset")
        return target

    def asset(self, name, data):
        target = self.path(name)
        with target.open("xb") as stream:
            stream.write(data)
        info = {"path": name, "sha256": sha(data), "bytes": len(data)}
        self.assets[name] = info
        return info

    def json(self, name, value):
        data = encoded(self.redactor.clean(value)) + b"\n"
        if name == "metadata.json":
            temp = self.root / (".metadata-" + uuid.uuid4().hex)
            with temp.open("xb") as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, self.root / name)
            return {"path": name, "sha256": sha(data), "bytes": len(data)}
        return self.asset(name, data)

    def event(self, kind, **data):
        row = {"seq": len(self.events), "event_id": f"e{len(self.events):07d}", "session_id": self.id,
            "utc": self.utc(), "wall_ns": self.clock() - self.started, "frame": self.frame,
            "kind": kind, "previous_hash": self.events[-1]["hash"] if self.events else "0" * 64,
            **self.redactor.clean(data)}
        row["hash"] = sha(encoded(row))
        self.log.write(encoded(row) + b"\n"); self.log.flush(); os.fsync(self.log.fileno())
        self.events.append(row)
        return row

    def checkpoint(self, data, label):
        info = self.asset(f"states/{label}.state", data)
        self.event("checkpoint.saved", artifact=info)
        return info

    def sample(self, sample, *, initial=False, **links):
        picture = None
        if sample.image is not None:
            if sample.image_suffix not in ("png", "svg"):
                raise ValueError("unsupported_image_format")
            picture = self.asset(f"frames/{self.frame:08d}.{sample.image_suffix}", sample.image)
        memory = self.asset(f"memory/{self.frame:08d}.bin", sample.memory) if sample.memory is not None else None
        return self.event("frame.initial" if initial else "frame.executed", image=picture, memory=memory,
            metrics=sample.metrics, game_events=sample.events, terminal=sample.terminal,
            memory_interventions=sample.memory_interventions, **links)

    def observation(self, sample):
        oid = f"o{len([e for e in self.events if e['kind']=='observation.captured']):05d}"
        info = self.json(f"observations/{oid}.json", {"frame": self.frame, "state": sample.state,
            "metrics": sample.metrics, "events": sample.events, "terminal": sample.terminal})
        self.event("observation.captured", observation_id=oid, artifact=info)
        return oid

    def finish(self, reason, **result):
        if self.log.closed:
            raise ValueError("already_finished")
        self.event("session.ended", reason=reason, **result)
        self.metadata.update(status="finished", stop_reason=reason, final_frame=self.frame,
            elapsed_wall_ns=self.clock()-self.started, journal_tip=self.events[-1]["hash"], **result)
        self.json("metadata.json", self.metadata)
        self.log.close()
        self.assets["events.jsonl"] = {"path": "events.jsonl", "bytes": (self.root/"events.jsonl").stat().st_size,
            "sha256": sha((self.root/"events.jsonl").read_bytes())}
        self.assets["metadata.json"] = {"path": "metadata.json", "bytes": (self.root/"metadata.json").stat().st_size,
            "sha256": sha((self.root/"metadata.json").read_bytes())}
        self.json("timeline.json", {"session_id": self.id, "events": self.events})
        from .viewer import render
        self.asset("index.html", render(self).encode())
        manifest = {"format_version": FORMAT_VERSION, "files": list(self.assets.values())}
        self.json("checksums.json", manifest)


def verify(root):
    root = Path(root)
    manifest = json.loads((root/"checksums.json").read_text())
    names=[x["path"] for x in manifest["files"]]
    if len(names)!=len(set(names)) or not {"events.jsonl","metadata.json","timeline.json","index.html"} <= set(names):
        raise ValueError("manifest_contract")
    for info in manifest["files"]:
        path = root / info["path"]
        if Path(info["path"]).is_absolute() or ".." in Path(info["path"]).parts or not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("unsafe_manifest_path")
        data = path.read_bytes()
        if len(data) != info["bytes"] or sha(data) != info["sha256"]:
            raise ValueError("artifact_integrity")
    previous, frame, last_wall = "0"*64, 0, -1
    rows = []
    for line in (root/"events.jsonl").read_bytes().splitlines():
        row = json.loads(line); digest = row.pop("hash")
        if row["seq"] != len(rows) or row["previous_hash"] != previous or sha(encoded(row)) != digest:
            raise ValueError("journal_integrity")
        if row["wall_ns"] < last_wall or row["frame"] < frame:
            raise ValueError("clock_regression")
        if row["kind"] == "frame.executed" and row["frame"] != frame + 1:
            raise ValueError("missing_executed_frame")
        if row["kind"] != "frame.executed" and row["frame"] != frame:
            raise ValueError("unlogged_frame_advance")
        frame, previous, last_wall = row["frame"], digest, row["wall_ns"]
        rows.append({**row,"hash":digest})
    if not rows or rows[-1]["kind"] != "session.ended":
        raise ValueError("session_incomplete")
    meta=json.loads((root/"metadata.json").read_text())
    if meta["journal_tip"] != previous or meta["final_frame"] != frame:
        raise ValueError("metadata_mismatch")
    if json.loads((root/"timeline.json").read_text())["events"] != rows:
        raise ValueError("timeline_mismatch")
    verify_links(rows,meta,manifest)
    return {"events": len(rows), "frames": frame, "reason": meta["stop_reason"], "integrity": "verified"}


def verify_links(rows,meta,manifest):
    """Audit causal references, not just bytes; hashes alone do not prove valid links."""
    assets={x["path"]:x for x in manifest["files"]}
    observations={};calls={};plans={};decisions={};executions={};offers={}
    def artifacts(value):
        if isinstance(value,dict):
            if {"path","bytes","sha256"} <= value.keys() and assets.get(value["path"])!=value:
                raise ValueError("unregistered_event_artifact")
            for v in value.values(): artifacts(v)
        elif isinstance(value,list):
            for v in value: artifacts(v)
    for row in rows:
        if row["session_id"]!=meta["session_id"] or row["event_id"]!=f"e{row['seq']:07d}":
            raise ValueError("event_identity")
        artifacts(row)
        k=row["kind"]
        if k=="observation.captured":
            if row["observation_id"] in observations: raise ValueError("duplicate_observation")
            observations[row["observation_id"]]=row
        elif row.get("observation_id") is not None:
            o=observations.get(row["observation_id"])
            if o is None or o["frame"]!=row["frame"]: raise ValueError("observation_link")
        if k=="call.started":
            if row["call_id"] in calls: raise ValueError("duplicate_call")
            calls[row["call_id"]]=row
        elif k.startswith("call."):
            c=calls.get(row["call_id"])
            if c is None or c["role"]!=row["role"] or c["frame"]!=row["frame"]:
                raise ValueError("call_link_or_frame_advance_during_wait")
        if k=="plan.installed":
            c=calls.get(row["call_id"])
            if c is None or c["role"]!="brain" or c["frame"]!=row["frame"] or row["plan_id"] in plans:
                raise ValueError("plan_call_link")
            plans[row["plan_id"]]=row
        if row.get("plan_id") is not None and row["plan_id"] not in plans:
            raise ValueError("unknown_plan")
        if k=="candidates.offered":
            offers[(row['observation_id'],row['plan_id'])]=row
        if k=="decision.selected":
            c=calls.get(row["call_id"])
            if row["decision_id"] in decisions:
                raise ValueError("decision_call_link")
            if row.get('selection_source')=='singleton_contract_no_model_choice':
                offered=offers.get((row['observation_id'],row['plan_id']),{}).get('actions',[])
                if (row['call_id'] is not None or row['model_choice'] is not None or
                        len(offered)!=1 or offered[0]['id']!=row['executor_choice']):
                    raise ValueError('invalid_singleton_contract_selection')
            elif c is None or c['role']!='controller' or c['frame']!=row['frame']:
                raise ValueError('decision_call_link')
            offered=offers.get((row['observation_id'],row['plan_id']),{}).get('actions',[])
            if row['executor_choice'] not in {a['id'] for a in offered}:
                raise ValueError('decision_not_offered')
            if row['model_choice'] is not None and row['model_choice']!=row['executor_choice']:
                raise ValueError('model_executor_mismatch')
            decisions[row["decision_id"]]=row
        if row.get("decision_id") is not None:
            d=decisions.get(row["decision_id"])
            if d is None or d["plan_id"]!=row.get("plan_id"): raise ValueError("decision_plan_link")
        if k=="execution.started":
            d=decisions[row["decision_id"]]
            if row["execution_id"] in executions or row["action"]["id"]!=d["executor_choice"]:
                raise ValueError("execution_choice_link")
            offered=offers[(row['observation_id'],row['plan_id'])]['actions']
            if row['action'] not in offered: raise ValueError('execution_recipe_changed')
            action=Action.from_json(row['action']).validate()
            if not 0<row['scheduled_frames']<=action.frames: raise ValueError('execution_scheduled_frames')
            executions[row["execution_id"]]={"start":row,"frames":[],"action":action}
        if k=="frame.executed" and row.get("execution_id")!="bootstrap":
            x=executions.get(row.get("execution_id"))
            if x is None or row["decision_id"]!=x["start"]["decision_id"]:
                raise ValueError("executed_input_link")
            offset=len(x['frames']);index,part,part_offset=x['action'].phase(offset)
            if tuple(row['input_buttons'])!=part.buttons:
                raise ValueError('executed_input_link')
            if offset>=x['start']['scheduled_frames']: raise ValueError('execution_overrun')
            if meta.get('format_version')=='2.0.0' and (
                    row.get('action_frame_offset')!=offset or row.get('segment_index')!=index or
                    row.get('segment_frame_offset')!=part_offset):
                raise ValueError('executed_segment_link')
            x["frames"].append(row["frame"])
        if k=="execution.completed":
            x=executions.get(row["execution_id"])
            if x is None: raise ValueError("unknown_execution")
            start=x["start"]
            if (row["frame_start"]!=start["frame"] or row["frame_end"]!=row["frame"] or
                row["requested_frames"]!=start["action"]["frames"] or
                row["buttons"]!=(None if x['action'].segments else start['action']['buttons']) or
                row["executed_frames"]!=len(x["frames"]) or
                x["frames"]!=list(range(row["frame_start"]+1,row["frame_end"]+1))):
                raise ValueError("execution_feedback_mismatch")
            if meta.get('format_version')=='2.0.0':
                expected=[];remaining=len(x['frames']);cursor=start['frame']
                for i,part in enumerate(x['action'].program()):
                    n=min(part.frames,remaining)
                    if not n: break
                    expected.append({'index':i,'name':part.name,'buttons':list(part.buttons),
                        'planned_frames':part.frames,'frame_start':cursor,'frame_end':cursor+n,'executed_frames':n})
                    remaining-=n;cursor+=n
                if row.get('executed_segments')!=expected or row.get('discarded_remaining_frames')!=x['action'].frames-len(x['frames']):
                    raise ValueError('executed_segment_feedback')


def pack(root, destination):
    root=Path(root); verify(root)
    manifest=json.loads((root/"checksums.json").read_text())
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name in [x["path"] for x in manifest["files"]] + ["checksums.json"]:
            z.write(root/name, arcname=root.name+"/"+name)
    return str(destination)
