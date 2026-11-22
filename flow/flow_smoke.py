"""Implementation-flow smoke evidence for rtl/smoke_reg.v (issue #18).

Runs the committed klt requests under flow/ -- synthesis, place-and-route,
DRC, gate-level LVS with its power/ground half, and the supply ERC read --
on rtl/smoke_reg.v, and writes or checks one evidence record per step
under flow/evidence/.  The smoke register is a toolchain exercise only:
nothing here is a claim about the CPU, the ISA, any spec content, or the
block's target library, site or corner (those stay spec decisions).

Same write/check pattern as tools/smoke.py, whose exit convention this
follows.

Modes
  check (default)  re-run every step from its committed request and require
                    the committed evidence to reproduce.
  --write           re-run and (re)write the committed evidence.  Every
                    step's record is written, including BLOCKED and FAIL
                    ones: a result is not dropped because it is bad.

Steps, in order: synth -> par -> drc, lvs, erc.  A step whose input step
is BLOCKED is recorded BLOCKED (not reached) and the run continues.

Gates (flow/README.md, "Structural power delivery"):
  1  par: power.pdn is true and power.tapcell_master is named
  2  lvs: status is "match" and power_connectivity.status is "match"
  3  erc: one electrical island per supply net and zero missing_tie, with
        the tie check actually run (a skipped check is never a pass)
  drc: status is "clean"
synth has no gate; it passes when klt reports status "ok" with no
structural finding.

Runner arguments: --cell-library, --corner and --site override the values
of the committed requests for one run (the committed files are never
edited; an overridden copy is materialized under flow/build/effective/ and
the override is recorded in the evidence).  --pdk-variant selects the
installed PDK variant klt resolves.

Statuses and exit codes
  PASS 0      every step reached a verdict, every gate is met and, in check
              mode, the committed evidence reproduces
  FAIL 1      a gate is unmet, or the committed evidence does not reproduce
  BLOCKED 2   the pinned toolchain is not what is installed, a host engine
              (yosys, openroad) is missing, or klt could not produce a
              report for a step (error exit, no JSON, timeout).  Never a
              pass.

What is compared in check mode: the whole scrubbed klt report of each step
plus the runner's own `flow` block (input hashes, overrides, verdict,
gates).  Excluded as run-scoped or tool churn, following klt's own
`--check --rerun` contract: artifact paths, run ids, the engine build
strings and klt's tool-version provenance.  Those are still recorded in
the evidence; the klt version in it is `tools/check_pins.py`'s job.

The pinned toolchain is `klayout-tools==0.9.2` in the venv `make smoke`
builds (.venv-fv); layout/toolchain_pin.py checks it before any step runs.
yosys and openroad come from the host PATH and are recorded, not pinned.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FLOW_REL = Path("flow")
EVID = REPO / FLOW_REL / "evidence"
BUILD_REL = FLOW_REL / "build"
EFFECTIVE_REL = BUILD_REL / "effective"

RTL_ALL = ["rtl/smoke_reg.v"]
SUPPLIES = ("VDD", "VSS")
DEFAULT_PDK_VARIANT = "gf180mcuC"
ERC_DECK = "gf180mcu"
KLT_TIMEOUT_S = 3600
VIOLATIONS_KEPT = 25
DIFF_SHOWN = 12

EXIT = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}
RANK = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}

CLAIM = ("smoke register runs through synthesis, place-and-route, DRC, "
         "gate-level LVS and the supply ERC read on gf180mcu via klt; "
         "not the CPU, the ISA, any spec content, or the block's target "
         "library, site or corner")


@dataclass(frozen=True)
class Step:
    name: str
    request: str
    command: str
    needs: tuple
    engines: tuple
    gate: str


STEPS = [
    Step("synth", "flow/request-synth-smoke.json", "synthesize", (),
         ("yosys",), "none"),
    Step("par", "flow/request-par-smoke.json", "place-and-route", ("synth",),
         ("openroad",), "gate1_pdn"),
    Step("drc", "flow/request-drc-smoke.json", "drc", ("par",), (), "drc_clean"),
    Step("lvs", "flow/request-lvs-smoke.json", "lvs", ("par",), (), "gate2_lvs"),
    Step("erc", "flow/request-erc-smoke.json", "erc", ("par",), (), "gate3_erc"),
]
BY_NAME = {s.name: s for s in STEPS}

REQUEST_PATHS = {
    "synthesize": (["sources"], (["outputs", "dir"],)),
    "place-and-route": (["netlist"], (["outputs", "dir"],)),
    "drc": (["file"], ()),
    "lvs": ((), (["layout", "file"], ["layout", "def_pins"],
                 ["reference", "netlist"])),
    "erc": ((), ()),
}

VOLATILE = [
    ["flow", "generated_at"], ["flow", "elapsed_s"],
    ["provenance", "klt_version"], ["provenance", "klt_git_commit"],
    ["provenance", "klt_reinstall_spec"], ["provenance", "klayout_version"],
    ["provenance", "klayout_version_mismatch"], ["provenance", "pdk"],
    ["provenance", "deck", "path"], ["engine_version"],
    ["environment", "engine_version"],
]
SCRUB = {
    "synthesize": [["run_id"], ["netlist_path"], ["script_path"],
                   ["run_script_path"], ["memory_mapping", "script_path"]],
    "place-and-route": [["engine_logs"], ["netlist"], ["def_path"],
                        ["unrouted_def_path"], ["gds_path"], ["verilog_path"],
                        ["power", "placed", "def_path"],
                        ["layer_map", "path"]],
    "drc": [["file"]],
    "lvs": [["layout"], ["reference"], ["provenance", "pin_order_sources"],
            ["environment", "extracted_netlist"]],
    "erc": [["file"], ["spec"]],
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rtl_hashes() -> dict:
    return {rel: sha256_file(REPO / rel) for rel in RTL_ALL}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def drop(record: dict, path: list) -> None:
    """Remove record[a][b]...[z] when it exists; a missing level is fine."""
    node = record
    for key in path[:-1]:
        if not isinstance(node, dict) or key not in node:
            return
        node = node[key]
    if isinstance(node, dict):
        node.pop(path[-1], None)


def scrub(step: str, record: dict) -> dict:
    """The committable form of a record: machine-local artifact paths
    dropped and the drc violation list bounded to its head (the counts
    and per-rule tallies stay)."""
    out = copy.deepcopy(record)
    for path in SCRUB[step]:
        drop(out, path)
    if step == "drc" and isinstance(out.get("violations"), list):
        kept = out["violations"][:VIOLATIONS_KEPT]
        for v in kept:
            v.pop("polygon", None)
        out["violations_listed"] = len(kept)
        out["violations"] = kept
    return out


def comparable(step: str, record: dict) -> dict:
    out = scrub(step, record)
    for path in VOLATILE:
        drop(out, path)
    return out


def diff_paths(a, b, prefix="") -> list:
    """JSON paths at which two JSON values differ (bounded by the caller)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            path = f"{prefix}/{key}"
            if key not in a or key not in b:
                out.append(path)
            else:
                out.extend(diff_paths(a[key], b[key], path))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out.extend(diff_paths(x, y, f"{prefix}/{i}"))
        return out
    return [] if a == b else [prefix or "/"]


