// Single-outstanding mode-0 SPI register transport; see M6_CHIP_INTERFACE.md.
module pa_m6_spi (
  input wire clk_i, rst_ni, cs_ni, sclk_i, mosi_i,
  output wire miso_o,
  output reg req_valid_o, output reg req_write_o,
  output reg [3:0] req_mask_o,
  output reg [31:0] req_addr_o, req_data_o,
  input wire req_ready_i, rsp_valid_i,
  input wire [1:0] rsp_error_i,
  input wire [31:0] rsp_data_i
);
  (* async_reg = "true" *) reg [2:0] cs_q, sclk_q;
  (* async_reg = "true" *) reg [1:0] mosi_q;
  reg [71:0] rx_q, tx_q;
  reg [7:0] count_q;
  reg in_flight_q, response_valid_q, rejected_q;
  reg [1:0] response_error_q;
  reg [31:0] response_data_q;
  wire busy = req_valid_o || in_flight_q;
  wire [7:0] status = {response_valid_q, busy, rejected_q, 3'b0, response_error_q};
  assign miso_o = tx_q[71];
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cs_q <= 3'b111; sclk_q <= 0; mosi_q <= 0;
      rx_q <= 0; tx_q <= 0; count_q <= 0;
      req_valid_o <= 0; req_write_o <= 0; req_mask_o <= 0;
      req_addr_o <= 0; req_data_o <= 0;
      in_flight_q <= 0; response_valid_q <= 0; rejected_q <= 0;
      response_error_q <= 0; response_data_q <= 0;
    end else begin
      cs_q <= {cs_q[1:0], cs_ni};
      sclk_q <= {sclk_q[1:0], sclk_i};
      mosi_q <= {mosi_q[0], mosi_i};
      if (req_valid_o && req_ready_i) begin
        req_valid_o <= 0; in_flight_q <= 1;
      end
      if (rsp_valid_i) begin
        in_flight_q <= 0; response_valid_q <= 1;
        response_error_q <= rsp_error_i; response_data_q <= rsp_data_i;
      end
      if (cs_q[2:1] == 2'b10) begin
        rx_q <= 0; count_q <= 0;
        tx_q <= {status, response_data_q, 32'b0};
      end else if (!cs_q[2]) begin
        if (sclk_q[2:1] == 2'b01) begin
          rx_q <= {rx_q[70:0], mosi_q[1]};
          if (count_q != 255) count_q <= count_q+1'b1;
        end
        if (sclk_q[2:1] == 2'b10) tx_q <= {tx_q[70:0], 1'b0};
      end
      if (cs_q[2:1] == 2'b01) begin
        if (count_q != 72) rejected_q <= 1;
        else if (rx_q[71:64] == 8'h00) begin end // Non-destructive poll.
        else if ((rx_q[71:64] == 8'h80 || rx_q[71:68] == 4'h9) && !busy) begin
          req_write_o <= rx_q[68]; req_mask_o <= rx_q[67:64];
          req_addr_o <= rx_q[63:32]; req_data_o <= rx_q[31:0];
          req_valid_o <= 1; response_valid_q <= 0; rejected_q <= 0;
        end else rejected_q <= 1;
      end
    end
  end
endmodule
