# SMB3 Agent Lab

Experiments in planning, low-latency control, and auditable evaluation in **Super Mario Bros. 3**.

**Research preview · September 2026.** We study how a high-level planner, a local action selector, and an emulator harness work together. This is an experiment journal and reproducibility toolkit—not a full-game solver or a benchmark leaderboard.

## Start here

- [中文说明](README.zh-CN.md)
- [Frame-stepped session adapter: offline demo and model interfaces](adapter/README.md)
- [Adapter pilots, context limits and pit failure](docs/adapter-results.md)
- [Recorded results and limitations](docs/results.md)
- [Architecture and experiment history](docs/architecture.md)
- [Memory assistance and physics findings](docs/memory-and-physics.md)
- [Reproduce the DQN trials](docs/reproduce.md)
- [Release validation](docs/release-validation.md)
- [Third-party provenance and licensing](THIRD_PARTY.md)

## What actually ran?

| Experiment | Evidence | Status |
|---|---|---|
| Astra + OpenRouter Jev | Archived, memory-assisted model-control experiments | Historical; adapter now includes transport code, not bundled services or a fresh Jev result |
| Astra + local DiffusionGemma | Route plans, action candidates, sampled choices, execution feedback | Historical; local Jev-like controller, **not** OpenRouter Jev |
| Astra + published CLM | Controller comparison with planner-restricted candidates | Historical; not an independent CLM clearance |
| Published MarioDQN checkpoint | Four recorded single-episode trials; deterministic input replay | Portable CPU evaluation example included |
| Jev supervising DQN | Proposed handoff/control architecture | **Not implemented or evaluated** |
| Session adapter + Codex/local selector | Frame/plan/decision audit, synthetic tests, reported memory-assisted pilots | Public core/client included; game and model services remain external |

## DQN: one successful course, three stopped transfers

These are reproductions of [ToadAIStation/MarioDQN](https://github.com/ToadAIStation/MarioDQN), **not a model trained by this project**.

| Start state | Policy time | Max forward progress | Deaths | Observed outcome |
|---|---:|---:|---:|---|
| World 1-1 | 19.12 s | 2,658 px | 0 | Course clear, independently confirmed after policy stopped |
| World 1-3 | 11.13 s | 491 px | 0 | Stopped at brick steps by inherited stagnation rule |
| World 1 Fortress | 5.05 s | 170 px | 0 | Stopped at opening stone steps by inherited stagnation rule |
| World 1 Airship | 15.67 s | 548 px | 0 | Damaged, then stopped near vertical cannon by inherited stagnation rule |

One seed per start state; different starting powerups; **not success-rate estimates**. Stagnation means 181 frames without a new maximum X, not death or proof the policy cannot finish. Airship includes a separate scripted boarding setup.

CPU inference median: about **2.2–2.3 ms** in these trials. Every recorded policy frame passed an input-replay comparison of RGB hashes and scoped RAM. Offline tools in this repo verify the published logs; replaying the emulator additionally requires your own ROM and locally generated save states.

### Watch

[World 1-1: policy + clearly separated completion observation](assets/w1-1-with-clear.mp4) ·
[World 1-3](assets/w1-3.mp4) ·
[Fortress](assets/fortress.mp4) ·
[Airship](assets/airship.mp4)

The W1-1 presentation appends 300 neutral frames after the policy stopped to show the course-clear screen. They are **scripted observation**, not extra model play.

![Verified course-clear screen](assets/w1-1-clear.png)

## Verify the included evidence — no ROM or models required

```sh
python3 tools/verify_records.py evidence
python3 -m unittest discover -s tests -v
```

For actual gameplay, see [reproduction instructions](docs/reproduce.md). You provide your own legally obtained ROM, and separately obtain any third-party model/source under its applicable terms. Nothing downloads a ROM or silently calls a paid API.

The new [session adapter](adapter/README.md) also runs without a ROM or API key:

```sh
cd adapter
python3 -m unittest discover -s tests -v
python3 -m session_adapter demo --output ../output/adapter-demo
```

This demo is a **scripted synthetic environment**, not Mario or a model result.

## Design principles

- **Advance frames → pause → decide.** Model latency affects wall time, not unobserved emulator time.
- Plans must refer to executable actions and measurable termination conditions.
- Log candidates, chosen inputs, actual frame counts, rewards, deaths, model costs, and stop reasons.
- Keep scripted calibration, memory-assisted control, pixel-policy evaluation, and hypothetical designs distinct.
- Preserve failures and earlier versions. Never turn a stopped run into an unreported retry.

## Scope and safety

No ROM, model weights, ROM-derived full maps, emulator save states, cloud credentials, private endpoints, or personal workspace archives are included. Gameplay media contains third-party game imagery; it is not licensed as our original artwork. See [THIRD_PARTY.md](THIRD_PARTY.md).

The preview includes DQN evaluation/evidence and a portable session-adapter core. Game harnesses, emulator services and model serving remain separately provisioned; this is not a one-command full-stack deployment. Session debug bundles remain private unless separately reviewed.

Our original code and documentation are MIT-licensed; third-party materials retain their own rights.
