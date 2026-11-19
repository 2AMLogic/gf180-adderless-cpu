#!/usr/bin/env python3
"""Smoke-verification evidence for rtl/smoke_reg.v (issue #2).

Regenerate, check, and negative-control the committed report, so the repo
has a runnable verification harness before any RTL or spec work depends
on it.  Claim covered: the smoke design resets to 0 and follows d on each
rising edge under Icarus.  It says nothing about the CPU, the ISA, or any
spec content -- it proves the toolchain and the evidence path.

Pattern copied from 2AMLogic/gf180-dx7 @
69f0464147172f3d4a5506fc2a0c555008d3f36e
(tools/functional_verification.py), reduced to one test and no playback.

Modes
  check (default)  re-run the committed request and compare verdicts and
                   RTL hashes with verification/evidence/smoke.json.
                   Wall-clock fields and absolute paths are not compared.
  --write          re-run and (re)write the committed report.
  --control        run the same request against the SMOKE_MUTATE build
                   and require the smoke test to FAIL there (otherwise a
                   vacuous pass is indistinguishable from a working
                   harness); with --write, records verification/
                   evidence/smoke-control.json only when the control
                   verdict is OK -- a BLOCKED or FAIL control is not a
                   control record and leaves the committed one untouched.

Statuses and exit codes
  PASS 0   re-run matches the committed report, every test passed
  FAIL 1   a verdict, count, or recorded environment differs, or a test
           fails
  NOT_RUN / BLOCKED 2   klt, cocotb or iverilog is missing (never a pass)
  STALE 3  the committed report names different RTL hashes than the tree

The pinned toolchain is `klayout-tools==0.9.2` + `cocotb==2.1.0` in a venv
(`make smoke` creates .venv-fv inside the checkout); no host tool is
installed or changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EVID = REPO / "verification" / "evidence"
REQUEST = EVID / "smoke-request.json"
REPORT = EVID / "smoke.json"
CONTROL = EVID / "smoke-control.json"

RTL_ALL = ["rtl/smoke_reg.v"]

# The negative control: this define compiles the mutant (inverted
# capture) into the smoke design; the same smoke test must fail under it.
# Matched against smoke-request.json's sources by path suffix.
MUTANT_SOURCE_SUFFIX = "rtl/smoke_reg.v"
MUTANT_DEFINE = {"SMOKE_MUTATE": None}

COPIED_FROM = ("2AMLogic/gf180-dx7 @ "
               "69f0464147172f3d4a5506fc2a0c555008d3f36e")

# compared on both sides; everything else in the klt envelope is
# wall-clock or machine-local
ENV_KEYS = ("engine", "engine_version", "cocotb_version", "random_seed")

EXIT = {"PASS": 0, "FAIL": 1, "NOT_RUN": 2, "BLOCKED": 2, "STALE": 3}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rtl_hashes() -> dict:
    return {rel: sha256_file(REPO / rel) for rel in RTL_ALL}


def normalize(report: dict) -> dict:
    """The comparable core of a report: verdicts, counts, recorded
    environment, provenance.  No timing, no paths."""
    env = report.get("environment", {})
    return {
        "status": report.get("status"),
        "counts": [report.get(k) for k in
                   ("test_count", "passed_count", "failed_count",
                    "skipped_count")],
        "tests": sorted((t["name"], t["status"])
                        for t in report.get("tests", [])),
        "environment": {k: env.get(k) for k in ENV_KEYS},
        "provenance": report.get("provenance", {}),
    }


def compare(committed: dict, fresh: dict, current_hashes: dict) -> tuple:
    """-> (status, [reasons]).  STALE wins over a re-run: a report naming
    other RTL than the tree is not evidence for the tree, whatever a
    re-run says."""
    named = committed.get("provenance", {}).get("rtl_sha256")
    if named != current_hashes:
        diff = sorted(k for k in set(named or {}) | set(current_hashes)
                      if (named or {}).get(k) != current_hashes.get(k))
        return "STALE", [f"committed report names different RTL: {diff}"]
    if fresh.get("status") != "pass":
        bad = [t["name"] for t in fresh.get("tests", [])
               if t["status"] != "passed"]
        return "FAIL", [f"re-run status {fresh.get('status')}: {bad}"]
    a, b = normalize(committed), normalize(fresh)
    if a == b:
        return "PASS", []
    reasons = [f"{k}: committed={a[k]!r} rerun={b[k]!r}"
               for k in a if a[k] != b[k] and k != "tests"
               and k != "provenance"]
    if a["provenance"] != b["provenance"]:
        reasons.append(f"provenance: committed={a['provenance']!r} "
                       f"rerun={b['provenance']!r}")
    ta, tb = dict(a["tests"]), dict(b["tests"])
    for name in sorted(set(ta) | set(tb)):
        if ta.get(name) != tb.get(name):
            reasons.append(f"test {name}: committed={ta.get(name)} "
                           f"rerun={tb.get(name)}")
    return "FAIL", reasons


def control_verdict(report: dict) -> tuple:
    """A negative control passes only if the mutant makes every smoke
    test fail (and at least one ran).  -> (status, message) with status
    in {"PASS", "FAIL", "BLOCKED"}: a run that executed no tests is a
    harness breakage (BLOCKED), not a FAIL verdict."""
    tests = {t["name"]: t["status"] for t in report.get("tests", [])}
    if not tests:
        return "BLOCKED", (f"no tests ran; report status "
                           f"{report.get('status')}")
    ok = all(s == "failed" for s in tests.values())
    if ok:
        return "PASS", "mutant fails the smoke test"
    return "FAIL", f"mutant did NOT fail: {tests}"


def tooling(venv: Path) -> tuple:
    """-> (klt path | None, why-not)."""
    klt = venv / "bin" / "klt"
    if not klt.exists():
        return None, f"{klt} missing (run `make smoke`)"
    for b in ("iverilog", "vvp"):
        if shutil.which(b) is None:
            return None, f"{b} not found on PATH"
    probe = subprocess.run([str(venv / "bin" / "python"), "-c",
                            "import cocotb"], capture_output=True)
    if probe.returncode != 0:
        return None, f"cocotb not importable in {venv}"
    return klt, ""


def run_klt(klt: Path, request: Path, outdir: Path, env: dict):
    """Run klt; -> the JSON report, or None when klt produced none
    (a BLOCKED harness breakage, not a FAIL verdict)."""
    proc = subprocess.run(
        [str(klt), "functional-verification", str(request),
         "--outdir", str(outdir), "--format", "json"],
        cwd=str(REPO), env=env, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(proc.stdout[-2000:] + proc.stderr[-2000:])
        print("BLOCKED: klt produced no JSON report", file=sys.stderr)
        return None


def klt_version(klt: Path) -> str:
    return subprocess.run([str(klt), "--version"], capture_output=True,
                          text=True).stdout.strip()


def provenance(klt: Path, defines: dict, claim: str) -> dict:
    return {
        "claim": claim,
        "rtl_sha256": rtl_hashes(),
        "request_sha256": sha256_file(REQUEST),
        "klt_version": klt_version(klt),
        "copied_from": COPIED_FROM,
        "defines": defines,
    }


def scrub(report: dict) -> dict:
    """Drop machine-local noise from the committed copy: artifact path
    records, the absolute source_defines keys klt records, and absolute
    path prefixes inside test error messages (wall-clock fields stay as
    informational evidence; compare() ignores them)."""
    out = json.loads(json.dumps(report))
    env = out.get("environment", {})
    for k in ("results_xml", "test_log", "build_log"):
        env.pop(k, None)
    sd = env.get("source_defines")
    if isinstance(sd, dict):
        env["source_defines"] = {
            os.path.relpath(k, REQUEST.parent): v for k, v in sd.items()
        }
    repo_prefix = str(REPO) + "/"
    scratch_re = re.compile(r"/tmp/fv-smoke-[A-Za-z0-9_]+")
    for t in out.get("tests", []):
        msg = t.get("error_message")
        if isinstance(msg, str):
            msg = scratch_re.sub("<scratch>", msg)
            t["error_message"] = msg.replace(repo_prefix, "")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="write the committed evidence from this run")
    ap.add_argument("--control", action="store_true",
                    help="run the SMOKE_MUTATE build; the smoke test must "
                         "fail (negative control)")
    ap.add_argument("--venv", default=str(REPO / ".venv-fv"))
    args = ap.parse_args()

    klt, why = tooling(Path(args.venv))
    if klt is None:
        print(f"NOT_RUN: {why}")
        return EXIT["NOT_RUN"]

    env = dict(os.environ)
    outdir = Path(tempfile.mkdtemp(prefix="fv-smoke-"))
    try:
        if args.control:
            # The mutant request is a scratch copy, so its request-relative
            # paths must be rebased onto the scratch dir (dx7 does the same
            # for its scratch copy): sources, the matching source_defines
            # keys, and the testbench search_path.
            req = json.loads(REQUEST.read_text(encoding="utf-8"))
            base = REQUEST.parent.resolve()
            orig_sources = req.get("sources", [])
            mutant_sources = [s for s in orig_sources
                              if s.endswith(MUTANT_SOURCE_SUFFIX)]
            if not mutant_sources:
                print(f"BLOCKED: no source ending {MUTANT_SOURCE_SUFFIX} "
                      "in smoke-request.json sources")
                return EXIT["BLOCKED"]

            def rebase(rel: str) -> str:
                return os.path.relpath((base / rel).resolve(), start=outdir)

            req["sources"] = [rebase(s) for s in orig_sources]
            req.setdefault("options", {})["source_defines"] = {
                rebase(s): dict(MUTANT_DEFINE) for s in mutant_sources}
            req["testbench"]["search_path"] = rebase(
                req["testbench"]["search_path"])
            rq = outdir / "request-mutant.json"
            rq.write_text(json.dumps(req, indent=2) + "\n", encoding="utf-8")
            # recorded in the request's own (machine-independent) naming
            defines = {s: dict(MUTANT_DEFINE) for s in mutant_sources}
            claim = ("negative control: the SMOKE_MUTATE build (inverted "
                     "capture) fails the same smoke test the committed "
                     "report passes")
        else:
            rq = REQUEST
            defines = {}
            claim = ("smoke design resets to 0 and follows d on each "
                     "rising edge under Icarus; not the CPU, the ISA, or "
                     "any spec content")

        fresh = run_klt(klt, rq, outdir / "run", env)
        if fresh is None:
            return EXIT["BLOCKED"]
        fresh["provenance"] = provenance(klt, defines, claim)

        if args.control:
            status, msg = control_verdict(fresh)
            prefix = {"PASS": "CONTROL_OK", "FAIL": "CONTROL_DEFECT",
                      "BLOCKED": "CONTROL_BLOCKED"}[status]
            if args.write:
                # Only a passing control is a control record: a run that
                # executed no tests (BLOCKED) or whose mutant did not
                # fail (FAIL) must not replace the committed evidence.
                if status == "PASS":
                    CONTROL.write_text(json.dumps(scrub(fresh), indent=1,
                                                  sort_keys=True) + "\n",
                                       encoding="utf-8")
                else:
                    print(f"{prefix} evidence not written: {CONTROL} kept "
                          f"(a {status} control is not a control record)")
            print(prefix + " " + msg)
            return EXIT[status]

        if args.write:
            REPORT.write_text(json.dumps(scrub(fresh), indent=1,
                                         sort_keys=True) + "\n",
                              encoding="utf-8")
            print(f"WROTE {REPORT} status={fresh.get('status')}")
            return 0 if fresh.get("status") == "pass" else 1

        if not REPORT.exists():
            print(f"NOT_RUN: no committed report at {REPORT}")
            return EXIT["NOT_RUN"]
        committed = json.loads(REPORT.read_text(encoding="utf-8"))
        status, reasons = compare(committed, fresh, rtl_hashes())
        print(status + ("" if not reasons else ": " + "; ".join(reasons)))
        return EXIT[status]
    finally:
        if not os.environ.get("FV_KEEP"):
            shutil.rmtree(outdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
