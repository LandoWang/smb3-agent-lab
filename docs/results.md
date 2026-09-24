# Results, evidence, and limits

Recorded on 2026-09-24. Each DQN row represents one policy episode, with policy seed 1 and the same published checkpoint. No training, fallback actions, cloud-model requests, GPU access, or automatic retry.

| Stage | Frames | Decisions | Progress px | Median / p95 inference ms | Stop |
|---|---:|---:|---:|---:|---|
| W1-1 | 1147 | 287 | 2658 | 2.223 / 3.126 | Upstream goal heuristic; subsequently visually confirmed |
| W1-3 | 668 | 167 | 491 | 2.303 / 2.491 | 181-frame stagnation |
| W1 Fortress | 303 | 76 | 170 | 2.274 / 5.791 | 181-frame stagnation |
| W1 Airship | 940 | 235 | 548 | 2.249 / 2.522 | 181-frame stagnation |

All four ended with zero detected deaths. The airship episode lost its starting powerup. Model API cost was $0; VM cost was not measured. Policy-loop wall time including logging/encoding, excluding setup: 4.968, 2.734, 1.178, 3.952 seconds respectively.

## What counts as success?

The author's W1-1 playback heuristic tests RAM byte $D6 == 216. Disassembly places $D6 inside an object-slot vertical velocity array, **not a general completion flag**.

We restored the exact terminal W1-1 state and executed 300 neutral frames, without calling the policy. The screen explicitly showed COURSE CLEAR / YOU GOT A CARD. That independent observation supports one W1-1 clearance. [Clear screenshot](../assets/w1-1-clear.png). The appended completion animation is not additional policy play.

For other levels, end-level runoff ($559) and map transition ($14) are only stop candidates, requiring visual interpretation. Stagnation, death, budget exhaustion, and completion must remain separate outcomes.

## Start states and selection

- W1-1: Stable-Retro's course-start state, small Mario.
- W1-3: one random draw, selection seed 5567945738785088911, Python random.Random(seed).choice(sorted(candidates)). Candidates were Fortress and Level3. No reroll; not a uniform draw over the whole game. Built-in state has raccoon form and existing score/cards.
- Fortress: deliberately chosen unused built-in state; raccoon form.
- Airship: deliberately chosen Castle state; starts with boarding animation. Exactly 600 scripted neutral setup frames were logged separately; policy begins on deck as Super Mario at X144/Y160. No RAM writes.

Different forms and starting game progress confound comparisons. These four episodes do not estimate win rates, prove a generalization ceiling, or establish relative model superiority.

## Controller details

The 3,298,480-parameter CNN uses four consecutive 84×84 grayscale frames and seven discrete actions. It is a dueling noisy DQN, not an LLM. Each decision executes up to four frames. NoisyNet noise is reset per decision, preserving upstream playback behavior. We preserve the author's BGR-to-gray conversion even though the environment returns RGB.

The policy receives pixels only. Read-only RAM supplies reward, stopping, and audit. This is distinct from the memory-conditioned observations used in the Astra/Jev experiments.

## Evidence layers

The four directories under [evidence](../evidence) contain:

- original decision JSONL, including all seven Q values, selected buttons, actual frame count, before/after RAM, rewards, timings, and a hash chain;
- original per-frame state/input/RGB-hash traces;
- original summaries and replay-audit reports;
- an explicitly allowlisted metadata export, with the original manifest's SHA256.

The original pixel/state replay matched all 3058 policy frames. Published logs can be structurally verified without a ROM, but a recorded audit report is **not** equivalent to independently replaying the emulator. State binaries and pixel-input arrays are deliberately not published; fresh local runs generate them.

The historical runner hashes remain in each manifest. The portable public runner is a later adaptation, not retroactively the source of these historical episodes.

## Historical planner experiments

The last sampled DiffusionGemma route trial recorded 31 local decisions, 5 Astra plans, 8 completed route nodes, and death at X581/Y352 after 288 game frames. It is not a level clearance. Two sampled actions differed from the raw model argmax. This single uncontrolled attempt does not demonstrate that sampling improves survival.

The archived CLM trial included 56 single-candidate actions constrained by Astra and only 5 actual CLM choices. It must not be described as independent CLM success.

These earlier experiments are summarized from preserved records; their raw provider logs and private service configurations are not part of this preview.
