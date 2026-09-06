// Single-credit MMIO publication/completion queue for the autonomous mover.
// Hart 1 owns runtime publication; reset/route policy: M5_TRANSFER_ABI.md.
module pa_m5_transfer_control (
  input logic clk_i,
  input logic rst_ni,
  input logic abort_i,
  input logic req_i,
  input logic we_i,
  input logic [3:0] be_i,
  input logic [31:0] addr_i,
  input logic [31:0] wdata_i,
  output logic rvalid_o,
  output logic [31:0] rdata_o,
  output logic err_o,
  output logic irq_o,
  output logic abort_request_o,
  output logic cmd_valid_o,
  input logic cmd_ready_i,
  output logic [31:0] cmd_src_addr_o [3],
  output logic [31:0] cmd_src_words_o [3],
  output logic [31:0] cmd_dst_addr_o,
  output logic [31:0] cmd_dst_words_o,
  output logic [31:0] cmd_tag_o,
  output logic [31:0] cmd_deadline_o,
  input logic busy_i,
  input logic stopped_i,
  input logic fault_abort_i,
  input logic done_valid_i,
  output logic done_ready_o,
  input logic [31:0] tag_i,
  input logic [7:0] fault_i,
  input logic [31:0] sent_words_i,
  input logic [31:0] received_words_i
);
  logic [31:0] staging_q [10];
  logic irq_enable_q, done_previous_q, ready;
  logic [1:0] rejection_q, access_fault;
  logic [31:0] accepted_q, completed_q, rejected_q, read_data, irq_new;
  logic staging_access, command_access;
  logic [3:0] staging_index;
  logic unused_address;
  assign unused_address = ^addr_i[31:10];
  assign staging_access = addr_i[9:2] >= 2 && addr_i[9:2] <= 11;
  assign staging_index = addr_i[5:2] - 4'd2;
  assign command_access = addr_i[9:2] == 8'h0c;
  assign ready = cmd_ready_i && !abort_i && !abort_request_o;
  assign irq_o = irq_enable_q && (done_valid_i || stopped_i || rejection_q != 0);
  for (genvar i = 0; i < 3; i++) begin : g_source
    assign cmd_src_addr_o[i] = staging_q[2*i];
    assign cmd_src_words_o[i] = staging_q[2*i + 1];
  end
  assign cmd_dst_addr_o = staging_q[6];
  assign cmd_dst_words_o = staging_q[7];
  assign cmd_tag_o = staging_q[8];
  assign cmd_deadline_o = staging_q[9];
  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value, new_value, input logic [3:0] enables);
    for (int i = 0; i < 4; i++)
      merge_bytes[8*i +: 8] = enables[i] ? new_value[8*i +: 8] : old_value[8*i +: 8];
  endfunction
  assign irq_new = merge_bytes({31'b0, irq_enable_q}, wdata_i, be_i);

  always_comb begin
    read_data = 0; access_fault = 0;
    if (staging_access) read_data = staging_q[staging_index];
    else case (addr_i[9:2])
      8'h00: read_data = 32'h50415435;
      8'h01: read_data = {25'b0, (rejection_q != 0), abort_request_o,
                         fault_abort_i, stopped_i, done_valid_i, busy_i, ready};
      8'h0c: read_data = 0;
      8'h0d: read_data = tag_i;
      8'h0e: read_data = {24'b0, fault_i};
      8'h0f: read_data = sent_words_i;
      8'h10: read_data = received_words_i;
      8'h11: read_data = {31'b0, irq_enable_q};
      8'h12: read_data = 1;
      8'h13: read_data = {30'b0, rejection_q};
      8'h14: read_data = accepted_q;
      8'h15: read_data = completed_q;
      8'h16: read_data = rejected_q;
      8'h17: read_data = 32'h00030101;
      default: access_fault = 3;
    endcase
    if (we_i && !staging_access) begin
      if (command_access) begin
        if (be_i != 4'hf || !(wdata_i == 1 || wdata_i == 2 || wdata_i == 4 || wdata_i == 8))
          access_fault = 2;
        else if ((wdata_i == 1 && !ready) || (wdata_i == 2 && !done_valid_i)) access_fault = 1;
      end else if (addr_i[9:2] == 8'h11) begin
        if (irq_new[31:1] != 0) access_fault = 3;
      end else access_fault = 3;
    end
    if (addr_i[1:0] != 0) access_fault = 3;
  end
  // A refused MMIO doorbell never exposes an unowned ready/valid command.
  assign cmd_valid_o = req_i && we_i && command_access && access_fault == 0 && wdata_i == 1;
  assign done_ready_o = req_i && we_i && command_access && access_fault == 0 && wdata_i == 2;

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      rvalid_o <= 0; rdata_o <= 0; err_o <= 0;
      irq_enable_q <= 0; done_previous_q <= 0; abort_request_o <= 0;
      rejection_q <= 0; accepted_q <= 0; completed_q <= 0; rejected_q <= 0;
      for (int i = 0; i < 10; i++) staging_q[i] <= 0;
    end else begin
      rvalid_o <= req_i; rdata_o <= read_data; err_o <= req_i && access_fault != 0;
      done_previous_q <= done_valid_i;
      if (done_valid_i && !done_previous_q) completed_q <= completed_q + 1;
      if (cmd_valid_o) accepted_q <= accepted_q + 1;
      if (req_i) begin
        if (access_fault != 0) begin
          rejection_q <= access_fault; rejected_q <= rejected_q + 1;
        end else if (we_i) begin
          if (staging_access) staging_q[staging_index] <= merge_bytes(staging_q[staging_index], wdata_i, be_i);
          else if (command_access) begin
            if (wdata_i == 4) abort_request_o <= 1;
            if (wdata_i == 8) rejection_q <= 0;
          end else if (addr_i[9:2] == 8'h11) irq_enable_q <= irq_new[0];
        end
      end
    end
  end
endmodule
