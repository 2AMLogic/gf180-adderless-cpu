#!/usr/bin/env python3
"""Exit-code contract tests for tools/smoke.py (issue #7).

Subprocess-driven and hermetic: each case points --venv at a scratch
fake venv whose bin/klt prints a canned stdout, so no real klt,
cocotb or iverilog run is involved.  Covers the tiers the live smoke
lane cannot hit on a healthy toolchain: klt emitting no JSON
(BLOCKED, exit 2, in check and --control mode), and a --control run
whose report carries no tests (BLOCKED, 2) versus a mutant that
passes (FAIL, 1) or fails everything (PASS, 0).

Run: python3 tools/test_smoke_exits.py
"""

import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SMOKE = Path(__file__).resolve().parent / "smoke.py"


class SmokeExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="smoke-exits-"))
        venv = self.tmp / "venv"
        (venv / "bin").mkdir(parents=True)
        # tooling() probes: bin/klt exists, bin/python imports cocotb
        # "successfully" (exit 0), iverilog/vvp come from PATH.
        py = venv / "bin" / "python"
        py.write_text("#!/bin/sh\nexit 0\n")
        py.chmod(0o755)
        self.klt = venv / "bin" / "klt"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_smoke(self, payload, *flags):
        """Write the fake klt (payload None -> prints nothing), then run
        smoke.py against it; -> the CompletedProcess."""
        if payload is None:
            body = "exit 0"
        else:
            f = self.tmp / "stdout.json"
            f.write_text(payload)
            body = f"cat {shlex.quote(str(f))}"
        self.klt.write_text(f"#!/bin/sh\n{body}\n")
        self.klt.chmod(0o755)
        return subprocess.run(
            [sys.executable, str(SMOKE), "--venv", str(self.tmp / "venv"),
             *flags], capture_output=True, text=True)

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


if __name__ == "__main__":
    unittest.main()
