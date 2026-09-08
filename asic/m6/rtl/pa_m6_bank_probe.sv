// Representative 4-bank, 2-read-copy cluster with registered boundary.
// It exercises actual SRAM/periphery timing, not CPU or full-system timing.
module pa_m6_bank_probe (
  input wire clk,
  input wire rst_n,
  input wire [1:0] rd_en,
  input wire [21:0] rd_addr,
  input wire [10:0] wr_addr,
  input wire [31:0] wr_data,
  input wire [3:0] wr_mask,
  output reg [63:0] rd_data
);
  reg [1:0] rd_en_q;
  reg [21:0] rd_addr_q;
  reg [10:0] wr_addr_q;
  reg [31:0] wr_data_q;
  reg [3:0] wr_mask_q;
  wire [63:0] result;
  always @(posedge clk) begin
    rd_en_q <= rd_en;
    rd_addr_q <= rd_addr;
    wr_addr_q <= wr_addr;
    wr_data_q <= wr_data;
    wr_mask_q <= wr_mask;
    rd_data <= result;
  end
  pa_m6_sram_1w2r #(.WIDTH(32), .DEPTH(2048), .READ_PORTS(2)) u_memory (
    .clk_sys_i(clk), .clk_mem_i(1'b0), .rst_ni(rst_n),
    .rd_en_i(rd_en_q), .rd_addr_i(rd_addr_q), .rd_data_o(result),
    .wr_mask_i(wr_mask_q), .wr_addr_i(wr_addr_q), .wr_data_i(wr_data_q)
  );
endmodule
