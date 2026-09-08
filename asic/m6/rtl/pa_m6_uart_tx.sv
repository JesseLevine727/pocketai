// 8-N-1 transmitter. Divider is sampled once per accepted byte.
module pa_m6_uart_tx (
  input wire clk_i, rst_ni, valid_i,
  input wire [7:0] data_i,
  input wire [15:0] divider_i,
  output wire ready_o, output wire tx_o
);
  reg [9:0] frame_q;
  reg [3:0] bits_q;
  reg [15:0] count_q, divider_q;
  assign ready_o = bits_q == 0;
  assign tx_o = bits_q == 0 ? 1'b1 : frame_q[0];
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      frame_q <= 10'h3ff; bits_q <= 0; count_q <= 0; divider_q <= 8;
    end else if (ready_o) begin
      if (valid_i) begin
        frame_q <= {1'b1, data_i, 1'b0}; bits_q <= 10;
        divider_q <= divider_i < 8 ? 16'd8 : divider_i;
        count_q <= (divider_i < 8 ? 16'd8 : divider_i)-1'b1;
      end
    end else if (count_q == 0) begin
      frame_q <= {1'b1, frame_q[9:1]}; bits_q <= bits_q-1'b1;
      count_q <= divider_q-1'b1;
    end else count_q <= count_q-1'b1;
  end
endmodule
