`timescale 1ns/1ps

module pa_mailbox_tb;
  logic        clk;
  logic        rst_n;
  logic        req;
  logic        we;
  logic [ 3:0] be;
  logic [31:0] addr;
  logic [31:0] wdata;
  logic        rvalid;
  logic [31:0] rdata;
  logic        irq0;
  logic        irq1;

  pa_mailbox dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .req_i(req),
    .we_i(we),
    .be_i(be),
    .addr_i(addr),
    .wdata_i(wdata),
    .rvalid_o(rvalid),
    .rdata_o(rdata),
    .irq0_o(irq0),
    .irq1_o(irq1)
  );

  always #5 clk <= ~clk;

  task automatic bus_write(
      input logic [31:0] write_addr,
      input logic [31:0] write_data,
      input logic [3:0] write_be
  );
    @(negedge clk);
    req   = 1'b1;
    we    = 1'b1;
    addr  = write_addr;
    wdata = write_data;
    be    = write_be;
    @(posedge clk);
    #1;
    if (!rvalid) $fatal(1, "mailbox write did not complete");
    @(negedge clk);
    req = 1'b0;
    we  = 1'b0;
  endtask

  task automatic bus_read(
      input  logic [31:0] read_addr,
      output logic [31:0] read_data
  );
    @(negedge clk);
    req  = 1'b1;
    we   = 1'b0;
    addr = read_addr;
    be   = 4'b0000;
    @(posedge clk);
    #1;
    if (!rvalid) $fatal(1, "mailbox read did not complete");
    read_data = rdata;
    @(negedge clk);
    req = 1'b0;
  endtask

  task automatic expect_status(
      input logic [1:0] expected,
      input string check_name
  );
    logic [31:0] value;
    bus_read(32'h00012008, value);
    if (value !== {30'd0, expected}) begin
      $fatal(1, "%s: status=%08x expected=%08x", check_name, value,
             {30'd0, expected});
    end
    if ({irq0, irq1} !== {expected[1], expected[0]}) begin
      $fatal(1, "%s: irq0=%0d irq1=%0d", check_name, irq0, irq1);
    end
  endtask

  initial begin
    logic [31:0] value;

    clk   = 1'b0;
    rst_n = 1'b0;
    req   = 1'b0;
    we    = 1'b0;
    be    = 4'b0000;
    addr  = 32'h0;
    wdata = 32'h0;

    repeat (3) @(posedge clk);
    @(negedge clk);
    rst_n = 1'b1;

    expect_status(2'b00, "after reset");

    bus_write(32'h00012000, 32'h11223344, 4'b1111);
    expect_status(2'b01, "0-to-1 pending");
    bus_write(32'h0001200c, 32'h00000001, 4'b0001);
    expect_status(2'b00, "0-to-1 acknowledged");

    bus_write(32'h00012000, 32'hAABBCCDD, 4'b0101);
    bus_read(32'h00012000, value);
    if (value !== 32'h11BB33DD) begin
      $fatal(1, "byte merge=%08x expected=11bb33dd", value);
    end

    bus_write(32'h00012004, 32'h55667788, 4'b1111);
    expect_status(2'b11, "both pending");
    bus_write(32'h0001200c, 32'h00000001, 4'b0001);
    expect_status(2'b10, "only 0-to-1 acknowledged");
    bus_write(32'h0001200c, 32'h00000002, 4'b0001);
    expect_status(2'b00, "both acknowledged");

    $display("MAILBOX PASS");
    $finish;
  end
endmodule
