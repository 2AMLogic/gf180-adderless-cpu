# gf180-adderless-cpu

An Adderless control processor on the [gf180mcu](https://github.com/google/gf180mcu-pdk) open PDK,
designed by AI agents driving
[klayout-tools](https://github.com/2AMLogic/klayout-tools) and the open-source
flow — cocotb + Icarus for verification, Yosys and OpenROAD for implementation.

It is a deliberately minimal 8-bit control processor with no adder: it can increment, decrement, compare, test and set bits, and branch, which is everything a state machine needs and nothing more.

**Where the idea came from.** Leaving the adder out is a real engineering choice: it makes the processor small and fast for control work. This repo builds a modern open one to measure how much that choice still buys. The prompt was a post on r/nicechips, a forum where engineers share parts they admire: [a 1970s control processor that "can't even add"](https://www.reddit.com/r/nicechips/comments/ipeqek/hp_18201691_inside_the_hp_nanoprocessor_a/). This repo is an original design of the same kind of part, not a copy of the one in the post.

## Status

```
Area (measured, post-layout): not yet measured
Design stage: spec
```

<!-- The two fields above are correct as they stand for a repo where nothing is
     built yet, so there is nothing to fill in here — only to keep current. They
     are a fixed-location summary a chip-level integrator reads without parsing
     the prose below, so the keys, their spelling, and their order do not change.

     Area (measured, post-layout): the as-built area of a DRC-clean,
     LVS-matched layout, as a number with units (e.g. 1.059 mm²), taken from
     this repo's own committed measurement. Never a target, a plan, or an
     estimate — the ratified bound is the AREA row of the target-specification
     table below. Until a layout exists, the literal "not yet measured".

     Design stage: exactly one token, from this ladder, in order —
     spec | schematic-sim | layout-DRC-LVS-clean | extracted-verified | silicon
     — describing what this repo has produced and recorded evidence for, never
     what it is aiming at. One token; not a range, not a hedge, not prose. -->

**Just opened, specification phase.** Nothing is designed yet, nothing has been
taped out, and nothing has been measured.

Not being built here: an adder, a multiplier, or compatibility with any historical part. The instruction set is original to this repo; no existing processor's encoding, masks or documentation are copied. No RTL, layout or silicon exists yet.

## Built agent-native

Every specification, decision record, testbench, and line of documentation in
this repo is produced by AI agents working from a ratified spec and an
append-only evidence trail — not human-authored work that agents merely
assisted with. Verification is the product: every claim traces to a recorded
result. Where the agents hit friction with the open-source tooling — most often
[klayout-tools](https://github.com/2AMLogic/klayout-tools) — that friction gets
filed as a public issue against the tool itself, so the fix benefits everyone
using gf180mcu, not just this repo.

## Target specification

Every value is carried by a decision record under [spec/](spec/) — see
[spec/target-table.md](spec/target-table.md) for the full table with the
verification method per row.

| Parameter | Target | Fallback | Stretch |
|---|---|---|---|
| Data width | 8 bits | — | — |
| Program address | 11 bits (2 KB of program) | 10 bits (1 KB) | 12 bits (4 KB) |
| Registers | 7 general registers plus an accumulator (eight 3-bit-addressable register slots); 8-entry return stack | — | 16 registers via a banked extension (future decision record) |
| Arithmetic | increment, decrement, compare, shift, logic; no add or subtract instruction, and no carry-propagate adder in the netlist | compare restricted to equality | — |
| I/O | 8 output strobes, 8 input selects, one 8-bit data bus | 4 strobes, 4 selects | — |
| Interrupt | one level, vectored; entry ≤ 8 cycles, return ≤ 4 cycles | fixed vector, entry ≤ 12 cycles | entry ≤ 4 cycles, return ≤ 2 cycles |
| Supply | 5 V on `gf180mcu_fd_sc_mcu7t5v0` | — | analysis-only closure at the library's 3.30 V corners |
| Clock | ≥ 10 MHz at 5 V | ≥ 6 MHz | ≥ 25 MHz |
| Tooling | assembler and cycle-accurate simulator in this repo, agreeing with the RTL on every test program | instruction-accurate agreement | — |
| AREA | ≤ 0.05 mm² core | ≤ 0.08 mm² | ≤ 0.03 mm² |

## Repo layout

```
flow/          synthesis + place-and-route (Yosys, OpenROAD)
layout/        GDS + DRC/LVS reports (klayout-tools driven)
measurements/  silicon characterization (empty until tape-out)
rtl/           Verilog sources
spec/          ratified spec + decision records
verification/  cocotb testbenches
WORK_LOG.md    chronological record of merged PRs and closed issues (Guide)
WORK_PLAN.md   backlog snapshot from GitHub label state (Guide)
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).
