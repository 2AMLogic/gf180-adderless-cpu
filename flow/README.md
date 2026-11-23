# flow

Synthesis and place-and-route recipes (Yosys, OpenROAD), driven through klt.

## Structural power delivery (T1 item 11)

**Every `klt place-and-route` request in this directory carries a `power`
block, and every digital claim built on one is gated on three reads, not
one.** Without `request.power`, `klt place-and-route` still reaches
`target_stage: "route"` and reports `status: "ok"` having run no `tapcell`,
no `global_connect`, no `pdngen` and no filler placement — the routed DEF
has no `SPECIALNETS` section at all, and gate-level LVS still reports
`match`, because a signal-only compare has nothing to say about power. That
is the exact shape `sky130-fpga#41` and `sky130-usb2-phy#59` shipped with.

**`power.row_rail.emitted: true` in a response is not evidence of a PDN
either.** It is a `sky130_fd_sc_hd`-only routing-obstruction fallback
(klayout-tools issue #1442): a real, drawn row-rail shape that keeps the
router from treating a standard cell's own `VPWR`/`VGND` rail as open space
even when `request.power` was omitted entirely. It draws no strap grid, runs
no `tapcell`, and inserts no filler — `emitted: true` only means the
fallback fired, never that a PDN exists.

The three gates, and where each is read:

1. **`power.pdn: true`** in the P&R response, with a named tapcell master.
2. **`power_connectivity.status: "match"`** in a `klt lvs` response — which
   requires `reference.form: "gate-level-verilog"`, the only reference form
   for which `klt lvs` runs the power/ground half of the compare at all.
   Gate on **both** `status` and `power_connectivity.status`; the exit code
   reflects the signal verdict only.
3. **A `klt erc` supply read** declaring `power_net`/`ground_net` as
   `"kind": "supply"` over every strap layer, reporting one electrical
   island per supply and zero `missing_tie`.

`request-par.json` in this directory is a starter request carrying this
PDK's default PDN strap geometry in its `power` block (`power_net`/
`ground_net` plus `straps[]`, layers listed bottom-to-top) — gate 1
above. Fill in the `<!-- FILL: ... -->` markers (netlist path, top-level
module, floorplan utilization, IO layers, clock constraints) once synthesis
is wired up; the `power` block itself needs no per-block edits. Gates 2
and 3 still need their own requests — a `klt lvs` request with
`reference.form: "gate-level-verilog"` and `options.power_connectivity`,
and a `klt erc` supply spec — once there is a routed layout to check.

## Smoke flow (issue #18)

