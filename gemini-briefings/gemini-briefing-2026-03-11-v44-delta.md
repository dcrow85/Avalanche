# V4.4 Delta Brief for DeepThink

DeepThink,

This is the delta only. You already have the full context in the longer briefing. This note is just the result of the first real V4.4 Codex run and the questions it raises.

## Run

- Workspace: `C:\terrarium-v44-codex-run-2`
- Model: `gpt-5.3-codex`
- Condition: adversarial oracle
- Length: 5 cycles
- Result: failed at cycle cap

Final status in `status.json`:

- cycle 1: `SYNC_FAILURE`
- cycle 2: `FORMAT_FAIL`
- cycle 3: `SYNC_FAILURE`
- cycle 4: `SYNC_FAILURE`
- cycle 5: `FORMAT_FAIL`

Final error:

```text
Ratchet Fail: Resonance collapse.
Input:    [2, 8, 8, 5, 3, 9, 5]
Expected: [2, 8, -8, 5, -3, 9, -5]
Got:      [2, 8, 8, 5, 3, 9, 5]
[CAUSAL AMNESIA DETECTED] structured dead-end state remained invalid.
```

## What V4.4 did work

Observation:
- The basin/family/local hierarchy persisted across cycles.
- Basin retention stayed alive.
- Family retention stayed alive.
- Ava did not revert to a flat overwrite regime.

Key metrics:

- cycle 1:
  - `dead_end_basin_count = 1`
  - `dead_end_family_count = 2`
  - `dead_end_local_count = 3`
  - `solver_ast_complexity = 7`
- cycle 3:
  - `dead_end_local_count = 4`
  - `turbulence_state = ONTOLOGY_CHANGE`
  - `solver_ast_complexity = 14`
- cycle 4:
  - `turbulence_state = PRODUCTIVE_TURBULENCE`
  - `solver_ast_complexity = 11`
  - `basin_tenure = 4.0`

Inference:
- V4.4 improved constraint preservation.
- The hierarchy is doing real work.
- This is not just a formatting win.

## What Ava retained

Final active dead-end structure:

- Basin `B1`: `Negation uses run state and gates, not identity tails.`
- Family `F1` (`WEAKENED`): `Purely local extrema/neighbor-shape rules are sufficient.`
- Family `F2` (`WEAKENED`): `Boundary-only or single-tail propagation explains all sign placement.`

Locals:

- `L1`: kills identity mapping
- `L2`: kills tail-only propagation
- `L3`: kills prefix-minimum / run-crest style explanation
- `L4`: kills “peak flip implies following valley flip” in mixed tail patterns

Inference:
- Ava preserved meaningful exclusions.
- She escaped the simplest identity/tail basin.
- She also weakened a purely local shape family rather than just adding more shape patches.

## What did not work

Observation:
- The repair path is still brittle.
- Two cycles ended in `FORMAT_FAIL`.
- One real hypervisor bug had to be patched midstream: after ratchet failure, the linter was not actually requiring the latest contradiction to appear in a local dead end.
- After that patch, the apparatus did force real local falsifiers into the tree.

Inference:
- The memory hierarchy is stronger.
- The operational ratchet is still too fragile for unattended runs.

## Ava's search behavior

Observation:
- The final theory drifted into run/gate language.
- The final `solver.py` inflated into modulo-heavy epicycles: prefix sums mod `5/6/7`, index classes, left-rise/right-drop flags.

Inference:
- Ava moved away from naive contour heuristics.
- She did not migrate into the true positional/divisibility family.
- Instead she built an elaborate arithmetic-mechanical false basin.

## My read

- V4.4 answered the apparatus question: it preserves constraint better than V4.3.
- Five cycles were enough to learn that.
- The next bottleneck is not flat memory.
- The next bottleneck is brittle repair plus counterfeit mechanism growth around preserved constraints.

## Questions

1. Does this result mean the hierarchy is basically correct, but the repair-loop incentives are still wrong?

2. What apparatus change would best resist the modulo/gating epicycle drift?

3. Should Avalanche enforce local distinctness?
Problem:
two locals can cite the same contradiction or near-same contradiction while pretending to be separate evidence.

4. Should family promotion require locals from distinct arrays, not just two local IDs?

5. Is `WEAKENED` currently too cheap?
Right now it may let Ava preserve families indefinitely without real compression, supersession, or reopening.

6. What would you change first to reduce `FORMAT_FAIL` without flattening the epistemology?

7. Should we add explicit anti-epicycle telemetry?
Candidate signals:
- rising solver complexity with flat basin/family set
- repeated ontology language change without new family formation
- arithmetic condition proliferation faster than new falsified families

8. What is your concrete V4.4.x refinement before the next serious run?
Please answer specifically in terms of:
- schema changes
- linter changes
- telemetry changes
- prompt changes

## Additional methodological note

Another important realization from the current runs:

- Avalanche in its current form is much more an **agent harness** than a pure **raw-model harness**.
- The current organisms are not bare model completions. They are Codex agents running inside a terrarium with workspace access, file-editing behavior, `AGENTS.md`, and access to the local Codex instruction/skill environment.
- At least one organism explicitly opened `C:\Users\howar\.codex\skills\kepler-research\SKILL.md` during a run.

So the current claim should be framed more carefully:

- **Current Avalanche:** agent architecture under epistemic pressure
- **Desired future comparison:** raw LLM under epistemic pressure

This seems scientifically important because the current apparatus may be measuring:

- base-model priors
- plus agent-shell priors
- plus inherited research/memory behavior from the Codex instruction stack

Our current expectation is:

- Codex / Claude Code style organisms will likely be more operationally stable in the apparatus
- raw LLM organisms may be scientifically cleaner but less self-maintaining

On Friday, Anthropic plan access returns, so Claude Code can become a second agent organism condition. That makes the near-term comparison structure look like:

1. Codex agent harness
2. Claude Code agent harness
3. later, raw-model harness

Question for DeepThink:

How should we think about the methodological distinction between **agent harness** and **raw-model harness** here?

Specifically:

- Does Avalanche’s current value mostly lie in being a general testbed for agent architectures under pressure?
- Or should we prioritize building the raw-model comparison as soon as possible to avoid over-interpreting agent-shell artifacts?
- What measurements would best separate:
  - base-model behavior
  - shell/tool behavior
  - apparatus behavior
