// Cycle-preserving synchronous read-before-write storage using 1RW SRAM IP.
// See docs/M6_MEMORY_PORT.md. clk_sys_i is a falling-edge /2 of clk_mem_i.
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
  reg [READ_PORTS-1:0] read_en_q;
  reg [READ_PORTS*ADDR_WIDTH-1:0] read_addr_q;
  reg [ADDR_WIDTH-1:0] write_addr_q;
  reg [MASK_WIDTH-1:0] write_mask_q;
  reg [WIDTH-1:0] write_data_q;
  // Separate DATA phase from the generated system CLOCK. Both toggle on
  // falling memory edges, with complementary reset polarity. Keeping phase
  // as ordinary FF data lets implementation buffer the address/control muxes
  // without discovering them as clock trees. The complementary set-reset
  // flop also prevents merging this state with the reset-low clock divider.
  reg write_phase_q;
  always @(negedge clk_mem_i or negedge rst_ni)
    if (!rst_ni) write_phase_q <= 1'b1;
    else write_phase_q <= !write_phase_q;
  wire [SLICES*32-1:0] padded_data = {{(SLICES*32-WIDTH){1'b0}}, write_data_q};
  wire [SLICES*4-1:0] padded_mask = {{(SLICES*4-MASK_WIDTH){1'b0}}, write_mask_q};

  always @(posedge clk_sys_i or negedge rst_ni) begin
    if (!rst_ni) begin
      read_en_q <= 0;
      read_addr_q <= 0;
      write_addr_q <= 0;
      write_mask_q <= 0;
      write_data_q <= 0;
    end else begin
      read_en_q <= rd_en_i;
      for (integer port = 0; port < READ_PORTS; port = port+1)
        if (rd_en_i[port])
          read_addr_q[port*ADDR_WIDTH+:ADDR_WIDTH] <= rd_addr_i[port*ADDR_WIDTH+:ADDR_WIDTH];
      write_addr_q <= wr_addr_i;
      write_mask_q <= wr_mask_i;
      write_data_q <= wr_data_i;
    end
  end

  for (genvar port = 0; port < READ_PORTS; port = port+1) begin : g_read
    wire [ADDR_WIDTH-1:0] read_addr = read_addr_q[port*ADDR_WIDTH+:ADDR_WIDTH];
    wire [SLICES*32-1:0] bank_data [BANKS];
    wire [SLICES*32-1:0] selected_data = bank_data[BANK_INDEX_WIDTH'(read_addr >> 9)];
    assign rd_data_o[port*WIDTH+:WIDTH] = selected_data[WIDTH-1:0];
    for (genvar bank = 0; bank < BANKS; bank = bank+1) begin : g_bank
      wire read_enable = read_en_q[port] && ((read_addr >> 9) == bank);
      wire write_enable = (|write_mask_q) && ((write_addr_q >> 9) == bank);
      wire enable = rst_ni && (write_phase_q ? write_enable : read_enable);
      wire [8:0] address = write_phase_q ? 9'(write_addr_q) : 9'(read_addr);
      for (genvar slice = 0; slice < SLICES; slice = slice+1) begin : g_slice
        sram22_512x32m4w8 u_sram (
`ifdef USE_POWER_PINS
          .vdd(vdd), .vss(vss),
`endif
          .clk(clk_mem_i), .rstb(1'b1), .ce(enable), .we(write_phase_q),
          .wmask(padded_mask[slice*4+:4]), .addr(address),
          .din(padded_data[slice*32+:32]), .dout(bank_data[bank][slice*32+:32])
        );
      end
    end
  end
endmodule
