# Work Log

Chronological record of completed work in this repository, maintained by the Guide role.

Entries are grouped by date, newest first. Each entry references the merged PR or closed issue.

<!-- Maintained automatically by the Guide triage agent. Manual edits are fine but may be overwritten. -->

## Archives

### 2026-11-19

- **Issue #15** (closed): ci: 'Pin-consistency check (fast lane)' runs after the iverilog build, not in the fast lane
- **PR #16**: ci: run pin-consistency check before the simulator build
- **Issue #10** (closed): tools/test_smoke_exits.py is not run by CI
- **PR #12**: ci: run exit-code contract tests in the smoke job's fast lane
- **Issue #11** (closed): smoke.py --control --write overwrites committed control evidence from a run that executed no tests
- **PR #14**: fix: only a passing control rewrites the committed smoke-control evidence
- **PR #8**: fix: smoke harness breakage exits BLOCKED (2), not FAIL (1)
- **Issue #7** (closed): smoke.py: a BLOCKED harness failure exits 1 (FAIL), not 2
- **PR #5**: feat: add smoke verification harness with committed evidence and negative control
- **Issue #2** (closed): Bootstrap the verification harness
- Work log created by the Guide role.
