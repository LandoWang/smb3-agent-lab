# Architecture and experiment history

## The experimental control loop

1. Pause the emulator and construct an observation.
2. A high-level planner proposes phase goals and an executable skill contract.
3. A local selector chooses among supported actions/durations using the plan and recent trajectory.
4. The harness advances a bounded number of game frames.
5. Record actual execution, termination events, and progress; replan when needed.

Emulator time is not wall time. Cloud response latency must not silently let the game keep running.

The planner cannot create capabilities by naming them in a prompt. A plan node needs an available skill, preconditions, parameters, a success condition, and failure/interruption conditions. The harness must report what was really executed, especially when an event shortens the requested duration.

## Components

The [public session adapter](../adapter/README.md) now implements the frame/plan/
decision loop, intent queue, declared motor recipes, audit and viewer. Its remote
Profile client is game-neutral; game-specific memory and model serving remain
separate dependencies. It has no learned dynamics or validated landing predictor.

| Component | Responsibility | Must not be confused with |
|---|---|---|
| NES emulator | Deterministic game state and input execution | A model inventing game dynamics |
| Astra | Phase goals, route plans, failure replanning | Every individual button press |
| OpenRouter Jev / local selector | Select a supported local action | A guarantee of safety |
| Harness | Observation, skills, stopping, control ownership, audit | Hidden policy decisions |
| DQN baseline | Pixel-based low-level button selection | A text-conditioned planner |

OpenRouter Jev, local DiffusionGemma, and CLM are different backends, not interchangeable names. The source of each decision must be explicit. Harness filtering/sampling is also a policy choice and must be separately logged.

## Milestones

- Astra + OpenRouter Jev with validated memory assistance.
- Jump physics, input hold duration, run-up/speed/airborne observations.
- Local DiffusionGemma action selection and route plans.
- Hazard tracking across camera movement and slot reuse.
- Phase contracts, no-abstention variants, and bounded calibration.
- Published CLM comparison with strong planner restrictions.
- Near-top weighted action sampling with reproducible sampling seeds.
- Scripted motion and brick-corner experiments; separate memory-modification atlas experiments.
- Published DQN evaluation, including stopped transfer trials.

Earlier versions were frozen rather than overwritten. An unimplemented CLM route draft is not a released algorithm. A pipe crossing is not a completed course.

## Proposed: Jev supervising DQN

**Not implemented in this release.**

One possible first experiment is handoff control: a frozen DQN handles normal motion, the harness returns control at a measured stall/damage event, and Jev chooses a brief intervention before returning to the DQN.

Only one controller may own the button stream at a time. Log owner, handoff reason, pre/post state, and every applied input. Compare against a DQN-only run with identical start states and stopping rules.

This wrapper does not require retraining. However, an API such as land_on(platform_id) does not magically make the published DQN understand targets. A genuine goal-conditioned controller Q(state, goal, action) would require appropriate training or a separately validated controller/search mechanism.

## Deliberately not promised

- Full-game completion or broad cross-level generalization.
- A universal Markov state reconstructed from a few RAM bytes.
- Calibrated survival probabilities from Q values or model preference scores.
- Bundled cloud/local model serving or a one-command emulator/model deployment.
