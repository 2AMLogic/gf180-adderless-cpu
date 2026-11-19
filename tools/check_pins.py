#!/usr/bin/env python3
"""Smoke-evidence pin/provenance gate.

Makefile's FV_PINS pins the toolchain that produced the committed smoke
evidence, and tools/smoke.py compares `provenance` (and the recorded
environment) verbatim on a re-run.  So a pin bump that does not
regenerate the evidence would turn the smoke lane FAIL-on-provenance at
the next re-run.  This check makes that debt visible at bump time, by
asserting that every version FV_PINS pins is the version the committed
evidence actually records:

  klayout-tools  <->  provenance.klt_version   (the stripped stdout of
                       `klt --version`, e.g. "klt 0.9.2" -- the version
                       token is compared, not the whole string)
  cocotb         <->  environment.cocotb_version

Files under verification/evidence/ without a `provenance` block (the klt
request) carry no recorded toolchain and are skipped without a verdict.

Adapted from 2AMLogic/gf180-dx7 @
69f0464147172f3d4a5506fc2a0c555008d3f36e (tools/check_fv_pins.py).

Exit codes: 0 pass, 1 check failure, 2 could-not-run.  Stdlib only.
"""

import argparse
import json
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
MAKEFILE = "Makefile"
EVIDENCE_DIR = os.path.join("verification", "evidence")

# FV_PINS pin -> the report field that must name the same version. A pin
# outside this table is a checker gap (could-not-run, never a silent
# pass): extend this module when FV_PINS grows a new distribution.
PIN_RULES = {
    "klayout-tools": "klt_version",
    "cocotb": "cocotb_version",
}

KLT_VERSION_RE = re.compile(r"klt\s+(\S+)")
PIN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9._+-]*)")

REMEDY = (
    "rm -rf .venv-fv && make smoke && "
    "python3 tools/smoke.py --venv .venv-fv --write && "
    "python3 tools/smoke.py --venv .venv-fv --control --write"
)


class CouldNotRun(Exception):
    """The check itself could not run (bad Makefile, unreadable file)."""


