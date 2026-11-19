# spec

Ratified target specification and decision records for the gf180-adderless-cpu.

Everything downstream — RTL, testbenches, the assembler/simulator, synthesis
and layout — grades against the documents here. A value in this directory is
only **ratified** when the decision record that carries it has `Status:
RATIFIED`, which happens by the record's ratifying PR being reviewed and
merged after two independent reviews (engineering and market) by sessions
that did not author the PR or the design. The `Status:` flip happens inside
that PR, never as a follow-up commit.

## Documents

| Document | Contents |
|---|---|
| [target-table.md](target-table.md) | The target table: one row per parameter, with target, fallback, stretch and a verification method. |
| [decisions/0001-instruction-set.md](decisions/0001-instruction-set.md) | The original instruction set: opcode map, addressing, semantics, the no-adder rule and the original-encoding statement. |
| [decisions/0002-registers-state.md](decisions/0002-registers-state.md) | Registers and architecturally visible state: accumulator, general registers, PC, flags, subroutine return stack, reset state. |
| [decisions/0003-io-model.md](decisions/0003-io-model.md) | The I/O model: output strobes, input selects, the shared data bus, cycle-level timing. |
| [decisions/0004-interrupt.md](decisions/0004-interrupt.md) | The interrupt model: one vectored level, masking, entry and return sequences and their cycle budgets. |
| [decisions/0005-tooling.md](decisions/0005-tooling.md) | Tooling: the in-repo assembler and cycle-accurate simulator, the RTL verification stack, and the agreement rule that binds them. |
| [decisions/0006-timing-area.md](decisions/0006-timing-area.md) | Timing and area: clock target and corners on the 7-track 5 V library, the core area bound, and the with-adder comparison plan. |

## Reading order

`target-table.md` first (it is the summary and points at the records), then
DR-0001 and DR-0002 together (the ISA is only meaningful with its state
model), then DR-0003/0004 (machinery around the core), then DR-0005/0006
(how every claim gets verified).

## Change policy

Changing a ratified value is a new decision record that says what changed,
why, and what it invalidates downstream — never an edit that silently moves
a number to make a result pass. Draft-stage values (before the ratifying PR
merges) may still be moved within this spec's own PR.
