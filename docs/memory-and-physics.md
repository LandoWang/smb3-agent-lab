# Memory assistance and physics: measured scope

Target: Super Mario Bros. 3 (USA) (Rev 1). Results do not automatically transfer to SMB1, another ROM revision, another form, or a different emulator.

## Fields used in DQN evaluation

| RAM | Interpretation in this ROM | Use / caution |
|---|---|---|
| $75/$90 | Player X high/low | World-X progress; not sufficient in auto-scroll or vertical courses |
| $87/$A2 | Player Y high/low | Screen Y and world Y are not interchangeable |
| $F1 | Dying state | Stop on death |
| $D8 | Airborne state | Read-only logging |
| $ED | Player form | Start states differ |
| $736 | Raw lives byte | Log raw value; do not infer total attempts from it alone |
| $D6 | Object-slot vertical velocity | **Not a universal win flag** |
| $559 / $14 | End-level runoff / map-transition candidates | Require contextual/visual confirmation |

Validation combined pinned community disassembly, controlled button probes, before/after observations, and deterministic replay. Unvalidated object identities or collision geometry must remain marked uncertain.

## Scripted calibration, not model gameplay

- Motion lab: 93 predefined cases, 8863 emulated frames, zero deaths/model calls; recorded-input replay matched pixels/motion and endpoint saves.
- Brick lab: 116 predefined branches, 12572 frames, zero deaths/model calls; replay matched pixels/motion/context and endpoints.
- Observed 42 head contacts and 28 position-correction frames in 14 brick branches.
- At a tested right corner, A-only from resting X200 moved the player to X205; a matched no-jump control stayed at X200. This supports corner correction in that scene, not arbitrary teleportation.

These comparisons restored initial states and replayed specified inputs. They were not retries scored as successful model play, and they did not write player velocity/position RAM.

## Useful approximate rules

SMB3 uses discrete state-dependent rules and fixed-point arithmetic. For ordinary small Mario in the measured conditions:

- Raw signed velocity is 4.4 fixed-point: 16 units = 1 pixel/frame.
- Ground acceleration averages about 14/256 px/frame²; released-input friction about 10/256; opposite-direction braking about 2/16. Fractional phases mean individual frames need not match the average.
- Walking/running/full-P reference speeds are 1.5/2.5/3.5 px/frame; do not reuse these for all terrain/forms.
- Airborne left/right input can change horizontal motion. Neutral airborne input does not apply ordinary ground friction.
- Holding A while rising faster than -2 px/frame uses about 1/16 px/frame² gravity; otherwise about 5/16, in the ordinary jump branch.
- Jump initiation depends on the A press edge; holding A and newly pressing A are different events.
- Collisions constrain/correct position and velocity. A free-flight formula is not a collision solver.

Observation timing matters: apply existing velocity, update control/gravity, and resolve collisions in engine order. Rounding each frame independently loses fractional accumulators.

## Maps and hazards

Loaded terrain and active enemy objects are different datasets. A full terrain map does not imply that every distant enemy has a live state in RAM.

Some projectile X positions are low-byte values. Reconstructing world coordinates requires camera context, identity/history, and validity checks. When an object is removed or its slot reused, extrapolation must stop or reinitialize.

A separate memory-modified atlas experiment loaded 252 regions through game-level loading routines. That was map research, not policy clearance. Full ROM-derived maps and memory-write tools are not distributed in this preview.

References: [pinned community disassembly](https://github.com/captainsouthbird/smb3/tree/09b1bd81a788de8ceec664a34094e84ddb463117). Community annotations are not Nintendo's original published development source.
