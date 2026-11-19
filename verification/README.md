# verification

cocotb testbenches. Recorded results are append-only evidence.

## Smoke harness (issue #2)

`rtl/smoke_reg.v` (a 1-bit register) plus one cocotb test prove the
toolchain and the evidence path before any RTL or spec work depends on
them. It claims nothing about the CPU, the ISA, or any spec content, and
nothing here implies an adder or compatibility with any historical part.

`make smoke` is the single command: it builds a throwaway `.venv-fv`
(pinned `klayout-tools==0.9.2` + `cocotb==2.1.0`, via `uv`; no host tool
is installed or changed), re-runs the committed klt request under Icarus,
and checks the committed evidence file reproduces (exit 0 = PASS). The
committed evidence records the tool versions, the RTL sha256 and the
verdict; wall-clock fields and absolute paths are excluded from the
comparison.

## Generic vs. block-specific

The harness pattern is copied from [`2AMLogic/gf180-dx7`](https://github.com/2AMLogic/gf180-dx7)
at `69f0464147172f3d4a5506fc2a0c555008d3f36e` (2026-11-19), by pinned
reference — dx7 is not a submodule or a package of this repo. Per file:

| File | Generic or specific |
| --- | --- |
| `Makefile` (`smoke*`, `check-pins`, `FV_PINS`, venv rule) | generic, copied from dx7's FV targets, reduced to the smoke lane |
| `tools/smoke.py` | generic, adapted from dx7's `tools/functional_verification.py`: same statuses, exit codes, evidence writer and compare; no playback, no dev-case grading |
| `tools/check_pins.py` | generic, adapted from dx7's `tools/check_fv_pins.py` |
| `.github/workflows/ci.yml` (smoke job) | generic, from dx7's ci.yml (pinned-simulator build + evidence check), smoke lane only |
| `rtl/smoke_reg.v` | specific to this block: a 1-bit register, toolchain exercise only |
| `verification/test_smoke.py` | specific: one cocotb test for `smoke_reg`, following dx7's cocotb-module pattern |
| `verification/evidence/smoke-request.json` | specific: this block's request, in dx7's committed-request shape |
| `verification/evidence/smoke.json` | specific evidence, written by `tools/smoke.py --write` |
| `verification/evidence/smoke-control.json` | specific evidence: the recorded mutant (negative-control) run |

## Re-run it

```
make smoke            # check mode, exit 0 = PASS
make smoke-control    # live negative control: the mutant must fail
python3 tools/check_pins.py   # fast lane: evidence names the pinned toolchain
```

Needs `uv` and `iverilog`/`vvp` (13.0) on `PATH`, and network access once,
to build `.venv-fv`.

## Statuses (`tools/smoke.py`)

| status | exit | meaning |
| --- | --- | --- |
| PASS | 0 | re-run matches the committed report; every test passed |
| FAIL | 1 | a verdict, count, or recorded environment differs, or a test failed |
| NOT_RUN / BLOCKED | 2 | `klt`, `cocotb`, `iverilog` or the committed report is missing, klt emitted no JSON report, or a `--control` run executed no tests; never reported as a pass |
| STALE | 3 | the committed report names RTL hashes different from the tree |

`--write` (a flag of `tools/smoke.py`, not of the make targets)
regenerates `verification/evidence/smoke.json`; `--control --write`
regenerates `verification/evidence/smoke-control.json`.

## Negative control

`make smoke-control` runs the same request against the `SMOKE_MUTATE`
build — set through the klt request's `options.source_defines`, which
compiles an inverted capture into `rtl/smoke_reg.v` — and requires the
same smoke test to FAIL there. Without it, a vacuous pass would be
indistinguishable from a working harness. The recorded mutant run is
`verification/evidence/smoke-control.json` (`CONTROL_OK` on the live
run).

## What is committed (`verification/evidence/`)

- `smoke-request.json` — the klt request (top `smoke_reg`, Icarus,
  pinned seed).
- `smoke.json` — the klt envelope with the per-test verdict plus
  `provenance`: sha256 of `rtl/smoke_reg.v`, sha256 of the request, the
  `klt --version` string, the cocotb version, and what the run copied
  from dx7.
- `smoke-control.json` — the same envelope for the mutant build,
  reporting `fail`.

## Bumping the pinned toolchain

`Makefile`'s `FV_PINS` and the committed evidence must move together:
the re-run compares `provenance` (including `klt_version`, the stripped
stdout of `klt --version`) and the recorded environment (including
`cocotb_version`) verbatim, so a bump without a regeneration turns this
lane FAIL-on-provenance at the next check. The recurrence guard
`tools/check_pins.py` makes that visible at bump time, in the fast lane.
When it fails:

1. bump `FV_PINS` in the `Makefile`;
2. regenerate: `rm -rf .venv-fv` (the make venv rule does not re-run
   while `.venv-fv/bin/klt` exists, so the old-pin venv would silently
   re-record the old versions), then `make smoke` (recreates the venv
   from the new `FV_PINS`; that run shows the provenance mismatch), then
   `python3 tools/smoke.py --venv .venv-fv --write` for the evidence and
   the same with `--control` for the mutant record;
3. the CI workflow's pinned iverilog build (13.0, cached) must move with
   the evidence's `engine_version` — bump both together.
