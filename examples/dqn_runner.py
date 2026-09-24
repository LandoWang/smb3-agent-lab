"""Bounded, headless reproduction of the published MarioDQN policy.

Pixels only enter the policy. Read-only RAM supplies upstream reward/stop signals.
No training, fallback controller, save-state search, or automatic episode retry.
"""
import argparse
import ast
from collections import deque
import gzip
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import random
import shutil
import subprocess
import time
import uuid

import cv2
import numpy as np
from PIL import Image
import stable_retro as retro
import torch
import torch.nn as nn
import torch.nn.functional as F

ROM_SHA256 = "4377a7f5e6eb50bdd2ac6f249bf1a7085500aca8eb41f38545c3a2731c51a579"
MODEL_SHA256 = "3232b5a6bc4adf61c6bb7a89d9c1dc74891cbe27f9eb1f938ec4f9d9ad38a144"
SOURCE_SHA256 = "99d3b03e35d32ccfb83243acdc3145ac41d7edea9672a0356dbbf7377785943f"
COMMIT = "ea6adb6e194e093ead6fd29b4ea768705609129f"
ACTION_NAMES = ["run_jump_right", "jump", "run_right", "walk_right", "walk_left", "jump_right", "idle"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def state(env):
    r = env.get_ram()
    return {"x": int(r[0x75])*256 + int(r[0x90]),
            "y": int(r[0x87])*256 + int(r[0xa2]),
            "dying_f1": int(r[0xf1]), "goal_d6": int(r[0xd6]),
            "far_23": int(r[0x23]), "lives_736": int(r[0x736]),
            "in_air_d8": int(r[0xd8]), "suit_ed": int(r[0xed])}


def save_state(env, path):
    data = env.em.get_state()
    Path(path).write_bytes(gzip.compress(data, mtime=0))
    return sha(data)


def reset_env(env, work):
    obs, info = env.reset(seed=1)
    ready = work / "bootstrap/ready.state.gz"
    if ready.exists():
        audit = json.loads((work / "bootstrap/audit.json").read_text())
        raw = gzip.decompress(ready.read_bytes())
        assert sha(raw) == audit["final_state_sha256"]
        env.em.set_state(raw)
        obs = env.get_screen()
    return obs, info


def make_env(work):
    rom = ROM_PATH
    raw = rom.read_bytes()
    assert sha(raw) == ROM_SHA256, "User ROM hash mismatch"
    games = [g for g in retro.data.list_games() if g in ("SuperMarioBros3-Nes", "SuperMarioBros3-Nes-v0")]
    assert len(games) == 1, games
    game = games[0]
    metadata = Path(retro.data.get_file_path(game, "metadata.json"))
    source = metadata.parent
    expected = (source / "rom.sha").read_text().split()
    assert hashlib.sha1(raw[16:]).hexdigest() in expected, "ROM not the emulator integration's expected revision"
    dest = work / "integration" / game
    dest.mkdir(parents=True, exist_ok=True)
    for p in source.iterdir():
        if p.suffix in (".json", ".state", ".sha"):
            target = dest / p.name
            if not target.exists():
                shutil.copy2(p, target)
    link = dest / "rom.nes"
    if not link.exists():
        link.symlink_to(rom)
    retro.data.Integrations.add_custom_path(str(dest.parent))
    chosen = json.loads((work / "selection.json").read_text())["selected"]
    env = retro.make(game=game, state=chosen, inttype=retro.data.Integrations.CUSTOM_ONLY, render_mode="rgb_array")
    assert env.buttons == ['B', None, 'SELECT', 'START', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'A'] or env.buttons == ['B', 'None', 'SELECT', 'START', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'A'], env.buttons
    return env, source


def load_policy():
    source = POLICY_SOURCE.read_bytes()
    assert sha(source) == SOURCE_SHA256
    # Copy only the reviewed architecture/action definitions, never upstream main.
    tree = ast.parse(source)
    allowed = {"NoisyLinear", "layer_init", "DQN", "selection_to_action"}
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in allowed]
    assert {n.name for n in nodes} == allowed
    ns = {"torch": torch, "nn": nn, "F": F, "np": np, "math": math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "reviewed_upstream_definitions", "exec"), ns)
    model_path = CHECKPOINT
    assert sha(model_path.read_bytes()) == MODEL_SHA256
    agent = ns["DQN"](7, 4).to("cpu")
    agent.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True), strict=True)
    # Upstream playback does not call eval(): keep its NoisyNet behavior.
    agent.train()
    return agent, ns["selection_to_action"]


