// EXPERIMENTAL ASIC refinement, NOT a drop-in 1W2R memory replacement.
// The physical SRAM runs at the system clock. Writes take priority; a read
// requested during a write is NOT performed, even on the other read copy.
// Accept only after each consumer's write/read-use exclusion is proved and
// full-system numerical/lifecycle behavior is requalified. Capacity, byte
// masks and broadcast-write coherence are retained. No timing pass is implied.
module pa_m6_sram_1w2r #(
  parameter integer WIDTH = 32,
  parameter integer DEPTH = 512,
  parameter integer ADDR_WIDTH = $clog2(DEPTH),
  parameter integer READ_PORTS = 1
) (
`ifdef USE_POWER_PINS
  inout wire vdd, vss,
`endif
  input wire clk_sys_i,
  input wire clk_mem_i,
  input wire rst_ni,
  input wire [READ_PORTS-1:0] rd_en_i,
  input wire [READ_PORTS*ADDR_WIDTH-1:0] rd_addr_i,
  output wire [READ_PORTS*WIDTH-1:0] rd_data_o,
  input wire [(WIDTH+7)/8-1:0] wr_mask_i,
  input wire [ADDR_WIDTH-1:0] wr_addr_i,
  input wire [WIDTH-1:0] wr_data_i
);
  localparam integer BANKS = (DEPTH+511)/512;
  localparam integer SLICES = (WIDTH+31)/32;
  localparam integer MASK_WIDTH = (WIDTH+7)/8;
  localparam integer BANK_INDEX_WIDTH = BANKS > 1 ? $clog2(BANKS) : 1;
  wire writing = |wr_mask_i;
  wire [SLICES*32-1:0] padded_data = {{(SLICES*32-WIDTH){1'b0}}, wr_data_i};
  wire [SLICES*4-1:0] padded_mask = {{(SLICES*4-MASK_WIDTH){1'b0}}, wr_mask_i};
  // clk_mem_i is intentionally unused: the old doubled-clock boundary is
  // retained only so a source-isolated experiment can reuse existing wrappers.
  wire unused_memory_clock = clk_mem_i;
  for (genvar port = 0; port < READ_PORTS; port = port+1) begin : g_read
    wire [ADDR_WIDTH-1:0] read_addr = rd_addr_i[port*ADDR_WIDTH+:ADDR_WIDTH];
    reg [BANK_INDEX_WIDTH-1:0] selected_bank_q;
    always @(posedge clk_sys_i or negedge rst_ni)
      if (!rst_ni) selected_bank_q <= 0;
      else if (!writing && rd_en_i[port]) selected_bank_q <= BANK_INDEX_WIDTH'(read_addr >> 9);
    wire [SLICES*32-1:0] bank_data [BANKS];
    wire [SLICES*32-1:0] selected_data = bank_data[selected_bank_q];
    assign rd_data_o[port*WIDTH+:WIDTH] = selected_data[WIDTH-1:0];
    for (genvar bank = 0; bank < BANKS; bank = bank+1) begin : g_bank
      wire enable = rst_ni && (writing ? ((wr_addr_i >> 9) == bank) :
                                (rd_en_i[port] && ((read_addr >> 9) == bank)));
      wire [8:0] address = writing ? 9'(wr_addr_i) : 9'(read_addr);
      for (genvar slice = 0; slice < SLICES; slice = slice+1) begin : g_slice
        sram22_512x32m4w8 u_sram (
`ifdef USE_POWER_PINS
          .vdd(vdd), .vss(vss),
`endif
          .clk(clk_sys_i), .rstb(1'b1), .ce(enable), .we(writing),
          .wmask(padded_mask[slice*4+:4]), .addr(address),
          .din(padded_data[slice*32+:32]), .dout(bank_data[bank][slice*32+:32])
        );
      end
    end
  end
endmodule
