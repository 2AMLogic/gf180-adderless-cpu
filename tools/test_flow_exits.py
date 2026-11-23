"""Exit-code contract tests for flow/flow_smoke.py (issue #18).

Subprocess-driven and hermetic, modelled on tools/test_smoke_exits.py:
each case points --venv at a scratch fake venv whose bin/klt is a script
that answers `--version`, `--help` and the five flow subcommands with
canned klt-shaped reports, so no real klt, yosys, openroad, PDK or network
is involved (yosys/openroad are stubbed on PATH).  Covers the verdict tiers
a healthy toolchain cannot hit on purpose: a DRC run with violations
(FAIL, 1), a klt tool failure (BLOCKED, 2) with its downstream steps
recorded as not reached, a tie check klt skipped rather than ran, an lvs
power/ground verdict klt left `unchecked` (both BLOCKED, never a pass), a
pin that names a command the install lacks (BLOCKED before any step runs),
and a committed record that no longer reproduces (FAIL).

Run: python3 tools/test_flow_exits.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TREE_DIRS = ("flow", "layout", "rtl")

PROV = {"klt_version": "0.9.2", "klt_git_commit": "c0ffee",
        "klt_reinstall_spec": "klayout-tools==0.9.2",
        "pdk": {"name": "gf180mcuC", "source": "search root: ~/x"},
        "deck": {"name": "d", "content_hash": "sha256:deck"},
        "input": {"content_hash": "sha256:in", "role": "layout"}}

REPORTS = {
    "synthesize": {
        "status": "ok", "instance_count": 1,
        "instance_counts_by_type": {"lib__dffrnq_1": 1},
        "structural": {"has_critical": False}, "netlist_sha256": "n" * 64,
        "netlist_path": {"path": "flow/build/synth/smoke_reg_synth.v",
                         "scope": "repo"},
        "provenance": dict(PROV, input={"content_hash": "sha256:rtl",
                                        "role": "source"})},
    "place-and-route": {
        "status": "ok", "stage_reached": "route",
        "power": {"pdn": True, "tapcell_master": "lib__filltie",
                  "placed": {"tapcells": 14,
                             "def_path": {"path": "flow/build/par/x.def",
                                          "scope": "repo"}}},
        "def_path": {"path": "flow/build/par/smoke_reg.def", "scope": "repo"},
        "provenance": dict(PROV, input={"content_hash": "sha256:netlist",
                                        "role": "netlist"})},
    "drc": {
        "status": "clean", "violation_count": 0, "rule_counts": {},
        "violations": [],
        "coverage": {"nothing_checked": False, "rules_skipped": ["a.b.1"]},
        "file": {"path": "flow/build/par/smoke_reg.gds", "scope": "repo"},
        "provenance": dict(PROV)},
    "lvs": {
        "status": "match", "power_connectivity": {"status": "match"},
        "layout": {"path": "flow/build/par/smoke_reg.gds", "scope": "repo"},
        "reference": {"path": "flow/build/par/smoke_reg.v", "scope": "repo"},
        "provenance": dict(PROV)},
    "erc": {
        "status": "clean", "erc_status": "clean", "erc_findings": [],
        "nets": [{"name": "VDD", "matched_islands": 1},
                 {"name": "VSS", "matched_islands": 1}],
        "erc_coverage": {"skipped": [], "missing_tie_checked": True},
        "file": {"path": "flow/build/par/smoke_reg.gds", "scope": "repo"},
        "spec": "flow/request-erc-smoke.json",
        "provenance": dict(PROV)},
}

POWER_UNCHECKED_REASON = ("no power-pin universe is derivable from the "
                          "reference library's pin-order data")
LVS_CASES = {
    "lvs_power_unchecked": ("match", {"status": "unchecked",
                                      "reason": POWER_UNCHECKED_REASON}),
    "lvs_power_unchecked_no_reason": ("match", {"status": "unchecked"}),
    "lvs_mismatch_power_unchecked": (
        "mismatch", {"status": "unchecked", "reason": POWER_UNCHECKED_REASON}),
}

FAKE_KLT = r'''#!/usr/bin/env python3
import json, os, sys, uuid
argv = sys.argv[1:]
def emit(report, code=0):
    print(json.dumps(report))
    sys.exit(code)
if "--version" in argv:
    print("klt 0.9.2")
    sys.exit(0)
if "--help" in argv:
    print("usage: klt [-h] [--version] <command> ...\n\npositional "
          "arguments:\n    drc      run a headless DRC deck\n    lvs      "
          "compare\n    erc      connectivity model\n    synthesize\n     "
          "           synthesize RTL\n    place-and-route\n              "
          "   place and route\n\noptions:\n  -h, --help\n")
    sys.exit(0)
cmd = argv[0]
scenario = os.environ.get("FLOW_TEST_SCENARIO", "clean")
with open(os.environ["FLOW_TEST_LOG"], "a") as fh:
    fh.write(cmd + "\n")
report = json.loads(json.dumps(__REPORTS__[cmd]))
if cmd == "place-and-route":
    report["engine_logs"] = [{"invocation_id": uuid.uuid4().hex}]
    if scenario == "par_fails":
        sys.stderr.write(json.dumps({"schema_version": 1, "error": {
            "command": cmd, "message": "openroad 'route' stage failed"}}))
        sys.exit(1)
if cmd == "drc" and scenario == "drc_violations":
    report.update({"status": "violations", "violation_count": 2,
                   "rule_counts": {"metal2.ongrid.1": 2},
                   "violations": [{"rule": "metal2.ongrid.1"},
                                  {"rule": "metal2.ongrid.1"}]})
    emit(report, 3)
if cmd == "erc" and scenario == "erc_tie_skipped":
    report["erc_status"] = "clean_partial"
    report["erc_coverage"] = {
        "skipped": [{"id": "erc.missing_tie:[\"nwell_tie\"]",
                     "reason": "degenerate_tap_declaration"}],
        "missing_tie_checked": False}
if cmd == "lvs" and scenario in __LVS_CASES__:
    report["status"], report["power_connectivity"] = __LVS_CASES__[scenario]
emit(report)
'''.replace("__REPORTS__", repr(REPORTS)).replace(
    "__LVS_CASES__", repr(LVS_CASES))


class FlowExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="flow-exits-"))
        for d in TREE_DIRS:
            shutil.copytree(REPO / d, self.tmp / d,
                            ignore=shutil.ignore_patterns("build", ".klt"))
        shutil.rmtree(self.tmp / "flow" / "evidence", ignore_errors=True)
        venv = self.tmp / "venv"
        (venv / "bin").mkdir(parents=True)
        klt = venv / "bin" / "klt"
        klt.write_text(FAKE_KLT.replace(
            "#!/usr/bin/env python3", f"#!{sys.executable}"), encoding="utf-8")
        klt.chmod(0o755)
        self.simbin = self.tmp / "simbin"
        self.simbin.mkdir()
        for b in ("yosys", "openroad"):
            stub = self.simbin / b
            stub.write_text("#!/bin/sh\necho fake-${0##*/} 1.0\n", encoding="utf-8")
            stub.chmod(0o755)
        self.log = self.tmp / "calls.log"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_flow(self, scenario="clean", *flags, engines=True):
        """Run flow_smoke.py in the tree copy against the fake klt;
        -> the CompletedProcess."""
        env = dict(os.environ)
        empty = self.tmp / "emptybin"
        empty.mkdir(exist_ok=True)
        env["PATH"] = str(self.simbin if engines else empty)
        env["FLOW_TEST_SCENARIO"] = scenario
        env["FLOW_TEST_LOG"] = str(self.log)
        return subprocess.run(
            [sys.executable, str(self.tmp / "flow" / "flow_smoke.py"),
             "--venv", str(self.tmp / "venv"), *flags],
            cwd=str(self.tmp), capture_output=True, text=True, env=env)

    def evidence(self, step):
        return json.loads((self.tmp / "flow" / "evidence" / f"{step}.json")
                          .read_text(encoding="utf-8"))

    def calls(self):
        return self.log.read_text(encoding="utf-8").split() \
            if self.log.exists() else []

    def test_all_steps_pass_then_reproduce(self):
        p = self.run_flow("clean", "--write")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.log.unlink()
        p = self.run_flow()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.calls(),
                         ["synthesize", "place-and-route", "drc", "lvs", "erc"])
        self.assertIn("flow-smoke: PASS", p.stdout)
        for step in ("synth", "par", "drc", "lvs", "erc"):
            rec = self.evidence(step)
            self.assertEqual(rec["flow"]["verdict"], "PASS", step)
            self.assertNotIn("/" + str(self.tmp), json.dumps(rec),
                             "evidence leaks the host path")
        self.assertEqual(self.evidence("par")["flow"]["gates"]["gate1_pdn"], True)
        self.assertEqual(self.evidence("lvs")["flow"]["gates"]["gate2_lvs"], True)
        self.assertEqual(self.evidence("erc")["flow"]["gates"]["gate3_erc"], True)

    def test_drc_violations_are_fail(self):
        p = self.run_flow("drc_violations", "--write")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        rec = self.evidence("drc")
        self.assertEqual(rec["flow"]["verdict"], "FAIL")
        self.assertEqual(rec["flow"]["klt_exit"], 3)
        self.assertEqual(rec["violation_count"], 2)
        p = self.run_flow("drc_violations")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("drc: FAIL", p.stdout)

    def test_tool_failure_is_blocked_and_downstream_not_reached(self):
        p = self.run_flow("par_fails", "--write")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        par = self.evidence("par")
        self.assertEqual(par["flow"]["verdict"], "BLOCKED")
        self.assertIn("openroad 'route' stage failed", par["flow"]["reasons"][0])
        self.assertNotIn("status", par, "a blocked step records no klt report")
        for step in ("drc", "lvs", "erc"):
            rec = self.evidence(step)
            self.assertEqual(rec["flow"]["verdict"], "BLOCKED", step)
            self.assertIn("not reached: step par is BLOCKED",
                          rec["flow"]["reasons"][0])
        self.assertEqual(self.evidence("synth")["flow"]["verdict"], "PASS")
        p = self.run_flow("par_fails")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)

    def test_skipped_tie_check_is_blocked_never_pass(self):
        p = self.run_flow("erc_tie_skipped", "--write")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        rec = self.evidence("erc")
        self.assertEqual(rec["flow"]["verdict"], "BLOCKED")
        self.assertEqual(rec["flow"]["gates"]["gate3_erc"], False)
        self.assertIn("tie check skipped", rec["flow"]["reasons"][0])

    def test_unchecked_power_verdict_is_blocked_never_fail(self):
        p = self.run_flow("lvs_power_unchecked", "--write")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        rec = self.evidence("lvs")
        self.assertEqual(rec["flow"]["verdict"], "BLOCKED")
        self.assertEqual(rec["flow"]["gates"]["gate2_lvs"], False)
        self.assertIn(POWER_UNCHECKED_REASON, rec["flow"]["reasons"])
        self.assertIn("lvs: BLOCKED", p.stdout)
        for step in ("synth", "par", "drc", "erc"):
            self.assertEqual(self.evidence(step)["flow"]["verdict"], "PASS",
                             step)

    def test_unchecked_power_verdict_without_reason_is_still_blocked(self):
        p = self.run_flow("lvs_power_unchecked_no_reason", "--write")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        rec = self.evidence("lvs")
        self.assertEqual(rec["flow"]["verdict"], "BLOCKED")
        self.assertNotIn(None, rec["flow"]["reasons"])

    def test_mismatch_with_unchecked_power_is_fail(self):
        p = self.run_flow("lvs_mismatch_power_unchecked", "--write")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        rec = self.evidence("lvs")
        self.assertEqual(rec["flow"]["verdict"], "FAIL")
        self.assertIn("lvs: FAIL", p.stdout)

    def test_altered_evidence_fails_check(self):
        self.assertEqual(self.run_flow("clean", "--write").returncode, 0)
        path = self.tmp / "flow" / "evidence" / "par.json"
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["power"]["placed"]["tapcells"] = 13
        path.write_text(json.dumps(rec, indent=1, sort_keys=True),
                        encoding="utf-8")
        p = self.run_flow()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("FAILS to reproduce", p.stdout)
        self.assertIn("/power/placed/tapcells", p.stdout)

    def test_blocked_record_that_now_passes_is_fail(self):
        self.assertEqual(self.run_flow("par_fails", "--write").returncode, 2)
        p = self.run_flow()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("committed evidence is BLOCKED", p.stdout)
        self.assertIn("regenerate it", p.stdout)

    def test_pin_naming_missing_command_blocks_before_any_step(self):
        pin_path = self.tmp / "layout" / "toolchain.json"
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        pin["klt_required_commands"] = ["drc", "nosuchcommand"]
        pin_path.write_text(json.dumps(pin, indent=2), encoding="utf-8")
        p = self.run_flow("clean", "--write")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("BLOCKED: toolchain pin", p.stdout)
        self.assertIn("`klt nosuchcommand` is missing", p.stdout)
        self.assertEqual(self.calls(), [], "a step ran despite the pin failure")

    def test_missing_host_engine_is_blocked(self):
        p = self.run_flow("clean", "--write", engines=False)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("host engine(s) not on PATH: openroad, yosys", p.stdout)
        self.assertEqual(self.calls(), [])

    def test_override_is_recorded_and_rebased(self):
        p = self.run_flow("clean", "--write", "--corner", "ff_125C_1v98")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.evidence("synth")["flow"]["request_overrides"],
                         {"corner": "ff_125C_1v98"})
        eff = self.tmp / "flow" / "build" / "effective" \
            / "request-synth-smoke.json"
        doc = json.loads(eff.read_text(encoding="utf-8"))
        self.assertEqual(doc["pdk"]["corner"], "ff_125C_1v98")
        self.assertEqual(doc["sources"], ["../../../rtl/smoke_reg.v"])
        committed = json.loads((self.tmp / "flow" / "request-synth-smoke.json")
                               .read_text(encoding="utf-8"))
        self.assertEqual(committed["pdk"]["corner"], "tt_025C_1v80",
                         "the committed request was edited")
        p = self.run_flow()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("/flow/request_overrides", p.stdout)

    def test_override_keeps_every_path_field_a_resolving_string(self):
        """The fake klt never reads its request, so assert on the effective
        requests directly: each path field keeps its committed JSON type and
        resolves (from flow/build/effective/) to the committed target."""
        p = self.run_flow("clean", "--write", "--corner", "ff_125C_1v98",
                          "--site", "gf180mcu_fd_sc_mcu9t5v0__site",
                          "--cell-library", "gf180mcu_fd_sc_mcu9t5v0")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        flow = self.tmp / "flow"
        eff_dir = flow / "build" / "effective"
        paths = {"synth": [("outputs", "dir")], "par": [("netlist",),
                 ("outputs", "dir")], "drc": [("file",)],
                 "lvs": [("layout", "file"), ("layout", "def_pins"),
                         ("reference", "netlist")]}

        def dig(doc, keys):
            for k in keys:
                doc = doc[k]
            return doc

        for step, fields in paths.items():
            name = f"request-{step}-smoke.json"
            committed = json.loads((flow / name).read_text(encoding="utf-8"))
            eff = json.loads((eff_dir / name).read_text(encoding="utf-8"))
            for keys in fields:
                want, got = dig(committed, keys), dig(eff, keys)
                self.assertIsInstance(got, str, f"{step} {keys}: {got!r}")
                self.assertEqual(
                    os.path.normpath(eff_dir / got),
                    os.path.normpath(flow / want), f"{step} {keys}")

    def test_missing_pin_module_is_blocked_not_fail(self):
        (self.tmp / "layout" / "toolchain_pin.py").unlink()
        p = self.run_flow()
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("BLOCKED: toolchain pin", p.stdout)
        self.assertNotIn("Traceback", p.stderr)


if __name__ == "__main__":
    unittest.main()
