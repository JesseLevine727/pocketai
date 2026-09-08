`timescale 1ns/1ps
module memory_case #(
  parameter integer WIDTH=32, DEPTH=768, PORTS=2,
  parameter integer AW=$clog2(DEPTH), MW=(WIDTH+7)/8
) (input wire clk_mem, clk_sys, rst_n, output reg done=0, output reg retained=0);
  reg [PORTS-1:0] ren=0;
  reg [PORTS*AW-1:0] raddr=0;
  reg [AW-1:0] waddr=0;
  reg [WIDTH-1:0] wdata=0;
  reg [MW-1:0] mask=0;
  wire [PORTS*WIDTH-1:0] actual;
  reg [WIDTH-1:0] reference [DEPTH];
  reg [WIDTH-1:0] expected [PORTS];
  reg [PORTS-1:0] valid=0;
  integer checks=0, collisions=0, held=0, masked=0;
  pa_m6_sram_1w2r #(.WIDTH(WIDTH), .DEPTH(DEPTH), .ADDR_WIDTH(AW), .READ_PORTS(PORTS)) dut (
    .clk_sys_i(clk_sys), .clk_mem_i(clk_mem), .rst_ni(rst_n),
    .rd_en_i(ren), .rd_addr_i(raddr), .rd_data_o(actual),
    .wr_mask_i(mask), .wr_addr_i(waddr), .wr_data_i(wdata));
  // This independent phase state must stay complementary to the actual
  // divider through both initial reset and reset-with-provisioned-data.
  always @(negedge clk_mem) begin
    #1;
    if (dut.write_phase_q !== !clk_sys)
      $fatal(1,"separate SRAM data phase lost divider alignment");
  end
  always @(posedge clk_sys or negedge rst_n) if (!rst_n) valid <= 0; else begin
    for (integer p=0; p<PORTS; p=p+1) begin
      if (ren[p]) begin
        expected[p] <= reference[raddr[p*AW+:AW]];
        valid[p] <= 1;
        if ((|mask) && raddr[p*AW+:AW] == waddr) collisions = collisions+1;
      end else if (valid[p]) held = held+1;
    end
    for (integer bitno=0; bitno<WIDTH; bitno=bitno+1)
      if (mask[bitno/8]) reference[waddr][bitno] <= wdata[bitno];
    if (mask != 0 && mask != {MW{1'b1}}) masked = masked+1;
  end
  // Read service occurs within the cycle; compare before the next sampling edge.
  always @(negedge clk_sys) begin
    #1;
    if (rst_n) for (integer p=0; p<PORTS; p=p+1)
      if (valid[p]) begin
        checks=checks+1;
        if (actual[p*WIDTH+:WIDTH] !== expected[p])
          $fatal(1,"WIDTH=%0d DEPTH=%0d port=%0d actual=%h expected=%h",WIDTH,DEPTH,p,actual[p*WIDTH+:WIDTH],expected[p]);
      end
  end
  task cycle;
    @(posedge clk_sys);
    // Deliberately disturb the external commands after capture. The SRAM
    // read/write phases must use captured commands, not these live inputs.
    #1;
    raddr=~raddr; waddr=~waddr; wdata=~wdata; mask=0; ren=0;
    @(negedge clk_sys); #2;
  endtask
  initial begin
    wait(rst_n);
    @(negedge clk_sys); #2;
    for (integer a=0; a<DEPTH; a=a+1) begin
      ren=0; waddr=AW'(a); wdata=WIDTH'(64'h9e3779b9e13579bd ^ 64'(a)); mask='1;
      cycle();
    end
    for (integer i=0; i<600; i=i+1) begin
      waddr=AW'(i%DEPTH);
      // Every supported byte mask; full-depth boundaries and collisions.
      mask=MW'(i); wdata=WIDTH'(64'hfca8517391badcfe ^ (i*7919));
      for (integer p=0; p<PORTS; p=p+1) begin
        ren[p]=(i%5 != 4);
        raddr[p*AW+:AW] = AW'((i%3==0) ? (i%DEPTH) : ((i*509+p*511) % DEPTH));
      end
      cycle();
    end
    ren=0; mask=0;
    repeat(3) cycle();
    if (checks==0 || collisions==0 || held==0 || masked==0) $fatal(1,"missing test coverage");
    $display("M6 SRAM ADAPTER PASS width=%0d depth=%0d ports=%0d checks=%0d collisions=%0d hold=%0d masks=%0d",
      WIDTH,DEPTH,PORTS,checks,collisions,held,masked);
    done=1;
    // System reset invalidates pending reads, not the provisioned SRAM data.
    @(negedge rst_n); @(posedge rst_n); @(negedge clk_sys); #2;
    for (integer i=0; i<80; i=i+1) begin
      ren='1; mask=0;
      for (integer p=0; p<PORTS; p=p+1) raddr[p*AW+:AW]=AW'((i*509+p*511)%DEPTH);
      cycle();
    end
    $display("M6 SRAM RESET RETENTION PASS width=%0d depth=%0d ports=%0d",WIDTH,DEPTH,PORTS);
    retained=1;
  end
endmodule

module sram_adapter_tb;
  reg clk_mem=0, rst_n=0;
  wire clk_sys;
  wire [2:0] done, retained;
  always #10 clk_mem=~clk_mem;
  pa_m6_clocking clocking_i(.clk_mem_i(clk_mem), .rst_ni(rst_n), .clk_sys_o(clk_sys));
  memory_case #(.WIDTH(32), .DEPTH(768), .PORTS(2)) a(clk_mem,clk_sys,rst_n,done[0],retained[0]);
  memory_case #(.WIDTH(36), .DEPTH(256), .PORTS(1)) b(clk_mem,clk_sys,rst_n,done[1],retained[1]);
  memory_case #(.WIDTH(32), .DEPTH(16384), .PORTS(2)) c(clk_mem,clk_sys,rst_n,done[2],retained[2]);
  initial begin
    #45 rst_n=1;
    wait(&done);
    @(negedge clk_sys); #2 rst_n=0;
    #80 rst_n=1;
    wait(&retained);
    $display("M6 MEMORY PHASE CONTRACT PASS");
    $finish;
  end
  initial begin #2000000; $fatal(1,"timeout"); end
endmodule
