# DR-0005 — Tooling

- **Status:** proposed
- **Decides:** the software tooling this repo carries — assembler,
  instruction-level simulator — the RTL verification stack, and the
  agreement rule that binds the three.
- **Owns table rows:** target-table row 9 (tooling).
- **Supersedes:** the DRAFT "assembler and instruction-level simulator in
  this repo, agreeing with the RTL on every test program" row (kept; now
  with the agreement rule made testable and the stack laid out).

## Decision

This repo carries, and only this repo maintains:

| Tool | Location | Role |
|---|---|---|
| Assembler | `asm/` (new at build time) | The only way ISA text (DR-0001) becomes binary. Rejects every reserved/illegal encoding; emits listings with cycle counts. |
| Instruction-level simulator | `sim/` (new at build time) | **Cycle-accurate**: executes the ISA and models the I/O windows (DR-0003) and interrupt timings (DR-0004) at cycle resolution. |
| RTL testbenches | `verification/` | cocotb testbenches against the RTL; the conformance, flag, I/O, interrupt and agreement suites. |
| Synthesis / PnR | `flow/` | Yosys for synthesis; OpenROAD for place-and-route; driven through `klt` where a tool exists. |
| Layout evidence | `layout/`, `measurements/` | GDS + DRC/LVS via klayout-tools; measurements are append-only records. |

### The agreement rule (the row's teeth)

> For every test program in the suite, the assembler, the simulator and the
> RTL must agree — **cycle-for-cycle** — on the architectural state (A,
> R0–R7, PC, Z, C, IE, strobe/select/bus windows) at every cycle.

- Cycle-accurate is the target; the fallback (row 9) is instruction-accurate
  agreement, meaning the state match is checked at instruction boundaries
  only. Retreating takes a decision record.
- The rule is enforced by the agreement suite: each test program runs in
  the simulator and on the RTL (cocotb) and the two traces are compared
  cycle-by-cycle (fallback: instruction-boundary-by-instruction-boundary).
  Any divergence fails CI.
- The suite covers, at minimum: every defined opcode (DR-0001 conformance
  set), every boundary flag case (DR-0002), all I/O timing windows
  (DR-0003), the interrupt entry/return paths (DR-0004), and the reserved-
  encoding halt-and-flag behavior.
- **Reserved encodings halt and flag**: the simulator and the RTL treat an
  undefined opcode identically — stop fetching, assert a `halt` output.
  Agreement includes this path.

### Tool roles and what is *not* built here

- cocotb is the RTL testbench framework; Icarus Verilog is the event
  simulator. Both are external dependencies of the harness — version pins
  belong to the harness bootstrap issue (#2), not to this record.
- The assembler and simulator are **in-repo and original**: they implement
  DR-0001 as written. No third-party assembler/simulator for this ISA
  exists (it is original), and none may be adopted without a decision
  record.
- Post-synthesis and post-layout simulation re-run the same cocotb suites
  against the gate-level netlist (Icarus with the library's functional
  Verilog) — the agreement rule extends to the netlist, so DRC/LVS-clean
  layout is not the only gate: behavior is re-proven at every stage.

## Options considered

- **Cycle-accurate simulator (chosen) vs instruction-accurate:** the ISA
  (DR-0001), the I/O model (DR-0003) and the interrupt budgets (DR-0004)
  all make claims *in cycles*. An instruction-accurate reference could not
  verify any of them; the fallback exists only as a cost retreat and
  invalidates those claims while active.
- **cocotb + Icarus (chosen):** named in the repo charter (README) and the
  standard open-source digital verification pairing; the harness issue (#2)
  owns versions and environment.
- **Trace comparison vs end-state comparison (chosen: trace):** comparing
  full traces catches extra/missing cycles, glitched strobes, and wrong
  interrupt timings that end-state comparison swallows.

## Evidence

- Tool project homes (roles only; versions pinned by #2): cocotb —
  <https://www.cocotb.org>; Icarus Verilog —
  <https://steveicarus.github.io/iverilog>; Yosys —
  <https://yosyshq.net/yosys/>; OpenROAD —
  <https://theopenroadproject.org>; klayout-tools —
  <https://github.com/2AMLogic/klayout-tools>.
- In-repo, as of this PR: `flow/README.md` documents the klt-driven
  synthesis/PnR conventions this record adopts.

## Verification method

Maps to target-table row 9.

1. **Agreement suite in CI:** every test program runs twice (sim, RTL);
   traces compared at cycle resolution; the build fails on any mismatch.
2. **Assembler negative tests** (shared with DR-0001's verification):
   reserved encodings and `ADD`/`SUB` rejected; listings carry cycle
   counts matching DR-0001.
3. **Stage extension:** the same suites re-run against post-synthesis and
   post-layout netlists; agreement must hold at every stage before any
   result is recorded in `measurements/`.
