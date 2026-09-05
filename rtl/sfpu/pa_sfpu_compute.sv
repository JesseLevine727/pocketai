// M3 v1 vector arithmetic controller. Operands are already validated and
// loaded into synchronous X/G/B memories. X is reused for the final output.
module pa_sfpu_compute #(
  parameter string GeluFile = "gelu_q8.mem",
  parameter string ExpFile = "exp_q24.mem"
) (
  input logic clk_i,
  input logic rst_ni,
  input logic abort_i,
  input logic start_i,
  input logic [2:0] op_i,
  input logic [11:0] length_i,
  input logic [4:0] shift_i,
  input logic [30:0] multiplier_i,
  output logic busy_o,
  output logic done_o,
  output logic error_o,
  output logic [31:0] cycles_o,
  output logic [11:0] raddr_o,
  input logic [31:0] x_i,
  input logic [31:0] g_i,
  input logic [31:0] b_i,
  output logic we_o,
  output logic [11:0] waddr_o,
  output logic [31:0] wdata_o
);
  typedef enum logic [5:0] {
    Idle, ReadIssue, ReadWait, ReadUse, Write,
    AluStart, AluWait, LnSquareDone, LnLTDone, LnSSDone, LnLLDone,
    LnEpsilonDone, LnRootDone, LnCenteredDone, LnGainDone, LnDivideDone,
    AffineMultiplyDone, RequantMultiplyDone, GeluRead, GeluWrite,
    ExpRead, ExpMix, ExpMultiplyDone, ExpWrite, SoftDivideDone, SoftWrite,
    LnCenterSubtract, LnCenterLaunch, LnEpsilonRound, LnRadicand,
    RoundIncrement, ResultSign, ResultBias, ResultClip, ExpRound
  } state_e;
  typedef enum logic [2:0] {
    Elements, LnReduce, LnApply, SoftMaximum, SoftExponent, SoftNormalize, SoftCorrect
  } phase_e;
  state_e state_q, return_q;
  phase_e phase_q;
  logic [2:0] op_q;
  logic [11:0] length_q, index_q;
  logic [4:0] shift_q;
  logic [30:0] multiplier_q;
  logic [31:0] running_cycles_q, write_value_q;
  logic signed [63:0] sum_q;
  logic [63:0] squares_q, lt_q, variance_q, denominator_q;
  logic [63:0] exp_sum_q;
  logic [31:0] probability_sum_q, correction_q;
  logic signed [15:0] maximum_q;
  logic any_valid_q;
  logic [31:0] saved_gain_q, saved_bias_q, gelu_x_q;
  logic input_sign_q, result_sign_q;
  logic [7:0] exp_index_q;
  logic [3:0] exp_fraction_q;
  logic [28:0] exp_base_q;
  logic [28:0] exp_mix_q;
  logic [31:0] shift_mask_q, shift_half_q;
  logic [63:0] rounded_q, epsilon_q;
  logic round_increment_q;
  logic signed [63:0] signed_result_q, biased_result_q;
  logic signed [27:0] signed_lx_q;
  logic signed [28:0] centered_q;
  logic signed [16:0] element_sum;
  // ADD input planes are canonical int16, validated by the stream shell.
  // Preserve the carry/sign bit without a BRAM-to-64-bit-add/clip path.
  assign element_sum = $signed({x_i[15], x_i[15:0]}) + $signed({g_i[15], g_i[15:0]});

  logic [1:0] alu_op_q;
  logic [63:0] alu_a_q, alu_b_q, alu_result, alu_remainder;
  logic [79:0] alu_radicand_q;
  logic alu_busy, alu_done, alu_error;
  pa_sfpu_alu u_alu (
    .clk_i, .rst_ni, .abort_i,
    .start_i(state_q == AluStart), .op_i(alu_op_q), .a_i(alu_a_q),
    .b_i(alu_b_q), .radicand_i(alu_radicand_q),
    .busy_o(alu_busy), .done_o(alu_done), .error_o(alu_error),
    .result_o(alu_result), .remainder_o(alu_remainder)
  );

  logic [15:0] gelu_rom [0:2048];
  logic [24:0] exp_rom [0:256];
  logic [15:0] gelu_data_q;
  logic [24:0] exp_left_q, exp_right_q;
  logic [24:0] exp_delta;
  logic [31:0] gelu_magnitude;
  logic [11:0] gelu_address;
  initial begin
    $readmemh(GeluFile, gelu_rom);
    $readmemh(ExpFile, exp_rom);
  end
  assign gelu_magnitude = gelu_x_q[31] ? -gelu_x_q : gelu_x_q;
  assign exp_delta = exp_left_q - exp_right_q;
  assign gelu_address = gelu_magnitude <= 2048 ? gelu_magnitude[11:0] : 12'd2048;
  always_ff @(posedge clk_i) begin
    gelu_data_q <= gelu_rom[gelu_address];
    exp_left_q <= exp_rom[{1'b0, exp_index_q}];
    exp_right_q <= exp_rom[{1'b0, exp_index_q} + 9'd1];
  end

  function automatic logic [63:0] magnitude32(input logic [31:0] value);
    logic signed [63:0] extended;
    extended = {{32{value[31]}}, value};
    return extended < 0 ? $unsigned(-extended) : $unsigned(extended);
  endfunction
  function automatic logic [63:0] magnitude64(input logic signed [63:0] value);
    return value < 0 ? $unsigned(-value) : $unsigned(value);
  endfunction
  function automatic logic division_round_up(
      input logic quotient_odd, input logic [63:0] remainder, divisor);
    logic [64:0] twice;
    twice = {remainder, 1'b0};
    return twice > {1'b0, divisor} ||
           (twice == {1'b0, divisor} && quotient_odd);
  endfunction
  function automatic logic [31:0] sat16_word(input logic signed [63:0] value);
    if (value > 32767) return 32'h00007fff;
    if (value < -32768) return 32'hffff8000;
    return {{16{value[15]}}, value[15:0]};
  endfunction
  function automatic logic [31:0] sat8_word(input logic signed [63:0] value);
    if (value > 127) return 32'h0000007f;
    if (value < -128) return 32'hffffff80;
    return {{24{value[7]}}, value[7:0]};
  endfunction
  task automatic launch(input logic [1:0] operation,
                         input logic [63:0] lhs, rhs,
                         input logic [79:0] radicand,
                         input state_e destination);
    alu_op_q <= operation;
    alu_a_q <= lhs;
    alu_b_q <= rhs;
    alu_radicand_q <= radicand;
    return_q <= destination;
    state_q <= AluStart;
  endtask

  assign busy_o = state_q != Idle;
  assign raddr_o = index_q;
  assign waddr_o = index_q;
  assign wdata_o = write_value_q;
  assign we_o = !abort_i && (state_q == Write || state_q == ExpWrite || state_q == SoftWrite);

  always_ff @(posedge clk_i) begin : controller
    logic [31:0] positive_gelu;
    logic [31:0] shift_remainder;
    logic [16:0] difference;
    if (!rst_ni || abort_i) begin
      state_q <= Idle;
      return_q <= Idle;
      phase_q <= Elements;
      op_q <= '0;
      length_q <= '0;
      index_q <= '0;
      shift_q <= '0;
      multiplier_q <= '0;
      running_cycles_q <= '0;
      cycles_o <= '0;
      done_o <= 1'b0;
      error_o <= 1'b0;
      write_value_q <= '0;
      sum_q <= '0;
      squares_q <= '0;
      lt_q <= '0;
      variance_q <= '0;
      denominator_q <= '0;
      exp_sum_q <= '0;
      probability_sum_q <= '0;
      correction_q <= '0;
      maximum_q <= '0;
      any_valid_q <= 1'b0;
      saved_gain_q <= '0;
      saved_bias_q <= '0;
      gelu_x_q <= '0;
      input_sign_q <= 1'b0;
      result_sign_q <= 1'b0;
      exp_index_q <= '0;
      exp_fraction_q <= '0;
      exp_base_q <= '0;
      exp_mix_q <= '0;
      shift_mask_q <= '0;
      shift_half_q <= '0;
      rounded_q <= '0;
      epsilon_q <= '0;
      round_increment_q <= 1'b0;
      signed_result_q <= '0;
      biased_result_q <= '0;
      signed_lx_q <= '0;
      centered_q <= '0;
      alu_op_q <= '0;
      alu_a_q <= '0;
      alu_b_q <= '0;
      alu_radicand_q <= '0;
    end else begin
      done_o <= 1'b0;
      if (busy_o) running_cycles_q <= running_cycles_q + 1'b1;
      unique case (state_q)
        Idle: if (start_i) begin
          op_q <= op_i;
          length_q <= length_i;
          shift_q <= shift_i;
          shift_mask_q <= 32'hffffffff >> (6'd32 - {1'b0, shift_i});
          shift_half_q <= shift_i == 0 ? 32'h0 : 32'd1 << (shift_i - 5'd1);
          multiplier_q <= multiplier_i;
          index_q <= '0;
          sum_q <= '0;
          squares_q <= '0;
          exp_sum_q <= '0;
          probability_sum_q <= '0;
          correction_q <= '0;
          any_valid_q <= 1'b0;
          maximum_q <= '0;
          running_cycles_q <= '0;
          error_o <= 1'b0;
          phase_q <= op_i == 2 ? LnReduce : op_i == 3 ? SoftMaximum : Elements;
          state_q <= ReadIssue;
        end
        ReadIssue: state_q <= ReadWait;
        ReadWait: state_q <= ReadUse;
        ReadUse: begin
          unique case (phase_q)
            LnReduce: begin
              sum_q <= sum_q + $signed({{32{x_i[31]}}, x_i});
              launch(0, magnitude32(x_i), magnitude32(x_i), '0, LnSquareDone);
            end
            LnApply: begin
              saved_gain_q <= g_i;
              saved_bias_q <= b_i;
              input_sign_q <= x_i[31];
              launch(0, magnitude32(x_i), 64'(length_q), '0, LnCenteredDone);
            end
            SoftMaximum: begin
              if (x_i[16] && (!any_valid_q || $signed(x_i[15:0]) > maximum_q)) begin
                maximum_q <= $signed(x_i[15:0]);
              end
              if (x_i[16]) any_valid_q <= 1'b1;
              if (index_q + 12'd1 == length_q) begin
                index_q <= '0;
                phase_q <= SoftExponent;
              end else index_q <= index_q + 1'b1;
              state_q <= ReadIssue;
            end
            SoftExponent: begin
              difference = $unsigned($signed({maximum_q[15], maximum_q}) -
                                      $signed({x_i[15], x_i[15:0]}));
              if (!any_valid_q || !x_i[16] || difference >= 17'd4096) begin
                write_value_q <= '0;
                state_q <= ExpWrite;
              end else begin
                exp_index_q <= difference[11:4];
                exp_fraction_q <= difference[3:0];
                state_q <= ExpRead;
              end
            end
            SoftNormalize: begin
              if (x_i == 0) begin
                write_value_q <= '0;
                state_q <= SoftWrite;
              end else begin
                launch(1, 64'(x_i) << 15, exp_sum_q, '0, SoftDivideDone);
              end
            end
            SoftCorrect: begin
              write_value_q <= {16'h0, x_i[15:0]} +
                               32'(x_i[31] && correction_q != 0);
              if (x_i[31] && correction_q != 0) correction_q <= correction_q - 1'b1;
              state_q <= Write;
            end
            default: begin
              if (op_q == 1) begin
                gelu_x_q <= x_i;
                state_q <= GeluRead;
              end else if (op_q == 4 || op_q == 6) begin
                saved_bias_q <= b_i;
                result_sign_q <= x_i[31];
                launch(0, magnitude32(x_i), 64'(g_i), '0, AffineMultiplyDone);
              end else if (op_q == 5) begin
                saved_bias_q <= '0;
                result_sign_q <= x_i[31];
                launch(0, magnitude32(x_i), {33'h0, multiplier_q}, '0, RequantMultiplyDone);
              end else begin
                write_value_q <= sat16_word({{47{element_sum[16]}}, element_sum});
                state_q <= Write;
              end
            end
          endcase
        end
        LnSquareDone: begin
          squares_q <= squares_q + alu_result;
          if (index_q + 12'd1 == length_q) begin
            launch(0, squares_q + alu_result, 64'(length_q), '0, LnLTDone);
          end else begin
            index_q <= index_q + 1'b1;
            state_q <= ReadIssue;
          end
        end
        LnLTDone: begin
          lt_q <= alu_result;
          launch(0, magnitude64(sum_q), magnitude64(sum_q), '0, LnSSDone);
        end
        LnSSDone: begin
          assert (lt_q >= alu_result);
          variance_q <= lt_q - alu_result;
          launch(0, 64'(length_q), 64'(length_q), '0, LnLLDone);
        end
        LnLLDone: launch(1, alu_result << 40, 64'd100000, '0, LnEpsilonDone);
        LnEpsilonDone: begin
          rounded_q <= alu_result;
          round_increment_q <= division_round_up(alu_result[0], alu_remainder, 64'd100000);
          state_q <= LnEpsilonRound;
        end
        LnEpsilonRound: begin
          epsilon_q <= rounded_q + 64'(round_increment_q);
          state_q <= LnRadicand;
        end
        LnRadicand: launch(2, '0, '0, (80'(variance_q) << 24) + 80'(epsilon_q), LnRootDone);
        LnRootDone: begin
          assert (alu_result != 0);
          denominator_q <= alu_result;
          index_q <= '0;
          phase_q <= LnApply;
          state_q <= ReadIssue;
        end
        LnCenteredDone: begin
          // |L*x| <=3072*32768 fits signed28; L*x-S fits signed29.
          assert (alu_result <= 64'd100663296);
          signed_lx_q <= input_sign_q ? -$signed(alu_result[27:0]) : $signed(alu_result[27:0]);
          state_q <= LnCenterSubtract;
        end
        LnCenterSubtract: begin
          centered_q <= $signed({signed_lx_q[27], signed_lx_q}) - $signed(sum_q[28:0]);
          state_q <= LnCenterLaunch;
        end
        LnCenterLaunch: begin
          result_sign_q <= centered_q[28] ^ saved_gain_q[31];
          launch(0, {35'h0, centered_q[28] ? $unsigned(-centered_q) : $unsigned(centered_q)},
                    magnitude32(saved_gain_q), '0, LnGainDone);
        end
        LnGainDone: launch(1, alu_result << 8, denominator_q, '0, LnDivideDone);
        LnDivideDone: begin
          rounded_q <= alu_result;
          round_increment_q <= division_round_up(alu_result[0], alu_remainder, denominator_q);
          state_q <= RoundIncrement;
        end
        AffineMultiplyDone, RequantMultiplyDone: begin
          shift_remainder = alu_result[31:0] & shift_mask_q;
          rounded_q <= alu_result >> shift_q;
          round_increment_q <= shift_q != 0 &&
              (shift_remainder > shift_half_q ||
               (shift_remainder == shift_half_q && alu_result[{1'b0, shift_q}]));
          state_q <= RoundIncrement;
        end
        RoundIncrement: begin
          rounded_q <= rounded_q + 64'(round_increment_q);
          state_q <= ResultSign;
        end
        ResultSign: begin
          signed_result_q <= result_sign_q ? -$signed(rounded_q) : $signed(rounded_q);
          state_q <= ResultBias;
        end
        ResultBias: begin
          biased_result_q <= signed_result_q + $signed({{32{saved_bias_q[31]}}, saved_bias_q});
          state_q <= ResultClip;
        end
        ResultClip: begin
          if (op_q == 6) begin
            gelu_x_q <= sat16_word(biased_result_q);
            state_q <= GeluRead;
          end else begin
            write_value_q <= op_q == 5 ? sat8_word(biased_result_q) : sat16_word(biased_result_q);
            state_q <= Write;
          end
        end
        GeluRead: state_q <= GeluWrite;
        GeluWrite: begin
          positive_gelu = gelu_magnitude <= 2048 ? {16'h0, gelu_data_q} : gelu_magnitude;
          write_value_q <= gelu_x_q[31] ? positive_gelu - gelu_magnitude : positive_gelu;
          state_q <= Write;
        end
        ExpRead: state_q <= ExpMix;
        ExpMix: begin
          exp_base_q <= {exp_left_q, 4'h0};
          launch(0, {39'h0, exp_delta},
                    64'(exp_fraction_q), '0, ExpMultiplyDone);
        end
        ExpMultiplyDone: begin
          assert (alu_result < (64'd1 << 29));
          exp_mix_q <= exp_base_q - alu_result[28:0];
          state_q <= ExpRound;
        end
        ExpRound: begin
          write_value_q <= 32'(exp_mix_q[28:4]) +
                           32'(exp_mix_q[3] && (|exp_mix_q[2:0] || exp_mix_q[4]));
          state_q <= ExpWrite;
        end
        ExpWrite: begin
          exp_sum_q <= exp_sum_q + 64'(write_value_q);
          if (index_q + 12'd1 == length_q) begin
            index_q <= '0;
            phase_q <= SoftNormalize;
          end else index_q <= index_q + 1'b1;
          state_q <= ReadIssue;
        end
        SoftDivideDone: begin
          assert (alu_result <= 32768);
          // Internal high bit retains nonzero-weight support until correction.
          write_value_q <= 32'h80000000 | 32'(alu_result);
          state_q <= SoftWrite;
        end
        SoftWrite: begin
          probability_sum_q <= probability_sum_q + {16'h0, write_value_q[15:0]};
          if (index_q + 12'd1 == length_q) begin
            correction_q <= any_valid_q ?
                32'd32768 - probability_sum_q - {16'h0, write_value_q[15:0]} : 32'h0;
            index_q <= '0;
            phase_q <= SoftCorrect;
          end else index_q <= index_q + 1'b1;
          state_q <= ReadIssue;
        end
        Write: begin
          if (index_q + 12'd1 == length_q) begin
            if (phase_q == SoftCorrect) assert (correction_q == 0);
            state_q <= Idle;
            done_o <= 1'b1;
            cycles_o <= running_cycles_q + 1'b1;
          end else begin
            index_q <= index_q + 1'b1;
            state_q <= ReadIssue;
          end
        end
        AluStart: begin
          assert (!alu_busy);
          state_q <= AluWait;
        end
        AluWait: if (alu_done) begin
          if (alu_error) begin
            // Legal v1 domains never overflow the unsigned ALU or divide by 0.
            error_o <= 1'b1;
            done_o <= 1'b1;
            state_q <= Idle;
          end else state_q <= return_q;
        end
        default: state_q <= Idle;
      endcase
    end
  end
endmodule
