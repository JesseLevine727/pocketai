// Preserve a fixed-one-cycle response across accelerator cancellation/reset.
// Only the accelerator state resets on cancel; this responder stays live.
module pa_m5_mmio_cancel (
  input logic clk_i,
  input logic rst_ni,
  input logic cancel_i,
  input logic req_i,
  output logic engine_req_o,
  input logic engine_rvalid_i,
  input logic [31:0] engine_rdata_i,
  input logic engine_err_i,
  output logic rvalid_o,
  output logic [31:0] rdata_o,
  output logic err_o
);
  logic cancelled_q;
  assign engine_req_o = req_i && !cancel_i;
  assign err_o = rvalid_o && (cancel_i || cancelled_q || engine_err_i || !engine_rvalid_i);
  assign rdata_o = err_o ? 32'b0 : engine_rdata_i;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      rvalid_o <= 0;
      cancelled_q <= 0;
    end else begin
      rvalid_o <= req_i;
      cancelled_q <= cancel_i;
      if (rvalid_o && !cancel_i && !cancelled_q) assert (engine_rvalid_i);
    end
  end
endmodule
