# DR-0002 — Registers and state

- **Status:** proposed
- **Decides:** the architecturally visible state — accumulator, general
  registers, program counter, flags, subroutine return stack — and the
  reset state.
- **Owns table rows:** target-table rows 2 (program address, jointly with
  DR-0001) and 3 (registers).
- **Supersedes:** the DRAFT "16 general registers plus an accumulator" row
  (changed to 8 + accumulator with the reason recorded in § Options
  considered; fallback, reset state, and stack rules added).

## Decision

| Element | Size | Count | Notes |
|---|---|---|---|
| Accumulator `A` | 8 bits | 1 | Implicit operand of logic/shift/immediate ops; register field value `000` (DR-0001). |
| General registers `R0`–`R7` | 8 bits | 8 | Uniform, interchangeable; no special roles assigned by hardware. |
| Program counter `PC` | 11 bits | 1 | 2 KB program space (row 2 target). Fallback 10 bits, stretch 12 bits — see trade below. |
| Flags | 1 bit each | 3 | `Z` (result zero), `C` (carry/borrow/shift-out capture), `IE` (interrupt enable). |
| Return stack | 11 bits × entries | 8 entries | Holds return addresses for `CALL`/`RET` and interrupt return (DR-0004). Hardware, not memory. |

Total register state: A + 8×8 + PC + 3 flags + 8×11 stack = 174 flip-flop
bits of architecturally visible state (plus control latching: interrupt
mask/vectored-capture bookkeeping, see DR-0004).

## Options considered

- **8 general registers (chosen) vs the draft's 16:** the draft value was
  16 + accumulator; the encoding analysis moves it to 8. Every register
  operation in DR-0001 is a single 8-bit byte, which forces 3-bit register
  fields (`00 rrr sss` MOV, `01 ooo rrr` group ops); 16 registers need
  4-bit fields, and 4+4 or 4+3 bit layouts do not fit an 8-bit word with an
  opcode. Keeping 16 would cost one of: two-byte register operations
  (cycles and code size in a 2 KB program), an A-only register access
  scheme, or register banking (more state, more decode). The flop area the
  extra eight registers would add is trivial — 64 bits ≈ 8 `dffq_1` cells
  ≈ 0.0005 mm² (see Evidence) — so the deciding currency is not area but
  uniformity: 8 flat registers keep every instruction single-byte and the
  decoder trivial. A 16-register banked extension remains available to a
  future decision record (DR-0001 § Registers named by the ISA).
- **8-entry hardware return stack (chosen) vs 4 or 16:** 4 entries is the
  floor for `CALL` nesting plus one interrupt (which needs 2: current PC and
  a safe margin, DR-0004); typical control hierarchies nest deeper than 4.
  16 entries doubles stack area for a depth most control programs never
  touch. 8 covers interrupt + 7 nesting levels.
- **Separate interrupt stack vs shared (chosen: shared):** one stack
  removes a second 11-bit pointer/index; the interrupt model (DR-0004) is
  one level, so interleaving depth is bounded.
- **PC width 11 (chosen):** 2 KB is the draft value and matches the class
  structure: branch targets are 11-bit absolutes `{aaa, byte1}` (DR-0001).
  10-bit fallback would shrink branch encodings to 2 KB→1 KB but the
  encodings do not shrink — only the reachable space does; 12-bit stretch
  would add a PC bit and page-7→page-15 vector space, reserved if ever
  needed.

## Flags semantics

- **Z** — set by result-producing operations when the 8-bit result is zero
  (logic ops, shifts, `IN`, immediates, `INC`/`DEC`); by `CMP` on equality.
  Not touched by `MOV` register-to-register, `RET`, `REI`, `NOP`, `CLC`,
  `STC`, `CALL`, branches.
- **C** — captures, in order of producer: `INC` carry-out (operand was
  0xFF), `DEC` borrow-out (operand was 0x00), `SHL` old bit 7, `SHR` old
  bit 0, `CMP` magnitude (A < R → 1), `STC` 1, `CLC` 0. C is the loop and
  serial-shift working bit; there is no chain of arithmetic flags (no
  overflow/negative/auxiliary — the ISA has no signed arithmetic to serve).
- **IE** — the interrupt mask. **IE = 0 (masked) at reset**, and set to 1
  only by `REI` (DR-0004). There is no `EI`/`DI` instruction: the
  ISA keeps interrupt control to entry/return hardware, and control code
  gets its critical sections from the automatic mask-at-entry behavior.

## Reset state

| Element | At reset |
|---|---|
| PC | 0x000 |
| A | 0x00 |
| Z, C | 0 |
| IE | 0 (interrupts masked) |
| R0–R7 | **Indeterminate** (no reset flops — area; software initializes before use) |
| Return stack | All 8 entries invalid; a pop from an all-invalid stack returns 0x000 (defined, testable) |

GPRs without reset is a deliberate area/robustness trade: resettable flops
(`dffrnq`-style cells) cost visibly more area per bit than plain `dffq`, and
a control processor's first act is initialization. The rule that keeps this
safe: **no test program may read a register before writing it**, enforced by
the simulator and the cocotb suite (DR-0005), so RTL X-propagation cannot
hide.

## Return stack rules

- `CALL` pushes the PC of the following instruction (already advanced past
  both bytes); `RET` pops.
- Interrupt entry pushes the interrupted PC (DR-0004); `REI` pops and sets
  IE.
- **Overflow** (push when all 8 entries hold valid returns): the entry
  index wraps to the bottom; the oldest return is overwritten and lost.
  The behavior is defined and testable, not trapped — this CPU has no
  exception machinery, and a trap path costs more than the discipline of
  not nesting 8 deep.
- **Underflow** (pop when no valid entry): PC ← 0x000. Defined and
  testable, same reasoning.
- Validity: each entry has a valid bit; entry 0 is valid after the first
  push, entries never valid at reset.

## Evidence

- Cell sizes used in the area trade above, from the library's LEF data
  (`main` @ `43beb45e4d32`, fetched 2026-11-19):
  `gf180mcu_fd_sc_mcu7t5v0__dffq_1` = 16.24 × 3.92 µm ≈ 63.7 µm²;
  `..._nand2_1` = 2.8 × 3.92 µm ≈ 11.0 µm²;
  `..._inv_1` = 2.24 × 3.92 µm ≈ 8.8 µm²;
  `..._mux2_1` = 7.28 × 3.92 µm ≈ 28.5 µm².
  Source: <https://github.com/google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0>
  (`cells/<cell>/<cell>_1.lef`).
- Draft value provenance: the pre-spec README target table (16 registers +
  accumulator) — **changed** to 8 by the encoding analysis in § Options
  considered; recorded here so the departure from the draft is traceable.

## Verification method

Maps to target-table row 3 (and row 2 jointly with DR-0001).

1. **cocotb register file test:** write/read every register index
   (including A as field `000`), all bit patterns, confirm independence
   between registers.
2. **Flag semantics test:** every producer/consumer pair from § Flags
   semantics, asserted against the DR-0001 table.
3. **Stack tests:** depth-8 nesting, deliberate overflow (oldest lost),
   deliberate underflow (PC ← 0x000), `CALL`/interrupt interleaving.
4. **Reset test:** post-reset PC/A/flags/IE/stack-validity asserted;
   GPR-indeterminacy enforced by the read-before-write rule in the
   simulator and testbench.
5. **PC width:** branch to every extreme target (0x000, 0x7FF) in sim and
   RTL; assembler rejects 12-bit targets.
