# DR-0006 — Timing and area

- **Status:** proposed
- **Decides:** the cell library and voltage, the clock target and corners,
  the core area bound, and the with-adder comparison plan (name, method,
  metrics — not the measurement itself).
- **Owns table rows:** target-table rows 7 (supply), 8 (clock), 10 (area),
  11 (with-adder comparison).
- **Supersedes:** the DRAFT "Supply 5 V (stretch 3.3 V and 5 V)", "Clock
  ≥ 10 MHz at 5 V (stretch ≥ 25 MHz)" and "AREA ≤ 0.05 mm² (stretch
  ≤ 0.03 mm²)" rows (supply stretch narrowed to what the library actually
  publishes; clock and area kept with verification methods attached).

## Cell library (the 7-track 5 V claim, confirmed)

The Curator flagged this as unverified; it is now verified against the PDK:

- The gf180mcu PDK ships exactly **two** standard-cell libraries:
  `gf180mcu_fd_sc_mcu7t5v0` (7-track, 5 V nominal) and
  `gf180mcu_fd_sc_mcu9t5v0` (9-track, 5 V nominal). There is no 3.3 V
  library and no 3.3 V track variant.
- **This design uses `gf180mcu_fd_sc_mcu7t5v0`** — the smaller track height
  fits the area bound; the 9-track library buys speed this clock target
  does not need.
- Site: `GF018hv5v_mcu_sc7`; cell height 3.92 µm (7 tracks). Process:
  GlobalFoundries 180 nm MCU (0.18 µm), high-voltage 5 V option.

## Corners (what the library actually publishes)

The 7t5v0 library's `liberty/` directory publishes, per corner family
(fetched 2026-11-19, `main` @ `43beb45e4d32`):

| Family | Files (temp/voltage) |
|---|---|
| slow (`ss`) | n40 °C and 125 °C at 1.62 V / 3.00 V / **4.50 V** |
| typical (`tt`) | 25 °C at 1.80 V / 3.30 V / **5.00 V** |
| fast (`ff`) | n40 °C and 125 °C at 1.98 V / 3.60 V / **5.50 V** |

The three voltage families are the same cell set characterized at 1.8 V,
3.3 V and 5.0 V corners; 5.0 V is the family this design signs off in.

