# Frame-stepped session adapter

A game-neutral loop connecting a **brain**, a **local action selector**, and a
**game profile**. It records what each component proposed and what actually ran.
Version 0.3.1 is a portable source export of the September 25 experiments, not a
new controller or a claim of improved Mario performance.

```text
profile observation + execution feedback
                 ↓
brain → ordered goals → controller → selected executable action
  ↑                                      ↓
  └──────── recorded outcome ← frame-by-frame executor
```

The adapter alone advances the simulation. Model waits consume wall time, not
game frames. Each Session is one attempt; there are no hidden restores/retries.

## Try it without a ROM, GPU, credentials or model requests

Python 3.11 or later; the core and fixture use only the standard library.
From the repository root:

```sh
cd adapter
python3 -m unittest discover -s tests -v
python3 -m session_adapter demo --output ../output/adapter-demo
```

The command prints a newly created Session path. Substitute that path below:

```sh
python3 -m session_adapter verify SESSION_PATH
python3 -m session_adapter serve SESSION_PATH
python3 -m session_adapter pack SESSION_PATH ../output/session-review.zip
```

`serve` prints an available loopback URL. The page shows recorded frames, brain
plans, controller choices and their linked inputs/responses. It is a replay of
a **scripted synthetic fixture**, not Mario gameplay or model performance.
`pack` creates a new archive; it never overwrites one. It includes only registered
Session artifacts, not sibling runtime/configuration files.

## Shipped and not shipped

| Included | Requires your own setup / intentionally excluded |
|---|---|
| Frame executor, ordered intent queue, cadence, exact input recipes | Game emulator, legally obtained ROM and initial save |
| Codex app-server and Azure Responses brain transports | Installed/authenticated provider client or private API configuration |
| OpenRouter Jev Decisions client | API credentials and paid live calls |
| Local DiffusionGemma client and token preflight | Compatible separately running model service and tokenizer |
| Loopback remote-profile client and Profile protocol | Your game-specific observation/memory harness and RPC server |
| Illustrative SMB3 motor vocabulary | A verified forward dynamics/collision model; none is implied by action names |
| Timeline, source snapshot, checksum/causal verification, archive writer | Private real-game Sessions, raw RAM, save states, full maps and deployment scripts |

The private SMB3 harness used in the experiments is **not** bundled here. Its
ROM-specific memory tables and enemy-ablation implementation stay outside this
publication. The remote client no longer assumes a private sibling source tree.
To use a game locally in Python, implement `contracts.Profile` and pass it to
`engine.Runner`; to use an existing isolated service, implement the documented
[RPC contract](REMOTE_PROFILE.md). This is not a complete one-command NES/model
deployment.

## Three clocks, one journal

- **Frame clock:** executed emulator steps. All input durations and planning
  intervals refer to this clock.
- **Brain calls:** observation frame, request, returned plan, latency, usage,
  installed goals and actual subsequent results.
- **Controller calls:** observation/plan reference, every offered action,
  response probabilities/selection, actual buttons, executed frames and interruption.

UTC timestamps and monotonic wall time are logged separately. A long brain wait
does not imply unobserved gameplay. See [FORMAT.md](FORMAT.md).

A Session contains `metadata.json`, authoritative `events.jsonl`, derived
`timeline.json`/`index.html`, `calls/`, `observations/`, `frames/`, optional `memory/`,
`states/`, a source snapshot and `checksums.json`. Images/frames are captured
when supplied by the Profile. The adapter does **not** encode MP4 or capture
audio; its HTML frame replay and any separately exported video are different
artifacts. Archived source snapshots are for review, not automatically executed.

## Planning and execution semantics

The brain supplies ordered intentions such as hitting a block, collecting an
item and crossing an obstacle. It cannot remove left/brake actions, change the
motor catalog, or execute buttons itself. Goals are not proof of success: a
location-region check verifies only location; unsupported item/collision goals
remain unverified until the Profile provides appropriate evidence.

Each candidate declares exact buttons and frames, optionally in multiple phases
with observed preconditions. Guards are rechecked before each phase. Execution
may stop at an observation, stage, cadence, hazard or terminal boundary, and the
unexecuted tail is discarded and logged. An A-only action means holding A; it
does not imply a second midair jump or cancellation of horizontal momentum.
The harness is an executor/auditor, **not a landing-safety oracle**.

Cadence fields are under `schedule`:

- `brain_min_frames` / `brain_every_frames`: ordinary review window; both 60
  means a normal 60-frame interval. Profile urgent events can bypass it.
- `decision_every_frames`: maximum scheduled action batch, also limited by the
  chosen recipe and interruption events. No per-frame model call is required.
