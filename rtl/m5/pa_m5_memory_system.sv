// Four independent Ibex ports + one autonomous bulk client, all DDR translated.
// stop/reset lifetime is documented in M5_ARCHITECTURE.md.
module pa_m5_memory_system (
  input logic clk_i,
  input logic rst_ni,
  input logic stop_i,
  input logic abort_i,
  input logic cfg_enable_i,
  input logic [31:0] cfg_table_base_i,
  input logic [31:0] cfg_arena_bytes_i,
  input logic cfg_flush_i,
  output logic flush_ready_o,
  output logic busy_o,
  output logic quiesced_o,
  output logic poisoned_o,
  input logic core_req_i [4],
  output logic core_gnt_o [4],
  input logic [31:0] core_addr_i [4],
  input logic core_we_i [4],
  input logic [3:0] core_be_i [4],
  input logic [31:0] core_wdata_i [4],
  output logic core_rvalid_o [4],
  output logic [31:0] core_rdata_o [4],
  output logic core_err_o [4],
  output logic local_req_o [4],
  input logic local_gnt_i [4],
  output logic [31:0] local_addr_o [4],
  output logic local_we_o [4],
  output logic [3:0] local_be_o [4],
  output logic [31:0] local_wdata_o [4],
  input logic local_rvalid_i [4],
  input logic [31:0] local_rdata_i [4],
  input logic local_err_i [4],
  input logic bulk_busy_i,
  input logic bulk_req_valid_i,
  output logic bulk_req_ready_o,
  input logic [31:0] bulk_req_addr_i,
  input logic [8:0] bulk_req_words_i,
  input logic bulk_req_write_i,
  input logic bulk_in_valid_i,
  output logic bulk_in_ready_o,
  input logic [31:0] bulk_in_data_i,
  input logic [3:0] bulk_in_strb_i,
  output logic bulk_out_valid_o,
  input logic bulk_out_ready_i,
  output logic [31:0] bulk_out_data_o,
  output logic bulk_out_last_o,
  output logic bulk_done_valid_o,
  input logic bulk_done_ready_i,
  output logic [3:0] bulk_done_fault_o,
  output logic [31:0] m_awaddr_o,
  output logic [7:0] m_awlen_o,
  output logic [2:0] m_awsize_o,
  output logic [1:0] m_awburst_o,
  output logic [3:0] m_awcache_o,
  output logic [2:0] m_awprot_o,
  output logic m_awid_o,
  output logic m_awvalid_o,
  input logic m_awready_i,
  output logic [31:0] m_wdata_o,
  output logic [3:0] m_wstrb_o,
  output logic m_wlast_o,
  output logic m_wvalid_o,
  input logic m_wready_i,
  input logic [1:0] m_bresp_i,
  input logic m_bid_i,
  input logic m_bvalid_i,
  output logic m_bready_o,
  output logic [31:0] m_araddr_o,
  output logic [7:0] m_arlen_o,
  output logic [2:0] m_arsize_o,
  output logic [1:0] m_arburst_o,
  output logic [3:0] m_arcache_o,
  output logic [2:0] m_arprot_o,
  output logic m_arid_o,
  output logic m_arvalid_o,
  input logic m_arready_i,
  input logic [31:0] m_rdata_i,
  input logic [1:0] m_rresp_i,
  input logic m_rid_i,
  input logic m_rlast_i,
  input logic m_rvalid_i,
  output logic m_rready_o
);
  logic target_req [4][2], target_gnt [4][2], target_rvalid [4][2], target_err [4][2];
  logic [31:0] target_rdata [4][2];
  logic router_busy [4], adapter_busy [4], cores_busy;
  logic req_valid [5], req_ready [5], req_write [5];
  logic [31:0] req_addr [5];
  logic [8:0] req_words [5];
  logic in_valid [5], in_ready [5], out_valid [5], out_ready [5];
  logic [31:0] in_data [5], out_data [5];
  logic [3:0] in_strb [5], done_fault [5];
  logic out_last [5], done_valid [5], done_ready [5];
  logic arb_busy, arb_quiet;
  logic mem_abort, mem_req, mem_ready, mem_write, mem_in_valid, mem_in_ready;
  logic [31:0] mem_addr, mem_in_data, mem_out_data;
  logic [8:0] mem_words;
  logic [3:0] mem_in_strb, mem_fault;
  logic mem_out_valid, mem_out_ready, mem_out_last, mem_done, mem_done_ready;
  logic mem_busy, mem_quiet, mem_flush_ready;
  always_comb begin
    cores_busy = 0;
    for (int h = 0; h < 4; h++) cores_busy |= router_busy[h] || adapter_busy[h];
  end
  assign busy_o = cores_busy || arb_busy || bulk_busy_i;
  assign quiesced_o = abort_i && !cores_busy && arb_quiet && !bulk_busy_i;
  assign flush_ready_o = !busy_o && mem_flush_ready;

  for (genvar h = 0; h < 4; h++) begin : g_core
    pa_m5_obi_router u_router (
      .clk_i, .rst_ni, .stop_i(stop_i || abort_i),
      .host_req_i(core_req_i[h]), .host_gnt_o(core_gnt_o[h]), .host_addr_i(core_addr_i[h]),
      .host_we_i(core_we_i[h]), .host_be_i(core_be_i[h]), .host_wdata_i(core_wdata_i[h]),
      .host_rvalid_o(core_rvalid_o[h]), .host_rdata_o(core_rdata_o[h]), .host_err_o(core_err_o[h]),
      .busy_o(router_busy[h]), .target_req_o(target_req[h]), .target_gnt_i(target_gnt[h]),
      .target_addr_o(local_addr_o[h]), .target_we_o(local_we_o[h]),
      .target_be_o(local_be_o[h]), .target_wdata_o(local_wdata_o[h]),
      .target_rvalid_i(target_rvalid[h]), .target_rdata_i(target_rdata[h]),
      .target_err_i(target_err[h])
    );
    assign local_req_o[h] = target_req[h][0];
    assign target_gnt[h][0] = local_gnt_i[h];
    assign target_rvalid[h][0] = local_rvalid_i[h];
    assign target_rdata[h][0] = local_rdata_i[h];
    assign target_err[h][0] = local_err_i[h];
    pa_m5_obi_ddr u_adapter (
      .clk_i, .rst_ni, .req_i(target_req[h][1]), .gnt_o(target_gnt[h][1]),
      .addr_i(local_addr_o[h]), .we_i(local_we_o[h]), .be_i(local_be_o[h]), .wdata_i(local_wdata_o[h]),
      .rvalid_o(target_rvalid[h][1]), .rdata_o(target_rdata[h][1]), .err_o(target_err[h][1]),
      .busy_o(adapter_busy[h]), .cmd_valid_o(req_valid[h]), .cmd_ready_i(req_ready[h]),
      .cmd_addr_o(req_addr[h]), .cmd_words_o(req_words[h]), .cmd_write_o(req_write[h]),
      .in_valid_o(in_valid[h]), .in_ready_i(in_ready[h]), .in_data_o(in_data[h]), .in_strb_o(in_strb[h]),
      .out_valid_i(out_valid[h]), .out_ready_o(out_ready[h]), .out_data_i(out_data[h]),
      .out_last_i(out_last[h]), .done_valid_i(done_valid[h]), .done_ready_o(done_ready[h]),
      .done_fault_i(done_fault[h])
    );
  end
  assign req_valid[4] = bulk_req_valid_i;
  assign bulk_req_ready_o = req_ready[4];
  assign req_addr[4] = bulk_req_addr_i;
  assign req_words[4] = bulk_req_words_i;
  assign req_write[4] = bulk_req_write_i;
  assign in_valid[4] = bulk_in_valid_i;
  assign bulk_in_ready_o = in_ready[4];
  assign in_data[4] = bulk_in_data_i;
  assign in_strb[4] = bulk_in_strb_i;
  assign bulk_out_valid_o = out_valid[4];
  assign out_ready[4] = bulk_out_ready_i;
  assign bulk_out_data_o = out_data[4];
  assign bulk_out_last_o = out_last[4];
  assign bulk_done_valid_o = done_valid[4];
  assign done_ready[4] = bulk_done_ready_i;
  assign bulk_done_fault_o = done_fault[4];

  pa_m5_memory_arbiter u_arb (
    .clk_i, .rst_ni, .abort_i, .pause_i(cfg_flush_i),
    .req_valid_i(req_valid), .req_ready_o(req_ready), .req_addr_i(req_addr),
    .req_words_i(req_words), .req_write_i(req_write), .in_valid_i(in_valid), .in_ready_o(in_ready),
    .in_data_i(in_data), .in_strb_i(in_strb), .out_valid_o(out_valid), .out_ready_i(out_ready),
    .out_data_o(out_data), .out_last_o(out_last), .done_valid_o(done_valid),
    .done_ready_i(done_ready), .done_fault_o(done_fault), .busy_o(arb_busy), .quiesced_o(arb_quiet),
    .m_abort_o(mem_abort), .m_req_valid_o(mem_req), .m_req_ready_i(mem_ready),
    .m_req_addr_o(mem_addr), .m_req_words_o(mem_words), .m_req_write_o(mem_write),
    .m_in_valid_o(mem_in_valid), .m_in_ready_i(mem_in_ready), .m_in_data_o(mem_in_data),
    .m_in_strb_o(mem_in_strb), .m_out_valid_i(mem_out_valid), .m_out_ready_o(mem_out_ready),
    .m_out_data_i(mem_out_data), .m_out_last_i(mem_out_last), .m_done_valid_i(mem_done),
    .m_done_ready_o(mem_done_ready), .m_done_fault_i(mem_fault), .m_busy_i(mem_busy),
    .m_quiesced_i(mem_quiet)
  );
  pa_m5_memory_bridge u_bridge (
    .clk_i, .rst_ni, .cfg_enable_i, .cfg_table_base_i, .cfg_arena_bytes_i,
    .cfg_flush_i(cfg_flush_i && !arb_busy), .flush_ready_o(mem_flush_ready),
    .abort_i(mem_abort), .req_valid_i(mem_req), .req_ready_o(mem_ready),
    .req_addr_i(mem_addr), .req_words_i(mem_words), .req_write_i(mem_write),
    .in_valid_i(mem_in_valid), .in_ready_o(mem_in_ready), .in_data_i(mem_in_data), .in_strb_i(mem_in_strb),
    .out_valid_o(mem_out_valid), .out_ready_i(mem_out_ready), .out_data_o(mem_out_data),
    .out_last_o(mem_out_last), .done_valid_o(mem_done), .done_ready_i(mem_done_ready),
    .done_fault_o(mem_fault), .busy_o(mem_busy), .quiesced_o(mem_quiet), .poisoned_o,
    .m_awaddr_o, .m_awlen_o, .m_awsize_o, .m_awburst_o, .m_awcache_o, .m_awprot_o,
    .m_awid_o, .m_awvalid_o, .m_awready_i, .m_wdata_o, .m_wstrb_o, .m_wlast_o,
    .m_wvalid_o, .m_wready_i, .m_bresp_i, .m_bid_i, .m_bvalid_i, .m_bready_o,
    .m_araddr_o, .m_arlen_o, .m_arsize_o, .m_arburst_o, .m_arcache_o, .m_arprot_o,
    .m_arid_o, .m_arvalid_o, .m_arready_i, .m_rdata_i, .m_rresp_i, .m_rid_i,
    .m_rlast_i, .m_rvalid_i, .m_rready_o
  );
endmodule
