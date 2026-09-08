// Experimental alternative to pa_m6_sram_1x_candidate.sv. Same write-priority
// access contract, but predecoded registered bank selection reduces the return
// path to a parallel AND/OR network. Physical/consumer qualification is separate.
module pa_m6_sram_1w2r #(
  parameter integer WIDTH=32, DEPTH=512, ADDR_WIDTH=$clog2(DEPTH), READ_PORTS=1
) (
`ifdef USE_POWER_PINS
  inout wire vdd, vss,
`endif
  input wire clk_sys_i, clk_mem_i, rst_ni,
  input wire [READ_PORTS-1:0] rd_en_i,
  input wire [READ_PORTS*ADDR_WIDTH-1:0] rd_addr_i,
  output wire [READ_PORTS*WIDTH-1:0] rd_data_o,
  input wire [(WIDTH+7)/8-1:0] wr_mask_i,
  input wire [ADDR_WIDTH-1:0] wr_addr_i,
  input wire [WIDTH-1:0] wr_data_i
);
  localparam integer BANKS=(DEPTH+511)/512, SLICES=(WIDTH+31)/32;
  localparam integer MASK_WIDTH=(WIDTH+7)/8;
  wire writing=|wr_mask_i;
  wire [SLICES*32-1:0] padded_data={{(SLICES*32-WIDTH){1'b0}},wr_data_i};
  wire [SLICES*4-1:0] padded_mask={{(SLICES*4-MASK_WIDTH){1'b0}},wr_mask_i};
  wire unused_memory_clock=clk_mem_i;
  for (genvar port=0; port<READ_PORTS; port=port+1) begin : g_read
    wire [ADDR_WIDTH-1:0] read_addr=rd_addr_i[port*ADDR_WIDTH+:ADDR_WIDTH];
    wire [SLICES*32-1:0] bank_data [BANKS];
    reg [BANKS-1:0] selected_bank_q;
    for (genvar bank=0; bank<BANKS; bank=bank+1) begin : g_bank
      always @(posedge clk_sys_i or negedge rst_ni)
        if (!rst_ni) selected_bank_q[bank] <= (bank == 0);
        else if (!writing && rd_en_i[port])
          selected_bank_q[bank] <= ((read_addr >> 9) == bank);
      wire enable=rst_ni && (writing ? ((wr_addr_i >> 9) == bank) :
                              (rd_en_i[port] && ((read_addr >> 9) == bank)));
      wire [8:0] address=writing ? 9'(wr_addr_i) : 9'(read_addr);
      for (genvar slice=0; slice<SLICES; slice=slice+1) begin : g_slice
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
    for (genvar bit_index=0; bit_index<WIDTH; bit_index=bit_index+1) begin : g_return
      wire [BANKS-1:0] terms;
      for (genvar bank=0; bank<BANKS; bank=bank+1) begin : g_term
        assign terms[bank]=selected_bank_q[bank] && bank_data[bank][bit_index];
      end
      assign rd_data_o[port*WIDTH+bit_index]=|terms;
    end
  end
endmodule
