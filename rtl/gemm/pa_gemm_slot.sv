// One M2 tile-buffer slot. A is banked by row and B by four-column group so
// the compute pipeline can select its A rows and all 16 B lanes in one cycle.

module pa_gemm_slot #(
  parameter int unsigned MaxM = 16,
  parameter int unsigned MaxK = 768,
  parameter int unsigned CWordsPerRow = 8
) (
  input logic clk_i,

  input logic                         a_we_i,
  input logic [$clog2(MaxM)-1:0]      a_row_i,
  input logic [$clog2((MaxK+3)/4)-1:0] a_waddr_i,
  input logic [31:0]                  a_wdata_i,
  input logic [$clog2((MaxK+3)/4)-1:0] a_raddr_i,
  output logic [31:0]                 a_rdata_o [MaxM],

  input logic                         b_we_i,
  input logic [1:0]                   b_group_i,
  input logic [$clog2(MaxK)-1:0]      b_waddr_i,
  input logic [31:0]                  b_wdata_i,
  input logic [$clog2(MaxK)-1:0]      b_raddr_i,
  output logic [31:0]                 b_rdata_o [4],

  input logic                         c_we_i,
  input logic [$clog2(MaxM*CWordsPerRow)-1:0] c_waddr_i,
  input logic [31:0]                  c_wdata_i,
  input logic [$clog2(MaxM*CWordsPerRow)-1:0] c_raddr_i,
  output logic [31:0]                 c_rdata_o
);

  for (genvar row = 0; row < MaxM; row++) begin : g_a_row
    logic [31:0] mem [0:(MaxK+3)/4-1];
    always_ff @(posedge clk_i) begin
      if (a_we_i && a_row_i == $clog2(MaxM)'(row)) begin
        mem[a_waddr_i] <= a_wdata_i;
      end
      a_rdata_o[row] <= mem[a_raddr_i];
    end
  end

  for (genvar group = 0; group < 4; group++) begin : g_b_group
    logic [31:0] mem [0:MaxK-1];
    always_ff @(posedge clk_i) begin
      if (b_we_i && b_group_i == 2'(group)) begin
        mem[b_waddr_i] <= b_wdata_i;
      end
      b_rdata_o[group] <= mem[b_raddr_i];
    end
  end

  logic [31:0] c_mem [0:MaxM*CWordsPerRow-1];
  always_ff @(posedge clk_i) begin
    if (c_we_i) c_mem[c_waddr_i] <= c_wdata_i;
  end
  assign c_rdata_o = c_mem[c_raddr_i];

endmodule
