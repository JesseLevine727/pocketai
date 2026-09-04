// PocketAI-T M1b -- AXI4-Lite slave bridge
//
// Presents an AXI4-Lite slave port and translates single-beat writes and
// reads into the simple "immediate grant, 1-cycle latency" host protocol
// used by the lowRISC `bus` module (the same protocol the Ibex cores use).
//
// Simplifications, per the M1b scope:
//   * no bursts (AXI4-Lite single transfers only)
//   * at most one outstanding transaction (writes and reads share one
//     request port; a new AW is only accepted once the previous
//     transaction has fully completed)
//   * ID / last signals are not present on AXI4-Lite
//   * internal bus errors are returned as AXI SLVERR (2)
//
// Channel ordering: while a write is in flight the AR channel is not
// accepted, and vice versa, which keeps the single host request port free
// of write/read arbitration issues.

module pa_axi_lite_bridge (
  input  logic        clk_i,
  input  logic        rst_ni,

  // AXI4-Lite slave interface
  input  logic [31:0] awaddr_i,
  input  logic        awvalid_i,
  output logic        awready_o,
  input  logic [31:0] wdata_i,
  input  logic [ 3:0] wstrb_i,
  input  logic        wvalid_i,
  output logic        wready_o,
  output logic [ 1:0] bresp_o,
  output logic        bvalid_o,
  input  logic        bready_i,
  input  logic [31:0] araddr_i,
  input  logic        arvalid_i,
  output logic        arready_o,
  output logic [31:0] rdata_o,
  output logic [ 1:0] rresp_o,
  output logic        rvalid_o,
  input  logic        rready_i,


  // Simple bus host port (immediate grant, 1-cycle latency)
  output logic        req_o,
  input  logic        gnt_i,
  output logic        we_o,
  output logic [ 3:0] be_o,
  output logic [31:0] addr_o,
  output logic [31:0] wdata_o,
  input  logic        rvalid_i,
  input  logic [31:0] rdata_i,
  input  logic        err_i
);

  typedef enum logic [2:0] {
    S_IDLE,     // accept AW (write) or AR (read)
    S_WAIT_W,   // AW accepted, waiting for W
    S_XFER,     // request driven to the bus, waiting for grant
    S_WWAIT,    // write request granted, waiting for bus completion/error
    S_BRESP,    // write done, B response
    S_RWAIT,    // read request granted, waiting for rvalid
    S_RRESP     // read done, R response
  } state_e;

  state_e      state_q;
  logic        we_q;
  logic [31:0] addr_q;
  logic [31:0] wdata_q;
  logic [ 3:0] wstrb_q;
  logic [31:0] rdata_q;
  logic        err_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= S_IDLE;
      we_q    <= 1'b0;
      addr_q  <= 32'h0;
      wdata_q <= 32'h0;
      wstrb_q <= 4'h0;
      rdata_q <= 32'h0;
      err_q   <= 1'b0;
    end else begin
      unique case (state_q)
        S_IDLE: begin
          err_q <= 1'b0;
          if (awvalid_i) begin
            state_q <= S_WAIT_W;
            addr_q  <= awaddr_i;
          end else if (arvalid_i) begin
            state_q <= S_XFER;
            we_q    <= 1'b0;
            addr_q  <= araddr_i;
          end
        end
        S_WAIT_W: begin
          if (wvalid_i) begin
            state_q <= S_XFER;
            we_q    <= 1'b1;
            wdata_q <= wdata_i;
            wstrb_q <= wstrb_i;
          end
        end
        S_XFER: begin
          if (gnt_i) begin
            state_q <= we_q ? S_WWAIT : S_RWAIT;
          end
        end
        S_WWAIT: begin
          if (rvalid_i) begin
            err_q   <= err_i;
            state_q <= S_BRESP;
          end
        end
        S_BRESP: begin
          if (bready_i) begin
            state_q <= S_IDLE;
          end
        end
        S_RWAIT: begin
          if (rvalid_i) begin
            rdata_q <= rdata_i;
            err_q   <= err_i;
            state_q <= S_RRESP;
          end
        end
        S_RRESP: begin
          if (rready_i) begin
            state_q <= S_IDLE;
          end
        end
        default: ;
      endcase
    end
  end

  assign awready_o = (state_q == S_IDLE);
  assign arready_o = (state_q == S_IDLE);
  assign wready_o  = (state_q == S_WAIT_W);
  assign bvalid_o  = (state_q == S_BRESP);
  assign bresp_o   = err_q ? 2'b10 : 2'b00;
  assign rvalid_o  = (state_q == S_RRESP);

  assign req_o   = (state_q == S_XFER);
  assign we_o    = we_q;
  assign be_o    = wstrb_q;
  assign addr_o  = addr_q;
  assign wdata_o = wdata_q;
  assign rdata_o = rdata_q;

  assign rresp_o = err_q ? 2'b10 : 2'b00;

endmodule
