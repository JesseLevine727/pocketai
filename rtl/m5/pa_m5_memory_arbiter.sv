// Round-robin whole-burst ownership. No physical address input or host service.
module pa_m5_memory_arbiter #(
  parameter int unsigned Clients = 5
) (
  input logic clk_i,
  input logic rst_ni,
  input logic abort_i,
  input logic pause_i,
  input logic req_valid_i [Clients],
  output logic req_ready_o [Clients],
  input logic [31:0] req_addr_i [Clients],
  input logic [8:0] req_words_i [Clients],
  input logic req_write_i [Clients],
  input logic in_valid_i [Clients],
  output logic in_ready_o [Clients],
  input logic [31:0] in_data_i [Clients],
  input logic [3:0] in_strb_i [Clients],
  output logic out_valid_o [Clients],
  input logic out_ready_i [Clients],
  output logic [31:0] out_data_o [Clients],
  output logic out_last_o [Clients],
  output logic done_valid_o [Clients],
  input logic done_ready_i [Clients],
  output logic [3:0] done_fault_o [Clients],
  output logic busy_o,
  output logic quiesced_o,
  output logic m_abort_o,
  output logic m_req_valid_o,
  input logic m_req_ready_i,
  output logic [31:0] m_req_addr_o,
  output logic [8:0] m_req_words_o,
  output logic m_req_write_o,
  output logic m_in_valid_o,
  input logic m_in_ready_i,
  output logic [31:0] m_in_data_o,
  output logic [3:0] m_in_strb_o,
  input logic m_out_valid_i,
  output logic m_out_ready_o,
  input logic [31:0] m_out_data_i,
  input logic m_out_last_i,
  input logic m_done_valid_i,
  output logic m_done_ready_o,
  input logic [3:0] m_done_fault_i,
  input logic m_busy_i,
  input logic m_quiesced_i
);
  localparam int IndexWidth = Clients > 1 ? $clog2(Clients) : 1;
  typedef enum logic [2:0] {Idle, Issue, Active, Drain, Respond} state_e;
  state_e state_q;
  logic [IndexWidth-1:0] rr_q, owner_q, selected;
  logic selected_valid;
  logic [31:0] addr_q;
  logic [8:0] words_q;
  logic write_q;
  logic [3:0] fault_q;
  initial assert (Clients >= 1 && Clients <= 16);
  always_comb begin
    selected = 0; selected_valid = 0;
    for (int i = 0; i < Clients; i++) begin
      int candidate;
      candidate = int'(rr_q) + i;
      if (candidate >= Clients) candidate -= Clients;
      if (!selected_valid && req_valid_i[candidate]) begin
        selected = IndexWidth'(candidate);
        selected_valid = 1;
      end
    end
  end
  assign busy_o = state_q != Idle || m_busy_i;
  assign quiesced_o = abort_i && !busy_o && m_quiesced_i && !selected_valid;
  assign m_abort_o = abort_i || state_q == Drain;
  assign m_req_valid_o = state_q == Issue && !abort_i;
  assign m_req_addr_o = addr_q;
  assign m_req_words_o = words_q;
  assign m_req_write_o = write_q;
  assign m_in_valid_o = state_q == Active && !abort_i && in_valid_i[owner_q];
  assign m_in_data_o = in_data_i[owner_q];
  assign m_in_strb_o = in_strb_i[owner_q];
  assign m_out_ready_o = state_q == Active && !abort_i && out_ready_i[owner_q];
  assign m_done_ready_o = state_q == Active || state_q == Drain;
  always_comb begin
    for (int i = 0; i < Clients; i++) begin
      req_ready_o[i] = state_q == Idle && !m_busy_i && selected_valid &&
                       selected == IndexWidth'(i) && (!pause_i || abort_i);
      in_ready_o[i] = state_q == Active && !abort_i && owner_q == IndexWidth'(i) && m_in_ready_i;
      out_valid_o[i] = state_q == Active && !abort_i && owner_q == IndexWidth'(i) && m_out_valid_i;
      out_data_o[i] = m_out_data_i;
      out_last_o[i] = m_out_last_i;
      done_valid_o[i] = state_q == Respond && owner_q == IndexWidth'(i);
      done_fault_o[i] = fault_q;
    end
  end
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle; rr_q <= 0; owner_q <= 0;
      addr_q <= 0; words_q <= 0; write_q <= 0; fault_q <= 0;
    end else case (state_q)
      Idle: if (selected_valid && req_ready_o[selected]) begin
        owner_q <= selected;
        rr_q <= selected == IndexWidth'(Clients - 1) ? '0 : selected + IndexWidth'(1);
        addr_q <= req_addr_i[selected]; words_q <= req_words_i[selected];
        write_q <= req_write_i[selected];
        fault_q <= abort_i ? 4'd11 : 4'd0;
        state_q <= abort_i ? Respond : Issue;
      end
      Issue: begin
        if (abort_i) begin fault_q <= 11; state_q <= Respond; end
        else if (m_req_ready_i) state_q <= Active;
      end
      Active: begin
        if (abort_i) state_q <= Drain;
        else if (m_done_valid_i) begin fault_q <= m_done_fault_i; state_q <= Respond; end
      end
      Drain: if (m_quiesced_i && !m_busy_i) begin fault_q <= 11; state_q <= Respond; end
      Respond: if (done_ready_i[owner_q] || abort_i) state_q <= Idle;
      default: state_q <= Drain;
    endcase
  end
endmodule
