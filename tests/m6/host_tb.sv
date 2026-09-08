`timescale 1ns/1ps
module host_tb;
  reg clk=0; always #5 clk=~clk;
  reg rstn=0, csn=1, sclk=0, mosi=0;
  wire miso, req_valid, req_ready, req_write, rsp_valid;
  wire [3:0] req_mask;
  wire [31:0] req_addr, req_data, rsp_data;
  wire [1:0] rsp_error;
  wire cluster_rstn, core_rstn, enable, flush, abort_mem, tx;
  wire [31:0] table_base, arena_bytes;
  wire [16:0] awaddr, araddr;
  wire awvalid, wvalid, arvalid, bready, rready;
  wire [31:0] wdata;
  wire [3:0] wstrb;
  reg awready=0, wready=0, arready=0, bvalid=0, rvalid=0;
  reg [1:0] bresp=0, rresp=0;
  reg [31:0] rdata=0;
  reg [31:0] memory [0:63];
  reg got_aw=0, got_w=0, stall_response=0;
  reg [16:0] saved_aw;
  reg [31:0] saved_w;
  reg [3:0] saved_mask;
  integer cycles=0, writes=0, reads=0, console_count=2, console_index=0;
  reg [7:0] console [0:1];
  pa_m6_spi spi(.clk_i(clk), .rst_ni(rstn), .cs_ni(csn), .sclk_i(sclk),
    .mosi_i(mosi), .miso_o(miso), .req_valid_o(req_valid), .req_write_o(req_write),
    .req_mask_o(req_mask), .req_addr_o(req_addr), .req_data_o(req_data),
    .req_ready_i(req_ready), .rsp_valid_i(rsp_valid), .rsp_error_i(rsp_error), .rsp_data_i(rsp_data));
  pa_m6_host host(.clk_i(clk), .rst_ni(rstn), .req_valid_i(req_valid),
    .req_write_i(req_write), .req_mask_i(req_mask), .req_addr_i(req_addr), .req_data_i(req_data),
    .req_ready_o(req_ready), .rsp_valid_o(rsp_valid), .rsp_error_o(rsp_error), .rsp_data_o(rsp_data),
    .cluster_aresetn_o(cluster_rstn), .core_aresetn_o(core_rstn), .cfg_enable_o(enable),
    .cfg_flush_o(flush), .memory_abort_o(abort_mem), .cfg_table_base_o(table_base),
    .cfg_arena_bytes_o(arena_bytes), .status_i(8'h25), .awaddr_o(awaddr), .araddr_o(araddr),
    .awvalid_o(awvalid), .wvalid_o(wvalid), .arvalid_o(arvalid), .awready_i(awready),
    .wready_i(wready), .arready_i(arready), .wdata_o(wdata), .wstrb_o(wstrb),
    .bresp_i(bresp), .rresp_i(rresp), .bvalid_i(bvalid), .rvalid_i(rvalid), .rdata_i(rdata),
    .bready_o(bready), .rready_o(rready), .uart_tx_o(tx));

  // Independently backpressured AXI-Lite endpoint. AW/W can arrive in either
  // order; responses remain asserted until ready, including forced stalls.
  always @(posedge clk) begin
    cycles <= cycles+1;
    awready <= !got_aw && cycles%7 == 0;
    wready <= !got_w && cycles%5 == 0;
    arready <= !rvalid && cycles%3 == 0;
    if (!rstn) begin
      got_aw <= 0; got_w <= 0; bvalid <= 0; rvalid <= 0;
    end else begin
      if (awvalid && awready) begin saved_aw <= awaddr; got_aw <= 1; end
      if (wvalid && wready) begin saved_w <= wdata; saved_mask <= wstrb; got_w <= 1; end
      if (got_aw && got_w && !bvalid && !stall_response) begin
        if (saved_aw < 256)
          for (integer b=0; b<4; b=b+1)
            if (saved_mask[b]) memory[saved_aw[7:2]][8*b+:8] <= saved_w[8*b+:8];
        bvalid <= 1; bresp <= 0; writes <= writes+1;
        got_aw <= 0; got_w <= 0;
      end
      if (bvalid && bready) bvalid <= 0;
      if (arvalid && arready) begin
        rvalid <= 1; rresp <= 0; reads <= reads+1;
        if (araddr == 17'h11004) rdata <= 32'(console_count);
        else if (araddr == 17'h11000) begin
          rdata <= {24'b0, console[console_index]};
          console_count <= console_count-1; console_index <= console_index+1;
        end else if (araddr < 256) rdata <= memory[araddr[7:2]];
        else begin rdata <= 0; rresp <= 2; end
      end
      if (rvalid && rready) rvalid <= 0;
    end
  end

  task automatic frame(input [7:0] command, input [31:0] address, data,
                       input integer length, output reg [71:0] received);
    reg [71:0] send_bits;
    send_bits={command,address,data}; received=0;
    sclk=0; csn=0; #53;
    for (integer bitno=0; bitno<length; bitno=bitno+1) begin
      mosi=bitno<72 ? send_bits[71-bitno] : 0;
      #47; sclk=1; received={received[70:0],miso};
      #47; sclk=0;
    end
    #53; csn=1; #103;
  endtask
  task automatic transaction(input [7:0] command, input [31:0] address, data,
                             input [1:0] error_expected, output reg [31:0] value);
    reg [71:0] reply;
    frame(command,address,data,72,reply);
    for (integer attempt=0; attempt<40; attempt=attempt+1) begin
      frame(0,0,0,72,reply);
      if (reply[71]) begin
        if (reply[70] || reply[69] || reply[65:64] != error_expected)
          $fatal(1,"bad SPI response %h address=%h",reply,address);
        value=reply[63:32]; return;
      end
    end
    $fatal(1,"SPI response timeout");
  endtask
  task automatic write_word(input [31:0] address, data, input [3:0] mask);
    reg [31:0] value;
    transaction(8'h90|{4'b0,mask},address,data,0,value);
  endtask
  reg [31:0] value, expected;
  reg [71:0] reply;
  integer before_writes;
  reg [7:0] uart_bytes [0:1];
  integer uart_count=0;
  // UART sampling is independent of the transmitter's internal state.
  initial begin
    wait(rstn);
    forever begin
      @(negedge tx); #120;
      for (integer b=0; b<8; b=b+1) begin
        if (uart_count >= 2) $fatal(1,"extra UART byte");
        uart_bytes[uart_count][b]=tx; #80;
      end
      if (!tx) $fatal(1,"UART stop bit");
      uart_count=uart_count+1;
    end
  end
  initial begin
    for (integer i=0;i<64;i=i+1) memory[i]=0;
    console[0]="M"; console[1]="6";
    #81; rstn=1; #103;
    transaction(8'h80,32'h20000,0,0,value);
    if(value!=32'h10 || core_rstn || cluster_rstn || !abort_mem) $fatal(1,"reset controls");
    transaction(8'h80,0,0,2,value); // Cluster held in reset: no hanging AXI read.
    write_word(32'h20000,32'h11,15);
    expected=0;
    for (integer mask=0;mask<16;mask=mask+1) begin
      write_word(0,32'h87654321 ^ (32'h1020304*32'(mask)),4'(mask));
      for(integer b=0;b<4;b=b+1)
        if((mask & (1<<b)) != 0) expected[8*b+:8]=8'((32'h87654321 ^ (32'h1020304*32'(mask))) >> (8*b));
      transaction(8'h80,0,0,0,value);
      if(value!==expected) $fatal(1,"byte mask %0d got=%h expected=%h",mask,value,expected);
    end
    transaction(8'h80,1,0,3,value);
    transaction(8'h80,32'h20014,0,3,value);
    transaction(8'h80,32'h100,0,2,value);
    transaction(8'h9f,32'h2000c,0,2,value);
    transaction(8'h9f,32'h20010,7,2,value);
    before_writes=writes;
    frame(8'h9f,0,32'hdeadbeef,31,reply);
    frame(8'h9f,0,32'hdeadbeef,73,reply);
    frame(0,0,0,72,reply);
    if(writes!=before_writes || !reply[69]) $fatal(1,"malformed frame committed");
    // Force a write response to stall, then reject a second command.
    stall_response=1;
    frame(8'h9f,4,32'h11223344,72,reply);
    frame(8'h9f,8,32'hbadbad00,72,reply);
    frame(0,0,0,72,reply);
    if(!reply[70] || !reply[69] || writes!=before_writes) $fatal(1,"busy reject");
    stall_response=0; #503;
    transaction(8'h80,4,0,0,value);
    if(value!=32'h11223344 || memory[2]!=0 || writes!=before_writes+1) $fatal(1,"overrun side effect");
    write_word(32'h20004,32'h12345678,15);
    write_word(32'h20004,32'hdeadbeef,5);
    if(table_base!=32'h12ad56ef) $fatal(1,"local mask");
    write_word(32'h20010,8,15);
    write_word(32'h20000,32'h31,15);
    repeat(4000) @(posedge clk);
    if(uart_count!=2 || uart_bytes[0]!="M" || uart_bytes[1]!="6" || console_count!=0)
      $fatal(1,"UART console drain");
    transaction(8'h80,32'h2000c,0,0,value);
    if(value!=32'h25) $fatal(1,"status readback");
    rstn=0; #103; rstn=1; #103;
    transaction(8'h80,32'h20000,0,0,value);
    if(value!=32'h10) $fatal(1,"reset recovery");
    $display("M6 HOST TRANSPORT PASS masks=16 malformed=2 busy_reject=1 uart_bytes=2 writes=%0d reads=%0d",writes,reads);
    $finish;
  end
  initial begin #5000000; $fatal(1,"bounded test timeout"); end
endmodule
