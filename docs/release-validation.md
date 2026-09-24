# Initial preview validation

This document concerns packaging/runtime validation, not another gameplay benchmark.

- Eight standard-library tests: all historical evidence records, valid prefix, action tampering, omitted frames, trajectory action tampering, summary tampering, endpoint tampering, runner syntax.
- Offline verification covers four historical policy runs, 765 decisions and 3058 frames.
- Release guard checks for forbidden artifacts, credential patterns, private home-directory paths, broken local Markdown links, and media checksums. It is heuristic, not a guarantee against all possible secrets.
- Portable runner SHA256: 597e967ca241119c405171cd4de6cf77ce88f2d1481d60ad6583cc33fe407d13.
- CPU-only, network-disabled runtime smoke: W1-1, seed 1, 12-frame right and 12-frame jump probes passed; a separate 13-frame policy run stopped exactly at frame_limit after 4 decisions (4+4+4+1). Zero deaths, cloud requests, or API fees.
- Smoke ID: 20260924T215038Z-smb3-dqn-048357c2. It is not a fifth benchmark trial or a completion claim.
- The 13-frame smoke input replay matched every RGB hash and scoped RAM observation; its decision hash chain also passed.
- Original historical sources and output directories were unchanged.

The smoke used the previously resolved Python 3.11 / Stable-Retro 1.0.1 / CPU PyTorch 2.7.1 environment, with explicit external input mounts. A fresh dependency installation on every supported operating system has not been validated; Linux is the documented target.
