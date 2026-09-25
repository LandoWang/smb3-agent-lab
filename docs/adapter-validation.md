# Public adapter validation

Publication validation, 2026-09-25. This is not a live gameplay benchmark.

- **78 public adapter tests passed.** Includes frame/call causality, no advancement
  during model waits, exact button segments, cadence, user/death/error stopping,
  discarded action tails, goal-verification boundaries, singleton provenance,
  transcript redaction, archive integrity, offline viewer escaping, fake Codex RPC,
  OpenRouter request shape and local token/revision guards.
- Local model limit/alias/revision tests use synthetic mocked responses, including
  rejecting overflow before inference and omitting internal upstream addresses.
  They do not validate a real model server or claim improved decisions.
- **8 existing evidence tests passed.** Original four DQN logs still verify:
  765 decisions and 3058 frames. Existing gameplay assets are unchanged.
- The public CLI completed a new **96-frame scripted fixture**, verified its
  journal, generated the replay page, served it on loopback and packed a portable
  review ZIP. No ROM, emulator, GPU inference, provider login or paid API call.
- Public release guard checks forbidden artifacts, credential patterns, private
  home-directory paths, local Markdown links and unchanged media hashes.
- Adapter-specific PII/deployment checks reject personal email strings, nonloopback
  IP addresses, private paths/mounts, keys, concrete cloud instance URLs, engine
  launch configuration and private artifact folders in staged/tracked adapter files.
- New commit identities use the public GitHub handle and GitHub noreply email.

Re-run from the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 tools/verify_records.py evidence
cd adapter
python3 -m unittest discover -s tests -v
cd ..
python3 tools/check_release.py
python3 tools/check_adapter_publication.py
```

Run the scans after tests finish, not while temporary fixture files are being
written. Stage intended new adapter files before the Git-index-based scan; it
does not examine untracked candidates. Review the actual staged diff as well.

Heuristic scans and manual review reduce publication risk; they are not a proof
that arbitrary future content contains no PII/secrets. Runtime session bundles
can contain private game/user/provider data and are not public-safe by default.
The public subset excludes real Sessions, saves, RAM, engine settings, machine
addresses, credentials, ROMs and model weights. Earlier local experiments were
not edited, retrained or redeployed by this publication.