- **Nominal/timing-sign-off corner: `tt_025C_5v00`; STA worst-case corner:
  `ss_n40C_4v50`** (the slowest published point of the 5 V family — note
  there is no `ss` file *at* 5.00 V; 4.50 V is the family's worst voltage).
- **Supply row (row 7) decision:** target 5.0 V on `gf180mcu_fd_sc_mcu7t5v0`.
  **Fallback: none** (no second library exists). **Stretch (narrowed from
  the draft):** timing *also* closed at the library's 3.30 V corner files
  (`ss_n40C_3v00`, `tt_025C_3v30`, `ff_*_3v60`) — analysis only, as a
  portability check. This is deliberately weaker than the draft's "3.3 V
  and 5 V": the library publishes 3.3 V corners, but no 3.3 V *product*
  configuration, so this spec claims at most analysis closure and makes no
  silicon claim at 3.3 V.

## Clock (row 8)

- **Target: ≥ 10 MHz at 5 V.** Verification: post-layout STA at
  `ss_n40C_4v50` meets a 100 ns period (10 MHz), with the number recorded
  from this repo's own run — never quoted from a tool default.
- **Fallback: ≥ 6 MHz** (166.7 ns period) — adopted by decision record if
  the target misses on routing-dominated paths.
- **Stretch: ≥ 25 MHz** (40 ns period), pursued only after the target
  verifies.
- Method detail: STA is post-layout (parasitics included); the constraint
  file and the STA report are committed with the measurement, and
  gate-level simulation re-proves a full test-program pass at the target
  period (DR-0005's agreement rule extends here).

## Area (row 10)

- **Target: ≤ 0.05 mm² core** (placement core area, standard cells only,
  excluding pads — pad frame and IO cells are the integrator's).
- **Fallback: ≤ 0.08 mm².** **Stretch: ≤ 0.03 mm².**
- **Verification:** measurement taken with klayout-tools on the DRC-clean,
  LVS-matched layout and committed under `measurements/` as append-only
  evidence. Estimates never satisfy this row.

Sanity check that the target is engineering-reachable, not aspiration — a
bottom-up flop+gate budget from the library's LEF sizes (`main`
@ `43beb45e4d32`): DR-0002's 166 state bits ≈ 10.6 kµm² of flops
(`dffq_1` ≈ 63.7 µm²); decoder, ALU-lite (the no-adder logic of DR-0001),
control and I/O machinery ≈ 1.5–3 k equivalent `nand2_1` (≈ 11 µm² each)
≈ 17–33 kµm²; total cell area ≈ 27–44 kµm². At a conventional 70%
placement utilization the core lands ≈ **0.039–0.063 mm²** — the
0.05 mm² target sits inside that band, the 0.08 mm² fallback
clearly covers its loose end, and the 0.03 mm² stretch demands the
high end of gate-count efficiency. These are budget numbers from LEF
arithmetic, not a result; the row's verification method is the only thing
that can claim area.

## With-adder comparison (row 11) — the plan, not the measurement

The charter asks the repo to measure **what leaving the adder out buys**.
This record fixes the experiment so the eventual number means something;
making the measurement is out of scope here (target-table row 11, stretch
column).

- **Baseline (`adder-ref`):** a variant of this CPU differing in exactly
  one ISA feature — it adds `ADD A,r` (semantics: `A ← A + r` mod 256,
  C ← carry-out). **Encoding source, stated exactly:** DR-0001's class
  `01` has **no** reserved encodings — all eight `ooo` values are defined
  (INC, DEC, AND, OR, XOR, CMP, SHL, SHR) — so the baseline cannot take an
  encoding from reserved space. It takes the class-`01` encodings whose
  `rrr` field DR-0001's hardware ignores, the `SHL`-slot aliases
  `01 110 rrr` with `rrr ≠ 000` (7 encodings), and defines `ADD A,r`
  there for `r` ∈ R0–R6. Those encodings are **aliases of defined
  instructions, not reserved encodings**: adopting them means the baseline
  demotes the ignored-field alias behavior — in the baseline, `SHL` keeps
  only its assembler-emitted `rrr = 000` encoding — and `ADD A,A` (the
  `rrr = 000` operand value) does not exist; the adderless design keeps
  the aliases, and no *reserved* encoding of DR-0001 is promoted. No other
  change: same registers, I/O, interrupt model, cycle targets. Its
  incrementer/decrementer/comparator may collapse onto the
  adder where the synthesis tool chooses; the `addf`/`addh` netlist
  exclusion of DR-0001 **does not apply** to the baseline.
- **Method:** both designs go through the identical flow — same RTL style,
  same Yosys scripts (minus the baseline's cell exclusion), same OpenROAD
  constraints, same `ss_n40C_4v50` timing closure target, same placement
  density and utilization, same corner set. No parameter is tuned
  independently; if one design needs a constraint change, both get it.
- **Metrics (all Δ = adderless − adder-ref):** core area (mm², klt
  measurement, row 10 method); standard-cell count; achieved Fmax at
  4.50 V worst corner (STA); and netlist cell-type histogram (to show
  *where* the difference lives, not just how big).
- **Falsification:** if Δarea ≈ 0, the charter's premise ("leaving the
  adder out buys") is not supported for this design point, and the result
  is recorded as such. A null result is a result; `measurements/` is
  append-only evidence, so it gets recorded, not buried.
- **When:** after both designs individually pass rows 1–10. The
  comparison is a difference of two verified designs, not of two sketches.

## Evidence

- Library identity, corner files, and cell sizes:
  `google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0` — `liberty/`
  directory listing (corner files named above), `cells/<cell>/…_1.lef`
  (sizes), fetched 2026-11-19 from `main` @ `43beb45e4d32` —
  <https://github.com/google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0>
- Two-library fact (7t5v0 and 9t5v0 only, both 5 V): `efabless/gf180mcu-pdk`,
  `libraries/` listing, fetched 2026-11-19 from `main` @ `ff2a6056a2e6` —
  <https://github.com/efabless/gf180mcu-pdk>
- Metal stack options (2LM–5LM + 1TM tech LEFs ship with the 7-track
  library's `tech/` directory, same source as above): routing layer choice
  is a flow-stage decision, not fixed by this record.

## Verification method

Maps to target-table rows 7, 8, 10, 11.

1. **Library check:** the flow scripts name `gf180mcu_fd_sc_mcu7t5v0`
   explicitly; a check fails the build on any other library name.
2. **Clock:** post-layout STA at `ss_n40C_4v50` at the target period,
   report committed; gate-level sim pass at the target period.
3. **Area:** klt measurement on the DRC-clean layout, committed under
   `measurements/`; compared against row 10's bound in the record itself.
4. **Comparison:** when run, both designs' metrics recorded side-by-side
   in `measurements/` with the flow's commit hashes, so the deltas are
   reproducible.
5. **Supply stretch (if pursued):** STA closure at the three 3.30 V corner
   files, recorded as analysis only — the record and the measurement
   explicitly disclaim a 3.3 V silicon claim.
