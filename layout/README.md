# layout

GDS and DRC/LVS reports. For the block, empty until there is something to
lay out: the only layout here is the smoke register's (issue #18), which
is a toolchain exercise, not the block.

## Toolchain pin

`toolchain.json` pins the klayout-tools install the layout and flow
evidence was produced against (`klt_install`, `klt_last_verified_commit`)
and lists every `klt` command the runners invoke
(`klt_required_commands`). Its header comment is append-only: the pin
choice is recorded there as a new paragraph, never by editing an earlier
one. `toolchain_pin.py` is the one shared check of that pin; it is run
before any step of `make flow-smoke`, and `python3 tools/check_pins.py`
(fast lane) keeps the pin, the `Makefile`'s `FV_PINS` line and the
committed evidence naming the same version.

## DRC of the smoke register

`flow/evidence/drc.json` is the `klt drc --deck gf180mcu` report for the
routed `smoke_reg` (gf180mcuC, 5-metal stack), committed by
`make flow-smoke-write`. Its verdict is `violations` (1489), so the
smoke's DRC gate is unmet; every hit is on the PDN `request.power` builds
(`metal2/3/4.ongrid.1`, `via2/3.ongrid.1`, `via2/3.width.1`, all on the
`VIA_via2_3_*` via arrays the `split_cuts`/`ongrid` connect tuning
generates) or on the tapcell pitch (`comp.tap_distance.nwell.mv.1`,
`comp.tap_distance.psub.mv.1`). The report's own coverage block, quoted
rather than described:

```json
{
  "layers_in_stream_without_rules": [
    "0/0",
    "21/10",
    "34/10",
    "46/10",
    "63/63",
    "81/10",
    "204/10"
  ],
  "rules_skipped": [
    "bjt.separation.comp.1",
    "cap_mk.ongrid.1",
    "comp.separation.guard_ring_mk.1",
    "comp.tap_distance.nwell.lv.1",
    "comp.tap_distance.psub.lv.1",
    "diode_mk.ongrid.1",
    "dnwell.ongrid.1",
    "drc_bjt.ongrid.1",
    "efuse_mk.enclosing.lvs_source.1",
    "efuse_mk.ongrid.1",
    "efuse_mk.space.1",
    "esd.area.1",
    "esd.holes_area.1",
    "esd.overlap.comp.1",
    "esd.separation.nplus.1",
    "esd.separation.pplus.1",
    "esd.space.1",
    "esd.width.1",
    "fusetop.ongrid.1",
    "ldmos_xtor.enclosing.mvpsd.1",
    "metal1.separation.guard_ring_mk.1",
    "metal2.separation.guard_ring_mk.1",
    "metal3.separation.guard_ring_mk.1",
    "metal4.separation.guard_ring_mk.1",
    "metal5.separation.guard_ring_mk.1",
    "metaltop.ongrid.1",
    "metaltop.separation.guard_ring_mk.1",
    "metaltop.space.1",
    "metaltop.width.1",
    "mim.enclosing.fusetop.1",
    "mim.enclosing.via4.1",
    "mim.space.1",
    "mim_l_mk.ongrid.1",
    "mvpsd.ongrid.1",
    "mvsd.ongrid.1",
    "mvsd.separation.dnwell.1",
    "mvsd.width.1",
    "nwell.separation.guard_ring_mk.1",
    "pad.enclosing.metal5.1",
    "pad.ongrid.1",
    "plfuse.ongrid.1",
    "plfuse.separation.comp.1",
    "plfuse.separation.esd.1",
    "plfuse.separation.nplus.1",
    "plfuse.separation.resistor.1",
    "plfuse.separation.sab.1",
    "poly2.enclosing.sab.1",
    "poly2.separation.guard_ring_mk.1",
    "res_mk.ongrid.1",
    "resistor.ongrid.1",
    "sab.ongrid.1",
    "sab.separation.contact.1",
    "sab.space.1",
    "sab.width.1"
  ],
  "deck_scope": [
    "10.4.2 MIM Option B",
    "10.7 DRC_BJT Mark Layer",
    "7.12 Contact",
    "7.13 Metaln",
    "7.14 Vian",
    "7.15 MetalTop",
    "7.4 Nwell",
    "7.5 Comp",
    "7.7 Poly2",
    "7.8 Nplus",
    "7.9 Pplus",
    "9.1 Bond Pad",
    "EF",
    "ESD",
    "GR",
    "MDN",
    "MDP",
    "OFFGRID",
    "SB"
  ]
}
```

`layers_in_stream_without_rules` are the label and annotation layers the
GDS carries that no deck rule reads (`0/0` die area, `21/10`/`204/10` well
labels, `34/10`/`46/10`/`81/10` pin labels, `63/63` vendor text);
`rules_skipped` are deck rules that had no applicable geometry in this
stream; `deck_scope` is what the curated deck claims to implement.
