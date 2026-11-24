.PHONY: smoke smoke-control harness-tests check-pins flow-smoke \
	flow-smoke-write flow-tests clean

# Smoke verification harness (issue #2).  Pattern copied from
# 2AMLogic/gf180-dx7 @ 69f0464147172f3d4a5506fc2a0c555008d3f36e (its FV
# targets).  Creates a throwaway .venv-fv in this checkout; no host tool
# is installed.  See verification/README.md.
FV_VENV ?= .venv-fv
FV_PINS = "klayout-tools==0.9.2" "cocotb==2.1.0"

$(FV_VENV)/bin/klt:
	uv venv $(FV_VENV)
	uv pip install --python $(FV_VENV)/bin/python $(FV_PINS)

# Check mode: re-run the committed smoke request and require the
# committed evidence (verification/evidence/smoke.json) to reproduce.
smoke: $(FV_VENV)/bin/klt
	python3 tools/smoke.py --venv $(FV_VENV)

# Negative control: the SMOKE_MUTATE build must fail the same smoke test.
smoke-control: $(FV_VENV)/bin/klt
	python3 tools/smoke.py --venv $(FV_VENV) --control

# Harness regression tests (issues #7 and #11): the smoke runner's
# exit-code contract, and its evidence-write guards (a record is only
# overwritten with a valid one).  Hermetic: fake venvs and a throwaway
# tree copy; no simulator, cocotb or network needed.
harness-tests:
	python3 -I tools/test_smoke_exits.py

# Implementation-flow smoke (issue #18): synthesis, place-and-route, DRC,
# gate-level LVS and the supply ERC read on rtl/smoke_reg.v, from the
# committed klt requests under flow/, through the same pinned venv.  Check
# mode: re-run and require flow/evidence/ to reproduce.  Needs yosys and
# openroad on PATH and an installed gf180mcu PDK (flow/README.md says
# where this runs and why it is not a CI job).
flow-smoke: $(FV_VENV)/bin/klt
	python3 flow/flow_smoke.py --venv $(FV_VENV)

flow-smoke-write: $(FV_VENV)/bin/klt
	python3 flow/flow_smoke.py --venv $(FV_VENV) --write

# Hermetic exit-code contract tests for flow/flow_smoke.py: a fake klt,
# no engine, PDK or network.
flow-tests:
	python3 tools/test_flow_exits.py

# Fast lane: the committed evidence must name the pinned toolchain.
check-pins:
	python3 tools/check_pins.py

clean:
	rm -rf .venv-fv build .klt flow/build flow/.klt
	find . -name __pycache__ -type d -exec rm -rf {} +
