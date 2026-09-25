# Source export provenance

Publication: 2026-09-25, adapter 0.3.1, Session format 2.0.0.
Derived from archived local experiments. Private directory names and deployment
details are not distributed. Earlier sources and game outputs remain frozen.

Unchanged parent runtime SHA256 values (also applicable to this export):

| File under session_adapter | SHA256 |
|---|---|
| engine.py | d4011331dfd11b1421eec7fa5196892ab85be4052e90f87f0618c2f2b3d4e1a6 |
| contracts.py | e50c767e44cba05a0bd88b18a80bfca19eb83cea8a895912b2aefc33fca89142 |
| local_context.py | adaa42a197422c19f40332f758ce503abe4cfa8a58fa53e4e016d3181359298e |

Public packaging changes:

- Version marker and CLI source snapshots reflect this public subset.
- Remove private serving assumptions: local model alias/reserve/revision pin are
  caller configuration; token limits come from the service. Do not emit the
  server's internal upstream URL. Azure model/deployment names come from external
  private configuration. No engine launch, GPU allocation or real endpoint is shipped.
- Add the game-neutral `remote` profile name, retaining `remote_smb3` compatibility.
- Remove CLI dependencies on a private sibling SMB3 source/archive directory.
- Do not distribute the ROM-specific memory harness, enemy object table, RAM
  writes, emulator service/deployment files, archives, ROMs, weights or save states.
- Include self-contained synthetic tests instead of private recorded-memory,
  archived-request, copied-parent and locally installed frontend integration tests.
  The renderer test checks a fixed wire contract; it does not claim to run the
  unpublished upstream service.
- Document a separately provided game RPC service as a prerequisite for live
  remote play. It is not silently replaced with the fixture.

The private parent's test results and independently replayed pilot sessions
are historical reported results. The public suite is run and counted separately;
it does not certify live provider access or reproduce private emulator audits.
No fresh Jev, Codex model or GPU inference was performed to publish this subset.

No model weights, provider server implementations, disassembly or game binaries
are copied. Original adapter code is covered by the repository's MIT license;
third-party services and dependencies retain their own terms.
