"""Regression test for the --control --write guard (issue #11).

Recorded results are append-only evidence: tools/smoke.py --control
--write must replace the committed negative-control record
(verification/evidence/smoke-control.json) only when the control verdict
is OK -- every smoke test failed under the mutant, and at least one ran.
A run that executed no tests (CONTROL_BLOCKED) or whose mutant did not
fail (CONTROL_DEFECT) is not a control record, so the committed file must
be left byte-identical.

Runs tools/smoke.py in a throwaway copy of the tree against a fake venv
whose bin/klt emits a canned JSON report, so no simulator, cocotb or
network is needed.

Run: python3 verification/test_smoke_control.py
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
SCRIPT = REPO / "tools" / "smoke.py"
CONTROL_REL = Path("verification") / "evidence" / "smoke-control.json"
TREE_DIRS = ("rtl", "tools", "verification")

# Canned klt reports: name -> (expected exit, verdict prefix)
NO_TESTS = {"status": "pass", "tests": []}
ALL_PASSED = {"status": "pass",
              "tests": [{"name": "smoke_reg_follows_d",
                         "status": "passed"}]}
ALL_FAILED = {"status": "fail",
              "tests": [{"name": "smoke_reg_follows_d",
                         "status": "failed"}]}


def fake_venv(root: Path, report: dict) -> Path:
    """A venv-shaped dir whose bin/klt prints `report` and whose bin/python
    imports cocotb "successfully"; PATH shims for iverilog/vvp too."""
    venv = root / "fv"
    (venv / "bin").mkdir(parents=True)
    (root / "fakebin").mkdir()
    klt = venv / "bin" / "klt"
    klt.write_text("#!/bin/sh\n"
                   f"cat <<'KLT_REPORT'\n{json.dumps(report)}\nKLT_REPORT\n",
                   encoding="utf-8")
    py = venv / "bin" / "python"
    py.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for b in ("iverilog", "vvp"):
        shim = root / "fakebin" / b
        shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for p in (klt, py, *(root / "fakebin").glob("*")):
        p.chmod(0o755)
    return venv


def run_control_write(report: dict) -> tuple:
    """Copy the tree, seed the committed control record, run
    `smoke.py --control --write` against the fake venv; -> (rc, stdout,
    bytes-before, bytes-after)."""
    root = Path(tempfile.mkdtemp(prefix="smoke-control-test-"))
    try:
        for d in TREE_DIRS:
            shutil.copytree(REPO / d, root / d)
        before = (root / CONTROL_REL).read_bytes()
        venv = fake_venv(root, report)
        env = dict(os.environ)
        env["PATH"] = f"{root / 'fakebin'}{os.pathsep}{env.get('PATH', '')}"
        proc = subprocess.run(
            [sys.executable, "tools/smoke.py", "--venv", str(venv),
             "--control", "--write"],
            cwd=str(root), env=env, capture_output=True, text=True)
        after = (root / CONTROL_REL).read_bytes()
        return proc.returncode, proc.stdout, before, after
    finally:
        shutil.rmtree(root, ignore_errors=True)


class ControlWriteGuard(unittest.TestCase):
    def test_blocked_run_keeps_committed_record(self):
        rc, out, before, after = run_control_write(NO_TESTS)
        self.assertEqual(rc, 2, out)
        self.assertEqual(after, before,
                         "a no-tests (BLOCKED) control run overwrote the "
                         "committed control record")
        self.assertIn("CONTROL_BLOCKED", out)
        self.assertIn("not written", out)

    def test_defect_run_keeps_committed_record(self):
        rc, out, before, after = run_control_write(ALL_PASSED)
        self.assertEqual(rc, 1, out)
        self.assertEqual(after, before,
                         "a mutant-did-not-fail (DEFECT) control run "
                         "overwrote the committed control record")
        self.assertIn("CONTROL_DEFECT", out)
        self.assertIn("not written", out)

    def test_passing_control_is_rewritten(self):
        rc, out, before, after = run_control_write(ALL_FAILED)
        self.assertEqual(rc, 0, out)
        self.assertIn("CONTROL_OK", out)
        self.assertNotIn("not written", out)
        self.assertNotEqual(after, before,
                            "a passing control run did not rewrite the "
                            "committed control record")
        recorded = json.loads(after)
        self.assertEqual(recorded.get("status"), "fail")
        self.assertEqual([t["status"] for t in recorded.get("tests", [])],
                         ["failed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
