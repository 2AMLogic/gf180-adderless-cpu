// Smoke design for the verification harness (issue #2).
//
// A 1-bit register with active-low asynchronous reset. It is a toolchain
// exercise only: it carries no ISA, datapath or compatibility meaning.
//
// SMOKE_MUTATE (set through request options.source_defines by
// tools/smoke.py --control) compiles the mutant: inverted capture, so the
// smoke test must fail. That is the harness's negative control -- without
// it a vacuous pass is indistinguishable from a working harness.

`timescale 1ns/1ps

module smoke_reg (
    input  wire clk,
    input  wire rst_n,
    input  wire d,
    output reg   q
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            q <= 1'b0;
        end else begin
`ifdef SMOKE_MUTATE
            q <= ~d;
`else
            q <= d;
`endif
        end
    end

endmodule
