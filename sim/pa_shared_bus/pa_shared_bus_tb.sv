`timescale 1ns/1ps

// Regression for hosts that legally keep req asserted across back-to-back
// transfers.  The address changes only after the first grant edge; the bus
// must accept both requests without requiring an intervening low req cycle.
module pa_shared_bus_tb;
  localparam int unsigned NrHosts = 1;
  localparam int unsigned NrDevices = 1;

  logic clk = 1'b0;
  logic rst_n = 1'b0;

  logic        host_req    [NrHosts];
  logic        host_gnt    [NrHosts];
  logic [31:0] host_addr   [NrHosts];
  logic        host_we     [NrHosts];
  logic [ 3:0] host_be     [NrHosts];
  logic [31:0] host_wdata  [NrHosts];
  logic        host_rvalid [NrHosts];
  logic [31:0] host_rdata  [NrHosts];
  logic        host_err    [NrHosts];

  logic        device_req    [NrDevices];
  logic [31:0] device_addr   [NrDevices];
  logic        device_we     [NrDevices];
  logic [ 3:0] device_be     [NrDevices];
  logic [31:0] device_wdata  [NrDevices];
  logic        device_rvalid [NrDevices];
  logic [31:0] device_rdata  [NrDevices];
  logic        device_err    [NrDevices];

  logic [31:0] cfg_device_addr_base [NrDevices];
  logic [31:0] cfg_device_addr_mask [NrDevices];

  always #5 clk <= ~clk;

  pa_shared_bus #(
    .NrDevices(NrDevices),
    .NrHosts(NrHosts)
  ) dut (.*,
    .clk_i(clk),
    .rst_ni(rst_n),
    .host_req_i(host_req),
    .host_gnt_o(host_gnt),
    .host_addr_i(host_addr),
    .host_we_i(host_we),
    .host_be_i(host_be),
    .host_wdata_i(host_wdata),
    .host_rvalid_o(host_rvalid),
    .host_rdata_o(host_rdata),
    .host_err_o(host_err),
    .device_req_o(device_req),
    .device_addr_o(device_addr),
    .device_we_o(device_we),
    .device_be_o(device_be),
    .device_wdata_o(device_wdata),
    .device_rvalid_i(device_rvalid),
    .device_rdata_i(device_rdata),
    .device_err_i(device_err)
  );

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      device_rvalid[0] <= 1'b0;
      device_rdata[0]  <= '0;
    end else begin
      device_rvalid[0] <= device_req[0];
      if (device_req[0]) device_rdata[0] <= device_addr[0];
    end
  end

  task automatic wait_grant(input logic [31:0] expected_addr);
    int unsigned cycles;
    cycles = 0;
    while (!host_gnt[0] && cycles < 10) begin
      @(negedge clk);
      cycles++;
    end
    if (!host_gnt[0]) $fatal(1, "request was not granted");
    if (!device_req[0] || device_addr[0] !== expected_addr ||
        device_we[0] !== 1'b0 || device_be[0] !== 4'h0 ||
        device_wdata[0] !== 32'h0) begin
      $fatal(1, "device request mismatch: req=%0d addr=%08x we=%0d be=%x wdata=%08x",
             device_req[0], device_addr[0], device_we[0], device_be[0],
             device_wdata[0]);
    end
  endtask

  task automatic wait_response(input logic [31:0] expected_data);
    int unsigned cycles;
    cycles = 0;
    while (!host_rvalid[0] && cycles < 10) begin
      @(negedge clk);
      cycles++;
    end
    if (!host_rvalid[0]) $fatal(1, "request did not receive a response");
    if (host_err[0] || host_rdata[0] !== expected_data) begin
      $fatal(1, "host response mismatch: err=%0d data=%08x expected=%08x",
             host_err[0], host_rdata[0], expected_data);
    end
  endtask

  initial begin
    host_req[0]   = 1'b0;
    host_addr[0]  = 32'h0;
    host_we[0]    = 1'b0;
    host_be[0]    = 4'h0;
    host_wdata[0] = 32'h0;
    device_err[0] = 1'b0;
    cfg_device_addr_base[0] = 32'h0;
    cfg_device_addr_mask[0] = 32'hFFFF_0000;

    repeat (3) @(posedge clk);
    rst_n = 1'b1;
    @(posedge clk);

    host_addr[0] = 32'h0000_0040;
    host_req[0]  = 1'b1;
    wait_grant(32'h0000_0040);

    // Hold req high, as Ibex may do, and present the next transfer after the
    // edge that accepts the first one.
    host_addr[0] = 32'h0000_0080;
    wait_response(32'h0000_0040);
    wait_grant(32'h0000_0080);
    wait_response(32'h0000_0080);

    host_req[0] = 1'b0;
    $display("PA_SHARED_BUS PASS");
    $finish;
  end
endmodule
