# THE BLUEPRINT

**Goal:** Avalanche is complete. A self-correcting agentic loop that
drives Claude Code through GRIND/RATCHET/SYNC cycles until tests pass.
The incremental ratchet tracks per-test progress across cycles.

**Architecture:** Single-file engine (avalanche.py). The main loop:
GRIND invokes Claude to edit code, RATCHET runs tests and either
commits (pass) or reverts via git reset (fail), SYNC invokes Claude
to rewrite this blueprint. enforce_amnesia wipes .claude/ between
invocations for stateless operation; .avalanche/ persists across
resets to hold test_state.json. parse_test_results extracts {name:
bool} from pytest -v output, stopping at the FAILURES section to
avoid false matches in tracebacks. detect_regressions catches
True→False transitions; has_progress detects newly passing tests.
smart_compress implements section-aware truncation: sacrifices
graveyard entries oldest-first, then truncates architecture, then
goal, ensuring the blueprint always fits the 200-word limit.
validate_blueprint enforces Goal/Architecture/Graveyard sections.
format_grind_prompt generates the Claude prompt, optionally listing
failing tests. DRY_RUN mode and distinct exit codes (0 success, 1
cycle cap, 2 missing prereqs) support testing and CI integration.

**Graveyard:**
- None yet.
