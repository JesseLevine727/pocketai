// PocketAI-T M1b -- inter-hart mailbox device
//
// Two one-word mailboxes plus a status register (level pending bits),
// behind a single
// "immediate grant, 1-cycle latency" bus device port (same protocol as
// `ram_1p` / `simulator_ctrl`):
//
//   +0x0  mbox0_to_1  (W) 0 -> 1, (R) last value written to this register
//       write sets pend0
//   +0x4  mbox1_to_0  (W) 1 -> 0, (R) last value written to this register
//       write sets pend1
//   +0x8  status      (R) bit0 = pend0, bit1 = pend1.  Writes are ignored.
//   +0xc  acknowledge (W1C) bit0 clears pend0, bit1 clears pend1.
//
// Interrupt lines are level signals:
//   irq0_o = pend1  (core0 is interested in mbox1_to_0)
//   irq1_o = pend0  (core1 is interested in mbox0_to_1)
//
// The pending bits are LEVELS: they latch when the peer writes a mailbox and
// remain asserted until software explicitly acknowledges that direction.
// A shared read-clear register is intentionally avoided because one hart
// could otherwise clear the other hart's pending message.

module pa_mailbox (
  input  logic        clk_i,
  input  logic        rst_ni,

  // Bus device port (immediate grant, 1-cycle latency)
  input  logic        req_i,
  input  logic        we_i,
  input  logic [ 3:0] be_i,
  input  logic [31:0] addr_i,
  input  logic [31:0] wdata_i,
  output logic        rvalid_o,
  output logic [31:0] rdata_o,

  // Level interrupt lines (mbox1_to_0 pending -> core0, mbox0_to_1 pending
  // -> core1)
  output logic        irq0_o,
  output logic        irq1_o
);

  logic [31:0] data0_q, data1_q;
  logic        pend0_q, pend1_q;
  logic        unused_addr_parts;
  assign unused_addr_parts = ^{addr_i[31:4], addr_i[1:0]};

  // Merge a byte-enable write into the previous register value
  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_val,
      input logic [31:0] new_val,
      input logic [ 3:0] be
    );
    for (int i = 0; i < 4; i++) begin
      merge_bytes[8*i +: 8] = be[i] ? new_val[8*i +: 8] : old_val[8*i +: 8];
    end
  endfunction

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      data0_q  <= 32'h0;
      data1_q  <= 32'h0;
      pend0_q  <= 1'b0;
      pend1_q  <= 1'b0;
      rvalid_o <= 1'b0;
      rdata_o  <= 32'h0;
    end else begin
      // Respond one cycle after the request, like ram_1p
      rvalid_o <= req_i;
      if (req_i) begin
        case (addr_i[3:2])
          2'b00: begin // mbox0_to_1 @ +0x0
            rdata_o <= data0_q;
            if (we_i) begin
              data0_q <= merge_bytes(data0_q, wdata_i, be_i);
              pend0_q <= 1'b1;
            end
          end
          2'b01: begin // mbox1_to_0 @ +0x4
            rdata_o <= data1_q;
            if (we_i) begin
              data1_q <= merge_bytes(data1_q, wdata_i, be_i);
              pend1_q <= 1'b1;
            end
          end
          2'b10: begin // status @ +0x8: level read (no clear; see header)
            rdata_o  <= {30'd0, pend1_q, pend0_q};
          end
          2'b11: begin // acknowledge @ +0xc: write-one-to-clear pending bits
            rdata_o <= 32'h0;
            if (we_i && be_i[0]) begin
              if (wdata_i[0]) pend0_q <= 1'b0;
              if (wdata_i[1]) pend1_q <= 1'b0;
            end
          end
          default: rdata_o <= 32'h0;
        endcase
      end
    end
  end

  assign irq0_o = pend1_q;
  assign irq1_o = pend0_q;

endmodule
