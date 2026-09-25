# Session adapter: reported pilot results and limits

Summaries of privately archived September 25 experiments, not a public benchmark
with redistributable RAM/save states. Their independent emulator replays were
performed locally. This release ships synthetic contract tests, not the private
inputs needed to reproduce these scores. No live model gameplay was performed
for publication.

Brain: a Codex planner. Selector: local DiffusionGemma through a separately
provided structured-choice frontend. It is **not OpenRouter Jev**. Specific
deployment names, revisions, runtime configuration and private source paths
are intentionally omitted from this public summary.

Same starting save, configuration and seed, one attempt per arm. Cloud plans
are not deterministic from that seed. Both read game memory; treatment also
suppressed verified enemy placements/slots. This is **memory-modified cheating**,
not fair gameplay. Player physics and terrain were not directly modified.

| Measurement | Normal | Enemy-suppressed |
|---|---:|---:|
| Game frames | 248 | 519 |
| Game duration | 4.13 s | 8.64 s |
| Wall duration | 208.59 s | 330.25 s |
| Maximum world X | 582.375 | 1142.125 |
| Brain calls | 7 | 10 |
| Local decisions | 32 | 53 |
| Largest input token count | 3860 | 3332 |
| Stop | death | suspected_death / pit scene |
| Verified level clear | No | No |

All 85 choices matched the selected executor action, subject to recorded
interruptions. Neither run hit the token guard. Independent replays matched all
248/519 RAM and pixel frames and both final saves. Treatment writes were recomputed
and checked during replay; replays made zero model calls.

Treatment made 14 direct byte writes: one active hostile cleared and 13 remaining
hostile spawn flags set. The protected end-card flag and object list were unchanged;
no active whitelisted hostile remained after any step. The ROM-specific table,
memory-write implementation and saves are not distributed here.

## Pit failure

At F451 the brain identified a suspected break near X=1088 and requested a
grounded landing at X=1024–1056. The controller selected A-only holds at F457/F469
while horizontal velocity stayed +2.5 pixels/frame, then repeatedly selected
RIGHT+A. A was held 80 consecutive frames, not new airborne jumps. Braking and
release actions were available, with explicit inertia/no-second-jump descriptions.

Mario descended into the pit. At F519 the monitored dying byte became 2, labeled
`suspected_death`; the profile stopped before a full life-loss animation. This is
neither a clear nor a surviving run just because its exact `death` count is zero.

This exposes a plan-to-motion gap. It does not prove an internal model belief,
that the requested landing was reachable, or that an alternative certainly saves
the state. No validated landing prediction exists. Enemy suppression changes
observations/plans/timing together, not just localization. Two attempts establish
no success rate or training conclusion. Total model/compute cost is unknown.

## Context packing

v3 removes repeated archival fields, preserving observations, goals, guidance,
sampled trajectory and all action criteria. A historical tokenizer-only regression
fit all 63 archived requests within that experiment's configured serving window.
This does not guarantee every future scene fits. The public client reads the
active limit from the caller-provided service; private engine settings are omitted.

See [adapter documentation](../adapter/README.md) and [provenance](../adapter/PROVENANCE.md).
