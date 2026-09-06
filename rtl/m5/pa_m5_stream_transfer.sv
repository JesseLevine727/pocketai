// One autonomous packet: up to three DDR source segments, one DDR destination.
// Cancellation requires the global memory abort and accelerator-stream reset;
// see docs/M5_TRANSFER_ABI.md. Never reset this client to abandon issued memory.
module pa_m5_stream_transfer (
  input logic clk_i,
  input logic rst_ni,
  input logic abort_i,
  output logic fault_abort_o,
  output logic busy_o,
  output logic stopped_o,
  input logic cmd_valid_i,
  output logic cmd_ready_o,
  input logic [31:0] cmd_src_addr_i [3],
  input logic [31:0] cmd_src_words_i [3],
  input logic [31:0] cmd_dst_addr_i,
  input logic [31:0] cmd_dst_words_i,
  input logic [31:0] cmd_tag_i,
  input logic [31:0] cmd_deadline_i,
  output logic done_valid_o,
  input logic done_ready_i,
  output logic [31:0] tag_o,
  output logic [7:0] fault_o,
  output logic [31:0] sent_words_o,
  output logic [31:0] received_words_o,
  // Accelerator packet input (mover is the AXI Stream master).
  output logic [31:0] tx_data_o,
  output logic [3:0] tx_keep_o,
  output logic tx_last_o,
  output logic tx_valid_o,
  input logic tx_ready_i,
  // Accelerator packet output.
  input logic [31:0] rx_data_i,
  input logic [3:0] rx_keep_i,
  input logic rx_last_i,
  input logic rx_valid_i,
  output logic rx_ready_o,
  // One client of pa_m5_memory_arbiter; no physical-address bypass.
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
  typedef enum logic [3:0] {
    Idle, Validate, ReadPrepare, ReadIssue, ReadData, ReadFinish,
    WritePrepare, WriteIssue, WriteData, WriteFinish, Complete, Stopped
  } state_e;
  state_e state_q, state_d;
  logic [31:0] src_addr_q [3], src_words_q [3];
  logic [31:0] dst_addr_q, dst_words_q, deadline_q;
  logic [31:0] address_q, remaining_q, source_total_q;
  logic [1:0] source_q;
  logic [8:0] burst_q, beat_q;
  logic [32:0] source_sum;
  logic descriptor_valid, cancelled, fatal_event;
  logic [7:0] fault_d;
  logic read_beat, write_beat, memory_owned;

  function automatic logic range_valid(input logic [31:0] address, words);
    logic [32:0] end_address;
    end_address = {1'b0, address} + ({1'b0, words} << 2);
    return words >= 1 && words <= 65535 && address[1:0] == 0 &&
           address[31:28] == 4'h4 && end_address <= 33'h050000000;
  endfunction
  function automatic logic [8:0] burst_words(input logic [11:0] offset, input logic [31:0] words);
    logic [10:0] page_words;
    logic [31:0] count;
    page_words = 11'((13'd4096 - {1'b0, offset}) >> 2);
    count = words < 256 ? words : 32'd256;
    if (count > {21'b0, page_words}) count = {21'b0, page_words};
    return count[8:0];
  endfunction

  always_comb begin
    source_sum = 0;
    descriptor_valid = deadline_q != 0 && range_valid(dst_addr_q, dst_words_q) &&
                       src_words_q[0] != 0;
    for (int i = 0; i < 3; i++) begin
      source_sum += {1'b0, src_words_q[i]};
      if (src_words_q[i] == 0) begin
        if (src_addr_q[i] != 0) descriptor_valid = 0;
      end else if (!range_valid(src_addr_q[i], src_words_q[i])) descriptor_valid = 0;
    end
    if (source_sum > 65535 || (src_words_q[1] == 0 && src_words_q[2] != 0)) descriptor_valid = 0;
  end

  assign cancelled = abort_i || fault_abort_o;
  assign busy_o = state_q != Idle && state_q != Stopped;
  assign stopped_o = state_q == Stopped;
  assign cmd_ready_o = state_q == Idle && !cancelled;
  assign done_valid_o = state_q == Complete && !cancelled;
  assign mem_req_valid_o = state_q == ReadIssue || state_q == WriteIssue;
  assign mem_req_addr_o = address_q;
  assign mem_req_words_o = burst_q;
  assign mem_req_write_o = state_q == WriteIssue;
  assign tx_data_o = mem_out_data_i;
  assign tx_keep_o = 4'hf;
  assign tx_last_o = sent_words_o + 1 == source_total_q;
  assign tx_valid_o = state_q == ReadData && mem_out_valid_i && !cancelled;
  assign mem_out_ready_o = state_q == ReadData && (tx_ready_i || cancelled);
  assign rx_ready_o = state_q == WriteData && mem_in_ready_i && !cancelled;
  assign mem_in_valid_o = state_q == WriteData && rx_valid_i && !cancelled;
  assign mem_in_data_o = rx_data_i;
  assign mem_in_strb_o = 4'hf;
  assign mem_done_ready_o = state_q == ReadData || state_q == ReadFinish ||
                            state_q == WriteData || state_q == WriteFinish;
  assign read_beat = tx_valid_o && tx_ready_i;
  assign write_beat = rx_valid_i && rx_ready_o;
  assign memory_owned = mem_done_ready_o;

  always_comb begin
    state_d = state_q;
    fault_d = fault_o;
    fatal_event = 0;
    case (state_q)
      Idle: if (cmd_valid_i && cmd_ready_o) begin state_d = Validate; fault_d = 0; end
      Validate: begin
        if (!descriptor_valid) begin fault_d = 16; state_d = Complete; end
        else state_d = ReadPrepare;
      end
      ReadPrepare: state_d = ReadIssue;
      WritePrepare: state_d = WriteIssue;
      ReadIssue: if (mem_req_ready_i) state_d = ReadData;
      WriteIssue: if (mem_req_ready_i) state_d = WriteData;
      ReadData: begin
        if (read_beat) begin
          if (mem_out_last_i != (beat_q + 9'd1 == burst_q)) begin
            fault_d = 19; fatal_event = 1;
          end
          if (beat_q + 9'd1 == burst_q) state_d = ReadFinish;
        end
      end
      WriteData: begin
        if (write_beat) begin
          if (rx_keep_i != 4'hf || rx_last_i != (received_words_o + 1 == dst_words_q)) begin
            fault_d = 18; fatal_event = 1;
          end
          if (beat_q + 9'd1 == burst_q) state_d = WriteFinish;
        end
      end
      ReadFinish: if (mem_done_valid_i) begin
        if (remaining_q != {23'b0, burst_q}) state_d = ReadPrepare;
        else if (source_q < 2 && src_words_q[source_q + 2'd1] != 0) state_d = ReadPrepare;
        else state_d = WritePrepare;
      end
      WriteFinish: if (mem_done_valid_i)
        state_d = remaining_q == {23'b0, burst_q} ? Complete : WritePrepare;
      Complete: if (done_ready_i) state_d = Idle;
      Stopped: state_d = Stopped;
      default: begin fault_d = 19; fatal_event = 1; end
    endcase

    if (!cancelled && memory_owned && mem_done_valid_i) begin
      if (mem_done_fault_i != 0) begin
        fault_d = 8'd32 + {4'b0, mem_done_fault_i}; fatal_event = 1;
      end else if (state_q == ReadData || state_q == WriteData) begin
        fault_d = 19; fatal_event = 1; // Completion before the complete payload.
      end
    end
    if (!cancelled && state_q == ReadFinish && mem_out_valid_i) begin
      fault_d = 19; fatal_event = 1;
    end
    if (!cancelled && state_q != Idle && state_q != Complete && state_q != Stopped &&
        !(state_q == Validate && !descriptor_valid) && deadline_q == 1 && !fatal_event) begin
      fault_d = 20; fatal_event = 1;
    end
    if (cancelled || fatal_event) begin
      if (fault_d == 0) fault_d = 17;
      // Once offered, a request must still be accepted/retired by the arbiter.
      // Once owned, no amount of time substitutes for its actual completion.
      if (state_q == ReadIssue || state_q == WriteIssue)
        state_d = mem_req_ready_i ? (state_q == ReadIssue ? ReadData : WriteData) : state_q;
      else if (memory_owned) state_d = mem_done_valid_i ? Stopped : state_q;
      else state_d = Stopped;
    end
  end

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle; fault_o <= 0; fault_abort_o <= 0;
      tag_o <= 0; sent_words_o <= 0; received_words_o <= 0;
      dst_addr_q <= 0; dst_words_q <= 0; deadline_q <= 0;
      address_q <= 0; remaining_q <= 0; source_total_q <= 0;
      source_q <= 0; burst_q <= 0; beat_q <= 0;
      for (int i = 0; i < 3; i++) begin src_addr_q[i] <= 0; src_words_q[i] <= 0; end
    end else begin
      state_q <= state_d; fault_o <= fault_d;
      if (fatal_event) fault_abort_o <= 1;
      if (cmd_valid_i && cmd_ready_o) begin
        src_addr_q <= cmd_src_addr_i; src_words_q <= cmd_src_words_i;
        dst_addr_q <= cmd_dst_addr_i; dst_words_q <= cmd_dst_words_i;
        tag_o <= cmd_tag_i; deadline_q <= cmd_deadline_i;
        sent_words_o <= 0; received_words_o <= 0; source_q <= 0;
      end else if (busy_o && state_q != Complete && !cancelled && deadline_q != 0)
        deadline_q <= deadline_q - 1;
      if (state_q == Validate) begin
        source_total_q <= source_sum[31:0];
        address_q <= src_addr_q[0]; remaining_q <= src_words_q[0];
      end
      if (state_q == ReadPrepare || state_q == WritePrepare) begin
        burst_q <= burst_words(address_q[11:0], remaining_q); beat_q <= 0;
      end
      if (read_beat) begin sent_words_o <= sent_words_o + 1; beat_q <= beat_q + 9'd1; end
      if (write_beat) begin received_words_o <= received_words_o + 1; beat_q <= beat_q + 9'd1; end
      if (!cancelled && !fatal_event && state_q == ReadFinish && mem_done_valid_i) begin
        if (remaining_q != {23'b0, burst_q}) begin
          address_q <= address_q + {21'b0, burst_q, 2'b0};
          remaining_q <= remaining_q - {23'b0, burst_q};
        end else if (source_q < 2 && src_words_q[source_q + 2'd1] != 0) begin
          source_q <= source_q + 2'd1;
          address_q <= src_addr_q[source_q + 2'd1]; remaining_q <= src_words_q[source_q + 2'd1];
        end else begin address_q <= dst_addr_q; remaining_q <= dst_words_q; end
      end
      if (!cancelled && !fatal_event && state_q == WriteFinish && mem_done_valid_i) begin
        address_q <= address_q + {21'b0, burst_q, 2'b0};
        remaining_q <= remaining_q - {23'b0, burst_q};
      end
    end
  end
endmodule