def preprocess(obs):
    # Intentionally preserve author's BGR grayscale conversion on RGB observations.
    return torch.from_numpy(cv2.cvtColor(cv2.resize(obs, (84, 84)), cv2.COLOR_BGR2GRAY).copy())


def prepare(work):
    env, source = make_env(work)
    obs, _ = reset_env(env, work)
    target = work / "preflight"
    target.mkdir(exist_ok=False)
    Image.fromarray(obs).save(target / "initial.png")
    initial_state = env.em.get_state()
    info = {"game": env.gamename, "default_state": env.statename, "buttons": env.buttons,
            "shape": list(obs.shape), "initial": state(env), "initial_state_sha256": sha(initial_state),
            "integration": str(source), "rom_sha256": ROM_SHA256, "probes": []}
    # Scripted calibration only. Restore the identical initial state for each probe.
    for label, action in [("right_12", [0,0,0,0,0,0,0,1,0]), ("jump_12", [0,0,0,0,0,0,0,0,1])]:
        obs, _ = reset_env(env, work)
        before = state(env)
        for _ in range(12):
            obs, _, _, _, _ = env.step(action)
        after = state(env)
        Image.fromarray(obs).save(target / f"{label}.png")
        info["probes"].append({"label": label, "buttons": action, "frames": 12, "before": before, "after": after})
    agent, action_fn = load_policy()
    info["model_parameters"] = sum(p.numel() for p in agent.parameters())
    info["model_actions"] = [action_fn(i) for i in range(7)]
    info["checks"] = {"move_right": info["probes"][0]["after"]["x"] > info["initial"]["x"],
                      "jump_up": info["probes"][1]["after"]["y"] < info["initial"]["y"],
                      "alive": all(p["after"]["dying_f1"] == 0 for p in info["probes"])}
    dump(target / "report.json", info)
    env.close()
    print(json.dumps(info), flush=True)
    assert all(info["checks"].values()), "Calibration failed; do not start policy episode"