- `request_timeout_s`: deadline for an individual model request.
- `max_frames`, `max_decisions`, `max_wall_s`: optional total limits; `null`
  disables that particular limit. Template budgets are examples, not changes
  to any recorded run.

Place a file named `STOP` in the active Session directory to request a stop.
The runner checks it between frames and while waiting for models. A pending
provider call may still complete/bill, but its late result is not executed.
Death, context terminal, invalid contract, token rejection or uncertain RPC step
ends the attempt. No uncertain step is automatically retried.

## Live backends: explicit opt-in, not exercised by the demo

The templates [codex + Jev](profiles/codex-jev.example.json) and
[codex + local DiffusionGemma](profiles/codex-local.example.json) require you to
replace `REPLACE_WITH_YOUR_CODEX_MODEL` with a model available to your account
and set each named environment reference. Then use:

```sh
python3 -m session_adapter run profiles/codex-jev.example.json --allow-live
```

Without `--allow-live`, every non-fixture configuration is rejected before
claiming the emulator. Do not run a live template merely to test installation.
The public tests simulate protocol responses; this publication does not make
new cloud or GPU inference calls.

`MARIO_ADAPTER_EMULATOR_URL` points to your own SSH-forwarded loopback service.
`MARIO_ADAPTER_OPENROUTER_CONFIG` names an external private file containing
`OPENROUTER_API_KEY=...`; never put the actual value in a profile or repository.
The loader parses the file without executing shell code. Existing Azure brain
support similarly takes an external file reference and validates the HTTPS domain;
it is not needed for the fixture or Codex templates. Deployment identifiers and
API keys are read from that file, never supplied by this repository.

Codex uses a separate `codex app-server` subprocess and a fresh provider thread
per Session, with reused conversation context for subsequent plans. Protocol
fixtures do not promise that every installed CLI has the same schema; check
compatibility with your own client before a live run.
Run it in an appropriately isolated, already authenticated service environment;
the adapter does not log in, copy credentials or change global configuration.
Tool requests are rejected, and shell/web/app/MCP features are disabled in the
owned process. Read-only mode alone is not a private-data isolation boundary.

### Jev versus local DiffusionGemma

They are different backends. Jev uses `typesafe/jev-1.13` on OpenRouter's Decisions
endpoint, not chat completions. [OpenRouter documents](https://openrouter.ai/docs/guides/community/jev)
a **32,000-token** context for the supplied state plus questions. A Session ID
groups requests; the adapter still supplies the relevant state and plan.

The local client requires compatible `/provenance`, `/tokenize` and
`/v1/systemone` interfaces. Its model alias comes from configuration; the tokenizer
reports the active context limit. It rejects requests when input tokens plus
`reserve_tokens` exceed that limit. Reserve defaults to 128 and is configurable.
The provenance backend must identify itself correctly; optional `expected_revision`
can pin a revision you supply. The repository contains no private revision pin,
internal upstream URL or engine launch/GPU configuration. Do not treat an unpinned
server's self-report as independently verified model identity.

All candidate descriptions count toward input size. v3 packing removes repeated
audit fields, retaining observations, current/upcoming goals, guidance and the
previously sampled trajectory. The full observation/journal remains on disk.
The public client uses the service-reported limit, rather than the private
experiment's fixed value. This packaging change is covered with synthetic tests,
not a new live-model result.

A deployed service window is not necessarily the architecture's maximum.
[Google's model card](https://huggingface.co/google/diffusiongemma-26B-A4B-it)
advertises up to 256K context. Expanding a particular service still needs separate
latency, memory and correctness validation. Changing an adapter guard alone does
not expand a server, and longer context does not guarantee better motion choices.
No existing service was changed for this publication.

## Privacy and evidence boundaries

Credentials are external; request/response logging redacts known configured
secrets and common secret fields, and error logs retain exception types rather
than raw provider bodies. This is a limited safeguard, not a general PII scrubber.
Observations and provider replies can contain private data. **Session bundles
are private debug artifacts** and must be separately reviewed before sharing.
Never upload runtime folders, authentication files, ROMs or save-state bundles.

Hashes and causal checks detect accidental corruption/inconsistent traces; they
are not a signed attestation that a malicious producer cannot fabricate. A
record-consistency check is also not an independent emulator replay. When usage
or prices are missing, total cost is unknown, not zero.

See [source provenance](PROVENANCE.md) and the [reported Mario pilot failures](../docs/adapter-results.md).
The [public validation report](../docs/adapter-validation.md) distinguishes synthetic
tests from historical live-game evidence.
