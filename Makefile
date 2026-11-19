.PHONY: smoke smoke-control harness-tests check-pins clean

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

# Harness regression tests (issue #11): the committed evidence writers
# only overwrite a record with a valid one.  Runs in a throwaway tree
# copy against a fake venv; no simulator, cocotb or network needed.
harness-tests:
	python3 verification/test_smoke_control.py

# Fast lane: the committed evidence must name the pinned toolchain.
check-pins:
	python3 tools/check_pins.py

clean:
	rm -rf .venv-fv build .klt
	find . -name __pycache__ -type d -exec rm -rf {} +
