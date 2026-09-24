"""Verify published decision hash chains and frame accounting without a ROM.

This checks integrity/consistency, not whether reported emulator outcomes are true.
Full RGB replay requires the emulator, your ROM and locally generated save states.
"""
import argparse
import hashlib
import json
from pathlib import Path


def digest(event):
    return hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()


def verify_run(root):
    root = Path(root)
    summary = json.loads((root / "summary.json").read_text())
    events = [json.loads(line) for line in (root / "decisions.jsonl").read_text().splitlines()]
    trajectory = [json.loads(line) for line in (root / "trajectory.jsonl").read_text().splitlines()]
    previous = "0" * 64
    frame = 0
    for number, original in enumerate(events, 1):
        event = dict(original)
        claimed = event.pop("event_sha256")
        if event["previous_event_sha256"] != previous or digest(event) != claimed:
            raise ValueError(f"Broken hash chain at decision {number}")
        if event["decision"] != number or event["start_frame"] != frame:
            raise ValueError("Decision numbering/frame continuity mismatch")
        duration = event["actual_frames"]
        if type(duration) is not int or not 1 <= duration <= event["action"]["frames"]:
            raise ValueError("Invalid executed duration")
        selected = event["selected"]
        if selected not in event["candidate_ids"] or event["action"]["id"] != selected:
            raise ValueError("Selected action not in candidates")
        if len(event["q_values"]) != len(event["candidate_ids"]):
            raise ValueError("Missing candidate scores")
        for _ in range(duration):
            if frame >= len(trajectory):
                raise ValueError("Missing physical-frame record")
            row = trajectory[frame]
            if row["frame"] != frame + 1 or row["decision"] != number or row["action"] != selected:
                raise ValueError("Input/trajectory mismatch")
            frame += 1
        if trajectory[frame-1]["state"] != event["after"]:
            raise ValueError("Decision endpoint differs from frame trace")
        previous = claimed
    if frame != len(trajectory) or frame != summary["game_frames"]:
        raise ValueError("Total frame mismatch")
    if len(events) != summary["decisions"] or previous != summary["last_event_sha256"]:
        raise ValueError("Summary/chain mismatch")
    return {"run": root.name, "decisions": len(events), "frames": frame, "chain_valid": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    runs = sorted(p.parent for p in args.root.glob("*/summary.json"))
    if not runs:
        parser.error("No evidence runs found")
    for run in runs:
        print(json.dumps(verify_run(run)))
