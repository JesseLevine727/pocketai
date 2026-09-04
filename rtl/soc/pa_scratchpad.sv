// PocketAI-T shared byte-writeable scratchpad.
//
// The synchronous read and byte-enable write form infer block RAM in Vivado.
// Storage is intentionally not reset: the A9 loads the firmware while the
// Ibex cores are held in reset, or simulation loads it through MemUtil.

module pa_scratchpad #(
  parameter int unsigned DepthWords = 16 * 1024,
  parameter string       MemInitFile = ""
) (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        req_i,
  input  logic        we_i,
  input  logic [ 3:0] be_i,
  input  logic [31:0] addr_i,
  input  logic [31:0] wdata_i,
  output logic        rvalid_o,
  output logic [31:0] rdata_o
);

  localparam int unsigned AddrWidth = $clog2(DepthWords);
  localparam int unsigned Width = 32;
  localparam int unsigned Depth = DepthWords;

  (* ram_style = "block" *)
  logic [31:0] mem [0:DepthWords-1] /* verilator public_flat_rw */;

  logic [AddrWidth-1:0] word_addr;
  logic unused_addr_parts;
  assign word_addr = addr_i[AddrWidth+1:2];
  assign unused_addr_parts = ^{addr_i[31:AddrWidth+2], addr_i[1:0]};

  `include "prim_util_memload.svh"

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) rvalid_o <= 1'b0;
    else          rvalid_o <= req_i;
  end

  always_ff @(posedge clk_i) begin
    if (req_i) begin
      rdata_o <= mem[word_addr];
      if (we_i) begin
        if (be_i[0]) mem[word_addr][ 7: 0] <= wdata_i[ 7: 0];
        if (be_i[1]) mem[word_addr][15: 8] <= wdata_i[15: 8];
        if (be_i[2]) mem[word_addr][23:16] <= wdata_i[23:16];
        if (be_i[3]) mem[word_addr][31:24] <= wdata_i[31:24];
      end
    end
  end

endmodule