def load_pin_module():
    spec = importlib.util.spec_from_file_location(
        "toolchain_pin", REPO / "layout" / "toolchain_pin.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tail(text: str, limit: int = 600) -> str:
    return (text or "").strip()[-limit:]


def get(record: dict, *path):
    node = record
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def overrides_for(args) -> dict:
    """The runner's library / site / corner arguments that differ from the
    committed requests (absent means "use the committed value")."""
    return {k: v for k, v in (("cell_library", args.cell_library),
                              ("corner", args.corner), ("site", args.site))
            if v is not None}


def apply_overrides(step: Step, request: dict, over: dict) -> dict:
    out = copy.deepcopy(request)
    if step.command in ("synthesize", "place-and-route"):
        if "cell_library" in over:
            out["pdk"]["cell_library"] = over["cell_library"]
        if "corner" in over:
            out["pdk"]["corner"] = over["corner"]
    if step.command == "place-and-route" and "site" in over:
        out["floorplan"]["site"] = over["site"]
    if step.command == "lvs" and "cell_library" in over:
        out["layout"]["abstract_cells"] = [over["cell_library"] + "__*"]
        out["reference"]["library"] = over["cell_library"]
    return out


def rebase(value: str, request_dir: Path, scratch_dir: Path) -> str:
    base = Path(os.path.normpath(os.path.join(str(request_dir), value)))
    return os.path.relpath(str(base), start=str(scratch_dir))


def effective_request(step: Step, over: dict) -> str:
    """-> the request path (relative to the repo root) to hand klt.
    Without overrides this is the committed file itself; with overrides
    it is a copy under flow/build/effective/ whose relative paths are
    rebased onto that directory."""
    committed = Path(step.request)
    if not over:
        return str(committed)
    doc = apply_overrides(step, load_json(REPO / committed), over)
    lists, singles = REQUEST_PATHS[step.command]
    for key in lists:
        doc[key] = [rebase(v, REPO / committed.parent, REPO / EFFECTIVE_REL)
                    for v in doc[key]]
    for path in singles:
        node = doc
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = rebase(node[path[-1]], REPO / committed.parent,
                                REPO / EFFECTIVE_REL)
    (REPO / EFFECTIVE_REL).mkdir(parents=True, exist_ok=True)
    out = EFFECTIVE_REL / committed.name
    (REPO / out).write_text(json.dumps(doc, indent=2) + "\n",
                            encoding="utf-8")
    return str(out)


def par_request() -> dict:
    return load_json(REPO / BY_NAME["par"].request)


def engine_versions(engines) -> dict:
    out = {}
    for binary in engines:
        try:
            proc = subprocess.run([binary, "--version"], capture_output=True,
                                  text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            continue
        lines = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines()
                 if ln.strip()]
        if lines:
            out[binary] = lines[0][:160]
    return out


def klt_command(step: Step, klt: Path, request: str, variant: str) -> list:
    """The argv klt is run with, relative to the repo root (klt's cwd)."""
    cmd = [str(klt), step.command]
    if step.command == "erc":
        par = par_request()
        cmd.append(str(FLOW_REL / par["outputs"]["dir"]
                       / f"{par['hdl_toplevel']}.gds"))
    cmd.append(request)
    if step.command in ("synthesize", "place-and-route"):
        cmd += ["--pdk", variant]
    if step.command == "erc":
        cmd += ["--top", par_request()["hdl_toplevel"],
                "--pdk", ERC_DECK, "--deck", ERC_DECK]
    return cmd + ["--format", "json"]


def run_klt(cmd: list, env: dict):
    """-> (report | None, exit code | None, why-not).  None means klt
    produced no report: a harness breakage, not a verdict."""
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), env=env,
                              capture_output=True, text=True,
                              timeout=KLT_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return None, None, f"klt did not complete within {KLT_TIMEOUT_S}s"
    except OSError as exc:
        return None, None, f"cannot run klt: {exc}"
    report = None
    for stream in (proc.stdout, proc.stderr):
        try:
            report = json.loads(stream)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(report, dict):
        return None, proc.returncode, (
            f"klt exit {proc.returncode} with no JSON report: "
            f"{tail(proc.stdout[-600:] + proc.stderr[-600:])}")
    if "error" in report:
        err = report["error"]
        msg = err.get("message") if isinstance(err, dict) else err
        return None, proc.returncode, f"klt error: {tail(str(msg))}"
    return report, proc.returncode, ""


