// SPI register requests + optional UART console draining share one AXI-Lite
// master. The native AXI memory master remains independent and unchanged.
module pa_m6_host (
  input wire clk_i, rst_ni,
  input wire req_valid_i, req_write_i,
  input wire [3:0] req_mask_i,
  input wire [31:0] req_addr_i, req_data_i,
  output wire req_ready_o,
  output reg rsp_valid_o,
  output reg [1:0] rsp_error_o,
  output reg [31:0] rsp_data_o,
  output wire cluster_aresetn_o, core_aresetn_o, cfg_enable_o, cfg_flush_o, memory_abort_o,
  output reg [31:0] cfg_table_base_o, cfg_arena_bytes_o,
  input wire [7:0] status_i,
  output reg [16:0] awaddr_o, araddr_o,
  output reg awvalid_o, wvalid_o, arvalid_o,
  input wire awready_i, wready_i, arready_i,
  output reg [31:0] wdata_o,
  output reg [3:0] wstrb_o,
  input wire [1:0] bresp_i, rresp_i,
  input wire bvalid_i, rvalid_i,
  input wire [31:0] rdata_i,
  output wire bready_o, rready_o,
  output wire uart_tx_o
);
  localparam [2:0] IDLE=0, WRITE=1, WRITE_RESP=2, READ_ADDR=3, READ_RESP=4;
  reg [2:0] state_q;
  reg [31:0] control_q;
  reg [15:0] uart_divider_q;
  reg [9:0] poll_q;
  reg background_q, console_pending_q, console_data_q;
  reg uart_valid_q;
  reg [7:0] uart_data_q;
  wire uart_ready;
  assign req_ready_o = state_q == IDLE;
  assign bready_o = state_q == WRITE_RESP;
  assign rready_o = state_q == READ_RESP;
  assign cluster_aresetn_o = control_q[0];
  assign core_aresetn_o = control_q[1];
  assign cfg_enable_o = control_q[2];
  assign cfg_flush_o = control_q[3];
  assign memory_abort_o = control_q[4];
  pa_m6_uart_tx u_uart(.clk_i(clk_i), .rst_ni(rst_ni),
    .valid_i(uart_valid_q), .data_i(uart_data_q), .divider_i(uart_divider_q),
    .ready_o(uart_ready), .tx_o(uart_tx_o));

  function automatic [31:0] masked(input [31:0] old_value, new_value, input [3:0] mask);
    for (integer b=0; b<4; b=b+1)
      masked[b*8+:8] = mask[b] ? new_value[b*8+:8] : old_value[b*8+:8];
  endfunction
  wire [31:0] divider_next = masked({16'b0, uart_divider_q}, req_data_i, req_mask_i);

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= IDLE; control_q <= 32'h10;
      cfg_table_base_o <= 0; cfg_arena_bytes_o <= 32'h10000000;
      uart_divider_q <= 217; poll_q <= 0;
      background_q <= 0; console_pending_q <= 0; console_data_q <= 0;
      uart_valid_q <= 0; uart_data_q <= 0;
      rsp_valid_o <= 0; rsp_error_o <= 0; rsp_data_o <= 0;
      awaddr_o <= 0; araddr_o <= 0; wdata_o <= 0; wstrb_o <= 0;
      awvalid_o <= 0; wvalid_o <= 0; arvalid_o <= 0;
    end else begin
      rsp_valid_o <= 0; uart_valid_q <= 0; poll_q <= poll_q+1'b1;
      if (!control_q[5]) console_pending_q <= 0;
      case (state_q)
        IDLE: begin
          if (req_valid_i) begin
            background_q <= 0;
            if (req_addr_i[1:0] != 0 || req_addr_i > 32'h20010) begin
              rsp_valid_o <= 1; rsp_error_o <= 2'b11; rsp_data_o <= 0;
            end else if (req_addr_i[17]) begin
              rsp_valid_o <= 1; rsp_error_o <= 0; rsp_data_o <= 0;
              case (req_addr_i[4:0])
                0: begin
                  rsp_data_o <= control_q;
                  if (req_write_i) control_q <= masked(control_q, req_data_i, req_mask_i) & 32'h3f;
                end
                4: begin
                  rsp_data_o <= cfg_table_base_o;
                  if (req_write_i) cfg_table_base_o <= masked(cfg_table_base_o, req_data_i, req_mask_i);
                end
                8: begin
                  rsp_data_o <= cfg_arena_bytes_o;
                  if (req_write_i) cfg_arena_bytes_o <= masked(cfg_arena_bytes_o, req_data_i, req_mask_i);
                end
                12: begin
                  rsp_data_o <= {24'b0, status_i};
                  if (req_write_i) rsp_error_o <= 2'b10;
                end
                16: begin
                  rsp_data_o <= {16'b0, uart_divider_q};
                  if (req_write_i) begin
                    if (divider_next < 8 || divider_next > 65535) rsp_error_o <= 2'b10;
                    else uart_divider_q <= divider_next[15:0];
                  end
                end
                default: rsp_error_o <= 2'b11;
              endcase
            end else if (!control_q[0]) begin
              // No bus transaction may hang on a deliberately reset cluster.
              rsp_valid_o <= 1; rsp_error_o <= 2'b10; rsp_data_o <= 0;
            end else if (req_write_i) begin
              awaddr_o <= req_addr_i[16:0]; wdata_o <= req_data_i; wstrb_o <= req_mask_i;
              awvalid_o <= 1; wvalid_o <= 1; state_q <= WRITE;
            end else begin
              araddr_o <= req_addr_i[16:0]; arvalid_o <= 1; state_q <= READ_ADDR;
            end
          end else if (control_q[0] && control_q[5] && uart_ready && !uart_valid_q &&
                       (console_pending_q || poll_q == 0)) begin
            background_q <= 1; console_data_q <= console_pending_q;
            araddr_o <= console_pending_q ? 17'h11000 : 17'h11004;
            arvalid_o <= 1; state_q <= READ_ADDR;
            console_pending_q <= 0;
          end
        end
        WRITE: begin
          if (awvalid_o && awready_i) awvalid_o <= 0;
          if (wvalid_o && wready_i) wvalid_o <= 0;
          if ((!awvalid_o || awready_i) && (!wvalid_o || wready_i)) state_q <= WRITE_RESP;
        end
        WRITE_RESP: if (bvalid_i) begin
          rsp_valid_o <= 1; rsp_error_o <= bresp_i; rsp_data_o <= 0; state_q <= IDLE;
        end
        READ_ADDR: if (arready_i) begin arvalid_o <= 0; state_q <= READ_RESP; end
        READ_RESP: if (rvalid_i) begin
          state_q <= IDLE;
          if (!background_q) begin
            rsp_valid_o <= 1; rsp_error_o <= rresp_i; rsp_data_o <= rdata_i;
          end else if (rresp_i == 0 && control_q[5]) begin
            if (console_data_q) begin uart_data_q <= rdata_i[7:0]; uart_valid_q <= 1; end
            else console_pending_q <= rdata_i[15:0] != 0;
          end
        end
        default: state_q <= IDLE;
      endcase
    end
  end
endmodule
