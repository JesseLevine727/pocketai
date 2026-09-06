// OBI one-word adapter to a translated-memory arbiter client.
module pa_m5_obi_ddr (
  input logic clk_i,
  input logic rst_ni,
  input logic req_i,
  output logic gnt_o,
  input logic [31:0] addr_i,
  input logic we_i,
  input logic [3:0] be_i,
  input logic [31:0] wdata_i,
  output logic rvalid_o,
  output logic [31:0] rdata_o,
  output logic err_o,
  output logic busy_o,
  output logic cmd_valid_o,
  input logic cmd_ready_i,
  output logic [31:0] cmd_addr_o,
  output logic [8:0] cmd_words_o,
  output logic cmd_write_o,
  output logic in_valid_o,
  input logic in_ready_i,
  output logic [31:0] in_data_o,
  output logic [3:0] in_strb_o,
  input logic out_valid_i,
  output logic out_ready_o,
  input logic [31:0] out_data_i,
  input logic out_last_i,
  input logic done_valid_i,
  output logic done_ready_o,
  input logic [3:0] done_fault_i
);
  logic active_q, write_q, sent_q, received_q, bad_read_q;
  logic [31:0] write_data_q, read_data_q;
  logic [3:0] strb_q;
  // Low address bits select byte lanes in OBI; translation addresses a word.
  logic unused_addr_low;
  assign unused_addr_low = ^addr_i[1:0];
  assign cmd_valid_o = req_i && !active_q;
  assign cmd_addr_o = {addr_i[31:2], 2'b00};
  assign cmd_words_o = 1;
  assign cmd_write_o = we_i;
  assign gnt_o = cmd_valid_o && cmd_ready_i;
  assign busy_o = active_q;
  assign in_valid_o = active_q && write_q && !sent_q;
  assign in_data_o = write_data_q;
  assign in_strb_o = strb_q;
  assign out_ready_o = active_q;
  assign done_ready_o = active_q;
  assign rvalid_o = active_q && done_valid_i;
  assign rdata_o = read_data_q;
  assign err_o = done_fault_i != 0 || bad_read_q ||
                 (!write_q && !received_q) || (write_q && !sent_q);
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      active_q <= 0; write_q <= 0; sent_q <= 0; received_q <= 0; bad_read_q <= 0;
      write_data_q <= 0; read_data_q <= 0; strb_q <= 0;
    end else begin
      if (gnt_o) begin
        active_q <= 1; write_q <= we_i; write_data_q <= wdata_i; strb_q <= be_i;
        sent_q <= 0; received_q <= 0; bad_read_q <= 0; read_data_q <= 0;
      end
      if (in_valid_o && in_ready_i) sent_q <= 1;
      if (out_valid_i && active_q) begin
        read_data_q <= out_data_i;
        received_q <= 1;
        if (write_q || received_q || !out_last_i) bad_read_q <= 1;
      end
      if (rvalid_o) active_q <= 0;
    end
  end
endmodule