def judge(step: Step, report: dict) -> tuple:
    """-> (verdict, gates, reasons).  A report that carries no verdict for
    the step's question is BLOCKED, never a pass."""
    gates, reasons = {}, []
    name = step.name
    if name == "synth":
        ok = (report.get("status") == "ok"
              and get(report, "structural", "has_critical") is False
              and isinstance(report.get("netlist_sha256"), str))
        if ok:
            return "PASS", gates, []
        return "FAIL", gates, [f"synthesis status {report.get('status')!r}, "
                               f"structural {report.get('structural')}"]
    if name == "par":
        power = report.get("power") or {}
        gates["pdn"] = power.get("pdn")
        gates["tapcell_master"] = power.get("tapcell_master")
        gates["gate1_pdn"] = (gates["pdn"] is True
                              and isinstance(gates["tapcell_master"], str)
                              and bool(gates["tapcell_master"]))
        if report.get("status") != "ok" or report.get("stage_reached") != "route":
            reasons.append(f"status {report.get('status')!r}, stage_reached "
                           f"{report.get('stage_reached')!r}")
        if not gates["gate1_pdn"]:
            reasons.append("gate 1 unmet: power.pdn is not true with a "
                           "named tapcell master")
        return ("PASS" if not reasons else "FAIL"), gates, reasons
    if name == "drc":
        status = report.get("status")
        coverage = report.get("coverage") or {}
        gates["status"] = status
        if status == "clean" and coverage.get("nothing_checked") is False:
            return "PASS", gates, []
        if status == "violations":
            return "FAIL", gates, [
                f"{report.get('violation_count')} DRC violations: "
                + json.dumps(report.get("rule_counts"), sort_keys=True)]
        return "BLOCKED", gates, [f"klt drc reached no clean/violations "
                                  f"verdict (status {status!r})"]
    if name == "lvs":
        pc = report.get("power_connectivity") or {}
        gates["status"] = report.get("status")
        gates["power_connectivity"] = pc.get("status")
        gates["gate2_lvs"] = (gates["status"] == "match"
                              and gates["power_connectivity"] == "match")
        if gates["gate2_lvs"]:
            return "PASS", gates, []
        if gates["status"] == "mismatch" or "match" in (
                gates["status"], gates["power_connectivity"]):
            return "FAIL", gates, [f"gate 2 unmet: status "
                                   f"{gates['status']!r}, power_connectivity "
                                   f"{gates['power_connectivity']!r}"]
        return "BLOCKED", gates, [f"klt lvs reached no verdict (status "
                                  f"{gates['status']!r})"]
    if name == "erc":
        nets = {n.get("name"): n for n in report.get("nets") or []}
        cov = report.get("erc_coverage") or {}
        skipped = json.dumps(cov.get("skipped") or [])
        findings = report.get("erc_findings") or []
        gates["erc_status"] = report.get("erc_status")
        gates["islands"] = {s: get(nets.get(s, {}), "matched_islands")
                            for s in SUPPLIES}
        gates["missing_tie_checked"] = (cov.get("missing_tie_checked") is True
                                        and "erc.missing_tie" not in skipped)
        gates["missing_tie_findings"] = sum(
            1 for f in findings if "missing_tie" in json.dumps(f))
        gates["gate3_erc"] = (all(v == 1 for v in gates["islands"].values())
                              and gates["missing_tie_checked"]
                              and gates["missing_tie_findings"] == 0)
        if gates["gate3_erc"]:
            return "PASS", gates, []
        if gates["missing_tie_checked"]:
            return "FAIL", gates, [f"gate 3 unmet: islands "
                                   f"{gates['islands']}, missing_tie findings "
                                   f"{gates['missing_tie_findings']}"]
        return "BLOCKED", gates, [f"gate 3 not decidable: erc_status "
                                  f"{gates['erc_status']!r}, tie check "
                                  f"skipped: {skipped}"]
    return "BLOCKED", gates, [f"no verdict rule for step {name}"]


