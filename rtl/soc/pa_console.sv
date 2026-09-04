// PocketAI-T synthesizable console FIFO.
//
// Register map:
//   +0x0 DATA    write low byte to enqueue; read low byte to dequeue
//   +0x4 STATUS  [15:0] queued bytes, [16] overflow, [31] software done
//   +0x8 CONTROL write bit0 to latch done; write bit1 to clear overflow
//
// The A9 drains this FIFO through the cluster AXI window and prints it as the
// soft-core UART/console. Simulation observes the same device and protocol.

module pa_console #(
  parameter int unsigned Depth = 64
) (
  input  logic        clk_i,
  input  logic        rst_ni,
  input  logic        req_i,
  input  logic        we_i,
  input  logic [ 3:0] be_i,
  input  logic [31:0] addr_i,
  input  logic [31:0] wdata_i,
  output logic        rvalid_o,
  output logic [31:0] rdata_o,
  output logic        char_valid_o,
  output logic [ 7:0] char_data_o,
  output logic        done_o
);

  localparam int unsigned PtrWidth = Depth > 1 ? $clog2(Depth) : 1;
  localparam int unsigned CountWidth = $clog2(Depth + 1);

  logic [7:0] fifo [0:Depth-1];
  logic [PtrWidth-1:0] read_ptr_q, write_ptr_q;
  logic [CountWidth-1:0] count_q;
  logic overflow_q, done_q;
  logic unused_addr_parts, unused_write_parts;
  assign unused_addr_parts = ^{addr_i[31:4], addr_i[1:0]};
  assign unused_write_parts = ^{be_i[3:1], wdata_i[31:8]};

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      read_ptr_q    <= '0;
      write_ptr_q   <= '0;
      count_q       <= '0;
      overflow_q    <= 1'b0;
      done_q        <= 1'b0;
      rvalid_o      <= 1'b0;
      rdata_o       <= 32'h0;
      char_valid_o  <= 1'b0;
      char_data_o   <= 8'h0;
    end else begin
      rvalid_o     <= req_i;
      char_valid_o <= 1'b0;

      if (req_i) begin
        unique case (addr_i[3:2])
          2'b00: begin
            rdata_o <= count_q != 0 ? {24'h0, fifo[read_ptr_q]} : 32'h0;
            if (we_i && be_i[0]) begin
              if (count_q < CountWidth'(Depth)) begin
                fifo[write_ptr_q] <= wdata_i[7:0];
                write_ptr_q       <= write_ptr_q + PtrWidth'(1);
                count_q           <= count_q + CountWidth'(1);
                char_valid_o      <= 1'b1;
                char_data_o       <= wdata_i[7:0];
              end else begin
                overflow_q <= 1'b1;
              end
            end else if (!we_i && count_q != 0) begin
              read_ptr_q <= read_ptr_q + PtrWidth'(1);
              count_q    <= count_q - CountWidth'(1);
            end
          end
          2'b01: begin
            rdata_o <= {done_q, 14'h0, overflow_q, 16'(count_q)};
          end
          2'b10: begin
            rdata_o <= {31'h0, done_q};
            if (we_i && be_i[0]) begin
              if (wdata_i[0]) done_q     <= 1'b1;
              if (wdata_i[1]) overflow_q <= 1'b0;
            end
          end
          default: rdata_o <= 32'h0;
        endcase
      end
    end
  end

  assign done_o = done_q;

endmodule
