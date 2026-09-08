// Check the explicit single-clock contract, including write-priority holds.
// This does NOT establish that arbitrary old 1W2R consumers can use it.
module sram_1x_case #(
  parameter integer WIDTH=32, DEPTH=2048, PORTS=2,
  parameter integer AW=$clog2(DEPTH), MW=(WIDTH+7)/8
) (input wire clk, rst_n, output reg done=0, retained=0);
  reg [PORTS-1:0] ren=0;
  reg [PORTS*AW-1:0] raddr=0;
  reg [AW-1:0] waddr=0;
  reg [WIDTH-1:0] wdata=0;
  reg [MW-1:0] mask=0;
  wire [PORTS*WIDTH-1:0] actual;
  reg [WIDTH-1:0] reference [DEPTH];
  reg [WIDTH-1:0] expected [PORTS];
  reg [PORTS-1:0] valid=0;
  integer reads=0, writes=0, conflicts=0, holds=0;
  pa_m6_sram_1w2r #(.WIDTH(WIDTH), .DEPTH(DEPTH), .READ_PORTS(PORTS)) dut (
    .clk_sys_i(clk), .clk_mem_i(1'b0), .rst_ni(rst_n),
    .rd_en_i(ren), .rd_addr_i(raddr), .rd_data_o(actual),
    .wr_mask_i(mask), .wr_addr_i(waddr), .wr_data_i(wdata));
  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) valid <= 0;
    else begin
      if (|mask) begin
        writes++;
        if (|ren) conflicts++;
        for (integer b=0; b<WIDTH; b++)
          if (mask[b/8]) reference[waddr][b] <= wdata[b];
      end
      for (integer p=0; p<PORTS; p++) begin
        if (!(|mask) && ren[p]) begin
          expected[p] <= reference[raddr[p*AW+:AW]];
          valid[p] <= 1;
          reads++;
        end else if (valid[p]) holds++;
      end
    end
  end
  always @(negedge clk) if (rst_n)
    for (integer p=0; p<PORTS; p++) if (valid[p])
      assert(actual[p*WIDTH+:WIDTH] === expected[p])
        else $fatal(1,"1x width=%0d depth=%0d port=%0d actual=%h expected=%h",
                    WIDTH,DEPTH,p,actual[p*WIDTH+:WIDTH],expected[p]);
  task cycle;
    @(posedge clk); #1;
    // Exercise true synchronous capture, not combinational live commands.
    ren=0; mask=0; raddr='1; waddr='1; wdata=~wdata;
    @(negedge clk); #1;
  endtask
  initial begin
    wait(rst_n); @(negedge clk); #1;
    for (integer a=0; a<DEPTH; a++) begin
      waddr=AW'(a); wdata=WIDTH'(64'h31feca5eac3471d9 ^ 64'(a*7919)); mask='1;
      cycle();
    end
    for (integer i=0; i<1200; i++) begin
      for (integer p=0; p<PORTS; p++) begin
        ren[p]=(i%5 != 4);
        raddr[p*AW+:AW]=AW'((i*509+p*511)%DEPTH);
      end
      waddr=AW'(i%DEPTH); wdata=WIDTH'(64'hbae8735cdca74198 ^ 64'(i*317));
      mask=(i%3==0) ? MW'(i/3) : 0;
      cycle();
    end
    ren=0; mask=0; repeat(3) cycle();
    if (reads==0 || writes==0 || conflicts==0 || holds==0) $fatal(1,"missing 1x coverage");
    $display("M6 SRAM 1X PASS width=%0d depth=%0d ports=%0d reads=%0d writes=%0d conflicts=%0d holds=%0d",
              WIDTH,DEPTH,PORTS,reads,writes,conflicts,holds);
    done=1;
    @(negedge rst_n); @(posedge rst_n); @(negedge clk); #1;
    for (integer i=0; i<80; i++) begin
      ren='1;
      for (integer p=0; p<PORTS; p++) raddr[p*AW+:AW]=AW'((i*509+p*511)%DEPTH);
      cycle();
    end
    $display("M6 SRAM 1X RETENTION PASS width=%0d depth=%0d",WIDTH,DEPTH);
    retained=1;
  end
endmodule

module sram_1x_tb;
  reg clk=0, rst_n=1;
  wire [2:0] done, retained;
  always #5 clk=~clk;
  sram_1x_case #(.WIDTH(32),.DEPTH(2048),.PORTS(2)) a(clk,rst_n,done[0],retained[0]);
  sram_1x_case #(.WIDTH(36),.DEPTH(256),.PORTS(1)) b(clk,rst_n,done[1],retained[1]);
  sram_1x_case #(.WIDTH(32),.DEPTH(16384),.PORTS(2)) c(clk,rst_n,done[2],retained[2]);
  initial begin
    // An explicit reset edge avoids relying on simulator X-initial events.
    #1 rst_n=0;
    #11 rst_n=1;
    wait(&done); @(negedge clk); #1 rst_n=0;
    #20 rst_n=1;
    wait(&retained);
    $display("M6 SINGLE-CLOCK STORAGE CONTRACT PASS; CONSUMER REFINEMENT SEPARATE");
    $finish;
  end
  initial begin #300000; $fatal(1,"1x timeout"); end
endmodule
