# Target specification

One row per parameter: the target the project engineers to, the fallback it
retreats to if the target proves costly, the stretch it reaches for if the
target lands cheaply, and the verification method — the test, tool or
measurement that will show the row met. No claim is made about any row until
its verification method has run and its result is recorded as evidence.

**Status: proposed** — ratification is this file's own PR merging after two
independent reviews (see [README.md](README.md) § Change policy). The
`Status:` line is flipped to RATIFIED inside that PR.

Every value here is carried by a decision record (DR-nnnn under
[decisions/](decisions/)); the table cites the record that owns it.

| # | Parameter | Target | Fallback | Stretch | Verification method |
|---|---|---|---|---|---|
| 1 | Data width | 8 bits | — | — | DR-0001 § Opcode map: assembler and simulator enforce 8-bit wrap; cocotb datapath tests assert the same wrap. |
| 2 | Program address | 11-bit PC, 2 KB program space | 10-bit PC, 1 KB | 12-bit PC, 4 KB | DR-0001 § Addressing modes + DR-0002: assembler rejects out-of-range targets; sim and RTL agree on PC width and wrap. |
| 3 | Registers and stack | Accumulator A plus 8 general registers R0–R7 (8 bits each); 8-entry hardware return stack | — | 16 registers via a banked extension (only by a future decision record) | DR-0002: cocotb register-file read/write test over all indices; stack depth/overflow/underflow tests; area from the committed layout report. The 16→8 change from the draft is recorded in DR-0002 § Options considered. |
| 4 | Arithmetic scope | INC, DEC, CMP, SHL, SHR, AND, OR, XOR — no ADD or SUB instruction, and no carry-propagate adder anywhere in the netlist | CMP restricted to equality (drop the magnitude bit) | — | DR-0001 § The no-adder rule: post-synthesis netlist check asserts zero `addf`/`addh` instances; assembler rejects `ADD`/`SUB`; cocotb proves no encoding performs addition. |
| 5 | I/O | 8 output strobes, 8 input selects, one shared 8-bit data bus | 4 strobes, 4 selects | — | DR-0003: cocotb strobe/select timing tests (assertion cycle, width, bus ownership); repeated at gate level. |
| 6 | Interrupt | One level, vectored into page 7; entry ≤ 8 cycles, return ≤ 4 cycles | Fixed vector (non-vectored), entry ≤ 12 cycles | Entry ≤ 4 cycles, return ≤ 2 cycles | DR-0004: cocotb measures assertion-to-first-handler-cycle and return cost; the cycle-accurate simulator must agree. |
| 7 | Supply | 5.0 V nominal on `gf180mcu_fd_sc_mcu7t5v0` | — | Timing also closed at the library's 3.30 V corner files (analysis only — no silicon claim at 3.3 V) | DR-0006 § Corners: corner names verified against the library's `liberty/` directory; STA runs use them. |
| 8 | Clock | ≥ 10 MHz at 5 V | ≥ 6 MHz | ≥ 25 MHz | DR-0006 § Clock: post-layout STA at the worst published corner (ss, n40 °C, 4.50 V) with the target period; the number recorded from this repo's own run. |
| 9 | Tooling | Assembler and cycle-accurate instruction-level simulator in this repo, agreeing with the RTL on every test program | Instruction-accurate agreement (cycle counts may differ) | — | DR-0005 § Agreement rule: the agreement suite runs on every test program in CI; any divergence fails the build. |
| 10 | Area | ≤ 0.05 mm² core | ≤ 0.08 mm² | ≤ 0.03 mm² | DR-0006 § Area: measurement taken with klayout-tools on the DRC-clean layout and committed under `measurements/`; never an estimate. |
| 11 | With-adder comparison | Plan in place: named baseline, same-flow method, and the Δ metrics defined | — | The measurement itself made and recorded | DR-0006 § With-adder comparison: the plan is reviewed as part of this spec; the measurement, when made, is committed under `measurements/`. |

## What the fallback and stretch columns mean

- **Target** — the committed engineering value. Flow scripts, timing
  constraints and review gates are set to this.
- **Fallback** — the pre-agreed retreat if verification shows the target is
  not reachable at sane cost. Adopting a fallback is a new decision record;
  it is not automatic.
- **Stretch** — reached for only after the target verifies; never traded
  against the target.
