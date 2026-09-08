// Technology-integration experiment, NOT the PocketAI system or chip.
// A registered interface exposes the actual SRAM timing to STA.
module pa_m6_sram_probe (
`ifdef USE_POWER_PINS
    inout vdd,
    inout vss,
`endif
    input clk,
    input rstb,
    input ce,
    input we,
    input [3:0] wmask,
    input [8:0] addr,
    input [31:0] din,
    output reg [31:0] dout
);
  reg ce_q, we_q;
  reg [3:0] mask_q;
  reg [8:0] addr_q;
  reg [31:0] data_q;
  wire [31:0] result;
  always @(posedge clk) begin
    ce_q <= ce && rstb;
    we_q <= we;
    mask_q <= wmask;
    addr_q <= addr;
    data_q <= din;
    dout <= result;
  end
  sram22_512x32m4w8 u_sram (
`ifdef USE_POWER_PINS
    .vdd(vdd), .vss(vss),
`endif
    // rstb at the probe boundary suppresses new requests; storage is never
    // reset. Keep the macro's self-timed internal reset stable during access.
    .clk(clk), .rstb(1'b1), .ce(ce_q), .we(we_q), .wmask(mask_q),
    .addr(addr_q), .din(data_q), .dout(result)
  );
endmodule
