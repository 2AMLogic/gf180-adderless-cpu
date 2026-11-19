# DR-0001 — Instruction set

- **Status:** proposed
- **Decides:** the opcode map, addressing modes, instruction semantics, the
  set of arithmetic capabilities, and the no-adder rule.
- **Owns table rows:** target-table rows 1 (data width), 2 (program
  address), 4 (arithmetic scope).
- **Supersedes:** the DRAFT rows in the pre-spec README.

## Statement of originality

The instruction set in this record is **original to this repository**. No
historical processor's opcode map, encoding structure, microarchitecture,
die layout, or manual text is copied, and no compatibility with any
historical part is claimed or intended — not in this record, not in the
assembler, not anywhere in this repo. The design's inspiration (a forum post
about a 1970s control processor that cannot add, linked from the README) is
acknowledged as inspiration only; it is not a source for anything technical
here, and this record deliberately does not import any detail from it.

Concretely, what this means for reviewers and future contributors:

- The encodings below were laid out for this ISA from its own structural
  rules (two-bit major classes, three-bit register fields, an 11-bit branch
  target split 3+8). They were not transcribed or adapted from any existing
  part's datasheet, programming manual, or die photograph.
- If a future change makes an encoding match a historical part by accident,
  that is a bug: file it, change the encoding, record the change.
- No instruction, addressing mode, or program idiom of any historical part
  is reproduced on purpose.

## The no-adder rule

This processor contains **no adder**. The rule has three parts, and all
three are verified:

1. **ISA level:** there is no ADD, SUB, ADC, SBC, or any other instruction
   whose semantics are `a + b` or `a − b` over two arbitrary operands. The
   assembler rejects the mnemonics `ADD` and `SUB` (and every synonym) as
   errors. A "compare" instruction that is really a subtractor, or an
   "increment" that is really an adder, violates this rule just as much.
