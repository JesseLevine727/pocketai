// Virtual-only M5 memory interface. All physical data access follows translation.
module pa_m5_memory_bridge (
  input logic clk_i,
  input logic rst_ni,
  input logic cfg_enable_i,
  input logic [31:0] cfg_table_base_i,
  input logic [31:0] cfg_arena_bytes_i,
  input logic cfg_flush_i,
  output logic flush_ready_o,
  input logic abort_i,
  input logic req_valid_i,
  output logic req_ready_o,
  input logic [31:0] req_addr_i,
  input logic [8:0] req_words_i,
  input logic req_write_i,
  input logic in_valid_i,
  output logic in_ready_o,
  input logic [31:0] in_data_i,
  input logic [3:0] in_strb_i,
  output logic out_valid_o,
  input logic out_ready_i,
  output logic [31:0] out_data_o,
  output logic out_last_o,
  output logic done_valid_o,
  input logic done_ready_i,
  output logic [3:0] done_fault_o,
  output logic busy_o,
  output logic quiesced_o,
  output logic poisoned_o,

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
  typedef enum logic [2:0] {
    Idle, StartTranslate, WaitTranslate, ReadPte, StartData, Data, Respond
  } state_e;
  state_e state_q;
  logic [31:0] addr_q, physical_q, pte_q;
  logic [8:0] words_q;
  logic write_q, aborted_q, aborting;
  logic [3:0] fault_q;
  logic tr_ready, tr_valid, tr_busy, tr_flush_ready;
  logic [31:0] tr_addr, table_addr;
  logic [3:0] tr_fault;
  logic table_valid, table_ready;
  logic bus_cmd_valid, bus_cmd_ready, bus_cmd_write, bus_abort;
  logic [31:0] bus_cmd_addr, bus_out_data;
  logic [8:0] bus_cmd_words;
  logic bus_in_ready, bus_out_valid, bus_out_ready, bus_out_last;
  logic bus_done_valid, bus_done_ready, bus_busy;
  logic [3:0] bus_fault;

  assign aborting = abort_i || aborted_q;
  assign busy_o = state_q != Idle || tr_busy || bus_busy;
  assign quiesced_o = abort_i && !busy_o;
  assign req_ready_o = !busy_o && !abort_i && !cfg_flush_i;
  assign flush_ready_o = !busy_o && tr_flush_ready;
  assign in_ready_o = state_q == Data && !aborting && bus_in_ready;
  assign out_valid_o = state_q == Data && !aborting && bus_out_valid;
  assign out_data_o = bus_out_data;
  assign out_last_o = bus_out_last;
  assign done_valid_o = state_q == Respond;
  assign done_fault_o = fault_q;

  // Do not abort a PTE transaction: it must return its response to translation.
  // Client data transactions have independently buffered drain capability.
  assign bus_abort = state_q == Data && aborting;
  assign table_ready = state_q == WaitTranslate && bus_cmd_ready;
  assign bus_cmd_valid = (state_q == WaitTranslate && table_valid) ||
                         (state_q == StartData && !aborting);
  assign bus_cmd_addr = state_q == WaitTranslate ? table_addr : physical_q;
  assign bus_cmd_words = state_q == WaitTranslate ? 9'd1 : words_q;
  assign bus_cmd_write = state_q == StartData && write_q;
  assign bus_out_ready = state_q == ReadPte ||
                         (state_q == Data && out_ready_i && !aborting);
  assign bus_done_ready = state_q == ReadPte || state_q == Data;

  pa_m5_page_translate u_translate (
    .clk_i, .rst_ni, .cfg_enable_i, .cfg_table_base_i, .cfg_arena_bytes_i,
    .cfg_flush_i(cfg_flush_i && !busy_o), .flush_ready_o(tr_flush_ready),
    .req_valid_i(state_q == StartTranslate && !aborting), .req_ready_o(tr_ready),
    .req_addr_i(addr_q), .req_words_i(words_q), .req_write_i(write_q),
    .rsp_valid_o(tr_valid), .rsp_ready_i(state_q == WaitTranslate),
    .rsp_addr_o(tr_addr), .rsp_fault_o(tr_fault), .busy_o(tr_busy),
    .table_req_valid_o(table_valid), .table_req_ready_i(table_ready),
    .table_req_addr_o(table_addr),
    .table_rsp_valid_i(state_q == ReadPte && bus_done_valid),
    .table_rsp_data_i(pte_q), .table_rsp_error_i(bus_fault != 0)
  );
  pa_m5_axi_burst u_axi (
    .clk_i, .rst_ni, .abort_i(bus_abort),
    .cmd_valid_i(bus_cmd_valid), .cmd_ready_o(bus_cmd_ready),
    .cmd_addr_i(bus_cmd_addr), .cmd_words_i(bus_cmd_words), .cmd_write_i(bus_cmd_write),
    .in_valid_i(state_q == Data && in_valid_i && !aborting), .in_ready_o(bus_in_ready),
    .in_data_i, .in_strb_i, .out_valid_o(bus_out_valid), .out_ready_i(bus_out_ready),
    .out_data_o(bus_out_data), .out_last_o(bus_out_last),
    .done_valid_o(bus_done_valid), .done_ready_i(bus_done_ready),
    .done_fault_o(bus_fault), .busy_o(bus_busy), .poisoned_o,
    .m_awaddr_o, .m_awlen_o, .m_awsize_o, .m_awburst_o, .m_awcache_o, .m_awprot_o,
    .m_awid_o, .m_awvalid_o, .m_awready_i, .m_wdata_o, .m_wstrb_o, .m_wlast_o,
    .m_wvalid_o, .m_wready_i, .m_bresp_i, .m_bid_i, .m_bvalid_i, .m_bready_o,
    .m_araddr_o, .m_arlen_o, .m_arsize_o, .m_arburst_o, .m_arcache_o, .m_arprot_o,
    .m_arid_o, .m_arvalid_o, .m_arready_i, .m_rdata_i, .m_rresp_i, .m_rid_i,
    .m_rlast_i, .m_rvalid_i, .m_rready_o
  );

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle;
      addr_q <= 0;
      physical_q <= 0;
      pte_q <= 0;
      words_q <= 0;
      write_q <= 0;
      aborted_q <= 0;
      fault_q <= 0;
    end else begin
      if (state_q != Idle && abort_i) aborted_q <= 1;
      case (state_q)
        Idle: if (req_valid_i && req_ready_o) begin
          addr_q <= req_addr_i;
          words_q <= req_words_i;
          write_q <= req_write_i;
          aborted_q <= 0;
          fault_q <= 0;
          state_q <= StartTranslate;
        end
        StartTranslate: begin
          if (aborting) begin
            fault_q <= 11;
            state_q <= Respond;
          end else if (tr_ready) state_q <= WaitTranslate;
        end
        WaitTranslate: begin
          if (table_valid && table_ready) state_q <= ReadPte;
          else if (tr_valid) begin
            if (aborting || tr_fault != 0) begin
              fault_q <= aborting ? 4'd11 : tr_fault;
              state_q <= Respond;
            end else begin
              physical_q <= tr_addr;
              state_q <= StartData;
            end
          end
        end
        ReadPte: begin
          if (bus_out_valid) pte_q <= bus_out_data;
          if (bus_done_valid) state_q <= WaitTranslate;
        end
        StartData: begin
          if (aborting) begin
            fault_q <= 11;
            state_q <= Respond;
          end else if (bus_cmd_ready) state_q <= Data;
        end
        Data: if (bus_done_valid) begin
          fault_q <= aborting ? 4'd11 : bus_fault;
          state_q <= Respond;
        end
        Respond: if (done_ready_i || abort_i) state_q <= Idle;
        default: state_q <= Idle;
      endcase
    end
  end
endmodule
