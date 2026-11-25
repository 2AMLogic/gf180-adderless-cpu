# DR-0003 — I/O model

- **Status:** proposed
- **Decides:** the port model — output strobes, input selects, the shared
  data bus — and the cycle-level timing of port access.
- **Owns table rows:** target-table row 5 (I/O).
- **Supersedes:** the DRAFT "8 output strobes, 8 input selects, one 8-bit
  data bus" row (kept; now with cycle-exact timing and bus ownership rules).

## Decision

The processor talks to the outside world through **eight output strobes**,
**eight input selects**, and **one shared 8-bit bidirectional data bus**.
There is no address bus, no wait states, no DMA, no bus arbitration: every
transfer is one instruction (`OUT #p` or `IN #p`, DR-0001) and the port
index is in the opcode.

| Signal group | Width | Direction | Driven by | Defined by |
|---|---|---|---|---|
| `strobe[7:0]` | 8 | output | CPU, during `OUT` | this record |
| `select[7:0]` | 8 | output | CPU, during `IN` | this record |
| `data[7:0]` | 8 | bidirectional, tri-state | CPU during `OUT` cycle 2; external world during `IN` cycle 2 and the interrupt acknowledge cycle (DR-0004); high-Z at all other times | this record |
| `irq` | 1 | input | interrupting controller | DR-0004 |
| `ack` | 1 | output | CPU, during the interrupt acknowledge cycle | DR-0004 |
| `halt` | 1 | output | CPU, on a reserved encoding (stop fetching; DR-0005) | DR-0005 |

This table is the complete top-level interface the RTL must present: every
core signal is listed here, and each control signal is defined by the
record named in the last column. Clock and reset are supplied by the
harness (repo charter), not by this record.

Ports are **index-addressed, not memory-mapped**: `OUT #3` pulses
`strobe[3]`; `IN #5` pulses `select[5]`. The 3-bit field caps the count at
8 each (fallback would halve to 4 — row 5 — with the same timing).

## Cycle-level timing (targets, verified by DR-0005)

### `OUT #p` — 2 cycles

| Cycle | strobe[p] | data bus | Notes |
|---|---|---|---|
| 1 | 0 | high-Z | opcode byte fetched |
| 2 | **1** | **A** | external world samples `data` on the rising edge ending cycle 2 |
| 3 (next instr) | 0 | high-Z | strobe is a one-cycle pulse |

Rules: exactly one strobe bit is high, for exactly one cycle, always cycle 2
of the instruction. Two `OUT`s to the same port back-to-back are two
distinguishable pulses. The value on the bus during the pulse is A at the
*start* of cycle 2 (an `OUT` cannot observe its own transfer).

### `IN #p` — 2 cycles

| Cycle | select[p] | data bus | Notes |
|---|---|---|---|
| 1 | **1** | high-Z | opcode byte fetched; external world sees the select early |
| 2 | 1 | **driven by external world** | CPU samples `data` on the rising edge ending cycle 2 |
| 3 (next instr) | 0 | high-Z | |

Rules: the select asserts a full cycle **before** the capture edge, so
slow external multiplexers have one cycle of settle time; the select stays
asserted through the capture cycle and drops with the next opcode fetch.
`Z` is set from the captured value (DR-0001). The CPU never drives the bus
during `IN`.

### Bus ownership

- The bus is high-Z unless an `OUT` is in its cycle 2. No idle drive, no
  pull state specified at the chip level (that is the integrator's job, via
  the PDK's IO cells — outside this spec's scope except that the core
  presents tri-state `data_io[7:0]`).
- Interrupt vector capture (DR-0004) is the one hardware-driven bus read:
  during the acknowledge cycle the interrupting controller drives the bus;
  rules are in DR-0004, this record owns the "who drives" split.

## Options considered

- **Memory-mapped I/O vs port-indexed (chosen):** port-indexed needs no
  address bus, no bus cycles beyond the transfer, and no address decoder in
  the peripheral fabric — it is the cheapest model consistent with a
  control processor that has no data memory space (DR-0001).
- **8 strobes / 8 selects (chosen):** matches the draft table; 8 is one
  3-bit field, which is why the fallback is 4/4 rather than 16/16. More
  strobes without widening the field means external decoding — the
  integrator's choice, not the ISA's.
- **One-cycle vs two-cycle transfers (chosen: two):** a one-cycle `OUT`
  would leave external logic no setup margin, and a one-cycle `IN` would
  allow no settle time; both would couple the core's cycle-exact timing to
  the slowest peripheral. Two cycles keep the core's promise clean and
  testable: pulse width = exactly 1 cycle, select lead = exactly 1 cycle.

## Evidence

- This record's timing is self-contained (a spec choice, not a fact to
  cite), but its feasibility constraints come from the verified corner
  context in DR-0006: at ≥ 10 MHz (100 ns period) a one-cycle pulse is
  ≥ 100 ns wide at target — ample for the peripheral fabrics this part is
  chartered for, and the cocotb tests assert the pulse at cycle resolution,
  not wall-clock.
- PDK IO cells exist outside the core library (`libraries/gf180mcu_fd_io`
  in `efabless/gf180mcu-pdk`, `main` @ `ff2a6056a2e6`, fetched 2026-11-19);
  the core-to-pad boundary is a flow-stage concern and is not specified
  here.

## Verification method

Maps to target-table row 5.

1. **cocotb strobe test:** run `OUT #p` for all 8 ports; assert `strobe[p]`
   high exactly in cycle 2, exactly one bit high, `data` == A during the
   pulse, high-Z after.
2. **cocotb select test:** run `IN #p` for all 8 ports; assert
   `select[p]` high in cycles 1–2, bus sampled at the cycle-2 edge, Z flag
   per captured value.
3. **Back-to-back test:** two `OUT`s to one port → two distinct pulses;
   `OUT` followed by `IN` → no overlap of drive windows.
4. **Gate-level repeat:** the same two tests on the post-synthesis netlist
   (DR-0005), so tri-state behavior survives synthesis.
5. **Simulator agreement:** the cycle-accurate simulator models the same
   windows; per DR-0005 it must agree with RTL on every test program.
