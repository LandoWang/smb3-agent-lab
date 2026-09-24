# Third-party provenance and distribution boundaries

Reviewed for this preview on 2026-09-24. Availability online is not equivalent to a redistribution license.

## Nintendo / Super Mario Bros. 3

Super Mario Bros. 3 and its game assets belong to their respective rights holders. This project is unaffiliated with Nintendo. Supply your own legally obtained ROM. No ROM, ROM patch, extracted CHR graphics, complete level-map image, or emulator save-state binary is distributed here.

Small gameplay screenshots and recordings document our experiments. The repository's MIT license does not grant rights to the game imagery.

## MarioDQN

- Source: https://github.com/ToadAIStation/MarioDQN
- Reviewed commit: ea6adb6e194e093ead6fd29b4ea768705609129f
- Upstream playback source SHA256: 99d3b03e35d32ccfb83243acdc3145ac41d7edea9672a0356dbbf7377785943f
- Checkpoint: pretrained_model/agent_model_5100000
- Checkpoint SHA256: 3232b5a6bc4adf61c6bb7a89d9c1dc74891cbe27f9eb1f938ec4f9d9ad38a144

No explicit license file was found in the reviewed repository tree, and GitHub's repository license field was null. We do **not** vendor its network definitions, training scripts, or checkpoint. The evaluation adapter requires locally supplied files and checks their exact hashes. Review the upstream terms and obtain permission where necessary; these references are not a grant of rights.

The adapter loads only four reviewed architecture/action definitions from the separately supplied source; it does not execute upstream main. Hash validation must not be disabled for arbitrary source files.

## Emulator and runtime

- [Stable-Retro](https://github.com/Farama-Foundation/stable-retro), version 1.0.1 in recorded DQN trials. Distributed separately; consult its LICENSE and the applicable emulator core notices.
- PyTorch 2.7.1+cpu, NumPy 2.2.6, OpenCV 4.11.0.86, Pillow 11.3.0, Gymnasium 1.3.0, FFmpeg. Dependencies are not vendored. Their own licenses apply.
- Builds should preserve third-party notices, especially when redistributing emulator binaries or container images. This preview does not publish such binaries/images.

## Historical model experiments

Astra, TypeSafe Jev through OpenRouter, local DiffusionGemma, and published CLM are separately identified experimental backends. Their names do not imply affiliation, endorsement, or bundled access. This preview contains no provider credentials, model weights, copied provider implementations, or promise of API availability.

## Reverse-engineering references

[Community SMB3 disassembly](https://github.com/captainsouthbird/smb3/tree/09b1bd81a788de8ceec664a34094e84ddb463117) informed interpretation. This is community reverse engineering, not Nintendo-published original source. We link to it and summarize findings; no disassembly files or ROM data are included.
