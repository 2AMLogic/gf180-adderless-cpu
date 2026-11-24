#!/usr/bin/env python3
"""Exit-code contract and write-guard tests for tools/smoke.py
(issues #7 and #11).

Subprocess-driven and hermetic: each case points --venv at a scratch
fake venv whose bin/klt prints a canned stdout, so no real klt,
cocotb or iverilog run is involved (simulator binaries are stubbed
on PATH, so no host toolchain is needed either).  Covers the tiers
the live smoke lane cannot hit on a healthy toolchain: klt emitting no JSON
(BLOCKED, exit 2, in check and --control mode), and a --control run
whose report carries no tests (BLOCKED, 2) versus a mutant that
passes (FAIL, 1) or fails everything (PASS, 0).

The write-guard cases (issue #11) run `--control --write` in a
throwaway copy of rtl/tools/verification: recorded results are
append-only evidence, so the committed negative-control record
(verification/evidence/smoke-control.json) may be replaced only when
the control verdict is OK -- every smoke test failed under the
mutant, and at least one ran.  A run that executed no tests
(CONTROL_BLOCKED) or whose mutant did not fail (CONTROL_DEFECT) is
not a control record, so the committed file must be left
byte-identical.

Run: python3 tools/test_smoke_exits.py
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SMOKE = Path(__file__).resolve().parent / "smoke.py"
TREE_DIRS = ("rtl", "tools", "verification")
CONTROL_REL = Path("verification") / "evidence" / "smoke-control.json"


def fake_venv(root: Path) -> Path:
    """A venv-shaped dir under root whose bin/python imports cocotb
    "successfully" (exit 0); -> the bin/klt path (its payload is
    written by write_klt)."""
    venv = root / "venv"
    (venv / "bin").mkdir(parents=True)
    py = venv / "bin" / "python"
    py.write_text("#!/bin/sh\nexit 0\n")
    py.chmod(0o755)
    return venv / "bin" / "klt"


def write_klt(klt: Path, payload) -> None:
    """Fake klt printing the canned JSON report (payload None ->
    prints nothing).  printf is a shell builtin: no PATH lookup, so the
    fake klt stays hermetic even with an empty ambient PATH."""
    if payload is None:
        body = "exit 0"
    else:
        body = f"printf '%s\\n' {shlex.quote(payload)}"
    klt.write_text(f"#!/bin/sh\n{body}\n")
    klt.chmod(0o755)


def sim_stubs(root: Path) -> Path:
    """Stub iverilog/vvp in a scratch dir (never run, but tooling()
    requires them on PATH -- CI's fast lane has no toolchain);
    -> that dir, to prepend to PATH."""
    simbin = root / "simbin"
    simbin.mkdir()
    for b in ("iverilog", "vvp"):
        stub = simbin / b
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    return simbin


def stub_env(simbin: Path) -> dict:
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(
        (str(simbin), env.get("PATH", "")))
    return env


class SmokeExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="smoke-exits-"))
        self.klt = fake_venv(self.tmp)
        self.simbin = sim_stubs(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_smoke(self, payload, *flags):
        """Write the fake klt (payload None -> prints nothing), then run
        smoke.py against it; -> the CompletedProcess."""
        write_klt(self.klt, payload)
        return subprocess.run(
            [sys.executable, str(SMOKE), "--venv", str(self.tmp / "venv"),
             *flags], capture_output=True, text=True,
            env=stub_env(self.simbin))

    def test_no_json_check_mode_is_blocked(self):
        p = self.run_smoke(None)
        self.assertEqual(p.returncode, 2)
        self.assertIn("BLOCKED", p.stderr)

    def test_no_json_control_mode_is_blocked(self):
        p = self.run_smoke(None, "--control")
        self.assertEqual(p.returncode, 2)
        self.assertIn("BLOCKED", p.stderr)

    def test_control_no_tests_is_blocked(self):
        report = json.dumps({"status": "pass", "tests": []})
        p = self.run_smoke(report, "--control")
        self.assertEqual(p.returncode, 2)
        self.assertIn("CONTROL_BLOCKED", p.stdout)

    def test_control_mutant_passes_is_fail(self):
        report = json.dumps({"status": "pass",
                             "tests": [{"name": "smoke", "status":
                                        "passed"}]})
        p = self.run_smoke(report, "--control")
        self.assertEqual(p.returncode, 1)
        self.assertIn("CONTROL_DEFECT", p.stdout)

    def test_control_mutant_fails_all_is_pass(self):
        report = json.dumps({"status": "fail",
                             "tests": [{"name": "smoke", "status":
                                        "failed"}]})
        p = self.run_smoke(report, "--control")
        self.assertEqual(p.returncode, 0)
        self.assertIn("CONTROL_OK", p.stdout)


class ControlWriteGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="smoke-control-"))
        for d in TREE_DIRS:
            shutil.copytree(REPO / d, self.tmp / d,
                            ignore=shutil.ignore_patterns("build", ".klt"))
        self.record = self.tmp / CONTROL_REL
        self.klt = fake_venv(self.tmp)
        self.simbin = sim_stubs(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_control_write(self, report):
        """Run smoke.py --control --write in the tree copy against the
        fake klt; -> (CompletedProcess, bytes-before, bytes-after)."""
        write_klt(self.klt, json.dumps(report))
        before = self.record.read_bytes()
        proc = subprocess.run(
            [sys.executable, "tools/smoke.py", "--venv",
             str(self.tmp / "venv"), "--control", "--write"],
            cwd=str(self.tmp), capture_output=True, text=True,
            env=stub_env(self.simbin))
        return proc, before, self.record.read_bytes()

    def test_blocked_run_keeps_committed_record(self):
        p, before, after = self.run_control_write(
            {"status": "pass", "tests": []})
        self.assertEqual(p.returncode, 2, p.stdout)
        self.assertEqual(after, before,
                         "a no-tests (BLOCKED) control run overwrote the "
                         "committed control record")
        self.assertIn("CONTROL_BLOCKED", p.stdout)
        self.assertIn("not written", p.stdout)

    def test_defect_run_keeps_committed_record(self):
        p, before, after = self.run_control_write(
            {"status": "pass",
             "tests": [{"name": "smoke_reg_follows_d",
                        "status": "passed"}]})
        self.assertEqual(p.returncode, 1, p.stdout)
        self.assertEqual(after, before,
                         "a mutant-did-not-fail (DEFECT) control run "
                         "overwrote the committed control record")
        self.assertIn("CONTROL_DEFECT", p.stdout)
        self.assertIn("not written", p.stdout)

    def test_passing_control_is_rewritten(self):
        p, before, after = self.run_control_write(
            {"status": "fail",
             "tests": [{"name": "smoke_reg_follows_d",
                        "status": "failed"}]})
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("CONTROL_OK", p.stdout)
        self.assertNotIn("not written", p.stdout)
        self.assertNotEqual(after, before,
                            "a passing control run did not rewrite the "
                            "committed control record")
        recorded = json.loads(after)
        self.assertEqual(recorded.get("status"), "fail")
        self.assertEqual([t["status"] for t in recorded.get("tests", [])],
                         ["failed"])


if __name__ == "__main__":
    unittest.main()
