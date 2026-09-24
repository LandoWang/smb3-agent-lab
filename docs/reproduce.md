# Reproduce the DQN evaluation

The public runner is adapted from the independently audited experiment harness. It does not ship the upstream architecture or weights. It is CPU-only and makes no model API calls.

## 1. Verify the public logs

```sh
python3 tools/verify_records.py evidence
python3 -m unittest discover -s tests -v
python3 tools/check_release.py
```

This needs only Python's standard library. It verifies chain/record consistency, not an independent game replay.

## 2. Prepare a Linux runtime and lawful inputs

Recorded runtime: Python 3.11, Stable-Retro 1.0.1, PyTorch 2.7.1+cpu. Install FFmpeg and the system libraries required by Stable-Retro/OpenCV (commonly libGL and libgomp).

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install torch==2.7.1+cpu --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

The dependency pins describe the tested core runtime, not a complete lock of every transitive dependency. Each new run records installed versions and emulator-core hashes. No container image is distributed in this preview.

Supply these files yourself:

| Input | Required identity |
|---|---|
| Legally obtained SMB3 USA Rev 1 ROM | SHA256 4377a7f5e6eb50bdd2ac6f249bf1a7085500aca8eb41f38545c3a2731c51a579 |
| Upstream playback source | SHA256 99d3b03e35d32ccfb83243acdc3145ac41d7edea9672a0356dbbf7377785943f |
| Upstream agent_model_5100000 | SHA256 3232b5a6bc4adf61c6bb7a89d9c1dc74891cbe27f9eb1f938ec4f9d9ad38a144 |

Source/checkpoint provenance and licensing caveat: [THIRD_PARTY.md](../THIRD_PARTY.md). Hash mismatch fails closed; do not normalize the upstream source's line endings. Never load arbitrary Python or pickle checkpoints from untrusted sources.

Keep ROM/source/model inputs outside this repository. Runtime output is ignored, but inspect files before sharing them: generated integration directories and save states are local-only artifacts.

## 3. Calibrate and run one episode

Replace the example paths with your local paths. Do not use shared-memory storage.

```sh
python examples/dqn_runner.py prepare \
  --stage w1-1 --work output/demo \
  --rom /path/to/your.nes \
  --policy-source /path/to/dqn_play_mario.py \
  --checkpoint /path/to/agent_model_5100000

python examples/dqn_runner.py run \
  --work output/demo --rom /path/to/your.nes \
  --policy-source /path/to/dqn_play_mario.py \
  --checkpoint /path/to/agent_model_5100000
```

Use a new work directory for each prepared start. Stages: w1-1, w1-3, fortress, airship. Policy seed is fixed at 1 to match the published episodes. Airship preparation records 600 neutral boarding frames and restores that endpoint before each movement/jump probe and policy run.

The policy uses all seven original actions and four-frame repeats. No training, automatic reset/retry, fallback control, or RAM writes. Default limits are 18000 game frames and 600 policy-loop wall seconds, stopping at first death, a completion/transition candidate, or the inherited 181-frame stagnation rule. For a short runtime check, pass --max-frames 13 --max-wall 60; the final action is shortened to respect the frame limit.

## 4. Audit your own run

Use the run ID printed by the runner:

```sh
python examples/dqn_runner.py replay \
  --work output/demo --rom /path/to/your.nes --run-id RUN_ID
```

Replay uses recorded inputs, no policy calls. It verifies per-frame pixels, scoped RAM, and the decision hash chain. It is an audit, not an additional success.

To inspect a possible course-clear animation:

```sh
python examples/dqn_runner.py confirm \
  --work output/demo --rom /path/to/your.nes --run-id RUN_ID
```

This advances 300 neutral frames from the saved endpoint in a separate output directory. **It never automatically certifies a win.** Check the screenshots/video. Existing audits and post-terminal observations are not overwritten.

## What changed for portability?

- Inputs/output paths are command-line arguments, not private machine paths.
- Explicit stage preparation and neutral airship setup.
- W1-1 retains the historical $D6 stop only as a visibly labelled candidate, not a universal win flag.
- Other stages use independently identified transition candidates; death takes precedence.
- Configurable positive frame/wall budgets, exact partial-action frame limit.
- No cloud configuration, private endpoints, downloaded model code, or bundled ROM.

These historical results were produced by the preserved original runner hashes in their manifests, not by pretending the later portable source existed earlier.