def parse_fv_pins(repo_root):
    """-> {distribution: version} from Makefile's FV_PINS assignment.

    Only quoted `distribution==version` pins are pins; any other
    non-comment text on the assignment (a dropped quote, a mangled pin)
    is unparseable -> CouldNotRun, never a partial or silent parse.
    Backslash continuations are joined; pin order and spacing are free.
    """
    path = os.path.join(repo_root, MAKEFILE)
    if not os.path.isfile(path):
        raise CouldNotRun(f"{MAKEFILE} not found under {repo_root}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise CouldNotRun(f"cannot read {path}: {exc}")
    assignments = []
    i = 0
    while i < len(lines):
        m = re.match(r"^\s*FV_PINS\s*[:?+]?=\s*(.*)$", lines[i])
        if m:
            body = [m.group(1)]
            while body[-1].rstrip().endswith("\\") and i + 1 < len(lines):
                body[-1] = body[-1].rstrip()[:-1]
                i += 1
                body.append(lines[i])
            assignments.append(" ".join(body))
        i += 1
    if not assignments:
        raise CouldNotRun(
            f"no FV_PINS assignment found in {MAKEFILE}; cannot check "
            "the smoke evidence pins")
    pins = {}
    for line in assignments:
        tokens = re.findall(r'"([^"]+)"', line)
        leftover = re.sub(r'"[^"]*"', "", line).split("#", 1)[0].strip()
        if leftover:
            raise CouldNotRun(
                f"FV_PINS in {MAKEFILE} is unparseable: unrecognised text "
                f"{leftover!r} outside the quoted pins")
        if not tokens:
            raise CouldNotRun(
                f"FV_PINS in {MAKEFILE} is unparseable: no quoted "
                '"distribution==version" pin found')
        for tok in tokens:
            m = PIN_RE.fullmatch(tok)
            if not m:
                raise CouldNotRun(
                    f"FV_PINS in {MAKEFILE} is unparseable: {tok!r} is not "
                    '"distribution==version"')
            dist, version = m.groups()
            if dist in pins and pins[dist] != version:
                raise CouldNotRun(
                    f"FV_PINS in {MAKEFILE} pins {dist} twice with "
                    f"different versions ({pins[dist]} vs {version})")
            pins[dist] = version
    return pins


def check_report(label, report, pins):
    """-> [reasons] for one committed report dict. Every FV_PINS pin is
    compared; a malformed or missing recorded version is a stated
    failure, never a silent pass."""
    reasons = []
    for dist, field in PIN_RULES.items():
        if dist not in pins:
            continue
        pinned = pins[dist]
        if dist == "klayout-tools":
            provenance = report.get("provenance")
            if not isinstance(provenance, dict):
                reasons.append(
                    f"{label}: no provenance block; cannot compare the "
                    f"klayout-tools pin {pinned} (regenerate: {REMEDY})")
                continue
            recorded = provenance.get("klt_version")
            if not isinstance(recorded, str) or not recorded.strip():
                reasons.append(
                    f"{label}: provenance.klt_version is missing or not a "
                    f"string; FV_PINS pins klayout-tools=={pinned} "
                    f"(regenerate: {REMEDY})")
                continue
            m = KLT_VERSION_RE.fullmatch(recorded.strip())
            if not m:
                reasons.append(
                    f"{label}: provenance.klt_version {recorded!r} is not "
                    '"klt <version>"; FV_PINS pins klayout-tools=='
                    f"{pinned} (regenerate: {REMEDY})")
                continue
            token = m.group(1)
            if token != pinned:
                reasons.append(
                    f"{label}: provenance.klt_version records klt "
                    f"{token}, but FV_PINS pins klayout-tools=={pinned}; "
                    "the committed evidence no longer names the pinned "
                    f"toolchain (regenerate: {REMEDY})")
        elif field == "cocotb_version":
            environment = report.get("environment")
            if not isinstance(environment, dict):
                reasons.append(
                    f"{label}: no environment block; cannot compare the "
                    f"cocotb pin {pinned} (regenerate: {REMEDY})")
                continue
            recorded = environment.get("cocotb_version")
            if not isinstance(recorded, str) or not recorded.strip():
                reasons.append(
                    f"{label}: environment.cocotb_version is missing or "
                    f"not a string; FV_PINS pins cocotb=={pinned} "
                    f"(regenerate: {REMEDY})")
            elif recorded.strip() != pinned:
                reasons.append(
                    f"{label}: environment.cocotb_version records "
                    f"{recorded.strip()}, but FV_PINS pins cocotb=="
                    f"{pinned}; the committed evidence no longer names "
                    f"the pinned toolchain (regenerate: {REMEDY})")
        else:
            raise CouldNotRun(
                f"no comparison rule implemented for FV_PINS pin {dist} "
                f"-> {field}; extend tools/check_pins.py")
    return reasons


def run_check(repo_root):
    pins = parse_fv_pins(repo_root)
    unknown = sorted(set(pins) - set(PIN_RULES))
    if unknown:
        raise CouldNotRun(
            f"FV_PINS pins {unknown}, for which no comparison rule is "
            "implemented; extend tools/check_pins.py")
    evid = os.path.join(repo_root, EVIDENCE_DIR)
    if not os.path.isdir(evid):
        raise CouldNotRun(f"evidence directory {evid} not found")
    checked, skipped, reasons = [], [], []
    for name in sorted(os.listdir(evid)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(evid, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            reasons.append(f"{name}: unreadable or not JSON: {exc}")
            continue
        if not isinstance(report, dict) or "provenance" not in report:
            skipped.append(name)
            continue
        checked.append(name)
        reasons.extend(check_report(name, report, pins))
    if not checked:
        raise CouldNotRun(
            f"no committed evidence report with a provenance block found "
            f"under {evid}; cannot check the FV_PINS pins")
    return checked, skipped, reasons, pins


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--repo-root", default=REPO_ROOT)
    args = ap.parse_args()
    try:
        checked, skipped, reasons, pins = run_check(args.repo_root)
    except CouldNotRun as exc:
        print(f"COULD_NOT_RUN: {exc}")
        return 2
    if skipped:
        print(f"skipped (no provenance block): {', '.join(skipped)}")
    if reasons:
        for r in reasons:
            print(f"PIN_MISMATCH: {r}")
        print(f"checked {len(checked)} evidence report(s): FAIL")
        return 1
    print(f"checked {len(checked)} evidence report(s): PASS "
          f"(FV_PINS {sorted(set(pins))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
