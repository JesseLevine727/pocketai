// Portable bounded-latency unsigned arithmetic shared by the M3 SFPU.
// op=0: 64x64 multiply (low64 + overflow); op=1: 64/64 floor division;
// op=2: floor sqrt of 80-bit radicand (remainder = radicand - root^2).
// start is accepted only while idle. Other starts are ignored. Results remain
// stable until next completion; done is a pulse. Reset/abort invalidate work.
// No fabric multiply/divide primitives or floating-point arithmetic.
module pa_sfpu_alu (
  input logic clk_i,
  input logic rst_ni,
  input logic abort_i,
  input logic start_i,
  input logic [1:0] op_i,
  input logic [63:0] a_i,
  input logic [63:0] b_i,
  input logic [79:0] radicand_i,
  output logic busy_o,
  output logic done_o,
  output logic error_o,
  output logic [63:0] result_o,
  output logic [63:0] remainder_o
);
  logic [1:0] op_q;
  logic [5:0] count_q;
  logic [63:0] operand_q;
  logic [127:0] product_q, product_next;
  logic [64:0] product_sum;
  logic [63:0] quotient_q, quotient_next;
  logic [63:0] division_remainder_q, division_remainder_next;
  logic [64:0] division_trial;
  logic [65:0] division_difference;
  logic [79:0] radicand_q;
  logic [39:0] root_q, root_next;
  logic [39:0] root_remainder_q;
  logic [41:0] root_remainder_next;
  logic [41:0] root_trial, root_divisor;

  // Add only the upper 64 bits, then shift the full product. This keeps the
  // multiplier's carry path to 65 bits rather than a 128-bit add each cycle.
  assign product_sum = {1'b0, product_q[127:64]} +
                       (product_q[0] ? {1'b0, operand_q} : 65'h0);
  assign product_next = {product_sum, product_q[63:1]};

  assign division_trial = {division_remainder_q, quotient_q[63]};
  assign division_difference = {1'b0, division_trial} - {2'b0, operand_q};
  assign quotient_next = {quotient_q[62:0], !division_difference[65]};
  assign division_remainder_next = division_difference[65] ?
                                    division_trial[63:0] : division_difference[63:0];

  assign root_trial = {root_remainder_q, radicand_q[79:78]};
  assign root_divisor = {root_q, 2'b01};
  assign root_next = {root_q[38:0], root_trial >= root_divisor};
  assign root_remainder_next = root_trial >= root_divisor ?
                               root_trial - root_divisor : root_trial;

  always_ff @(posedge clk_i) begin
    if (!rst_ni || abort_i) begin
      busy_o <= 1'b0;
      done_o <= 1'b0;
      error_o <= 1'b0;
      result_o <= '0;
      remainder_o <= '0;
      op_q <= '0;
      count_q <= '0;
      operand_q <= '0;
      product_q <= '0;
      quotient_q <= '0;
      division_remainder_q <= '0;
      radicand_q <= '0;
      root_q <= '0;
      root_remainder_q <= '0;
    end else begin
      done_o <= 1'b0;
      if (start_i && !busy_o) begin
        error_o <= 1'b0;
        op_q <= op_i;
        count_q <= '0;
        operand_q <= op_i == 2'd0 ? a_i : b_i;
        product_q <= {64'h0, b_i};
        quotient_q <= a_i;
        division_remainder_q <= '0;
        radicand_q <= radicand_i;
        root_q <= '0;
        root_remainder_q <= '0;
        if (op_i == 2'd3 || (op_i == 2'd1 && b_i == 0)) begin
          busy_o <= 1'b0;
          done_o <= 1'b1;
          error_o <= 1'b1;
          result_o <= '0;
          remainder_o <= '0;
        end else begin
          busy_o <= 1'b1;
        end
      end else if (busy_o) begin
        count_q <= count_q + 1'b1;
        unique case (op_q)
          2'd0: begin
            product_q <= product_next;
            if (count_q == 6'd63) begin
              busy_o <= 1'b0;
              done_o <= 1'b1;
              result_o <= product_next[63:0];
              remainder_o <= 64'h0;
              error_o <= |product_next[127:64];
            end
          end
          2'd1: begin
            // A successful subtraction yields remainder < divisor <= 2^64-1.
            assert (division_difference[65] || !division_difference[64]);
            quotient_q <= quotient_next;
            division_remainder_q <= division_remainder_next;
            if (count_q == 6'd63) begin
              busy_o <= 1'b0;
              done_o <= 1'b1;
              result_o <= quotient_next;
              remainder_o <= division_remainder_next;
            end
          end
          2'd2: begin
            root_q <= root_next;
            // Before the last iteration the remainder fits 40 bits. The
            // complete final 42-bit remainder goes straight to the result.
            root_remainder_q <= root_remainder_next[39:0];
            radicand_q <= {radicand_q[77:0], 2'b00};
            if (count_q == 6'd39) begin
              busy_o <= 1'b0;
              done_o <= 1'b1;
              result_o <= {24'h0, root_next};
              remainder_o <= {22'h0, root_remainder_next};
            end
          end
          default: begin
            busy_o <= 1'b0;
            done_o <= 1'b1;
            error_o <= 1'b1;
          end
        endcase
      end
    end
  end
endmodule
