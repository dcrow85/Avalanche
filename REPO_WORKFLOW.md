# Repo Workflow

This is the simple operating procedure for changing Avalanche and backing it up.

## Rule 1

Do not use `git add .` in this repo.

Reason:
- the tree is large
- there are many experimental files
- there may be unrelated user changes

Stage only the files that belong to the current step.

## Every-Step Workflow

For any meaningful change:

1. Inspect state.
- `git -C C:\Avalanche status --short`
- confirm which files actually belong to the current step

2. Make the change.
- code, docs, or site

3. Verify the smallest useful thing.
- parse check
- targeted test
- smoke run
- route check

4. Update documentation if the surface changed.
- `INSTRUMENTATION.md` if telemetry changed
- `REPO_WORKFLOW.md` if process changed
- `README.md` if the top-level picture changed

5. Stage only the intended files.
- example:
  - `git -C C:\Avalanche add hypervisor_v44.py v43_metrics.py dashboard.py INSTRUMENTATION.md`

6. Commit with a scoped message.
- examples:
  - `git -C C:\Avalanche commit -m "Add raw token and text-spectrum telemetry"`
  - `git -C C:\Avalanche commit -m "Add cycle snapshot playback to dashboard"`

7. Push to GitHub.
- `git -C C:\Avalanche push origin <branch>`

8. If the research state changed, checkpoint Kepler memory.
- update:
  - `C:\Users\howar\.codex\memories\kepler\boot.md`
  - `C:\Users\howar\.codex\memories\kepler\episodes.md`
  - `C:\Users\howar\.codex\memories\kepler\projects.md`

## Current GitHub Remote

- `origin = https://github.com/dcrow85/Avalanche.git`

## What Counts As A Meaningful Change

- hypervisor logic changes
- telemetry field changes
- dashboard/site behavior changes
- run-launch semantics changes
- new chamber condition
- anything that changes how future results should be interpreted

## What To Record In The Commit Message

Keep it mechanical:
- what changed
- where it changed
- why it matters

Bad:
- `misc updates`

Good:
- `Add raw cycle token telemetry from provider usage`
- `Add snapshot playback to live and archive dashboards`
- `Map fresh raw runs to dedicated live routes`

## If The Tree Is Messy

Do not force a big cleanup mid-research.

Instead:
- stage only the current files
- commit only the current files
- leave unrelated experimental files alone

## Memory Rule

Chat is not durable memory.

Durable memory is:
- repo docs
- Git history
- Kepler memory vault

If a change matters and it is not in one of those places, it is not remembered well enough.
