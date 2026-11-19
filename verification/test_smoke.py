"""Cocotb smoke test for rtl/smoke_reg.v (issue #2).

One test: reset clears q, then q follows d on each rising edge. Under the
SMOKE_MUTATE build (tools/smoke.py --control) the same test must fail --
that is the harness's negative control.

Pattern copied from 2AMLogic/gf180-dx7 @
69f0464147172f3d4a5506fc2a0c555008d3f36e (tools/fv_cocotb_dx7_core.py),
reduced to a single test driving the DUT directly: no playback, no
subprocess bench -- the cocotb simulation is the whole verdict here.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

PATTERN = (1, 0, 1, 1, 0)


@cocotb.test()
async def smoke_reg_follows_d(dut):
    """Reset clears q; afterwards q follows d on each rising edge."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.d.value = 0
    for _ in range(2):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert dut.q.value == 0, f"reset did not clear q: {dut.q.value}"
    dut.rst_n.value = 1
    for bit in PATTERN:
        dut.d.value = bit
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        assert dut.q.value == bit, f"q={dut.q.value} after feeding d={bit}"
