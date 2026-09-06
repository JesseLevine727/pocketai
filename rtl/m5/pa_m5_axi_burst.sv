// Private buffered AXI4 master. Never expose this physical interface to firmware.
// Reset is NOT cancellation of a live AXI transaction; see M5_ARCHITECTURE.md.
module pa_m5_axi_burst (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic abort_i,
  input  logic cmd_valid_i,
  output logic cmd_ready_o,
  input  logic [31:0] cmd_addr_i,
  input  logic [8:0] cmd_words_i,
  input  logic cmd_write_i,
  input  logic in_valid_i,
  output logic in_ready_o,
  input  logic [31:0] in_data_i,
  input  logic [3:0] in_strb_i,
  output logic out_valid_o,
  input  logic out_ready_i,
  output logic [31:0] out_data_o,
  output logic out_last_o,
  output logic done_valid_o,
  input  logic done_ready_i,
  output logic [3:0] done_fault_o,
  output logic busy_o,
  output logic poisoned_o,

  output logic [31:0] m_awaddr_o,
  output logic [7:0] m_awlen_o,
  output logic [2:0] m_awsize_o,
  output logic [1:0] m_awburst_o,
  output logic [3:0] m_awcache_o,
  output logic [2:0] m_awprot_o,
  output logic m_awid_o,
  output logic m_awvalid_o,
  input  logic m_awready_i,
  output logic [31:0] m_wdata_o,
  output logic [3:0] m_wstrb_o,
  output logic m_wlast_o,
  output logic m_wvalid_o,
  input  logic m_wready_i,
  input  logic [1:0] m_bresp_i,
  input  logic m_bid_i,
  input  logic m_bvalid_i,
  output logic m_bready_o,
  output logic [31:0] m_araddr_o,
  output logic [7:0] m_arlen_o,
  output logic [2:0] m_arsize_o,
  output logic [1:0] m_arburst_o,
  output logic [3:0] m_arcache_o,
  output logic [2:0] m_arprot_o,
  output logic m_arid_o,
  output logic m_arvalid_o,
  input  logic m_arready_i,
  input  logic [31:0] m_rdata_i,
  input  logic [1:0] m_rresp_i,
  input  logic m_rid_i,
  input  logic m_rlast_i,
  input  logic m_rvalid_i,
  output logic m_rready_o
);
  typedef enum logic [3:0] {
    Idle, Validate, LoadWrite, WriteAddr, WriteData, WriteResp,
    ReadAddr, ReadData, ReadPrepare, ReadOut, Respond, Poisoned
  } state_e;
  state_e state_q;
  logic [31:0] addr_q;
  logic [8:0] words_q;
  logic write_q, aborted_q;
  logic [7:0] index_q;
  logic [3:0] fault_q;
  logic [35:0] buffer_q;
  logic [35:0] data_mem [256];
  logic mem_we, mem_re;
  logic [7:0] mem_waddr, mem_raddr;
  logic [35:0] mem_wdata;
  logic final_word, aborting, bad_command;
  logic [32:0] command_end;
  logic [12:0] page_end;

  assign final_word = {1'b0, index_q} == words_q - 9'd1;
  assign aborting = abort_i || aborted_q;
  assign command_end = {1'b0, addr_q} + {22'b0, words_q, 2'b0};
  assign page_end = {1'b0, addr_q[11:0]} + {2'b0, words_q, 2'b0};
  assign bad_command = words_q == 0 || words_q > 256 || addr_q[1:0] != 0 ||
                       page_end > 4096 || command_end > 33'h100000000;
  assign cmd_ready_o = state_q == Idle && !abort_i;
  assign in_ready_o = state_q == LoadWrite && !aborting;
  assign out_valid_o = state_q == ReadOut && !aborting;
  assign out_data_o = buffer_q[31:0];
  assign out_last_o = final_word;
  assign done_valid_o = state_q == Respond;
  assign done_fault_o = fault_q;
  assign busy_o = state_q != Idle;
  assign poisoned_o = state_q == Poisoned;

  assign m_awaddr_o = addr_q;
  assign m_awlen_o = 8'(words_q - 9'd1);
  assign m_awsize_o = 3'd2;
  assign m_awburst_o = 2'b01;
  assign m_awcache_o = 0;
  assign m_awprot_o = 0;
  assign m_awid_o = 0;
  assign m_awvalid_o = state_q == WriteAddr;
  assign m_wdata_o = buffer_q[31:0];
  assign m_wstrb_o = buffer_q[35:32];
  assign m_wlast_o = final_word;
  assign m_wvalid_o = state_q == WriteData;
  assign m_bready_o = state_q == WriteResp || state_q == Poisoned;
  assign m_araddr_o = addr_q;
  assign m_arlen_o = 8'(words_q - 9'd1);
  assign m_arsize_o = 3'd2;
  assign m_arburst_o = 2'b01;
  assign m_arcache_o = 0;
  assign m_arprot_o = 0;
  assign m_arid_o = 0;
  assign m_arvalid_o = state_q == ReadAddr;
  assign m_rready_o = state_q == ReadData || state_q == Poisoned;

  // One synchronous write and one synchronous read port; no reset of the
  // storage array. Only fully populated words can become AXI/output data.
  always_comb begin
    mem_we = 0;
    mem_waddr = index_q;
    mem_wdata = {in_strb_i, in_data_i};
    if (in_valid_i && in_ready_o) mem_we = 1;
    else if (state_q == ReadData && m_rvalid_i) begin
      mem_we = 1;
      mem_wdata = {4'hf, m_rdata_i};
    end
    mem_re = 0;
    mem_raddr = 0;
    if ((state_q == WriteAddr && m_awready_i) || state_q == ReadPrepare)
      mem_re = 1;
    else if ((state_q == WriteData && m_wready_i && !final_word) ||
             (state_q == ReadOut && out_ready_i && !aborting && !final_word)) begin
      mem_re = 1;
      mem_raddr = index_q + 8'd1;
    end
  end
  always_ff @(posedge clk_i) begin
    if (mem_we) data_mem[mem_waddr] <= mem_wdata;
    if (mem_re) buffer_q <= data_mem[mem_raddr];
  end

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle;
      addr_q <= 0;
      words_q <= 0;
      write_q <= 0;
      aborted_q <= 0;
      index_q <= 0;
      fault_q <= 0;
    end else begin
      if (state_q != Idle && abort_i) aborted_q <= 1;
      case (state_q)
        Idle: if (cmd_valid_i && !abort_i) begin
          addr_q <= cmd_addr_i;
          words_q <= cmd_words_i;
          write_q <= cmd_write_i;
          aborted_q <= 0;
          index_q <= 0;
          fault_q <= 0;
          state_q <= Validate;
        end
        Validate: begin
          if (aborting || bad_command) begin
            fault_q <= aborting ? 4'd11 : 4'd10;
            state_q <= Respond;
          end else state_q <= write_q ? LoadWrite : ReadAddr;
        end
        LoadWrite: begin
          if (aborting) begin
            fault_q <= 11;
            state_q <= Respond;
          end else if (in_valid_i) begin
            if (final_word) begin
              index_q <= 0;
              state_q <= WriteAddr;
            end else index_q <= index_q + 8'd1;
          end
        end
        WriteAddr: if (m_awready_i) state_q <= WriteData;
        WriteData: if (m_wready_i) begin
          if (final_word) state_q <= WriteResp;
          else index_q <= index_q + 8'd1;
        end
        WriteResp: if (m_bvalid_i) begin
          if (m_bid_i != 0) begin
            fault_q <= 13;
            state_q <= Poisoned;
          end else begin
            fault_q <= aborting ? 4'd11 : (m_bresp_i != 0 ? 4'd12 : 4'd0);
            state_q <= Respond;
          end
        end
        ReadAddr: if (m_arready_i) state_q <= ReadData;
        ReadData: if (m_rvalid_i) begin
          if (m_rid_i != 0 || m_rlast_i != final_word) begin
            fault_q <= 13;
            state_q <= Poisoned;
          end else begin
            if (m_rresp_i != 0) fault_q <= 12;
            if (final_word) begin
              index_q <= 0;
              if (aborting || fault_q != 0 || m_rresp_i != 0) begin
                if (aborting) fault_q <= 11;
                state_q <= Respond;
              end else state_q <= ReadPrepare;
            end else index_q <= index_q + 8'd1;
          end
        end
        ReadPrepare: begin
          if (aborting) begin
            fault_q <= 11;
            state_q <= Respond;
          end else state_q <= ReadOut;
        end
        ReadOut: begin
          if (aborting) begin
            fault_q <= 11;
            state_q <= Respond;
          end else if (out_ready_i) begin
            if (final_word) state_q <= Respond;
            else index_q <= index_q + 8'd1;
          end
        end
        Respond: if (done_ready_i || abort_i) state_q <= Idle;
        Poisoned: state_q <= Poisoned;
        default: begin
          fault_q <= 13;
          state_q <= Poisoned;
        end
      endcase
    end
  end
endmodule
