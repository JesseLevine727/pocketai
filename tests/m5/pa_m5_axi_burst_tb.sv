module pa_m5_axi_burst_tb;
  logic clk_i = 0, rst_ni = 0;
  always #5 clk_i <= ~clk_i;
  logic abort_i = 0, cmd_valid_i = 0, cmd_ready_o;
  logic [31:0] cmd_addr_i = 0;
  logic [8:0] cmd_words_i = 0;
  logic cmd_write_i = 0;
  logic in_valid_i = 0, in_ready_o;
  logic [31:0] in_data_i = 0;
  logic [3:0] in_strb_i = 0;
  logic out_valid_o, out_ready_i = 0, out_last_o;
  logic [31:0] out_data_o;
  logic done_valid_o, done_ready_i = 0, busy_o, poisoned_o;
  logic [3:0] done_fault_o;
  logic [31:0] m_awaddr_o, m_wdata_o, m_araddr_o;
  logic [7:0] m_awlen_o, m_arlen_o;
  logic [2:0] m_awsize_o, m_awprot_o, m_arsize_o, m_arprot_o;
  logic [1:0] m_awburst_o, m_arburst_o;
  logic [3:0] m_awcache_o, m_wstrb_o, m_arcache_o;
  logic m_awid_o, m_awvalid_o, m_awready_i = 0;
  logic m_wlast_o, m_wvalid_o, m_wready_i = 0;
  logic [1:0] m_bresp_i = 0;
  logic m_bid_i = 0, m_bvalid_i = 0, m_bready_o;
  logic m_arid_o, m_arvalid_o, m_arready_i = 0;
  logic [31:0] m_rdata_i = 0;
  logic [1:0] m_rresp_i = 0;
  logic m_rid_i = 0, m_rlast_i = 0, m_rvalid_i = 0, m_rready_o;
  int cases = 0, write_beats = 0, read_beats = 0;
  pa_m5_axi_burst dut (.*);

  // These properties also cover abort while a bus channel is stalled.
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    m_awvalid_o && !m_awready_i |=> m_awvalid_o &&
    $stable({m_awaddr_o, m_awlen_o, m_awsize_o, m_awburst_o,
             m_awcache_o, m_awprot_o, m_awid_o}));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    m_arvalid_o && !m_arready_i |=> m_arvalid_o &&
    $stable({m_araddr_o, m_arlen_o, m_arsize_o, m_arburst_o,
             m_arcache_o, m_arprot_o, m_arid_o}));
  assert property (@(posedge clk_i) disable iff (!rst_ni)
    m_wvalid_o && !m_wready_i |=> m_wvalid_o &&
    $stable({m_wdata_o, m_wstrb_o, m_wlast_o}));

  function automatic logic [31:0] pattern(input logic [31:0] addr, input int idx);
    return addr ^ 32'hcbaf0000 ^ (32'(idx) * 32'h10201);
  endfunction
  task automatic tick;
    @(posedge clk_i); #1;
  endtask
  task automatic launch(input logic [31:0] addr, input logic [8:0] words,
                        input bit write_access);
    @(negedge clk_i);
    if (!cmd_ready_o || busy_o || poisoned_o) $fatal(1, "launch while not idle");
    cmd_valid_i = 1; cmd_addr_i = addr; cmd_words_i = words; cmd_write_i = write_access;
    tick();
    @(negedge clk_i); cmd_valid_i = 0;
  endtask
  task automatic finish(input logic [3:0] fault);
    int watchdog = 0;
    while (!done_valid_o) begin
      tick(); watchdog++;
      if (watchdog > 8) $fatal(1, "missing completion");
    end
    if (done_fault_o != fault || !busy_o || poisoned_o)
      $fatal(1, "bad completion: got %0d expected %0d", done_fault_o, fault);
    if (!abort_i) repeat (3) begin
      tick();
      if (!done_valid_o || done_fault_o != fault || !busy_o || cmd_ready_o)
        $fatal(1, "completion changed under backpressure");
    end
    @(negedge clk_i); done_ready_i = 1;
    tick();
    if (busy_o || done_valid_o || (abort_i && cmd_ready_o))
      $fatal(1, "completion did not retire / abort admission broken");
    @(negedge clk_i); done_ready_i = 0; abort_i = 0;
    cases++;
  endtask
  task automatic check_address(input bit write_access, input logic [31:0] addr,
                               input int words);
    if (write_access) begin
      if (!m_awvalid_o || m_awaddr_o != addr || int'(m_awlen_o) != words - 1 ||
          m_awsize_o != 2 || m_awburst_o != 1 || m_awcache_o != 0 ||
          m_awprot_o != 0 || m_awid_o != 0 || m_arvalid_o)
        $fatal(1, "bad AW descriptor");
    end else if (!m_arvalid_o || m_araddr_o != addr || int'(m_arlen_o) != words - 1 ||
                 m_arsize_o != 2 || m_arburst_o != 1 || m_arcache_o != 0 ||
                 m_arprot_o != 0 || m_arid_o != 0 || m_awvalid_o)
      $fatal(1, "bad AR descriptor");
  endtask

  // abort_phase: 1 AW stall, 2 W stall, 3 missing B. The input producer stops
  // after the payload has been buffered, so bus drain cannot depend on it.
  task automatic write_test(input int words, input logic [31:0] addr,
                            input int abort_phase = 0, input bit error_response = 0,
                            input bit bad_id = 0);
    int watchdog = 0;
    launch(addr, 9'(words), 1);
    while (!in_ready_o) begin
      tick(); watchdog++;
      if (watchdog > 5) $fatal(1, "write payload admission missing");
    end
    for (int i = 0; i < words; i++) begin
      repeat (i % 3) tick();
      if (m_awvalid_o || !in_ready_o) $fatal(1, "AW before full payload");
      @(negedge clk_i);
      in_valid_i = 1; in_data_i = pattern(addr, i); in_strb_i = 4'(i);
      tick();
      @(negedge clk_i); in_valid_i = 0;
    end
    if (abort_phase == 1) abort_i = 1;
    repeat (4) begin
      tick(); check_address(1, addr, words);
      if (!busy_o || done_valid_o) $fatal(1, "AW stall falsely quiescent");
    end
    @(negedge clk_i); m_awready_i = 1;
    tick();
    @(negedge clk_i); m_awready_i = 0;
    for (int i = 0; i < words; i++) begin
      if (abort_phase == 2 && i == words / 2) abort_i = 1;
      repeat (1 + i % 3) begin
        tick();
        if (!m_wvalid_o || m_wdata_o != pattern(addr, i) || m_wstrb_o != 4'(i) ||
            m_wlast_o != (i == words - 1) || !busy_o)
          $fatal(1, "bad/stalled W beat %0d", i);
      end
      @(negedge clk_i); m_wready_i = 1;
      tick(); write_beats++;
      @(negedge clk_i); m_wready_i = 0;
    end
    if (abort_phase == 3) abort_i = 1;
    repeat (7) begin
      tick();
      if (!busy_o || !m_bready_o || done_valid_o || m_wvalid_o)
        $fatal(1, "missing B incorrectly treated as drained");
    end
    @(negedge clk_i);
    m_bvalid_i = 1; m_bresp_i = error_response ? 2'b10 : 0; m_bid_i = bad_id;
    tick();
    @(negedge clk_i); m_bvalid_i = 0; m_bresp_i = 0; m_bid_i = 0;
    if (bad_id) check_poison();
    else finish(abort_phase != 0 ? 4'd11 : (error_response ? 4'd12 : 4'd0));
  endtask

  // abort_phase: 1 AR stall, 2 mid-R, 3 buffered output. Error injection is
  // independent of data values. A bad RLAST/ID is a protocol poison, not SLVERR.
  task automatic read_test(input int words, input logic [31:0] addr,
                           input int abort_phase = 0, input int error_index = -1,
                           input int malformed = 0);
    int watchdog = 0;
    launch(addr, 9'(words), 0);
    while (!m_arvalid_o) begin
      tick(); watchdog++;
      if (watchdog > 5) $fatal(1, "AR missing");
    end
    @(negedge clk_i);
    if (abort_phase == 1) abort_i = 1;
    repeat (4) begin
      tick(); check_address(0, addr, words);
      if (!busy_o || done_valid_o) $fatal(1, "AR stall falsely quiescent");
    end
    @(negedge clk_i); m_arready_i = 1;
    tick();
    @(negedge clk_i); m_arready_i = 0;
    for (int i = 0; i < words; i++) begin
      if (abort_phase == 2 && i == words / 2) abort_i = 1;
      repeat (1 + i % 3) begin
        tick();
        if (!busy_o || !m_rready_o || out_valid_o || done_valid_o)
          $fatal(1, "read failed to wait/drain independently of consumer");
      end
      @(negedge clk_i);
      m_rvalid_i = 1; m_rdata_i = pattern(addr, i);
      m_rresp_i = i == error_index ? 2'b11 : 0;
      m_rlast_i = (i == words - 1);
      if (malformed == 1 && i == 0) m_rlast_i = 1;
      if (malformed == 2 && i == words - 1) m_rlast_i = 0;
      m_rid_i = malformed == 3;
      tick(); read_beats++;
      @(negedge clk_i); m_rvalid_i = 0; m_rresp_i = 0; m_rlast_i = 0; m_rid_i = 0;
      if (poisoned_o) break;
    end
    if (malformed != 0) begin
      check_poison();
      return;
    end
    if (abort_phase < 1 || abort_phase == 3) begin
      if (error_index < 0) begin
        watchdog = 0;
        while (!out_valid_o) begin
          tick(); watchdog++;
          if (watchdog > 5) $fatal(1, "buffered read data missing");
        end
        if (abort_phase == 3) begin
          @(negedge clk_i); abort_i = 1;
        end else for (int i = 0; i < words; i++) begin
          repeat (1 + i % 3) begin
            tick();
            if (!out_valid_o || out_data_o != pattern(addr, i) ||
                out_last_o != (i == words - 1) || done_valid_o)
              $fatal(1, "bad/stalled buffered read beat %0d", i);
          end
          @(negedge clk_i); out_ready_i = 1;
          tick();
          @(negedge clk_i); out_ready_i = 0;
        end
      end else if (out_valid_o) $fatal(1, "errored read exposed payload");
    end
    finish(abort_phase != 0 ? 4'd11 : (error_index >= 0 ? 4'd12 : 4'd0));
  endtask

  task automatic check_poison;
    @(negedge clk_i); abort_i = 1;
    repeat (12) begin
      tick();
      if (!poisoned_o || !busy_o || done_valid_o || cmd_ready_o ||
          m_arvalid_o || m_awvalid_o || m_wvalid_o || done_fault_o != 13)
        $fatal(1, "malformed protocol incorrectly declared drained/recovered");
    end
    // Model a coordinated reset of BOTH master and downstream bus; this is not
    // evidence that resetting the master alone would drain a physical fabric.
    @(negedge clk_i); rst_ni = 0;
    tick();
    @(negedge clk_i); rst_ni = 1; abort_i = 0;
    cases++;
  endtask
  task automatic bad_command(input logic [31:0] addr, input logic [8:0] words);
    launch(addr, words, 0);
    repeat (2) begin
      tick();
      if (m_arvalid_o || m_awvalid_o) $fatal(1, "bad command reached AXI");
    end
    finish(10);
  endtask

  initial begin
    tick(); tick();
    @(negedge clk_i); rst_ni = 1;
    bad_command(32'h10000000, 0);
    bad_command(32'h10000000, 257);
    bad_command(32'h10000002, 1);
    bad_command(32'h10000ffc, 2);
    bad_command(32'hfffffffc, 2);
    // Abort before AXI while only part of a write has arrived.
    launch(32'h10000000, 8, 1);
    tick();
    @(negedge clk_i); in_valid_i = 1; in_data_i = 32'hdeadbeef; in_strb_i = 15;
    tick();
    @(negedge clk_i); in_valid_i = 0; abort_i = 1;
    if (m_awvalid_o) $fatal(1, "partial write issued AW");
    finish(11);
    // Abort in validation also creates no bus request.
    launch(32'h10000000, 1, 0);
    abort_i = 1;
    finish(11);
    for (int n = 1; n <= 256; n++) begin
      write_test(n, 32'h01000000 + (32'(n) << 12));
      read_test(n, 32'h02000000 + (32'(n) << 12));
    end
    read_test(1, 32'hfffffffc);
    write_test(1, 32'hfffffffc);
    for (int phase = 1; phase <= 3; phase++) begin
      write_test(17, 32'h03000000, phase);
      read_test(17, 32'h04000000, phase);
      write_test(1, 32'h03000000, phase);
      read_test(1, 32'h04000000, phase);
    end
    write_test(1, 32'h01000000, 0, 1);
    read_test(17, 32'h02000000, 0, 0);
    read_test(17, 32'h02000000, 0, 8);
    read_test(17, 32'h02000000, 0, 16);
    read_test(1, 32'h02000000, 0, 0);
    for (int malformed = 1; malformed <= 3; malformed++) begin
      read_test(4, 32'h02000000, 0, -1, malformed);
      read_test(1, 32'h02000000);
    end
    write_test(1, 32'h01000000, 0, 0, 1);
    write_test(2, 32'h01000000);
    $display("M5 BUFFERED AXI RTL PASS cases=%0d write_beats=%0d read_beats=%0d",
             cases, write_beats, read_beats);
    $finish;
  end
  initial begin
    #20000000;
    $fatal(1, "global timeout");
  end
endmodule