def flow_block(step: Step, cmd: list, code, over: dict, klt_ver: str,
               versions: dict, elapsed: float) -> dict:
    return {
        "step": step.name,
        "claim": CLAIM,
        "klt_command": [Path(cmd[0]).name] + cmd[1:] if cmd else [],
        "klt_exit": code,
        "klt_version": klt_ver,
        "engine_versions": versions,
        "request": step.request,
        "request_sha256": sha256_file(REPO / step.request),
        "request_overrides": over,
        "rtl_sha256": rtl_hashes(),
        "generated_at": datetime.datetime.now(
            datetime.UTC).isoformat(timespec="seconds"),
        "elapsed_s": round(elapsed, 3),
    }


def blocked_record(flow: dict, reasons: list, issue) -> dict:
    flow = dict(flow)
    flow.update({"verdict": "BLOCKED", "gates": {}, "reasons": reasons})
    if issue:
        flow["upstream_issue"] = issue
    return {"flow": flow}


def verdict_record(flow: dict, step: Step, report: dict) -> dict:
    verdict, gates, reasons = judge(step, report)
    flow = dict(flow)
    flow.update({"verdict": verdict, "gate": step.gate, "gates": gates,
                 "reasons": reasons})
    out = scrub(step.command, report)
    out["flow"] = flow
    return out


