// Real M3 operators plus the M5 autonomous transfer/control path.
// MMIO indices: 0 GEMM, 1 SFPU, 2 transfer. No external packet path.
module pa_m5_accelerator_system (
  input logic clk_i,
  input logic rst_ni,
  input logic abort_i,
  output logic cancel_o,
  input logic req_i [3],
  input logic we_i [3],
  input logic [3:0] be_i [3],
  input logic [31:0] addr_i [3],
  input logic [31:0] wdata_i [3],
  output logic rvalid_o [3],
  output logic [31:0] rdata_o [3],
  output logic err_o [3],
  output logic irq_o,
  output logic busy_o,
  output logic stopped_o,
  output logic mem_req_valid_o,
  input logic mem_req_ready_i,
  output logic [31:0] mem_req_addr_o,
  output logic [8:0] mem_req_words_o,
  output logic mem_req_write_o,
  output logic mem_in_valid_o,
  input logic mem_in_ready_i,
  output logic [31:0] mem_in_data_o,
  output logic [3:0] mem_in_strb_o,
  input logic mem_out_valid_i,
  output logic mem_out_ready_o,
  input logic [31:0] mem_out_data_i,
  input logic mem_out_last_i,
  input logic mem_done_valid_i,
  output logic mem_done_ready_o,
  input logic [3:0] mem_done_fault_i
);
  logic cancel_q, fault_abort, control_abort, engine_rst_n;
  logic engine_req [2], engine_rvalid [2], engine_err [2];
  logic [31:0] engine_rdata [2];
  logic gemm_irq, sfpu_irq, transfer_irq, gemm_busy, route;
  logic cmd_valid, cmd_ready, done_valid, done_ready;
  logic [31:0] src_addr [3], src_words [3];
  logic [31:0] dst_addr, dst_words, cmd_tag, deadline, tag, sent, received;
  logic [7:0] fault;
  logic [31:0] tx_data, rx_data, gemm_data, sfpu_data;
  logic [3:0] tx_keep, rx_keep, gemm_keep, sfpu_keep;
  logic tx_valid, tx_ready, tx_last, rx_valid, rx_ready, rx_last;
  logic gemm_ready, sfpu_ready, gemm_valid, sfpu_valid, gemm_last, sfpu_last;
  assign cancel_o = abort_i || cancel_q || fault_abort || control_abort;
  assign engine_rst_n = rst_ni && !cancel_o;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) cancel_q <= 0;
    else if (cancel_o) cancel_q <= 1;
  end
  assign irq_o = gemm_irq || sfpu_irq || transfer_irq;
  for (genvar i = 0; i < 2; i++) begin : g_response
    pa_m5_mmio_cancel u_response (
      .clk_i, .rst_ni, .cancel_i(cancel_o), .req_i(req_i[i]), .engine_req_o(engine_req[i]),
      .engine_rvalid_i(engine_rvalid[i]), .engine_rdata_i(engine_rdata[i]),
      .engine_err_i(engine_err[i]), .rvalid_o(rvalid_o[i]), .rdata_o(rdata_o[i]), .err_o(err_o[i])
    );
  end
  pa_gemm #(.EnableWide(1'b1)) u_gemm (
    .clk_i, .rst_ni(engine_rst_n), .req_i(engine_req[0]), .we_i(we_i[0]), .be_i(be_i[0]),
    .addr_i(addr_i[0]), .wdata_i(wdata_i[0]), .rvalid_o(engine_rvalid[0]),
    .rdata_o(engine_rdata[0]), .err_o(engine_err[0]),
    .s_axis_data_i(tx_data), .s_axis_keep_i(tx_keep), .s_axis_last_i(tx_last),
    .s_axis_valid_i(tx_valid && !route && !cancel_o), .s_axis_ready_o(gemm_ready),
    .m_axis_data_o(gemm_data), .m_axis_keep_o(gemm_keep), .m_axis_last_o(gemm_last),
    .m_axis_valid_o(gemm_valid), .m_axis_ready_i(rx_ready && !route && !cancel_o),
    .irq_o(gemm_irq), .busy_o(gemm_busy)
  );
  pa_sfpu u_sfpu (
    .clk_i, .rst_ni(engine_rst_n), .req_i(engine_req[1]), .we_i(we_i[1]), .be_i(be_i[1]),
    .addr_i(addr_i[1]), .wdata_i(wdata_i[1]), .rvalid_o(engine_rvalid[1]),
    .rdata_o(engine_rdata[1]), .err_o(engine_err[1]),
    .s_axis_data_i(tx_data), .s_axis_keep_i(tx_keep), .s_axis_last_i(tx_last),
    .s_axis_valid_i(tx_valid && route && !cancel_o), .s_axis_ready_o(sfpu_ready),
    .m_axis_data_o(sfpu_data), .m_axis_keep_o(sfpu_keep), .m_axis_last_o(sfpu_last),
    .m_axis_valid_o(sfpu_valid), .m_axis_ready_i(rx_ready && route && !cancel_o),
    .gemm_busy_i(gemm_busy || busy_o), .stream_route_o(route), .busy_o(), .irq_o(sfpu_irq)
  );
  assign tx_ready = !cancel_o && (route ? sfpu_ready : gemm_ready);
  assign rx_data = route ? sfpu_data : gemm_data;
  assign rx_keep = route ? sfpu_keep : gemm_keep;
  assign rx_last = route ? sfpu_last : gemm_last;
  assign rx_valid = !cancel_o && (route ? sfpu_valid : gemm_valid);
  pa_m5_transfer_control u_control (
    .clk_i, .rst_ni, .abort_i(cancel_o), .req_i(req_i[2]), .we_i(we_i[2]),
    .be_i(be_i[2]), .addr_i(addr_i[2]), .wdata_i(wdata_i[2]),
    .rvalid_o(rvalid_o[2]), .rdata_o(rdata_o[2]), .err_o(err_o[2]),
    .irq_o(transfer_irq), .abort_request_o(control_abort),
    .cmd_valid_o(cmd_valid), .cmd_ready_i(cmd_ready), .cmd_src_addr_o(src_addr),
    .cmd_src_words_o(src_words), .cmd_dst_addr_o(dst_addr), .cmd_dst_words_o(dst_words),
    .cmd_tag_o(cmd_tag), .cmd_deadline_o(deadline), .busy_i(busy_o), .stopped_i(stopped_o),
    .fault_abort_i(fault_abort), .done_valid_i(done_valid), .done_ready_o(done_ready),
    .tag_i(tag), .fault_i(fault), .sent_words_i(sent), .received_words_i(received)
  );
  pa_m5_stream_transfer u_transfer (
    .clk_i, .rst_ni, .abort_i(cancel_o), .fault_abort_o(fault_abort), .busy_o, .stopped_o,
    .cmd_valid_i(cmd_valid), .cmd_ready_o(cmd_ready), .cmd_src_addr_i(src_addr),
    .cmd_src_words_i(src_words), .cmd_dst_addr_i(dst_addr), .cmd_dst_words_i(dst_words),
    .cmd_tag_i(cmd_tag), .cmd_deadline_i(deadline), .done_valid_o(done_valid),
    .done_ready_i(done_ready), .tag_o(tag), .fault_o(fault), .sent_words_o(sent),
    .received_words_o(received), .tx_data_o(tx_data), .tx_keep_o(tx_keep),
    .tx_last_o(tx_last), .tx_valid_o(tx_valid), .tx_ready_i(tx_ready),
    .rx_data_i(rx_data), .rx_keep_i(rx_keep), .rx_last_i(rx_last),
    .rx_valid_i(rx_valid), .rx_ready_o(rx_ready),
    .mem_req_valid_o, .mem_req_ready_i, .mem_req_addr_o, .mem_req_words_o, .mem_req_write_o,
    .mem_in_valid_o, .mem_in_ready_i, .mem_in_data_o, .mem_in_strb_o,
    .mem_out_valid_i, .mem_out_ready_o, .mem_out_data_i, .mem_out_last_i,
    .mem_done_valid_i, .mem_done_ready_o, .mem_done_fault_i
  );
endmodule
