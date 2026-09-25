# Remote Profile contract

The shipped `remote_profile.RemoteProfile` is a synchronous client, not an
emulator server. It connects only to HTTP on `localhost` or `127.0.0.1`, normally
an SSH tunnel to an isolated service you own. No remote credentials are logged.
The RPC protocol has **no built-in authentication**: do not expose it publicly.

Each POST to `/rpc` has `{"seq": 0, "method": "claim", "params": {}}` with a
strictly increasing sequence number. Success is HTTP 200 with the matching
`seq` and `result`. Lost/invalid responses are errors, never automatic retries.
The client caps a response at 4,000,000 bytes and uses a 20-second socket timeout.
The server must advance **exactly one emulator frame per `advance` request** and
never run autonomously while a model is deciding. This is a trust contract, not
something the client can prove merely from a successful response.

Methods:

- `claim`: one exclusive owner per attempt; returns metadata, skills, metric_names,
  bootstrap_frames, all action recipes, and the initial sample.
- `advance`, params `{"buttons":["RIGHT","A"]}`: execute exactly one frame,
  return the new sample. Reject inputs outside the profile's supported recipes
  and any further advance after a terminal state.
- `checkpoint`: return `{"data":"BASE64_SAVE_BYTES"}`. This is read-only capture,
  not a restore or retry operation.
- `close`: release the owned emulator. No new attempt or respawn is implied.

Required metadata contracts are `action_program_contract="segments-v1"` and
`intent_contract="ordered-goals-v1"`. Also provide a game/profile version, FPS,
observation mode, emulator version, input/checkpoint hashes where applicable,
metric-based goal verifiers, limitations and reward source. Label raw-memory,
pixel-only, scripted or memory-modified conditions honestly. The remote service's
source/ROM/core hashes belong in provenance; the generic adapter does not possess
or redistribute those files.

An action is the JSON form of `contracts.Action`: id, skill, buttons, frames,
optional label/description and multi-phase segments. A phase can require observed
metrics via `(metric, "eq"|"ge"|"le", value)`; these are not predicted success.

Each sample is the JSON form of `contracts.Sample` plus:

- `views`: `brain` and `controller` dictionaries for role-specific observations;
- `eligibility`: action ID → `[eligible_boolean, reason_string]`;
- `image` and `memory`: base64 strings or null; other Sample fields are normal JSON.

Sample `state` supplies observations; `metrics` supplies numeric/boolean facts;
`events` can request observation/replanning; `terminal` carries the stopping
reason. `memory_interventions`, when applicable, records explicit writes separately
from model controls. Declaring an intervention does not validate that it is safe.
The core saves every supplied frame/sample and links it to its execution.

For an in-process game, implement `contracts.Profile` directly instead. The
synthetic implementation in `profiles/fixture.py` is a complete executable
reference. Its physics is not NES physics. `profiles/smb3_skills.py` demonstrates
explicit button recipes, not a memory decoder, emulator or collision solver.