def compare_step(step: Step, committed: dict, fresh: dict) -> list:
    """-> [reasons] the committed evidence does not reproduce."""
    reasons = []
    old = committed.get("flow") or {}
    if old.get("rtl_sha256") != rtl_hashes():
        reasons.append("committed evidence names different RTL")
    if old.get("verdict") == "BLOCKED":
        reasons.append(f"committed evidence is BLOCKED "
                       f"({old.get('reasons')}) but the step now reaches "
                       f"verdict {fresh['flow']['verdict']}; regenerate it")
        return reasons
    prov_new = fresh.get("provenance") or {}
    prov_old = committed.get("provenance") or {}
    if prov_old.get("klt_version") != prov_new.get("klt_version"):
        reasons.append(f"committed evidence was written by klt "
                       f"{prov_old.get('klt_version')}, this run used "
                       f"{prov_new.get('klt_version')}; regenerate it")
    paths = diff_paths(comparable(step.command, committed),
                       comparable(step.command, fresh))
    if paths:
        shown = ", ".join(paths[:DIFF_SHOWN])
        more = ("" if len(paths) <= DIFF_SHOWN
                else f" (+{len(paths) - DIFF_SHOWN} more)")
        reasons.append(f"committed evidence does not reproduce at "
                       f"{shown}{more}")
    return reasons


def parse_issue(value: str) -> tuple:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected STEP=URL")
    step, url = value.split("=", 1)
    if step not in BY_NAME:
        raise argparse.ArgumentTypeError(f"unknown step {step!r}")
    return step, url


