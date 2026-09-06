// One owned request per Ibex port. A core-only reset must not reset this router.
module pa_m5_obi_router (
  input logic clk_i,
  input logic rst_ni,
  input logic stop_i,
  input logic host_req_i,
  output logic host_gnt_o,
  input logic [31:0] host_addr_i,
  input logic host_we_i,
  input logic [3:0] host_be_i,
  input logic [31:0] host_wdata_i,
  output logic host_rvalid_o,
  output logic [31:0] host_rdata_o,
  output logic host_err_o,
  output logic busy_o,
  // Downstream index 0 = existing local bus; index 1 = translated DDR.
  output logic target_req_o [2],
  input logic target_gnt_i [2],
  output logic [31:0] target_addr_o,
  output logic target_we_o,
  output logic [3:0] target_be_o,
  output logic [31:0] target_wdata_o,
  input logic target_rvalid_i [2],
  input logic [31:0] target_rdata_i [2],
  input logic target_err_i [2]
);
  typedef enum logic [1:0] {Idle, Send, WaitResponse, Respond} state_e;
  state_e state_q;
  logic route_q, we_q, error_q;
  logic [31:0] addr_q, data_q, response_q;
  logic [3:0] be_q;
  assign host_gnt_o = state_q == Idle && host_req_i && !stop_i;
  assign target_req_o[0] = state_q == Send && !route_q;
  assign target_req_o[1] = state_q == Send && route_q;
  assign target_addr_o = addr_q;
  assign target_we_o = we_q;
  assign target_be_o = be_q;
  assign target_wdata_o = data_q;
  assign host_rvalid_o = state_q == Respond;
  assign host_rdata_o = response_q;
  assign host_err_o = error_q;
  assign busy_o = state_q != Idle;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      state_q <= Idle;
      route_q <= 0; we_q <= 0; error_q <= 0;
      addr_q <= 0; data_q <= 0; response_q <= 0; be_q <= 0;
    end else case (state_q)
      Idle: if (host_gnt_o) begin
        route_q <= host_addr_i[31:28] == 4'h4;
        addr_q <= host_addr_i; data_q <= host_wdata_i;
        we_q <= host_we_i; be_q <= host_be_i;
        state_q <= Send;
      end
      Send: if (target_gnt_i[route_q]) state_q <= WaitResponse;
      WaitResponse: if (target_rvalid_i[route_q]) begin
        response_q <= target_rdata_i[route_q];
        error_q <= target_err_i[route_q];
        state_q <= Respond;
      end
      Respond: state_q <= Idle;
      default: state_q <= Idle;
    endcase
  end
endmodule
