// PocketAI-T M2 descriptor-driven 16x16 signed-int8 GEMM engine.
// Numerical, stream, register, and error semantics are defined in
// docs/NUMERICS.md and docs/M2_ARCHITECTURE.md.

module pa_gemm #(
  parameter int unsigned MaxM = 16,
  parameter int unsigned MaxN = 16,
  parameter int unsigned MaxK = 768,
  parameter int unsigned PhysicalRows = 4
) (
  input logic clk_i,
  input logic rst_ni,

  input  logic        req_i,
  input  logic        we_i,
  input  logic [3:0]  be_i,
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic [31:0] addr_i,
  /* verilator lint_on UNUSEDSIGNAL */
  input  logic [31:0] wdata_i,
  output logic        rvalid_o,
  output logic [31:0] rdata_o,
  output logic        err_o,

  input  logic [31:0] s_axis_data_i,
  input  logic [3:0]  s_axis_keep_i,
  input  logic        s_axis_last_i,
  input  logic        s_axis_valid_i,
  output logic        s_axis_ready_o,

  output logic [31:0] m_axis_data_o,
  output logic [3:0]  m_axis_keep_o,
  output logic        m_axis_last_o,
  output logic        m_axis_valid_o,
  input  logic        m_axis_ready_i,

  output logic irq_o
);

  localparam int unsigned Slots = 2;
  localparam int unsigned AWordAddrWidth = $clog2((MaxK + 3) / 4);
  localparam int unsigned KAddrWidth = $clog2(MaxK);
  localparam int unsigned CWordAddrWidth = $clog2(MaxM * 8);
  localparam int unsigned AccWidth = 25;

  localparam logic [31:0] GemmId = 32'h50414732;
  localparam logic [7:0] ErrBadDims = 8'd1;
  localparam logic [7:0] ErrBadFlags = 8'd2;
  localparam logic [7:0] ErrQueueFull = 8'd3;
  localparam logic [7:0] ErrInputKeep = 8'd4;
  localparam logic [7:0] ErrEarlyLast = 8'd5;
  localparam logic [7:0] ErrMissingLast = 8'd6;

  typedef enum logic [2:0] {
    SlotEmpty,
    SlotLoad,
    SlotReady,
    SlotCompute,
    SlotPack,
    SlotOutput
  } slot_state_e;

  typedef enum logic [1:0] {
    EngineIdle,
    EngineRun,
    EnginePack
  } engine_state_e;

  slot_state_e slot_state_q [Slots];
  logic [4:0] slot_m_q [Slots];
  logic [4:0] slot_n_q [Slots];
  logic [KAddrWidth:0] slot_k_q [Slots];
  logic [31:0] slot_tag_q [Slots];
  logic [AWordAddrWidth:0] slot_a_stride_q [Slots];
  logic [7:0] slot_output_words_q [Slots];
  logic [19:0] slot_macs_q [Slots];
  logic [8:0] slot_mn_q [Slots];
  logic [31:0] slot_cycles_q [Slots];

  logic alloc_ptr_q, load_ptr_q, compute_ptr_q, output_ptr_q;
  logic [1:0] occupied_count;

  logic [31:0] staging_m_q, staging_n_q, staging_k_q;
  logic [31:0] staging_flags_q, staging_tag_q;
  logic done_q, error_q, irq_enable_q;
  logic [7:0] error_code_q;
  logic [31:0] completed_tag_q, last_cycles_q, last_macs_q;
  logic [31:0] completed_count_q;

  logic load_phase_b_q;
  logic [3:0] load_a_row_q;
  logic [AWordAddrWidth-1:0] load_a_word_q;
  logic [KAddrWidth-1:0] load_b_k_q;
  logic [1:0] load_b_group_q;
  logic drop_until_last_q;

  engine_state_e engine_state_q;
  logic engine_slot_q;
  logic [KAddrWidth:0] issue_k_q;
  logic read_valid_q, read_last_q;
  logic [1:0] read_a_lane_q;
  logic operand_valid_q, operand_last_q;
  logic [7:0] operand_a_q [PhysicalRows];
  logic [7:0] operand_b_q [MaxN];
  logic partial_valid_q, partial_last_q;
  logic cross_valid_q, cross_last_q;
  logic upper_valid_q, upper_last_q;
  logic prod_valid_q, prod_last_q;
  logic [7:0] partial_uu_q [PhysicalRows][MaxN];
  logic signed [7:0] partial_su_q [PhysicalRows][MaxN];
  logic signed [7:0] partial_us_q [PhysicalRows][MaxN];
  logic signed [7:0] partial_ss_q [PhysicalRows][MaxN];
  logic [7:0] cross_uu_q [PhysicalRows][MaxN];
  logic signed [7:0] cross_ss_q [PhysicalRows][MaxN];
  logic signed [8:0] cross_q [PhysicalRows][MaxN];
  logic [7:0] upper_uu_q [PhysicalRows][MaxN];
  logic signed [11:0] upper_q [PhysicalRows][MaxN];
  logic signed [15:0] product_q [PhysicalRows][MaxN];
  logic signed [AccWidth-1:0] accumulator_q [PhysicalRows][MaxN];
  logic [4:0] row_base_q;
  logic [CWordAddrWidth-1:0] pack_word_q;
  logic [31:0] engine_cycles_q;
  logic [CWordAddrWidth-1:0] output_word_q;

  logic a_we [Slots];
  logic [$clog2(MaxM)-1:0] a_wrow;
  logic [AWordAddrWidth-1:0] a_waddr, a_raddr;
  logic [31:0] a_wdata;
  logic [31:0] a_rdata [Slots][MaxM];
  logic b_we [Slots];
  logic [1:0] b_wgroup;
  logic [KAddrWidth-1:0] b_waddr, b_raddr;
  logic [31:0] b_wdata;
  logic [31:0] b_rdata [Slots][4];
  logic c_we [Slots];
  logic [CWordAddrWidth-1:0] c_waddr, c_raddr;
  logic [31:0] c_wdata;
  logic [31:0] c_rdata [Slots];

  logic [31:0] selected_a_word [MaxM];
  logic [31:0] selected_b_word [4];
  logic input_transfer, expected_input_last, input_frame_ok;
  logic output_transfer;
  logic issue_valid;
  logic [31:0] mmio_read_data;
  logic [AWordAddrWidth:0] staging_a_stride;
  logic [12:0] staging_input_words;
  logic [7:0] staging_output_words;
  logic descriptor_dims_valid;
  logic protocol_error_event, clear_error_event;
  logic [4:0] active_group_rows;
  logic [4:0] remaining_group_rows;
  logic [7:0] active_group_words;

  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value,
      input logic [31:0] new_value,
      input logic [3:0] byte_enable
  );
    for (int lane = 0; lane < 4; lane++) begin
      merge_bytes[8*lane +: 8] =
          byte_enable[lane] ? new_value[8*lane +: 8] : old_value[8*lane +: 8];
    end
  endfunction

  function automatic logic [AWordAddrWidth:0] a_stride_for_k(
      input logic [KAddrWidth:0] k
  );
    a_stride_for_k = (AWordAddrWidth+1)'(
        (k + (KAddrWidth+1)'(3)) >> 2);
  endfunction

  function automatic logic [12:0] input_words_for(
      input logic [4:0] m,
      input logic [KAddrWidth:0] k
  );
    input_words_for =
        13'(m) * 13'(a_stride_for_k(k)) + (13'(k) << 2);
  endfunction

  function automatic logic [7:0] output_words_for(input logic [4:0] m);
    output_words_for = {m, 3'b000};
  endfunction

  // Split each signed 8x8 soft multiply into short registered stages. This
  // preserves one K position per cycle after fill without consuming DSPs.
  function automatic logic [7:0] mul_u4_u4(
      input logic [3:0] lhs,
      input logic [3:0] rhs
  );
    logic [7:0] lhs_ext, rhs_ext;
    lhs_ext = {4'h0, lhs};
    rhs_ext = {4'h0, rhs};
    mul_u4_u4 = lhs_ext * rhs_ext;
  endfunction

  function automatic logic signed [7:0] mul_s4_u4(
      input logic signed [3:0] lhs,
      input logic [3:0] rhs
  );
    logic signed [7:0] lhs_ext, rhs_ext;
    lhs_ext = {{4{lhs[3]}}, lhs};
    rhs_ext = $signed({4'h0, rhs});
    mul_s4_u4 = lhs_ext * rhs_ext;
  endfunction

  function automatic logic signed [7:0] mul_u4_s4(
      input logic [3:0] lhs,
      input logic signed [3:0] rhs
  );
    logic signed [7:0] lhs_ext, rhs_ext;
    lhs_ext = $signed({4'h0, lhs});
    rhs_ext = {{4{rhs[3]}}, rhs};
    mul_u4_s4 = lhs_ext * rhs_ext;
  endfunction

  function automatic logic signed [7:0] mul_s4_s4(
      input logic signed [3:0] lhs,
      input logic signed [3:0] rhs
  );
    logic signed [7:0] lhs_ext, rhs_ext;
    lhs_ext = {{4{lhs[3]}}, lhs};
    rhs_ext = {{4{rhs[3]}}, rhs};
    mul_s4_s4 = lhs_ext * rhs_ext;
  endfunction

  function automatic logic [15:0] saturate_i16(
      input logic signed [31:0] value
  );
    if (value > 32'sd32767) begin
      saturate_i16 = 16'h7fff;
    end else if (value < -32'sd32768) begin
      saturate_i16 = 16'h8000;
    end else begin
      saturate_i16 = value[15:0];
    end
  endfunction

  for (genvar slot = 0; slot < Slots; slot++) begin : g_slot
    pa_gemm_slot #(
      .MaxM(MaxM),
      .MaxK(MaxK)
    ) u_slot (
      .clk_i,
      .a_we_i(a_we[slot]),
      .a_row_i(a_wrow),
      .a_waddr_i(a_waddr),
      .a_wdata_i(a_wdata),
      .a_raddr_i(a_raddr),
      .a_rdata_o(a_rdata[slot]),
      .b_we_i(b_we[slot]),
      .b_group_i(b_wgroup),
      .b_waddr_i(b_waddr),
      .b_wdata_i(b_wdata),
      .b_raddr_i(b_raddr),
      .b_rdata_o(b_rdata[slot]),
      .c_we_i(c_we[slot]),
      .c_waddr_i(c_waddr),
      .c_wdata_i(c_wdata),
      .c_raddr_i(c_raddr),
      .c_rdata_o(c_rdata[slot])
    );
  end

  always_comb begin
    occupied_count = 2'(
        (slot_state_q[0] != SlotEmpty) + (slot_state_q[1] != SlotEmpty));
    staging_a_stride = a_stride_for_k((KAddrWidth+1)'(staging_k_q));
    staging_input_words = input_words_for(5'(staging_m_q),
                                          (KAddrWidth+1)'(staging_k_q));
    staging_output_words = output_words_for(5'(staging_m_q));
    descriptor_dims_valid =
        staging_m_q >= 1 && staging_m_q <= MaxM &&
        staging_n_q >= 1 && staging_n_q <= MaxN &&
        staging_k_q >= 1 && staging_k_q <= MaxK;
  end

  always_comb begin
    remaining_group_rows = slot_m_q[engine_slot_q] - row_base_q;
    if (remaining_group_rows > 5'(PhysicalRows)) begin
      active_group_rows = 5'(PhysicalRows);
    end else begin
      active_group_rows = remaining_group_rows;
    end
    active_group_words = {active_group_rows, 3'b000};
  end

  always_comb begin
    mmio_read_data = 32'h0;
    unique case (addr_i[6:2])
      5'h00: mmio_read_data = GemmId;
      5'h01: mmio_read_data = {
          22'h0,
          occupied_count,
          2'h0,
          m_axis_valid_o,
          s_axis_ready_o,
          error_q,
          done_q,
          occupied_count != 0,
          slot_state_q[alloc_ptr_q] == SlotEmpty && !error_q
      };
      5'h02: mmio_read_data = 32'(staging_m_q);
      5'h03: mmio_read_data = 32'(staging_n_q);
      5'h04: mmio_read_data = 32'(staging_k_q);
      5'h05: mmio_read_data = staging_flags_q;
      5'h06: mmio_read_data = staging_tag_q;
      5'h08: mmio_read_data = completed_tag_q;
      5'h09: mmio_read_data = last_cycles_q;
      5'h0a: mmio_read_data = last_macs_q;
      5'h0b: mmio_read_data = 32'(staging_input_words);
      5'h0c: mmio_read_data = 32'(staging_output_words);
      5'h0d: mmio_read_data = completed_count_q;
      5'h0e: mmio_read_data = 32'(error_code_q);
      5'h0f: mmio_read_data = {16'(MaxK), 8'(MaxN), 8'(MaxM)};
      5'h10: mmio_read_data = {31'h0, irq_enable_q};
      default: mmio_read_data = 32'h0;
    endcase
  end

  assign input_transfer = s_axis_valid_i && s_axis_ready_o;
  assign expected_input_last =
      !drop_until_last_q && slot_state_q[load_ptr_q] == SlotLoad &&
      load_phase_b_q &&
      {1'b0, load_b_k_q} + 1'b1 == slot_k_q[load_ptr_q] &&
      load_b_group_q == 2'd3;
  assign input_frame_ok = s_axis_keep_i == 4'hf &&
                          s_axis_last_i == expected_input_last;
  assign protocol_error_event = input_transfer && !drop_until_last_q &&
                                !input_frame_ok;
  assign clear_error_event = req_i && we_i && addr_i[6:2] == 5'h07 &&
                             be_i[0] && wdata_i[2];
  assign s_axis_ready_o = drop_until_last_q ||
      (slot_state_q[load_ptr_q] == SlotLoad);

  always_comb begin
    a_wrow = load_a_row_q;
    a_waddr = load_a_word_q;
    a_wdata = s_axis_data_i;
    b_wgroup = load_b_group_q;
    b_waddr = load_b_k_q;
    b_wdata = s_axis_data_i;
    for (int slot = 0; slot < Slots; slot++) begin
      a_we[slot] = input_transfer && !drop_until_last_q && input_frame_ok &&
                   !load_phase_b_q && load_ptr_q == 1'(slot);
      b_we[slot] = input_transfer && !drop_until_last_q && input_frame_ok &&
                   load_phase_b_q && load_ptr_q == 1'(slot);
    end
  end

  assign issue_valid = engine_state_q == EngineRun &&
                       issue_k_q < slot_k_q[engine_slot_q];
  assign a_raddr = AWordAddrWidth'(issue_k_q >> 2);
  assign b_raddr = KAddrWidth'(issue_k_q);

  always_comb begin
    for (int row = 0; row < MaxM; row++) begin
      selected_a_word[row] = engine_slot_q ? a_rdata[1][row] : a_rdata[0][row];
    end
    for (int group = 0; group < 4; group++) begin
      selected_b_word[group] =
          engine_slot_q ? b_rdata[1][group] : b_rdata[0][group];
    end
  end

  for (genvar row = 0; row < PhysicalRows; row++) begin : g_multiply_row
    // Separate BRAM/slot/row/byte selection from multiplication. Otherwise
    // BRAM clock-to-out plus the selection muxes and soft multiply form one
    // long path whose timing margin depends heavily on routing.
    always_ff @(posedge clk_i) begin
      operand_a_q[row] <= selected_a_word[4'(row_base_q + 5'(row))]
          [8*read_a_lane_q +: 8];
    end
    for (genvar column = 0; column < MaxN; column++) begin : g_multiply_column
      always_ff @(posedge clk_i) begin
        // Data registers run continuously. The parallel valid pipeline alone
        // determines which product reaches the accumulator, avoiding high-
        // fanout clock-enable paths across the multiplier array.
        partial_uu_q[row][column] <= mul_u4_u4(
            operand_a_q[row][3:0], operand_b_q[column][3:0]);
        partial_su_q[row][column] <= mul_s4_u4(
            $signed(operand_a_q[row][7:4]), operand_b_q[column][3:0]);
        partial_us_q[row][column] <= mul_u4_s4(
            operand_a_q[row][3:0], $signed(operand_b_q[column][7:4]));
        partial_ss_q[row][column] <= mul_s4_s4(
            $signed(operand_a_q[row][7:4]), $signed(operand_b_q[column][7:4]));
        cross_uu_q[row][column] <= partial_uu_q[row][column];
        cross_ss_q[row][column] <= partial_ss_q[row][column];
        cross_q[row][column] <=
            $signed({partial_su_q[row][column][7],
                     partial_su_q[row][column]}) +
            $signed({partial_us_q[row][column][7],
                     partial_us_q[row][column]});
        upper_uu_q[row][column] <= cross_uu_q[row][column];
        upper_q[row][column] <=
            $signed({{3{cross_q[row][column][8]}},
                     cross_q[row][column]}) +
            $signed({cross_ss_q[row][column], 4'h0});
        product_q[row][column] <=
            $signed({8'h0, upper_uu_q[row][column]}) +
            $signed({upper_q[row][column], 4'h0});
      end
    end
  end

  for (genvar column = 0; column < MaxN; column++) begin : g_operand_b
    always_ff @(posedge clk_i) begin
      operand_b_q[column] <= selected_b_word[column/4][8*(column % 4) +: 8];
    end
  end

  always_comb begin
    logic [$clog2(PhysicalRows)-1:0] pack_local_row;
    logic [3:0] pack_global_row;
    logic [3:0] pack_column;
    logic [15:0] low_value, high_value;
    pack_local_row = $clog2(PhysicalRows)'(pack_word_q >> 3);
    pack_global_row = row_base_q[3:0] + {1'b0, pack_local_row};
    pack_column = {pack_word_q[2:0], 1'b0};
    low_value = 16'h0;
    high_value = 16'h0;
    if ({1'b0, pack_column} < slot_n_q[engine_slot_q]) begin
      low_value = saturate_i16(
          {{(32-AccWidth){accumulator_q[pack_local_row][pack_column][AccWidth-1]}},
           accumulator_q[pack_local_row][pack_column]});
    end
    if ({1'b0, pack_column} + 1'b1 < slot_n_q[engine_slot_q]) begin
      high_value = saturate_i16(
          {{(32-AccWidth){
                accumulator_q[pack_local_row][4'(pack_column + 1'b1)][AccWidth-1]}},
           accumulator_q[pack_local_row][4'(pack_column + 1'b1)]});
    end
    c_waddr = {pack_global_row, 3'b000} +
              CWordAddrWidth'(pack_word_q[2:0]);
    c_wdata = {high_value, low_value};
    for (int slot = 0; slot < Slots; slot++) begin
      c_we[slot] = engine_state_q == EnginePack && engine_slot_q == 1'(slot);
    end
  end

  assign c_raddr = output_word_q;
  assign m_axis_valid_o = slot_state_q[output_ptr_q] == SlotOutput;
  assign m_axis_data_o = output_ptr_q ? c_rdata[1] : c_rdata[0];
  assign m_axis_keep_o = 4'hf;
  assign m_axis_last_o = m_axis_valid_o &&
      {1'b0, output_word_q} + 1'b1 == slot_output_words_q[output_ptr_q];
  assign output_transfer = m_axis_valid_o && m_axis_ready_i;
  assign irq_o = irq_enable_q && (done_q || error_q);

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      rvalid_o <= 1'b0;
      rdata_o <= 32'h0;
      err_o <= 1'b0;
      staging_m_q <= 32'd1;
      staging_n_q <= 32'd1;
      staging_k_q <= 1;
      staging_flags_q <= 32'h0;
      staging_tag_q <= 32'h0;
      done_q <= 1'b0;
      error_q <= 1'b0;
      irq_enable_q <= 1'b0;
      error_code_q <= 8'h0;
      completed_tag_q <= 32'h0;
      last_cycles_q <= 32'h0;
      last_macs_q <= 32'h0;
      completed_count_q <= 32'h0;
      alloc_ptr_q <= 1'b0;
      load_ptr_q <= 1'b0;
      compute_ptr_q <= 1'b0;
      output_ptr_q <= 1'b0;
      load_phase_b_q <= 1'b0;
      load_a_row_q <= 4'h0;
      load_a_word_q <= '0;
      load_b_k_q <= '0;
      load_b_group_q <= 2'h0;
      drop_until_last_q <= 1'b0;
      engine_state_q <= EngineIdle;
      engine_slot_q <= 1'b0;
      issue_k_q <= '0;
      read_valid_q <= 1'b0;
      read_last_q <= 1'b0;
      read_a_lane_q <= 2'h0;
      operand_valid_q <= 1'b0;
      operand_last_q <= 1'b0;
      partial_valid_q <= 1'b0;
      partial_last_q <= 1'b0;
      cross_valid_q <= 1'b0;
      cross_last_q <= 1'b0;
      upper_valid_q <= 1'b0;
      upper_last_q <= 1'b0;
      prod_valid_q <= 1'b0;
      prod_last_q <= 1'b0;
      row_base_q <= '0;
      pack_word_q <= '0;
      engine_cycles_q <= 32'h0;
      output_word_q <= '0;
      for (int slot = 0; slot < Slots; slot++) begin
        slot_state_q[slot] <= SlotEmpty;
        slot_m_q[slot] <= '0;
        slot_n_q[slot] <= '0;
        slot_k_q[slot] <= '0;
        slot_tag_q[slot] <= '0;
        slot_a_stride_q[slot] <= '0;
        slot_output_words_q[slot] <= '0;
        slot_macs_q[slot] <= '0;
        slot_mn_q[slot] <= '0;
        slot_cycles_q[slot] <= '0;
      end
      for (int row = 0; row < PhysicalRows; row++) begin
        for (int column = 0; column < MaxN; column++) begin
          accumulator_q[row][column] <= '0;
        end
      end
    end else begin
      rvalid_o <= req_i;
      rdata_o <= mmio_read_data;
      err_o <= 1'b0;

      // Descriptor statistics need no triple-product combinational path.
      // M*N is captured on submit; multiply it by the captured K next cycle.
      // Even the smallest legal packet needs five input handshakes, so this
      // count is stable well before that slot can produce an output.
      for (int slot = 0; slot < Slots; slot++) begin
        slot_macs_q[slot] <= 20'(slot_mn_q[slot]) * 20'(slot_k_q[slot]);
      end

      if (req_i && we_i) begin
        unique case (addr_i[6:2])
          5'h02: staging_m_q <= merge_bytes(staging_m_q, wdata_i, be_i);
          5'h03: staging_n_q <= merge_bytes(staging_n_q, wdata_i, be_i);
          5'h04: staging_k_q <= merge_bytes(staging_k_q, wdata_i, be_i);
          5'h05: staging_flags_q <= merge_bytes(staging_flags_q, wdata_i, be_i);
          5'h06: staging_tag_q <= merge_bytes(staging_tag_q, wdata_i, be_i);
          5'h10: if (be_i[0]) irq_enable_q <= wdata_i[0];
          default: begin end
        endcase
      end

      if (req_i && we_i && addr_i[6:2] == 5'h07 && be_i[0]) begin
        if (wdata_i[2]) begin
          error_q <= 1'b0;
          error_code_q <= 8'h0;
          done_q <= 1'b0;
          alloc_ptr_q <= 1'b0;
          load_ptr_q <= 1'b0;
          compute_ptr_q <= 1'b0;
          output_ptr_q <= 1'b0;
          load_phase_b_q <= 1'b0;
          load_a_row_q <= 4'h0;
          load_a_word_q <= '0;
          load_b_k_q <= '0;
          load_b_group_q <= 2'h0;
          output_word_q <= '0;
          engine_state_q <= EngineIdle;
          read_valid_q <= 1'b0;
          operand_valid_q <= 1'b0;
          partial_valid_q <= 1'b0;
          cross_valid_q <= 1'b0;
          upper_valid_q <= 1'b0;
          prod_valid_q <= 1'b0;
          for (int slot = 0; slot < Slots; slot++) begin
            slot_state_q[slot] <= SlotEmpty;
          end
        end else if (wdata_i[1]) begin
          done_q <= 1'b0;
        end else if (wdata_i[0] && !error_q) begin
          if (!descriptor_dims_valid) begin
            error_q <= 1'b1;
            error_code_q <= ErrBadDims;
          end else if (staging_flags_q != 0) begin
            error_q <= 1'b1;
            error_code_q <= ErrBadFlags;
          end else if (slot_state_q[alloc_ptr_q] != SlotEmpty) begin
            error_q <= 1'b1;
            error_code_q <= ErrQueueFull;
          end else begin
            slot_state_q[alloc_ptr_q] <= SlotLoad;
            slot_m_q[alloc_ptr_q] <= 5'(staging_m_q);
            slot_n_q[alloc_ptr_q] <= 5'(staging_n_q);
            slot_k_q[alloc_ptr_q] <= (KAddrWidth+1)'(staging_k_q);
            slot_tag_q[alloc_ptr_q] <= staging_tag_q;
            slot_a_stride_q[alloc_ptr_q] <= staging_a_stride;
            slot_output_words_q[alloc_ptr_q] <= staging_output_words;
            slot_mn_q[alloc_ptr_q] <=
                9'(staging_m_q[4:0]) * 9'(staging_n_q[4:0]);
            alloc_ptr_q <= ~alloc_ptr_q;
          end
        end
      end

      if (drop_until_last_q && input_transfer && s_axis_last_i) begin
        drop_until_last_q <= 1'b0;
      end else if (input_transfer && !drop_until_last_q) begin
        if (s_axis_keep_i != 4'hf) begin
          error_q <= 1'b1;
          error_code_q <= ErrInputKeep;
          drop_until_last_q <= !s_axis_last_i;
          engine_state_q <= EngineIdle;
          for (int slot = 0; slot < Slots; slot++) slot_state_q[slot] <= SlotEmpty;
        end else if (s_axis_last_i && !expected_input_last) begin
          error_q <= 1'b1;
          error_code_q <= ErrEarlyLast;
          drop_until_last_q <= 1'b0;
          engine_state_q <= EngineIdle;
          for (int slot = 0; slot < Slots; slot++) slot_state_q[slot] <= SlotEmpty;
        end else if (!s_axis_last_i && expected_input_last) begin
          error_q <= 1'b1;
          error_code_q <= ErrMissingLast;
          drop_until_last_q <= 1'b1;
          engine_state_q <= EngineIdle;
          for (int slot = 0; slot < Slots; slot++) slot_state_q[slot] <= SlotEmpty;
        end else if (!load_phase_b_q) begin
          if (load_a_word_q + 1 == slot_a_stride_q[load_ptr_q]) begin
            load_a_word_q <= '0;
            if (load_a_row_q + 1 == slot_m_q[load_ptr_q]) begin
              load_a_row_q <= '0;
              load_phase_b_q <= 1'b1;
            end else begin
              load_a_row_q <= load_a_row_q + 1'b1;
            end
          end else begin
            load_a_word_q <= load_a_word_q + 1'b1;
          end
        end else if (expected_input_last) begin
          slot_state_q[load_ptr_q] <= SlotReady;
          load_ptr_q <= ~load_ptr_q;
          load_phase_b_q <= 1'b0;
          load_a_row_q <= '0;
          load_a_word_q <= '0;
          load_b_k_q <= '0;
          load_b_group_q <= '0;
        end else if (load_b_group_q == 2'd3) begin
          load_b_group_q <= 2'h0;
          load_b_k_q <= load_b_k_q + 1'b1;
        end else begin
          load_b_group_q <= load_b_group_q + 1'b1;
        end
      end

      if (output_transfer) begin
        if (m_axis_last_o) begin
          slot_state_q[output_ptr_q] <= SlotEmpty;
          completed_tag_q <= slot_tag_q[output_ptr_q];
          last_cycles_q <= slot_cycles_q[output_ptr_q];
          last_macs_q <= {12'h0, slot_macs_q[output_ptr_q]};
          completed_count_q <= completed_count_q + 1'b1;
          done_q <= 1'b1;
          output_ptr_q <= ~output_ptr_q;
          output_word_q <= '0;
        end else begin
          output_word_q <= output_word_q + 1'b1;
        end
      end

      unique case (engine_state_q)
        EngineIdle: begin
          read_valid_q <= 1'b0;
          operand_valid_q <= 1'b0;
          partial_valid_q <= 1'b0;
          cross_valid_q <= 1'b0;
          upper_valid_q <= 1'b0;
          prod_valid_q <= 1'b0;
          if (slot_state_q[compute_ptr_q] == SlotReady) begin
            engine_slot_q <= compute_ptr_q;
            slot_state_q[compute_ptr_q] <= SlotCompute;
            issue_k_q <= '0;
            row_base_q <= '0;
            pack_word_q <= '0;
            engine_cycles_q <= '0;
            engine_state_q <= EngineRun;
            for (int row = 0; row < PhysicalRows; row++) begin
              for (int column = 0; column < MaxN; column++) begin
                accumulator_q[row][column] <= '0;
              end
            end
          end
        end
        EngineRun: begin
          engine_cycles_q <= engine_cycles_q + 1'b1;
          read_valid_q <= issue_valid;
          if (issue_valid) begin
            read_last_q <= issue_k_q + 1 == slot_k_q[engine_slot_q];
            read_a_lane_q <= issue_k_q[1:0];
            issue_k_q <= issue_k_q + 1'b1;
          end
          operand_valid_q <= read_valid_q;
          operand_last_q <= read_last_q;
          partial_valid_q <= operand_valid_q;
          partial_last_q <= operand_last_q;
          cross_valid_q <= partial_valid_q;
          cross_last_q <= partial_last_q;
          upper_valid_q <= cross_valid_q;
          upper_last_q <= cross_last_q;
          prod_valid_q <= upper_valid_q;
          prod_last_q <= upper_last_q;
          if (prod_valid_q) begin
            for (int row = 0; row < PhysicalRows; row++) begin
              for (int column = 0; column < MaxN; column++) begin
                accumulator_q[row][column] <=
                    accumulator_q[row][column] +
                    {{(AccWidth-16){product_q[row][column][15]}},
                     product_q[row][column]};
              end
            end
            if (prod_last_q) begin
              slot_state_q[engine_slot_q] <= SlotPack;
              pack_word_q <= '0;
              engine_state_q <= EnginePack;
            end
          end
        end
        EnginePack: begin
          engine_cycles_q <= engine_cycles_q + 1'b1;
          if ({1'b0, pack_word_q} + 1'b1 == active_group_words) begin
            pack_word_q <= '0;
            if (row_base_q + 5'(PhysicalRows) < slot_m_q[engine_slot_q]) begin
              row_base_q <= row_base_q + 5'(PhysicalRows);
              issue_k_q <= '0;
              read_valid_q <= 1'b0;
              operand_valid_q <= 1'b0;
              partial_valid_q <= 1'b0;
              cross_valid_q <= 1'b0;
              upper_valid_q <= 1'b0;
              prod_valid_q <= 1'b0;
              slot_state_q[engine_slot_q] <= SlotCompute;
              engine_state_q <= EngineRun;
              for (int row = 0; row < PhysicalRows; row++) begin
                for (int column = 0; column < MaxN; column++) begin
                  accumulator_q[row][column] <= '0;
                end
              end
            end else begin
              slot_state_q[engine_slot_q] <= SlotOutput;
              slot_cycles_q[engine_slot_q] <= engine_cycles_q + 1'b1;
              compute_ptr_q <= ~compute_ptr_q;
              engine_state_q <= EngineIdle;
            end
          end else begin
            pack_word_q <= pack_word_q + 1'b1;
          end
        end
        default: engine_state_q <= EngineIdle;
      endcase

      // Stream framing errors invalidate every in-flight slot. A clear-error
      // command is also the documented pipeline abort/reinitialization point.
      // Keep this override after the normal engines so no simultaneous state
      // transition can resurrect an invalidated slot.
      if (protocol_error_event || clear_error_event) begin
        // Software first quiesces/resets DMA, then aborts the engine. A
        // malformed source may never send TLAST, so abort must also release
        // the drain state rather than depend on an eventual packet terminator.
        if (clear_error_event) begin
          error_q <= 1'b0;
          error_code_q <= '0;
          done_q <= 1'b0;
          drop_until_last_q <= 1'b0;
        end
        alloc_ptr_q <= 1'b0;
        load_ptr_q <= 1'b0;
        compute_ptr_q <= 1'b0;
        output_ptr_q <= 1'b0;
        load_phase_b_q <= 1'b0;
        load_a_row_q <= '0;
        load_a_word_q <= '0;
        load_b_k_q <= '0;
        load_b_group_q <= '0;
        output_word_q <= '0;
        engine_state_q <= EngineIdle;
        read_valid_q <= 1'b0;
        operand_valid_q <= 1'b0;
        partial_valid_q <= 1'b0;
        cross_valid_q <= 1'b0;
        upper_valid_q <= 1'b0;
        prod_valid_q <= 1'b0;
        for (int slot = 0; slot < Slots; slot++) begin
          slot_state_q[slot] <= SlotEmpty;
        end
      end
    end
  end

endmodule
