#!/usr/bin/env python3
"""Shared toolchain pin check for this repo's layout/ and flow/ runners.

layout/toolchain.json is the toolchain pin: the klayout-tools install the
committed evidence was produced against (klt_install,
klt_last_verified_commit) and the klt subcommands the runners invoke
(klt_required_commands).  Its header asks for ONE shared check that every
runner imports rather than re-deriving, so the runners cannot drift apart
on what they check.  This module is that check; flow/flow_smoke.py calls
check_pin() before it runs anything.

What is checked, in order:
  1. layout/toolchain.json is readable JSON whose klt_install,
     klt_last_verified_commit and klayout_package_min carry no FILL marker,
     and whose klt_required_commands is a non-empty list of strings.
  2. `klt --version` names the version klt_install pins.
  3. every klt_required_commands entry is a subcommand of `klt --help`.
A failed check names the missing piece and the install command that fixes
it.  It is never a silently-skipped check.

klt_install is a PyPI `klayout-tools==<version>` pin, the same pin the
Makefile's FV_PINS line installs into the throwaway venv.

Exit codes (standalone): 0 pass, 1 check failure, 2 could-not-run.
Stdlib only.

Run: python3 layout/toolchain_pin.py [--klt PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIN_FILE = os.path.join("layout", "toolchain.json")
DEFAULT_KLT = os.path.join(".venv-fv", "bin", "klt")

SCALAR_FIELDS = ("klt_install", "klt_last_verified_commit",
                 "klayout_package_min")
COMMANDS_FIELD = "klt_required_commands"

INSTALL_RE = re.compile(r"klayout-tools==([0-9][A-Za-z0-9._+-]*)")
VERSION_RE = re.compile(r"klt\s+(\S+)")
HELP_COMMAND_RE = re.compile(r"^ {4}([a-z0-9][a-z0-9-]*)(?:\s{2,}.*)?$")


class PinError(Exception):
    """The check itself could not run (unreadable pin, unusable klt)."""


def load_pin(repo_root: str) -> dict:
    """-> the parsed layout/toolchain.json, with its shape validated."""
    path = os.path.join(repo_root, PIN_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            pin = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise PinError(f"cannot read {PIN_FILE}: {exc}") from exc
    if not isinstance(pin, dict):
        raise PinError(f"{PIN_FILE} is not a JSON object")
    problems = []
    for field in SCALAR_FIELDS:
        value = pin.get(field)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{field} is missing or not a string")
        elif "FILL" in value:
            problems.append(f"{field} still carries a FILL marker")
    commands = pin.get(COMMANDS_FIELD)
    if (not isinstance(commands, list) or not commands
            or not all(isinstance(c, str) and c for c in commands)):
        problems.append(f"{COMMANDS_FIELD} must be a non-empty list of "
                        "command names")
    if problems:
        raise PinError(f"{PIN_FILE} is not a usable pin: " + "; ".join(problems))
    return pin


def pinned_version(pin: dict) -> str:
    """The klayout-tools version klt_install pins."""
    m = INSTALL_RE.fullmatch(pin["klt_install"].strip())
    if not m:
        raise PinError(
            f"{PIN_FILE}: klt_install {pin['klt_install']!r} is not a "
            '"klayout-tools==<version>" pin; this check compares `klt '
            "--version` against that version")
    return m.group(1)


def klt_version(klt: str) -> str:
    """The version token of `klt --version` (e.g. "0.9.2")."""
    try:
        proc = subprocess.run([klt, "--version"], capture_output=True,
                              text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PinError(f"cannot run `{klt} --version`: {exc}") from exc
    m = VERSION_RE.fullmatch(proc.stdout.strip())
    if proc.returncode != 0 or not m:
        raise PinError(f"`{klt} --version` did not print \"klt <version>\": "
                       f"{proc.stdout.strip()[:200]} {proc.stderr.strip()[:200]}")
    return m.group(1)


def klt_commands(klt: str) -> set:
    """The subcommand names `klt --help` lists: each sits at a four-space
    indent, followed by two or more spaces and its description, or by
    nothing when a long name's description wraps onto the next line."""
    try:
        proc = subprocess.run([klt, "--help"], capture_output=True,
                              text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PinError(f"cannot run `{klt} --help`: {exc}") from exc
    commands = set()
    in_commands = False
    for line in proc.stdout.splitlines():
        if "positional arguments:" in line:
            in_commands = True
            continue
        if "options:" in line:
            in_commands = False
        if in_commands:
            m = HELP_COMMAND_RE.match(line)
            if m:
                commands.add(m.group(1))
    if not commands:
        raise PinError(f"could not read a subcommand list from "
                       f"`{klt} --help`")
    return commands


def check_pin(klt: str, pin: dict, needed=()) -> list:
    """-> [problems]; empty means the installed klt is the pinned one and
    has every required command.  `needed` names commands the calling
    runner invokes; each must also be listed in the pin."""
    if not os.path.isfile(klt):
        return [f"{klt} is missing (run `make flow-smoke` to build the "
                "throwaway venv)"]
    problems = []
    wanted = pin[COMMANDS_FIELD]
    for command in needed:
        if command not in wanted:
            problems.append(
                f"the runner invokes `klt {command}` but {PIN_FILE} does "
                f"not list it in {COMMANDS_FIELD}; add it there")
    try:
        version = klt_version(klt)
        commands = klt_commands(klt)
    except PinError as exc:
        problems.append(str(exc))
        return problems
    expected = pinned_version(pin)
    if version != expected:
        problems.append(
            f"installed klt is {version}, but {PIN_FILE} pins "
            f"klayout-tools=={expected}")
    for command in wanted:
        if command not in commands:
            problems.append(
                f"`klt {command}` is missing from this install "
                f"(klt {version}); {PIN_FILE} requires it -- reinstall with: "
                "uv venv .venv-fv && uv pip install --python "
                f".venv-fv/bin/python \"klayout-tools=={expected}\"")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--klt", default=os.path.join(REPO_ROOT, DEFAULT_KLT))
    ap.add_argument("--repo-root", default=REPO_ROOT)
    args = ap.parse_args(argv)
    try:
        pin = load_pin(args.repo_root)
        problems = check_pin(args.klt, pin)
    except PinError as exc:
        print(f"COULD_NOT_RUN: {exc}")
        return 2
    if problems:
        for p in problems:
            print(f"PIN_MISMATCH: {p}")
        return 1
    print(f"PIN_OK: klt {pinned_version(pin)} has every command in "
          f"{COMMANDS_FIELD} ({', '.join(pin[COMMANDS_FIELD])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
