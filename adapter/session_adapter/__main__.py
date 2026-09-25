import argparse
from dataclasses import asdict
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import sys
import uuid
from .backends import CodexBackend, HTTPBackend, Scripted
from .engine import Runner, Schedule
from .profiles.fixture import Fixture
from .recording import Redactor, Session, pack, verify


ROOT=Path(__file__).resolve().parent.parent


def env_path(name):
    value=os.environ.get(name)
    if not value: raise ValueError("missing_required_environment_reference")
    return value


def backend(config,workspace,seed):
    kind=config["kind"]
    if kind=="scripted_fixture": return Scripted()
    if kind=="codex":
        return CodexBackend(config["model"],workspace)
    return HTTPBackend(kind,model=config.get("model"),seed=seed,
        private_config=env_path(config["private_config_env"]) if config.get("private_config_env") else None,
        endpoint=env_path(config["endpoint_env"]) if config.get("endpoint_env") else None,
        token_endpoint=env_path(config["token_endpoint_env"]) if config.get("token_endpoint_env") else None,
        reserve_tokens=config.get("reserve_tokens",128),expected_revision=config.get("expected_revision"))


def run(config,output,allow_live=False):
    live=config["profile"]["kind"]!="fixture" or any(config[r]["kind"]!="scripted_fixture" for r in ("brain","controller"))
    if live and not allow_live: raise ValueError("live_requires_explicit_flag")
    schedule=Schedule(**config.get("schedule",{}))
    schedule.validate()  # Reject invalid cadence before claiming/starting any emulator.
    seed=config.get("seed",1)
    runtime=Path(output)/"runtime"/uuid.uuid4().hex
    pc=config["profile"]
    if pc["kind"]=="fixture": profile=Fixture(**pc.get("options",{}))
    elif pc["kind"] in ("remote", "remote_smb3"):
        from .remote_profile import RemoteProfile
        profile=RemoteProfile(env_path(pc['endpoint_env']))
    else: raise ValueError("unknown_profile")
    # Backends launch no network/process work during construction except config parsing.
    brain=backend(config["brain"],runtime/"codex-workspace",seed)
    controller=backend(config["controller"],runtime/"controller-workspace",seed)
    session=Session(output,{"profile":profile.metadata,"seed":seed,"schedule":asdict(schedule),
        "backends":{"brain":brain.descriptor,"controller":controller.descriptor},
        "config_reference":config,"session_semantics":"one attempt; no automatic restore/retry"},
        Redactor([*brain.secrets,*controller.secrets]))
    # Snapshot only allowlisted source/config, never environment files or installed credentials.
    for source in sorted((ROOT/"session_adapter").rglob("*.py")):
        session.asset("code/"+str(source.relative_to(ROOT)),source.read_bytes())
    for name in ("README.md","FORMAT.md","PROVENANCE.md"):
        if (ROOT/name).exists(): session.asset("code/"+name,(ROOT/name).read_bytes())
    # The remote service owns its game harness and must report its provenance.
    # Never require or snapshot a publisher's private sibling checkout here.
    return Runner(session,profile,brain,controller,schedule).run()


def main():
    p=argparse.ArgumentParser(description="Game-neutral frame-stepped session adapter")
    s=p.add_subparsers(dest="command",required=True)
    r=s.add_parser("run");r.add_argument("config");r.add_argument("--output",default=str(ROOT/"sessions"));r.add_argument("--allow-live",action="store_true")
    d=s.add_parser("demo");d.add_argument("--output",default=str(ROOT/"sessions"))
    v=s.add_parser("verify");v.add_argument("session")
    a=s.add_parser("pack");a.add_argument("session");a.add_argument("destination")
    w=s.add_parser("serve");w.add_argument("session");w.add_argument("--port",type=int,default=0)
    c=s.add_parser("codex-probe");c.add_argument("--workspace",default=str(ROOT/"runtime"/"probe"))
    args=p.parse_args()
    if args.command in ("run","demo"):
        cfg=json.loads((ROOT/"profiles"/"fixture.json" if args.command=="demo" else Path(args.config)).read_text())
        root=run(cfg,args.output,getattr(args,"allow_live",False));print(json.dumps({"session":str(root),**verify(root)}))
    elif args.command=="verify": print(json.dumps(verify(args.session)))
    elif args.command=="pack": print(pack(args.session,args.destination))
    elif args.command=="serve":
        root=Path(args.session).resolve();verify(root)
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root))
        server=http.server.ThreadingHTTPServer(("127.0.0.1",args.port),handler)
        print(f"http://127.0.0.1:{server.server_port}/",flush=True);server.serve_forever()
    elif args.command=="codex-probe":
        b=CodexBackend("not-used-no-model-request",args.workspace)
        try: print(json.dumps(b.initialize()))
        finally: b.close()


if __name__=="__main__":
    try: main()
    except Exception as e:
        print(json.dumps({"error_type":type(e).__name__,"message":"Operation failed; private details intentionally omitted."}),file=sys.stderr)
        sys.exit(1)
