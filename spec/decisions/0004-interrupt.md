# DR-0004 — Interrupt model

- **Status:** proposed
- **Decides:** the interrupt structure — level count, vectoring, masking —
  and the entry/return sequences with their cycle budgets.
- **Owns table rows:** target-table row 6 (interrupt).
- **Supersedes:** the DRAFT "one level, vectored" row (kept; now with the
  vector mechanism, cycle budgets, and the entry/return cost figures the
  issue asks for).

## Decision

**One interrupt level, vectored, edge-requested, masked by `IE`.**

- A single request input `irq`. One level: no priority encoder, no nesting
  — while inside a handler, interrupts are masked until `REI`.
- **Vectored without arithmetic.** The vector comes from the requesting
  controller over the data bus during the acknowledge cycle, and the new PC
  is a **concatenation, not a sum**: `PC ← {3'b111, vector[7:0]}`. Vectors
  therefore live in the top program page, 0xE00–0xEFF (512 bytes), and the
  hardware performs no address arithmetic — consistent with the no-adder
  rule (DR-0001).
- **Masking:** `IE` (DR-0002) gates recognition. `IE` is 0 at reset, set to
  1 by `REI`, set to 0 by the entry sequence. There is no `EI`/`DI`
  instruction: critical sections are the automatic entry mask; a program
  that wants interrupts off simply never executes `REI`'s unmask on that
  path (i.e. returns with `RET` after pushing nothing — the ISA supports
  it, DR-0001).
- **`WAI`** (`DR-0001`) halts the core at the instruction boundary until an
  unmasked request arrives, then runs the entry sequence. `WAI` is the
  intended idle state for event-driven control code.

## Entry sequence (target ≤ 8 cycles from `irq` assertion to first handler cycle)

| Step | Cycles | Action |
|---|---|---|
| Recognize | 0–1 | `irq` sampled high with `IE`=1; the current instruction is allowed to finish (≤ 2 cycles by DR-0001 cycle targets) |
| Acknowledge | 1 | `ack` strobe to the controller; controller drives `vector[7:0]` on `data` (bus ownership per DR-0003) |
| Capture + push | 1 | `vector` captured; interrupted PC pushed to the return stack (DR-0002) |
| Redirect | 1 | `PC ← {3'b111, vector}`; `IE ← 0`; first handler opcode fetch begins |

Counting from the cycle after the request is sampled: ≤ 1 (finish current
instruction) + 1 (ack) + 1 (capture/push) + 1 (redirect) = **≤ 4 core
cycles**, comfortably inside the ≤ 8-cycle target; the 8-cycle figure is
the budget that still holds if the final instruction before the request is
a two-byte branch taken-path. Fallback (row 6): a fixed-vector build that
skips the acknowledge cycle. Stretch: ≤ 4 cycles, i.e. the sequence above
with no margin — reached only if the target verifies with room.

Latency caveat recorded in the table's verification method: the ≤ 8-cycle
budget covers the core's own entry cost from `irq` to the first handler
cycle. It does **not** include external controller response time to `ack`
or `WAI`-state wakeup for masked requests.

## Return sequence (`REI`, target ≤ 4 cycles)

| Step | Cycles | Action |
|---|---|---|
| Pop | 1 | return address popped from the stack |
| Restore | 1 | `PC ← popped`; `IE ← 1`; first original-flow opcode fetch begins |

Pop + restore is the 2-cycle critical path; with the following opcode fetch
the instruction's total cost is the 3-cycle target DR-0001 assigns `REI`,
inside row 6's ≤ 4-cycle return budget. Stretch ≤ 2 would collapse the
fetch overlap.

- **`RET` vs `REI`**: `REI` is required to leave an interrupt handler — it
  pops **and** unmasks. A handler that returns with plain `RET` leaves
  `IE`=0: interrupts stay masked. That is a defined behavior (it is how a
  program keeps interrupts off), and the assembler will not diagnose it.
- A request asserted while masked is **latched**: it stays pending and is
  serviced as soon as `IE` returns to 1 (at `REI`). A request de-asserted
  before service is forgotten (edge-requested, not queued).

## Options considered

- **One level (chosen) vs several:** the draft says one; a priority encoder
  plus per-level masking costs control logic the ISA has no use for. One
  level + `WAI` covers the chartered control workloads (see DR-0001's
  omission table).
- **Concatenated vector (chosen) vs arithmetic vectoring:** a classic
  vectored scheme computes base + offset — that is an adder, banned here.
  Concatenation gives the same dispatch behavior with zero arithmetic;
  the cost is vector locality (all vectors share page 7), which is a
  linker concern, not a hardware one.
- **Auto-mask at entry (chosen) vs manual `DI`:** automatic masking removes
  the race a manual `DI` has between sampling the request and disabling;
  the ISA carries no `DI`/`EI` encodings, so there is no way to build the
  racy pattern.

## Evidence

- The `irq`/`ack` interface is realized with the PDK's signal I/O context
  (`libraries/gf180mcu_fd_io` in `efabless/gf180mcu-pdk`, `main`
  @ `ff2a6056a2e6`, fetched 2026-11-19 —
  <https://github.com/efabless/gf180mcu-pdk>): the interrupt model consumes
  ordinary core-side signals; the pad stage is the integrator's.
- The vector page arithmetic-free scheme is a direct consequence of the
  no-adder rule (DR-0001 § The no-adder rule); no external source asserts
  or denies it — this record is a design choice documented for review.
- Cycle budgets are targets set against the DR-0001 per-instruction cycle
  table (worst pre-request instruction = taken two-byte branch, 3 cycles);
  they will be confirmed or retreated per row 6's verification method.

## Verification method

Maps to target-table row 6.

1. **cocotb latency test:** assert `irq` before, during, and after each
   opcode class's execution; count cycles from assertion to the first
   handler cycle; assert ≤ 8 (target) and record the measured number.
2. **Vector capture test:** for a sweep of all 256 vector values, assert
   `PC == {3'b111, vector}` at handler entry and that the bus is driven by
   the controller during `ack` (per DR-0003 ownership).
3. **Masking tests:** request while `IE`=0 → latched pending; `REI` →
   serviced; de-assert before service → forgotten. Handler-returning-with-
   `RET` → stays masked.
4. **`WAI` test:** `WAI` with masked request → stall; unmasked pending
   request → entry sequence begins; `WAI` inside handler not reachable
   (masked).
5. **Return cost test:** `REI` measured at ≤ 4 cycles (target); sim and
   RTL agree (DR-0005).
