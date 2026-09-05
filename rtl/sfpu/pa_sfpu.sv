// M3 v1 single-slot SFPU: validated descriptor/packet shell, private vector
// memories, integer compute controller, ordered completion and stream routing.
module pa_sfpu #(
  parameter string GeluFile = "gelu_q8.mem",
  parameter string ExpFile = "exp_q24.mem"
) (
  input logic clk_i,
  input logic rst_ni,
  input logic req_i,
  input logic we_i,
  input logic [3:0] be_i,
  /* verilator lint_off UNUSEDSIGNAL */
  input logic [31:0] addr_i,
  /* verilator lint_on UNUSEDSIGNAL */
  input logic [31:0] wdata_i,
  output logic rvalid_o,
  output logic [31:0] rdata_o,
  output logic err_o,
  input logic [31:0] s_axis_data_i,
  input logic [3:0] s_axis_keep_i,
  input logic s_axis_last_i,
  input logic s_axis_valid_i,
  output logic s_axis_ready_o,
  output logic [31:0] m_axis_data_o,
  output logic [3:0] m_axis_keep_o,
  output logic m_axis_last_o,
  output logic m_axis_valid_o,
  input logic m_axis_ready_i,
  input logic gemm_busy_i,
  output logic stream_route_o,
  output logic busy_o,
  output logic irq_o
);
  typedef enum logic [2:0] {
    Idle, Load, ComputeStart, Compute, OutputRead, OutputWait, OutputValid
  } state_e;
  state_e state_q;
  logic [31:0] staging_op_q, staging_length_q, staging_shift_q;
  logic [31:0] staging_multiplier_q, staging_tag_q;
  logic [2:0] op_q;
  logic [11:0] length_q, load_index_q, output_index_q;
  logic [4:0] shift_q;
  logic [30:0] multiplier_q;
  logic [31:0] tag_q;
  logic [1:0] load_plane_q, planes_q;
  logic done_q, error_q, irq_enable_q, drain_q;
  logic [7:0] error_code_q;
  logic [31:0] completed_tag_q, last_cycles_q, last_elements_q, completed_count_q;
  logic [31:0] output_data_q;
  logic [7:0] descriptor_error, payload_error;
  logic [1:0] staged_planes;
  logic [13:0] staged_word_count;
  logic [31:0] read_data, enabled_wdata;
  logic command_write, abort_event, input_transfer, input_error;
  logic expected_last, payload_canonical;

  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value, new_value, input logic [3:0] enables);
    for (int lane = 0; lane < 4; lane++) begin
      merge_bytes[8*lane +: 8] = enables[lane] ?
                                new_value[8*lane +: 8] : old_value[8*lane +: 8];
    end
  endfunction
  function automatic logic [1:0] planes_for(input logic [31:0] op);
    return op == 2 || op == 4 || op == 6 ? 2'd3 : op == 7 ? 2'd2 : 2'd1;
  endfunction

  always_comb begin
    staged_planes = planes_for(staging_op_q);
    descriptor_error = 0;
    if (staging_op_q < 1 || staging_op_q > 7) descriptor_error = 1;
    else if (staging_length_q < 1 || staging_length_q > 3072 ||
             (staging_op_q == 3 && staging_length_q > 1024)) descriptor_error = 2;
    else if (staging_op_q == 4 || staging_op_q == 6) begin
      if (staging_shift_q > 31 || staging_multiplier_q != 0) descriptor_error = 3;
    end else if (staging_op_q == 5) begin
      if (staging_shift_q > 31 || staging_multiplier_q[31]) descriptor_error = 3;
    end else if (staging_shift_q != 0 || staging_multiplier_q != 0) descriptor_error = 3;
  end
  assign enabled_wdata = merge_bytes(0, wdata_i, be_i);
  // Valid length is <=3072. Keep this descriptor-side count off a wide
  // inferred multiplier; invalid full-width staging is rejected above.
  assign staged_word_count = staged_planes == 3 ?
      ({2'b0, staging_length_q[11:0]} << 1) + {2'b0, staging_length_q[11:0]} :
      staged_planes == 2 ? {1'b0, staging_length_q[11:0], 1'b0} :
                           {2'b0, staging_length_q[11:0]};
  assign command_write = req_i && we_i && addr_i[9:2] == 8'h07 && be_i[0];
  assign abort_event = command_write && enabled_wdata[2];
  assign busy_o = state_q != Idle || drain_q;
  assign s_axis_ready_o = state_q == Load || drain_q;
  assign input_transfer = s_axis_valid_i && s_axis_ready_o;
  assign expected_last = load_index_q + 12'd1 == length_q &&
                         load_plane_q + 2'd1 == planes_q;

  always_comb begin
    payload_canonical = 1'b1;
    if (op_q == 1 || op_q == 2 || op_q == 7) begin
      payload_canonical = s_axis_data_i[31:16] == {16{s_axis_data_i[15]}};
    end else if (op_q == 3) begin
      payload_canonical = s_axis_data_i[31:17] == 0;
    end else if ((op_q == 4 || op_q == 6) && load_plane_q == 1) begin
      payload_canonical = !s_axis_data_i[31];
    end
    payload_error = 0;
    if (s_axis_keep_i != 4'hf) payload_error = 5;
    else if (s_axis_last_i && !expected_last) payload_error = 6;
    else if (!s_axis_last_i && expected_last) payload_error = 7;
    else if (!payload_canonical) payload_error = 8;
  end
  assign input_error = input_transfer && !drain_q && payload_error != 0;

  logic [31:0] x_mem [0:3071];
  logic [31:0] g_mem [0:3071];
  logic [31:0] b_mem [0:3071];
  logic [31:0] x_data_q, g_data_q, b_data_q;
  logic [11:0] memory_raddr, compute_raddr, compute_waddr;
  logic [31:0] compute_wdata, compute_cycles;
  logic compute_we, compute_busy, compute_done, compute_error;
  logic load_memory, x_write;
  logic [11:0] x_waddr;
  logic [31:0] x_wdata;
  assign memory_raddr = state_q == OutputRead || state_q == OutputWait || state_q == OutputValid ?
                        output_index_q : compute_raddr;
  assign load_memory = input_transfer && !drain_q && payload_error == 0 && !abort_event;
  assign x_write = (load_memory && load_plane_q == 0) ||
                   (!load_memory && compute_we && state_q == Compute);
  assign x_waddr = load_memory ? load_index_q : compute_waddr;
  assign x_wdata = load_memory ? s_axis_data_i : compute_wdata;
  // One explicit write port lets portable inference select a block RAM;
  // compute and packet loading never overlap in this single-slot design.
  always_ff @(posedge clk_i) begin
    if (x_write) x_mem[x_waddr] <= x_wdata;
    if (load_memory) begin
      if (load_plane_q == 1) g_mem[load_index_q] <= s_axis_data_i;
      if (load_plane_q == 2) b_mem[load_index_q] <= s_axis_data_i;
    end
    x_data_q <= x_mem[memory_raddr];
    g_data_q <= g_mem[memory_raddr];
    b_data_q <= b_mem[memory_raddr];
  end
  pa_sfpu_compute #(.GeluFile(GeluFile), .ExpFile(ExpFile)) u_compute (
    .clk_i, .rst_ni, .abort_i(abort_event || input_error),
    .start_i(state_q == ComputeStart), .op_i(op_q), .length_i(length_q),
    .shift_i(shift_q), .multiplier_i(multiplier_q),
    .busy_o(compute_busy), .done_o(compute_done), .error_o(compute_error),
    .cycles_o(compute_cycles), .raddr_o(compute_raddr),
    .x_i(x_data_q), .g_i(g_data_q), .b_i(b_data_q),
    .we_o(compute_we), .waddr_o(compute_waddr), .wdata_o(compute_wdata)
  );
  assign m_axis_data_o = output_data_q;
  assign m_axis_keep_o = 4'hf;
  assign m_axis_valid_o = state_q == OutputValid;
  assign m_axis_last_o = m_axis_valid_o && output_index_q + 12'd1 == length_q;
  assign irq_o = irq_enable_q && (done_q || error_q);

  always_comb begin
    read_data = 0;
    unique case (addr_i[9:2])
      8'h00: read_data = 32'h50415333;
      8'h01: read_data = {26'h0, m_axis_valid_o, s_axis_ready_o, error_q,
                          done_q, busy_o, !busy_o && !error_q};
      8'h02: read_data = staging_op_q;
      8'h03: read_data = staging_length_q;
      8'h04: read_data = staging_shift_q;
      8'h05: read_data = staging_multiplier_q;
      8'h06: read_data = staging_tag_q;
      8'h08: read_data = completed_tag_q;
      8'h09: read_data = last_cycles_q;
      8'h0a: read_data = last_elements_q;
      8'h0b: read_data = descriptor_error == 0 ? {18'h0, staged_word_count} : 32'h0;
      8'h0c: read_data = descriptor_error == 0 ? staging_length_q : 32'h0;
      8'h0d: read_data = completed_count_q;
      8'h0e: read_data = {24'h0, error_code_q};
      8'h0f: read_data = 32'h01000c00;
      8'h10: read_data = {31'h0, irq_enable_q};
      8'h11: read_data = 32'h000000fe;
      8'h12: read_data = 32'h00030001;
      8'h13: read_data = 32'd1024;
      8'h14: read_data = {31'h0, stream_route_o};
      default: read_data = 0;
    endcase
  end

  task automatic control_error(input logic [7:0] code);
    if (!error_q) begin
      error_q <= 1'b1;
      error_code_q <= code;
    end
  endtask

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle;
      staging_op_q <= 1;
      staging_length_q <= 1;
      staging_shift_q <= 0;
      staging_multiplier_q <= 0;
      staging_tag_q <= 0;
      op_q <= 0;
      length_q <= 0;
      shift_q <= 0;
      multiplier_q <= 0;
      tag_q <= 0;
      load_index_q <= 0;
      output_index_q <= 0;
      load_plane_q <= 0;
      planes_q <= 0;
      done_q <= 1'b0;
      error_q <= 1'b0;
      error_code_q <= 0;
      drain_q <= 1'b0;
      irq_enable_q <= 1'b0;
      stream_route_o <= 1'b0;
      completed_tag_q <= 0;
      last_cycles_q <= 0;
      last_elements_q <= 0;
      completed_count_q <= 0;
      output_data_q <= 0;
      rvalid_o <= 1'b0;
      rdata_o <= 0;
      err_o <= 1'b0;
    end else begin
      rvalid_o <= req_i;
      rdata_o <= read_data;
      err_o <= 1'b0;
      unique case (state_q)
        Load: if (input_transfer && !input_error) begin
          if (expected_last) begin
            state_q <= ComputeStart;
          end else if (load_index_q + 12'd1 == length_q) begin
            load_index_q <= 0;
            load_plane_q <= load_plane_q + 1'b1;
          end else load_index_q <= load_index_q + 1'b1;
        end
        ComputeStart: begin
          assert (!compute_busy);
          state_q <= Compute;
        end
        Compute: if (compute_done) begin
          if (compute_error) begin
            control_error(8);
            state_q <= Idle;
          end else begin
            output_index_q <= 0;
            state_q <= OutputRead;
          end
        end
        OutputRead: state_q <= OutputWait;
        OutputWait: begin
          output_data_q <= x_data_q;
          state_q <= OutputValid;
        end
        OutputValid: if (m_axis_ready_i && !abort_event) begin
          if (m_axis_last_o) begin
            completed_tag_q <= tag_q;
            last_cycles_q <= compute_cycles;
            last_elements_q <= {20'h0, length_q};
            completed_count_q <= completed_count_q + 1'b1;
            done_q <= 1'b1;
            state_q <= Idle;
          end else begin
            output_index_q <= output_index_q + 1'b1;
            state_q <= OutputRead;
          end
        end
        default: begin end
      endcase

      if (req_i && we_i) begin
        unique case (addr_i[9:2])
          8'h02: staging_op_q <= merge_bytes(staging_op_q, wdata_i, be_i);
          8'h03: staging_length_q <= merge_bytes(staging_length_q, wdata_i, be_i);
          8'h04: staging_shift_q <= merge_bytes(staging_shift_q, wdata_i, be_i);
          8'h05: staging_multiplier_q <= merge_bytes(staging_multiplier_q, wdata_i, be_i);
          8'h06: staging_tag_q <= merge_bytes(staging_tag_q, wdata_i, be_i);
          8'h10: if (be_i[0]) irq_enable_q <= wdata_i[0];
          8'h14: if (be_i[0]) begin
            if (enabled_wdata > 1) control_error(3);
            else if (enabled_wdata[0] != stream_route_o) begin
              if (busy_o || gemm_busy_i) control_error(9);
              else stream_route_o <= enabled_wdata[0];
            end
          end
          default: begin end
        endcase
      end
      if (command_write && !abort_event) begin
        if (enabled_wdata == 2) begin
          done_q <= 1'b0;
          error_q <= 1'b0;
          error_code_q <= 0;
        end else if (enabled_wdata == 1 && !error_q) begin
          if (descriptor_error != 0) control_error(descriptor_error);
          else if (busy_o) control_error(4);
          else begin
            op_q <= staging_op_q[2:0];
            length_q <= staging_length_q[11:0];
            shift_q <= staging_shift_q[4:0];
            multiplier_q <= staging_multiplier_q[30:0];
            tag_q <= staging_tag_q;
            planes_q <= staged_planes;
            load_index_q <= 0;
            load_plane_q <= 0;
            state_q <= Load;
          end
        end else if (enabled_wdata != 0 && enabled_wdata != 1) control_error(10);
      end
      if (drain_q && input_transfer && s_axis_last_i) drain_q <= 1'b0;
      if (input_error) begin
        state_q <= Idle;
        error_q <= 1'b1;
        error_code_q <= payload_error;
        drain_q <= !s_axis_last_i;
      end
      if (abort_event) begin
        state_q <= Idle;
        drain_q <= 1'b0;
        done_q <= 1'b0;
        error_q <= 1'b0;
        error_code_q <= 0;
        load_index_q <= 0;
        load_plane_q <= 0;
        output_index_q <= 0;
      end
    end
  end
endmodule