`flow_smoke.py` pushes `rtl/smoke_reg.v` (the 1-bit register from the
verification harness) through the whole implementation path from committed
klt requests, and writes or checks one evidence record per step under
`evidence/`. It is a toolchain exercise: it says nothing about the CPU,
the ISA, any spec content, or the block's target library, site or corner.
Those stay spec decisions (#6).

| Step | Committed request | klt command | Evidence | Gate |
| --- | --- | --- | --- | --- |
| `synth` | `request-synth-smoke.json` | `klt synthesize` | `evidence/synth.json` | none (`status: "ok"`, no structural finding) |
| `par` | `request-par-smoke.json` | `klt place-and-route` to `target_stage: "route"` | `evidence/par.json` | gate 1: `power.pdn: true` with a named tapcell master |
| `drc` | `request-drc-smoke.json` | `klt drc --deck gf180mcu` | `evidence/drc.json` | `status: "clean"` |
| `lvs` | `request-lvs-smoke.json` | `klt lvs`, `reference.form: "gate-level-verilog"`, `options.power_connectivity` | `evidence/lvs.json` | gate 2: `status` and `power_connectivity.status` both `"match"` |
| `erc` | `request-erc-smoke.json` | `klt erc` supply read | `evidence/erc.json` | gate 3: one island per supply, zero `missing_tie`, tie check run |

`request-par-smoke.json` is the starter request with its `FILL` markers
filled and the `power` block unchanged; `request-par.json` stays for the
real block. The smoke fills it as follows, none of which is a statement
about the block:

- `utilization_pct: 0.5`. The starter's Metal5 strap needs at least
  94.08 um of core height (klt's own pre-flight), and a one-flop design
  only yields a core that large at a sub-percent target.
- `core_margin_um: 4`, IO layers `Metal3` (horizontal) / `Metal4`
  (vertical): inside klt's `Metal2-Metal5` signal range for this library.
- `clock_port: "clk"`, `clock_period_ns: 30`: an arbitrary constraint so
  the clock exists; `timing_status` is still `"unconstrained"` (the design
  has no register-to-register path and no I/O delays are given), and
  timing is out of scope here.
- `outputs.dir` under `flow/build/` and `portable_paths: true`, so the
  artifacts land at stable, repo-relative paths and the reports carry no
  host path. `flow/build/` is scratch and is cleared at the start of every
  run.

**PDK variant.** The `power` block straps `Metal4` and `Metal5`, which only
the 5-metal-stack gf180mcu variants have; klt's default discovery picks
`gf180mcuA` (3 metals), where `place` dies with `PPL-0051`. The runner
therefore resolves `--pdk gf180mcuC` (a runner argument, set for klt both
as the `--pdk` flag and as `$PDK`), and the requests name it where they
can. `--cell-library`, `--corner` and `--site` are runner arguments too
that default to the committed requests' values; an override is applied to
a copy under `flow/build/effective/`, never to the committed file, and is
recorded in the evidence's `request_overrides`.

### Toolchain pin

`layout/toolchain_pin.py` runs first: it reads `layout/toolchain.json`,
requires `klt --version` to name the pinned klayout-tools version and
every `klt_required_commands` entry to be a subcommand of `klt --help`,
and the run is BLOCKED otherwise. The klt install is the same
`klayout-tools==0.9.2` venv `make smoke` builds (`FV_PINS`); `yosys` and
`openroad` come from the host `PATH` and are recorded in each record's
`flow.engine_versions`, not pinned.

### What the committed evidence says

Every record is klt's own JSON report (artifact paths dropped, the DRC
violation list cut to its first 25 entries with the counts kept) plus a
`flow` block: the claim, the klt argv, the request and RTL sha256, any
override, the verdict, the gate readings and the reasons. On this
toolchain (klt 0.9.2, Yosys 0.67+post, OpenROAD 26Q3-1510, gf180mcuC):

- `synth`: one `gf180mcu_fd_sc_mcu9t5v0__dffrnq_1`.
- `par`: route reached, 0 routing DRC violations, 0 antenna violations,
  `power.pdn: true`, tapcell master `gf180mcu_fd_sc_mcu9t5v0__filltie`,
  `power.placed.status: "complete"` -- **gate 1 met**.
- `lvs`: `status: "match"`, `power_connectivity.status: "match"` --
  **gate 2 met**.
- `erc`: `erc_status: "clean"`, VDD and VSS each one island, the nwell and
  pwell tie checks run with zero findings -- **gate 3 met**.
- `drc`: `status: "violations"`, 1489 hits, all on the PDN: the via
  arrays the `power.connects` tuning generates (`metal2/3/4.ongrid.1`,
  `via2/3.ongrid.1`, `via2/3.width.1`) and the tapcell pitch
  (`comp.tap_distance.nwell.mv.1`, `comp.tap_distance.psub.mv.1`). The
  smoke's `power` block is the starter's, kept unchanged as the issue
  requires, so this is a finding about the flow, not something to work
  around: [klayout-tools#7311](https://github.com/2AMLogic/klayout-tools/issues/7311),
  tracked here in #23.
  The report's coverage block is quoted in `layout/README.md`.

So `make flow-smoke` currently exits 1 (FAIL): four steps pass, the DRC
gate is unmet. A blocked gate is never reported as a pass.

### Statuses (`flow/flow_smoke.py`)

Same convention as `make smoke`:

| status | exit | meaning |
| --- | --- | --- |
| PASS | 0 | every step reached a verdict, every gate is met and, in check mode, the committed evidence reproduces |
| FAIL | 1 | a gate is unmet, or the committed evidence does not reproduce (an altered record, a BLOCKED record whose step now runs, other RTL or klt version) |
| BLOCKED | 2 | the pinned toolchain is not what is installed, `yosys`/`openroad` is missing, klt could not produce a report for a step (error exit, no JSON, timeout), or klt reached no verdict (for example a skipped tie check). Never a pass |

A step whose input step is BLOCKED is recorded BLOCKED as not reached and
the run continues with the steps that do not depend on it. `--write`
records every step as it came out, BLOCKED and FAIL included; a step that
waits on an upstream klayout-tools issue takes `--blocked-issue STEP=URL`
and the link is written into its record. `make` itself exits 2 whenever a
recipe fails; the runner's own exit code is the `flow-smoke: <STATUS>`
line's status.

Check mode re-runs every step and compares the whole scrubbed report and
`flow` block with the committed record. Artifact paths, run ids and klt's
tool-version provenance are excluded, as klt's own `--check --rerun`
excludes them (a tool upgrade that leaves the result untouched is churn,
not drift); that exclusion covers the engine build strings klt itself
reports per step (`engine_version`, `environment.engine_version`). The
klt version is still required to match, and `python3
tools/check_pins.py` keeps the committed records naming the pinned
version. The runner's own `flow.engine_versions` -- the yosys and
openroad build strings recorded from the host PATH -- are not excluded:
check mode compares them verbatim.

A check failure confined to `/flow/engine_versions/yosys` or
`/flow/engine_versions/openroad` means the committed evidence was written
by a differently built engine, not that the physical results drifted.
Compare the build strings recorded in the committed evidence with the
ones your host reports, and rerun on a host whose builds match before
drawing conclusions about the physical results.

### Where it runs, and why not in CI

`make flow-smoke` needs the pinned venv (network once), `yosys` and
`openroad` on `PATH`, and an installed gf180mcu PDK that klt can resolve
(`klt pdk find`). CI runs only the hermetic parts: `tools/test_flow_exits.py`
(a fake klt, no engine, PDK or network) and `tools/check_pins.py`. The
live lane is not a CI job because none of that installs within the job:
OpenROAD has no Ubuntu package (this evidence was produced with the
`openroad/orfs` image pinned by digest), a gf180mcu install is a
multi-gigabyte fetch, and the place-and-route numbers in the evidence are
tied to the OpenROAD build that produced them, so a differently built
runner would report drift that is not evidence drift. Run it on a host
that has those tools; the committed evidence names the builds it came
from.

```
make flow-smoke          # check mode, exit 0 = PASS
make flow-smoke-write    # regenerate flow/evidence/ from this host
make flow-tests          # hermetic exit-code contract tests
python3 tools/check_pins.py   # fast lane: evidence names the pinned toolchain
```

### Bumping the pinned toolchain

Bump `FV_PINS` in the `Makefile` and `klt_install` /
`klt_last_verified_commit` in `layout/toolchain.json` together, appending
the reason to that file's header, then `rm -rf .venv-fv`, `make smoke`
(recreates the venv) and `make flow-smoke-write` to regenerate the flow
evidence (and the verification evidence, see `verification/README.md`).
The pin check BLOCKS a run whose installed klt is not the pinned one, and
`check_pins.py` fails the fast lane while any committed record names
another version.