def run(work):
    preflight = json.loads((work / "preflight/report.json").read_text())
    assert all(preflight["checks"].values())
    random.seed(1); np.random.seed(1); torch.manual_seed(1)
    torch.set_num_threads(2)
    env, integration = make_env(work)
    obs, _ = reset_env(env, work)
    agent, action_fn = load_policy()
    obs, _ = reset_env(env, work)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-smb3-dqn-" + uuid.uuid4().hex[:8]
    root = work / "runs" / run_id
    root.mkdir(parents=True, exist_ok=False)
    for name in ("states", "inputs", "frames"):
        (root / name).mkdir()
    fps = float(env.metadata.get("video.frames_per_second", 60))
    initial = state(env)
    candidates = [{"id": i, "name": ACTION_NAMES[i], "buttons": action_fn(i), "frames": 4} for i in range(7)]
    manifest = {"run_id": run_id, "parent_commit": COMMIT, "seed": 1, "device": "cpu", "training": False,
                "stage_draw": json.loads((work / "selection.json").read_text()),
                "model": "ToadAIStation/MarioDQN/pretrained_model/agent_model_5100000", "model_sha256": MODEL_SHA256,
                "upstream_source_sha256": SOURCE_SHA256, "runner_sha256": sha(Path(__file__).read_bytes()),
                "rom_sha256": ROM_SHA256, "policy_observation": "4x84x84 grayscale pixels only",
                "reward_and_termination": "read-only RAM assisted; upstream signals plus explicit safety limits",
                "initial": initial, "game": env.gamename, "default_state": env.statename,
                "buttons": env.buttons, "candidates": candidates, "fps": fps,
                "noisy_network": "train mode and reset_noise before each decision, matching upstream playback",
                "compatibility_changes": ["stable_retro import and versioned game ID", "headless recording", "CPU threads=2", "weights_only=True", "one episode, no reset on done", "preselected nontraining stage; D6 is object-slot velocity, not generic win flag: log upstream reward but only stop for independently checked end-level/map-transition candidates"],
                "limits": {"wall_seconds": MAX_WALL, "game_frames": MAX_FRAMES, "deaths": 1, "episodes": 1},
                "cost": {"cloud_model_requests": 0, "cloud_model_usd": 0, "vm_usd": None},
                "versions": {p: importlib.metadata.version(p) for p in ("torch", "numpy", "stable-retro", "gymnasium", "opencv-python-headless")},
                "integration_hashes": {p.name: sha(p.read_bytes()) for p in integration.iterdir() if p.suffix in (".json", ".sha", ".state")}}
    core = Path(retro.get_core_path(env.system))
    manifest["scripted_setup"] = (json.loads((work / "bootstrap/audit.json").read_text()) if (work / "bootstrap/audit.json").exists() else None)
    manifest["emulator_core"] = {"system": env.system, "path": str(core), "sha256": sha(core.read_bytes())}
    manifest["initial_state_sha256"] = save_state(env, root / "states/initial.state.gz")
    dump(root / "manifest.json", manifest)
    Image.fromarray(obs).save(root / "frames/initial.png")
    h, w = obs.shape[:2]
    video = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(root / "video.mp4")], stdin=subprocess.PIPE)
    video.stdin.write(obs.tobytes())
    stack = deque([preprocess(obs)]*4, maxlen=4)
    max_x = initial["x"]
    stagnant = frames = decisions = 0
    total_reward = 0.0
    reason = "unknown"
    started = time.monotonic()
    latencies = []
    previous_hash = "0"*64
    print(json.dumps({"run_id": run_id, "status": "running"}), flush=True)
    try:
        with (root / "decisions.jsonl").open("x") as logs, (root / "trajectory.jsonl").open("x") as trajectory:
            while True:
                if time.monotonic() - started >= MAX_WALL or frames >= MAX_FRAMES:
                    reason = "wall_limit" if time.monotonic() - started >= MAX_WALL else "frame_limit"
                    break
                decisions += 1
                tensor = torch.stack(list(stack), dim=-1)
                np.savez_compressed(root / "inputs" / f"{decisions:05d}.npz", observation=tensor.numpy())
                t = time.perf_counter()
                agent.reset_noise()
                with torch.inference_mode():
                    q = agent.get_qvals(tensor.float())[0]
                    choice = int(q.argmax().item())
                latency = (time.perf_counter()-t)*1000
                latencies.append(latency)
                before = state(env)
                start_frame = frames
                reward = 0.0
                terminated = truncated = False
                for _ in range(min(4, MAX_FRAMES - frames)):
                    obs, _, terminated, truncated, _ = env.step(action_fn(choice))
                    frames += 1
                    video.stdin.write(obs.tobytes())
                    now = state(env)
                    r = -0.0025
                    end_reward = 0.0
                    if now["dying_f1"] > 0:
                        terminated = True; end_reward = -2.0; reason = "death"
                    elif LEGACY_GOAL and now["goal_d6"] == 216:
                        terminated = True; reason = "legacy_w1_1_goal_candidate_requires_visual_confirmation"
                    elif env.get_ram()[0x559] > 0:
                        terminated = True; reason = "end_level_runoff_candidate"
                    elif env.get_ram()[0x14] > 0:
                        terminated = True; reason = "map_transition_candidate_not_automatically_a_win"
                    if now["goal_d6"] == 216 and now["dying_f1"] == 0:
                        end_reward = 5.0
                    delta = now["x"] - max_x
                    if delta > 0:
                        r += 0.01*delta; max_x = now["x"]; stagnant = 0
                    else:
                        stagnant += 1
                    if now["far_23"] >= 176:
                        r = 0.0
                    if stagnant > 180:
                        truncated = True
                        if not terminated:
                            reason = "upstream_stagnation"
                    reward += r + end_reward
                    stack.append(preprocess(obs))
                    trajectory.write(json.dumps({"frame": frames, "decision": decisions, "action": choice, "state": now, "reward": r+end_reward, "rgb_sha256": sha(obs.tobytes())})+"\n")
                    if terminated or truncated:
                        if reason == "unknown":
                            reason = "emulator_done"
                        break
                total_reward += reward
                state_hash = save_state(env, root / "states" / f"{decisions:05d}.state.gz")
                Image.fromarray(obs).save(root / "frames" / f"{decisions:05d}.png")
                event = {"decision": decisions, "start_frame": start_frame, "actual_frames": frames-start_frame,
                         "candidate_ids": list(range(7)), "q_values": q.tolist(), "selected": choice,
                         "action": candidates[choice], "latency_ms": latency, "before": before, "after": state(env),
                         "reward": reward, "state_sha256": state_hash, "previous_event_sha256": previous_hash}
                previous_hash = sha(json.dumps(event, sort_keys=True).encode())
                event["event_sha256"] = previous_hash
                logs.write(json.dumps(event)+"\n"); logs.flush()
                if decisions % 100 == 0:
                    print(json.dumps({"frames": frames, "x": max_x, "decisions": decisions}), flush=True)
                if terminated or truncated:
                    break
    except BaseException as exc:
        reason = "error_" + type(exc).__name__
        raise
    finally:
        video.stdin.close()
        code = video.wait(timeout=45)
        Image.fromarray(obs).save(root / "frames/final.png")
        summary = {"run_id": run_id, "stop_reason": reason, "game_frames": frames, "decisions": decisions,
                   "video_frames": frames+1, "game_seconds": frames/fps, "wall_seconds": time.monotonic()-started,
                   "max_x": max_x, "progress_pixels": max_x-initial["x"], "initial": initial, "final": state(env),
                   "deaths": int(reason == "death"), "reward": total_reward, "video_encoder_exit": code,
                   "median_inference_ms": float(np.median(latencies)) if latencies else None,
                   "p95_inference_ms": float(np.percentile(latencies,95)) if latencies else None,
                   "last_event_sha256": previous_hash, "cloud_model_requests": 0, "cloud_model_usd": 0,
                   "result_scope": "single seeded episode, not a success-rate estimate; upstream goal signal requires visual confirmation"}
        dump(root / "summary.json", summary)
        save_state(env, root / "states/final.state.gz")
        env.close()
        print(json.dumps(summary), flush=True)


