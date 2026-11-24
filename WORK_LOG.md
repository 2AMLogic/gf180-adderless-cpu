# Work Log

Chronological record of completed work in this repository, maintained by the Guide role.

Entries are grouped by date, newest first. Each entry references the merged PR or closed issue.

<!-- Maintained automatically by the Guide triage agent. Manual edits are fine but may be overwritten. -->

## Archives

### 2026-11-24

- **Issue #34** (closed): flow/README.md still tells the real block its starter `power` block needs no per-block edits
- **PR #36**: docs: qualify flow README claim that starter power block needs no edits
- **Issue #23** (closed): flow smoke: DRC gate unmet on smoke_reg (PDN via stacks and tapcell pitch fail klt drc's gf180mcu deck; waits on klayout-tools#7311)
- **PR #32**: fix: clear smoke DRC with standard PDN vias and 10 µm tap spacing

### 2026-11-23

- **Issue #25** (closed): flow smoke: an `unchecked` klt lvs power verdict is recorded FAIL, not BLOCKED
- **PR #29**: fix(flow): grade an unchecked lvs power verdict BLOCKED, not FAIL
- **PR #28**: docs(flow): say check mode compares flow.engine_versions verbatim
- **Issue #26** (closed): flow smoke check mode compares the runner's own engine build strings, so committed evidence cannot reproduce on another worker
- **PR #24**: feat: add the klt implementation-flow smoke for the smoke register
- **Issue #18** (closed): Bring up the implementation flow on the smoke register: synthesize, place-and-route, DRC, LVS and supply ERC through klt, with committed evidence and a pinned toolchain

### 2026-11-22

- **PR #19**: chore(loom): resync installed Loom to v0.20.8 (clears the dispatch hold)

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