2. **Netlist level:** after synthesis, the netlist contains **zero**
   instances of the library's carry-propagate cells. The 7-track 5 V
   library ships `addf` (full adder) and `addh` (half adder) cells
   (verified in the library's `cells/` directory; see Evidence); those two
   cell names are excluded from the synthesis view and a post-synthesis
   check fails the build if either appears — including inside an
   incrementer, decrementer, or comparator.
3. **Structure level:** increment, decrement and compare are implemented
   without carry propagation. The incrementer's carry-out is an AND tree
   (`c[i] = AND(x[0..i−1])`, pure AND/NOR gates), not a chain of
   half-adders; the comparator is a bitwise XNOR/AND tree (equality) plus a
   priority structure (magnitude), neither of which propagates a carry.

What remains, and why it is not an adder: INC/DEC change a register by one
step; CMP produces equality and less-than flags from gate logic. Neither
performs addition of two independent operands, and neither needs or uses a
carry-propagate structure. This is the line the spec draws, and the netlist
check in (2) is what enforces it mechanically.

## Registers named by the ISA

`A` (accumulator) and `R0`–`R7` (general registers). In every encoding, the
3-bit register field value `000` designates **A**, so `MOV r,A` and
`MOV A,r` cover register↔accumulator moves with no separate opcode. See
DR-0002 for the full state model and for why the target is 8 flat registers
rather than the draft's 16.

Encoding consequence, stated so it cannot be "fixed" casually: **every
register field in this ISA is 3 bits.** A 16-register file does not fit the
8-bit instruction word with uniform single-byte register operations (a
4-bit field leaves no room for the opcode; 2-byte register ops cost cycles
and bytes). If a future revision wants more registers, the honest path is a
banked extension — a bank-select with the same 3-bit fields — adopted by its
own decision record, never by promoting reserved encodings ad hoc.

## Addressing modes

| Mode | Syntax | Encoded as |
|---|---|---|
| Implied | `SHL` | opcode only; operand is A |
| Register | `INC R3`, `MOV R7,A` | 3-bit register field in the opcode (`000` = A) |
| Register + immediate | `MOV R2,#imm8` | opcode byte, then one immediate byte |
| Absolute (program) | `JMP addr`, `CALL addr` | opcode byte carrying target bits [10:8], then one byte carrying bits [7:0] |
| Port | `OUT #p`, `IN #p` | 3-bit port field in the opcode |

There is no indirect, indexed, stack-relative or PC-relative addressing.
Control code addresses memory-like resources only through ports and
registers; the ISA has no data memory space. (Program memory is internal
and not programmatically readable except by executing it.)

## Opcode map

Every instruction word is 8 bits; two-byte instructions fetch one following
byte. All reserved encodings are illegal: the assembler rejects them, the
simulator and the RTL treat them as halt-and-flag (documented in DR-0005 /
DR-0002), and no future revision will silently promote a reserved encoding
to a defined one — that takes a new decision record.

### Class `00` — MOV (register to register)

```
00 rrr sss   MOV R(rrr), R(sss)     ; field 000 means A; covers A + R0–R7
```

64 encodings, all defined. `MOV X,X` is legal and defined as a no-op (it
still costs one cycle; it does not touch flags).

### Class `01` — register and accumulator operations

```
01 ooo rrr   ; rrr: 000 means A where the operand is a register
```

| `ooo` | Mnemonic | Semantics (8-bit) | Flags | Cycles (target) |
|---|---|---|---|---|
| 000 | `INC r` | r ← r + 1 (mod 256) | C ← carry-out (r was 0xFF → C=1); Z ← result==0 | 1 |
| 001 | `DEC r` | r ← r − 1 (mod 256) | C ← borrow-out (r was 0x00 → C=1); Z ← result==0 | 1 |
| 010 | `AND A,r` | A ← A & r | Z ← result==0 | 1 |
| 011 | `OR A,r` | A ← A \| r | Z ← result==0 | 1 |
| 100 | `XOR A,r` | A ← A ^ r | Z ← result==0 | 1 |
| 101 | `CMP A,r` | no operand written; Z ← (A == r); C ← (A < r, unsigned) | Z, C | 1 |
| 110 | `SHL` | A ← A << 1; A[0] ← 0; C ← old A[7] | C, Z | 1 |
| 111 | `SHR` | A ← A >> 1; A[7] ← 0; C ← old A[0] | C, Z | 1 |

For `SHL`/`SHR` the `rrr` field is ignored by hardware; the assembler always
emits `000`.

Note on `CMP`: the magnitude result comes from the gate-level comparator of
the no-adder rule (equality from an XNOR tree, less-than from a priority
structure) — no subtraction is performed, no carry propagates. `INC`/`DEC`
carry/borrow come from the AND-tree rule above.

### Class `10` — branches (two bytes: absolute 11-bit target)

```
10 ccc aaa   + [7:0]     ; target = {aaa, byte1}, 11 bits
```

| `ccc` | Mnemonic | Taken when | Not-taken cycles | Taken cycles |
|---|---|---|---|---|
| 000 | `JMP addr` | always | — (2 total) | — (2 total) |
| 001 | `JZ addr` | Z = 1 | 2 | 3 |
| 010 | `JNZ addr` | Z = 0 | 2 | 3 |
| 011 | `JC addr` | C = 1 | 2 | 3 |
| 100 | `JNC addr` | C = 0 | 2 | 3 |
| 101 | reserved | — | — | — |
| 110 | reserved | — | — | — |
| 111 | reserved | — | — | — |

`JMP` is 2 cycles (it is always taken).

### Class `11` — immediate, port, stack and control operations

```
1100 rrrx  + imm8      MOV r,#imm8   (x = 0; rrr = 000 is LDA A,#imm8;
                       x = 1 encodings reserved)
1101 0ppp              OUT #p   (p = 0..7)
1101 1ppp              IN #p    (p = 0..7)
1110 0000             RET
1110 0001             REI
1110 0010             WAI
1110 0011             NOP
1110 0100             CLC   (C ← 0)
1110 0101             STC   (C ← 1)
1110 0110..1110 1111  reserved
1111 0aaa  + [7:0]    CALL addr   ; 11-bit absolute target = {aaa, byte1},
                      ; encoded exactly like a class 10 branch target
1111 1aaa  + [7:0]    reserved
```

| Mnemonic | Semantics | Flags | Cycles (target) |
|---|---|---|---|
| `MOV r,#imm8` | r ← imm8 (rrr=000: `LDA A,#imm8`) | Z ← result==0 | 2 |
| `OUT #p` | cycle 1: nothing observable; cycle 2: data bus ← A, strobe[p] asserted (see DR-0003) | none | 2 |
| `IN #p` | cycle 1: select[p] asserted; cycle 2: A ← data bus (see DR-0003) | Z ← result==0 | 2 |
| `RET` | PC ← pop() from return stack | none | 2 |
| `REI` | PC ← pop(); IE ← 1 (unmask) | IE | 3 |
| `WAI` | halt at end of this instruction until an unmasked interrupt arrives, then run the DR-0004 entry sequence | — | (stall + entry cost) |
| `NOP` | nothing | none | 1 |
| `CLC` | C ← 0 | C | 1 |
| `STC` | C ← 1 | C | 1 |
| `CALL addr` | push PC (already advanced past both bytes); PC ← target | none | 3 |

## Full ISA summary

24 defined mnemonics: `MOV`, `LDA`, `INC`, `DEC`, `AND`, `OR`, `XOR`, `CMP`,
`SHL`, `SHR`, `JMP`, `JZ`, `JNZ`, `JC`, `JNC`, `OUT`, `IN`, `RET`, `REI`,
`WAI`, `NOP`, `CLC`, `STC`, `CALL`. What the set deliberately omits, and
what replaces it:

| Omitted | Replacement |
|---|---|
| ADD / ADC | `INC` in a loop; counting is event-driven, not arithmetic |
| SUB / SBC / negative operands | `DEC` in a loop; `CMP` for threshold tests |
| Bit-addressable memory | `AND`/`OR`/`XOR` with immediate masks on A and registers |
| Multi-level, prioritized interrupts | one level (DR-0004) |
| Multiply / divide | out of scope by charter: this is a control processor |
| Data memory (load/store) | registers hold all working state; I/O through ports |

## Evidence

- PDK primary source, library cell inventory (the `addf`/`addh` cells the
  netlist check must exclude): `google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0`,
  `cells/` directory listing, fetched 2026-11-19 from `main` @ `43beb45e4d32`
  — <https://github.com/google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0>
- Umbrella PDK repository (the standard-cell libraries the flow uses):
  `efabless/gf180mcu-pdk`, `libraries/` listing, fetched 2026-11-19 from
  `main` @ `ff2a6056a2e6` — <https://github.com/efabless/gf180mcu-pdk>
- Inspiration acknowledged, not a source: r/nicechips post linked from the
  README. Deliberately not consulted for any technical content of this
  record; no historical opcode map was compared against these encodings,
  because importing one is exactly what the charter forbids.

## Verification method

Maps to target-table rows 1, 2, 4.

1. **Assembler negative tests:** `ADD`, `SUB`, `ADC`, `SBC` and every
   reserved encoding are rejected with errors; every defined mnemonic
   assembles to exactly the encoding above.
2. **Simulator conformance:** the instruction-level simulator implements
   exactly the semantics and cycle counts of this record; a table-driven
   conformance suite exercises every defined opcode, every boundary value
   (0x00, 0xFF wraps, shift bit capture, flag outcomes).
3. **Netlist check:** post-synthesis, a script asserts the netlist
   instantiates zero `addf`/`addh` cells (rule 2 of the no-adder rule).
4. **RTL agreement:** cocotb runs the same conformance programs against the
   RTL; per DR-0005, sim and RTL must agree cycle-for-cycle on every one.
