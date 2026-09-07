    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        mult_state_q <= ALBL;
        mac_phase_q <= '0;
        product_low_q <= '0;
        product_high_q <= '0;
        product_q <= '0;
      end else if (mult_en_internal) begin
        case (mac_phase_q)
          0: begin
            product_low_q <= $signed({1'b0, mult_op_a[7:0]}) * $signed({sign_b, mult_op_b});
            product_high_q <= $signed({sign_a, mult_op_a[15:8]}) * $signed({sign_b, mult_op_b});
            mac_phase_q <= 1;
          end
          1: begin
            product_q <= {{8{product_low_q[25]}}, product_low_q} + {product_high_q, 8'b0};
            mac_phase_q <= 2;
          end
          2: begin
            mult_state_q <= mult_state_d;
            mac_phase_q <= 0;
          end
          default: begin
            mult_state_q <= ALBL;
            mac_phase_q <= 0;
          end
        endcase
      end
    end