def replay(work, run_id):
    root = work / "runs" / run_id
    env, _ = make_env(work)
    reset_env(env, work)
    env.em.set_state(gzip.decompress((root / "states/initial.state.gz").read_bytes()))
    events = [json.loads(x) for x in (root / "decisions.jsonl").read_text().splitlines()]
    trajectory = [json.loads(x) for x in (root / "trajectory.jsonl").read_text().splitlines()]
    i = 0
    previous_hash = "0"*64
    for event in events:
        claimed = event.pop("event_sha256")
        assert event["previous_event_sha256"] == previous_hash
        assert sha(json.dumps(event, sort_keys=True).encode()) == claimed
        previous_hash = claimed
        for _ in range(event["actual_frames"]):
            obs, _, _, _, _ = env.step(event["action"]["buttons"])
            expected = trajectory[i]
            assert sha(obs.tobytes()) == expected["rgb_sha256"], f"Frame {i+1} pixel mismatch"
            assert state(env) == expected["state"], f"Frame {i+1} RAM mismatch"
            i += 1
    assert i == len(trajectory)
    env.close()
    report = {"run_id": run_id, "replayed_frames": i, "all_pixels_and_ram_match": True, "event_chain_valid": True,
              "model_calls": 0, "classification": "recorded-input audit, not another policy episode"}
    assert not (root / "replay-audit.json").exists(), "Audit already exists; do not overwrite"
    dump(root / "replay-audit.json", report)
    print(json.dumps(report), flush=True)


