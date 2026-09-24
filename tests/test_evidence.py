import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify", ROOT / "tools/verify_records.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class EvidenceTests(unittest.TestCase):
    def test_all_published_runs(self):
        paths = sorted((ROOT / "evidence").glob("*/summary.json"))
        self.assertEqual(len(paths), 4)
        self.assertEqual(sum(verify.verify_run(p.parent)["frames"] for p in paths), 3058)

    def fixture(self):
        path = next((ROOT / "evidence").glob("*/summary.json")).parent
        event = json.loads((path / "decisions.jsonl").read_text().splitlines()[0])
        rows = [json.loads(x) for x in (path / "trajectory.jsonl").read_text().splitlines()[:event["actual_frames"]]]
        summary = {"game_frames": len(rows), "decisions": 1, "last_event_sha256": event["event_sha256"]}
        return event, rows, summary

    def verify_fixture(self, event, rows, summary):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "summary.json").write_text(json.dumps(summary))
            (root / "decisions.jsonl").write_text(json.dumps(event) + "\n")
            (root / "trajectory.jsonl").write_text("".join(json.dumps(x)+"\n" for x in rows))
            return verify.verify_run(root)

    def test_valid_prefix(self):
        self.verify_fixture(*self.fixture())

    def test_action_tamper(self):
        event, rows, summary = self.fixture()
        event["selected"] = 99
        with self.assertRaises(ValueError):
            self.verify_fixture(event, rows, summary)

    def test_frame_omission(self):
        event, rows, summary = self.fixture()
        with self.assertRaises(ValueError):
            self.verify_fixture(event, rows[:-1], summary)

    def test_trajectory_tamper(self):
        event, rows, summary = self.fixture()
        rows[0]["action"] = 99
        with self.assertRaises(ValueError):
            self.verify_fixture(event, rows, summary)

    def test_summary_tamper(self):
        event, rows, summary = self.fixture()
        summary["game_frames"] += 1
        with self.assertRaises(ValueError):
            self.verify_fixture(event, rows, summary)

    def test_endpoint_tamper(self):
        event, rows, summary = self.fixture()
        rows[-1]["state"]["x"] += 1
        with self.assertRaises(ValueError):
            self.verify_fixture(event, rows, summary)

    def test_runner_parses(self):
        import ast
        ast.parse((ROOT / "examples/dqn_runner.py").read_text())


if __name__ == "__main__":
    unittest.main()