def describe(rec: dict, step: Step) -> None:
    f = rec["flow"]
    print(f"{step.name}: {f['verdict']} gate={step.gate} "
          + json.dumps(f.get("gates"), sort_keys=True)
          + ("" if not f["reasons"] else " -- " + "; ".join(f["reasons"])))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--write", action="store_true",
                    help="write the committed evidence from this run")
    ap.add_argument("--venv", default=str(REPO / ".venv-fv"))
    ap.add_argument("--pdk-variant", default=DEFAULT_PDK_VARIANT,
                    help="installed PDK variant klt resolves (default: "
                         f"{DEFAULT_PDK_VARIANT}, a 5-metal-stack variant, "
                         "which the committed power block straps)")
    ap.add_argument("--cell-library", default=None,
                    help="override pdk.cell_library of the committed "
                         "requests for this run")
    ap.add_argument("--corner", default=None,
                    help="override pdk.corner of the committed requests")
    ap.add_argument("--site", default=None,
                    help="override floorplan.site of the committed request")
    ap.add_argument("--blocked-issue", action="append", default=[],
                    type=parse_issue, metavar="STEP=URL",
                    help="upstream klayout-tools issue a BLOCKED step "
                         "waits on; recorded with --write")
    args = ap.parse_args()

    klt = Path(args.venv) / "bin" / "klt"
    issues = dict(args.blocked_issue)
    env = dict(os.environ)
    env["PDK"] = args.pdk_variant

    try:
        pin = load_pin_module()
        problems = pin.check_pin(klt, pin.load_pin(str(REPO)),
                                 needed=[s.command for s in STEPS])
    except pin.PinError as exc:
        problems = [str(exc)]
    if problems:
        for p in problems:
            print(f"BLOCKED: toolchain pin: {p}")
        return EXIT["BLOCKED"]
    klt_ver = pin.klt_version(str(klt))
    print(f"toolchain: klt {klt_ver}, PDK variant {args.pdk_variant}")

    missing = sorted({b for s in STEPS for b in s.engines
                      if shutil.which(b) is None})
    if missing:
        print(f"BLOCKED: host engine(s) not on PATH: {', '.join(missing)}")
        return EXIT["BLOCKED"]

    over = overrides_for(args)
    if over:
        print(f"request overrides for this run: "
              f"{json.dumps(over, sort_keys=True)}")
    shutil.rmtree(REPO / BUILD_REL, ignore_errors=True)

    versions = engine_versions(sorted({b for s in STEPS for b in s.engines}))
    worst, records = "PASS", {}
    for step in STEPS:
        t0 = time.time()
        blocked_in = [n for n in step.needs
                      if records[n]["flow"]["verdict"] == "BLOCKED"]
        if blocked_in:
            flow = flow_block(step, [], None, over, klt_ver, {}, 0.0)
            rec = blocked_record(
                flow, [f"not reached: step {n} is BLOCKED" for n in blocked_in],
                issues.get(step.name))
        else:
            try:
                request = effective_request(step, over)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                flow = flow_block(step, [], None, over, klt_ver, {}, 0.0)
                rec = blocked_record(flow, [f"cannot prepare the request: "
                                            f"{exc}"], issues.get(step.name))
                request = None
            if request is not None:
                cmd = klt_command(step, klt, request, args.pdk_variant)
                report, code, why = run_klt(cmd, env)
                flow = flow_block(step, cmd, code, over, klt_ver, versions,
                                  time.time() - t0)
                if report is None:
                    rec = blocked_record(flow, [why], issues.get(step.name))
                else:
                    rec = verdict_record(flow, step, report)
        records[step.name] = rec
        if RANK[rec["flow"]["verdict"]] > RANK[worst]:
            worst = rec["flow"]["verdict"]
        describe(rec, step)

    if args.write:
        EVID.mkdir(parents=True, exist_ok=True)
        for step in STEPS:
            path = EVID / f"{step.name}.json"
            path.write_text(json.dumps(records[step.name], indent=1,
                                       sort_keys=True) + "\n",
                            encoding="utf-8")
            print(f"WROTE {path.relative_to(REPO)} "
                  f"verdict={records[step.name]['flow']['verdict']}")
        print(f"flow-smoke: {worst}")
        return EXIT[worst]

    for step in STEPS:
        path = EVID / f"{step.name}.json"
        if not path.exists():
            print(f"BLOCKED: no committed evidence at "
                  f"{path.relative_to(REPO)} (run with --write)")
            return EXIT["BLOCKED"]
        rec = records[step.name]
        if rec["flow"]["verdict"] == "BLOCKED":
            continue
        reasons = compare_step(step, load_json(path), rec)
        if reasons:
            rec["flow"]["verdict"] = "FAIL"
            rec["flow"]["reasons"] = reasons
            worst = "FAIL" if worst == "PASS" else worst
            print(f"{step.name}: committed evidence FAILS to reproduce -- "
                  + "; ".join(reasons))
    print(f"flow-smoke: {worst}")
    return EXIT[worst]


if __name__ == "__main__":
    sys.exit(main())