def bootstrap(work, frames):
    """Neutral scripted setup only; no policy, training, or RAM writes."""
    out = work / "bootstrap"
    out.mkdir(exist_ok=False)
    env, _ = make_env(work)
    obs, _ = env.reset(seed=1)
    save_state(env, out / "original.state.gz")
    records = []
    for frame in range(1, frames + 1):
        obs, _, _, _, _ = env.step([0]*9)
        records.append({"frame": frame, **state(env), "rgb_sha256": sha(obs.tobytes())})
        if state(env)["dying_f1"]:
            raise RuntimeError("Death during neutral setup; policy not started")
    Image.fromarray(obs).save(out / "ready.png")
    digest = save_state(env, out / "ready.state.gz")
    dump(out / "audit.json", {"classification": "scripted neutral setup, not policy gameplay",
         "frames": frames, "buttons": [0]*9, "model_calls": 0,
         "final_state_sha256": digest, "records": records})
    env.close()


def confirm(work, run_id):
    """Observe the final state with neutral inputs; never automatically label victory."""
    root = work / "runs" / run_id
    out = root / "post-terminal"
    out.mkdir(exist_ok=False)
    env, _ = make_env(work)
    env.reset(seed=1)
    raw = gzip.decompress((root / "states/final.state.gz").read_bytes())
    env.em.set_state(raw)
    obs = env.get_screen()
    h, w = obs.shape[:2]
    video = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", "60",
        "-i", "pipe:0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(out / "video.mp4")], stdin=subprocess.PIPE)
    records = []
    for frame in range(1, 301):
        obs, _, _, _, _ = env.step([0]*9)
        video.stdin.write(obs.tobytes())
        records.append({"frame": frame, **state(env)})
        if frame % 60 == 0:
            Image.fromarray(obs).save(out / f"{frame:03d}.png")
    video.stdin.close()
    if video.wait(timeout=30) != 0:
        raise RuntimeError("Video encoding failed")
    dump(out / "audit.json", {"classification": "post-terminal neutral observation, not another policy trial",
         "source_state_sha256": sha(raw), "model_calls": 0, "frames": 300, "records": records,
         "completion": "requires human visual confirmation"})
    env.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run", "replay", "confirm"])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--policy-source", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--stage", choices=["w1-1", "w1-3", "fortress", "airship"])
    parser.add_argument("--run-id")
    parser.add_argument("--max-frames", type=int, default=18000)
    parser.add_argument("--max-wall", type=int, default=600)
    args = parser.parse_args()
    if args.max_frames < 1 or args.max_wall < 1:
        parser.error("Limits must be positive")
    if args.mode in ("prepare", "run") and (not args.policy_source or not args.checkpoint):
        parser.error("--policy-source and --checkpoint are required for prepare/run")
    if args.mode in ("replay", "confirm") and (not args.run_id or Path(args.run_id).name != args.run_id):
        parser.error("Supply a run ID, not a path")
    work = args.work.resolve()
    if "/dev/shm" in str(work) or "/dev/shm" in str(args.rom.resolve()):
        parser.error("Shared-memory storage is unsupported; use disk")
    ROM_PATH = args.rom.resolve()
    POLICY_SOURCE = args.policy_source.resolve() if args.policy_source else None
    CHECKPOINT = args.checkpoint.resolve() if args.checkpoint else None
    MAX_FRAMES, MAX_WALL = args.max_frames, args.max_wall
    stages = {"w1-1": "1Player.World1.Level1", "w1-3": "1Player.World1.Level3",
              "fortress": "1Player.World1.Fortress", "airship": "1Player.World1.Castle"}
    if args.mode == "prepare":
        if not args.stage:
            parser.error("--stage is required for prepare")
        work.mkdir(parents=True, exist_ok=False)
        dump(work / "selection.json", {"selected": stages[args.stage], "stage": args.stage,
             "selection_method": "explicit CLI choice", "policy_seed": 1,
             "legacy_w1_1_goal_candidate": args.stage == "w1-1"})
        if args.stage == "airship":
            bootstrap(work, 600)
    selection = json.loads((work / "selection.json").read_text())
    if args.stage and selection["selected"] != stages[args.stage]:
        parser.error("Stage differs from the prepared session")
    LEGACY_GOAL = selection.get("legacy_w1_1_goal_candidate", False)
    if args.mode == "prepare":
        prepare(work)
    elif args.mode == "run":
        run(work)
    elif args.mode == "replay":
        replay(work, args.run_id)
    else:
        confirm(work, args.run_id)
