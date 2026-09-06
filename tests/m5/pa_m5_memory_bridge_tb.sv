module pa_m5_memory_bridge_tb;
  logic clk_i = 0, rst_ni = 0;
  always #5 clk_i <= ~clk_i;
  logic cfg_enable_i = 1, cfg_flush_i = 0, flush_ready_o;
  logic [31:0] cfg_table_base_i = 32'h02000000, cfg_arena_bytes_i = 16384;
  logic abort_i = 0, req_valid_i = 0, req_ready_o;
  logic [31:0] req_addr_i = 0;
  logic [8:0] req_words_i = 0;
  logic req_write_i = 0;
  logic in_valid_i = 0, in_ready_o;
  logic [31:0] in_data_i = 0;
  logic [3:0] in_strb_i = 0;
  logic out_valid_o, out_ready_i = 0, out_last_o;
  logic [31:0] out_data_o;
  logic done_valid_o, done_ready_i = 0, busy_o, quiesced_o, poisoned_o;
  logic [3:0] done_fault_o;
  logic [31:0] m_awaddr_o, m_wdata_o, m_araddr_o;
  logic [7:0] m_awlen_o, m_arlen_o;
  logic [2:0] m_awsize_o, m_awprot_o, m_arsize_o, m_arprot_o;
  logic [1:0] m_awburst_o, m_arburst_o;
  logic [3:0] m_awcache_o, m_wstrb_o, m_arcache_o;
  logic m_awid_o, m_awvalid_o, m_awready_i;
  logic m_wlast_o, m_wvalid_o, m_wready_i;
  logic [1:0] m_bresp_i = 0;
  logic m_bid_i = 0, m_bvalid_i = 0, m_bready_o;
  logic m_arid_o, m_arvalid_o, m_arready_i;
  logic [31:0] m_rdata_i = 0;
  logic [1:0] m_rresp_i = 0;
  logic m_rid_i = 0, m_rlast_i = 0, m_rvalid_i = 0, m_rready_o;
  pa_m5_memory_bridge dut (.*);

  logic [31:0] ptes [4];
  logic [31:0] memory [4096], expected [4096];
  bit hold_addresses = 0, hold_responses = 0, error_table = 0, error_data = 0;
  bit bad_read_id = 0;
  bit read_active = 0, write_active = 0, pending_b = 0;
  logic [31:0] read_address = 0, write_address = 0;
  int read_index = 0, write_index = 0, read_count = 0, write_count = 0;
  int cycles = 0, cases = 0, table_reads = 0, data_reads = 0, writes = 0;
  assign m_arready_i = !read_active && !write_active && !pending_b && !m_bvalid_i &&
                       !hold_addresses && cycles % 3 != 0;
  assign m_awready_i = !read_active && !write_active && !pending_b && !m_bvalid_i &&
                       !hold_addresses && cycles % 4 != 0;
  assign m_wready_i = write_active && cycles % 3 != 0;

  function automatic bit is_table(input logic [31:0] addr);
    return addr >= 32'h02000000 && addr < 32'h02000010;
  endfunction
  function automatic int data_index(input logic [31:0] addr);
    if (addr < 32'h10000000 || addr >= 32'h10004000 || addr[1:0] != 0)
      $fatal(1, "AXI access escaped owned model pages: %h", addr);
    return int'((addr - 32'h10000000) >> 2);
  endfunction
  function automatic int expected_index(input logic [31:0] virtual_address);
    logic [31:0] physical;
    physical = (ptes[(virtual_address - 32'h40000000) >> 12] & 32'hfffff000) |
               (virtual_address & 32'hfff);
    return data_index(physical);
  endfunction
  function automatic logic [31:0] payload(input int index);
    return 32'hd30aa731 ^ (32'(index) * 32'h204081);
  endfunction

  // Independent memory slave: noncontiguous owned pages, fixed PTE table,
  // clock-dependent stalls and ordinary error injection. Unexpected physical
  // accesses are fatal, even if client-visible results happen to match.
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      read_active <= 0; write_active <= 0; pending_b <= 0;
      m_rvalid_i <= 0; m_bvalid_i <= 0;
      read_index <= 0; write_index <= 0;
      read_address <= 0; write_address <= 0;
      read_count <= 0; write_count <= 0;
      m_rdata_i <= 0; m_rresp_i <= 0; m_rid_i <= 0; m_rlast_i <= 0;
      m_bresp_i <= 0; m_bid_i <= 0;
      cycles <= 0;
    end else begin
      cycles <= cycles + 1;
      if (quiesced_o && (read_active || write_active || pending_b || m_rvalid_i || m_bvalid_i))
        $fatal(1, "bridge reported quiescent with outstanding slave state");
      if (m_arvalid_o && m_arready_i) begin
        if (m_arsize_o != 2 || m_arburst_o != 1 || m_arcache_o != 0 ||
            m_arprot_o != 0 || m_arid_o != 0) $fatal(1, "bad AR attributes");
        if (is_table(m_araddr_o)) begin
          if (m_arlen_o != 0 || m_araddr_o[1:0] != 0) $fatal(1, "bad PTE burst");
          table_reads <= table_reads + 1;
        end else begin
          if (data_index(m_araddr_o) + int'(m_arlen_o) >= 4096)
            $fatal(1, "data read range escape");
          data_reads <= data_reads + 1;
        end
        read_active <= 1; read_address <= m_araddr_o;
        read_count <= int'(m_arlen_o) + 1; read_index <= 0;
      end
      if (read_active && !m_rvalid_i && !hold_responses && cycles % 3 != 1) begin
        m_rvalid_i <= 1;
        m_rdata_i <= is_table(read_address) ? ptes[(read_address - 32'h02000000) >> 2] :
                     memory[data_index(read_address) + read_index];
        m_rresp_i <= (is_table(read_address) ? error_table : error_data) ? 2'b10 : 0;
        m_rid_i <= bad_read_id;
        m_rlast_i <= read_index == read_count - 1;
      end
      if (m_rvalid_i && m_rready_o) begin
        m_rvalid_i <= 0;
        if (read_index == read_count - 1) read_active <= 0;
        else read_index <= read_index + 1;
      end
      if (m_awvalid_o && m_awready_i) begin
        if (m_awsize_o != 2 || m_awburst_o != 1 || m_awcache_o != 0 ||
            m_awprot_o != 0 || m_awid_o != 0) $fatal(1, "bad AW attributes");
        if (data_index(m_awaddr_o) + int'(m_awlen_o) >= 4096)
          $fatal(1, "data write range escape");
        writes <= writes + 1;
        write_active <= 1; write_address <= m_awaddr_o;
        write_count <= int'(m_awlen_o) + 1; write_index <= 0;
      end
      if (m_wvalid_o && m_wready_i) begin
        if (m_wlast_o != (write_index == write_count - 1)) $fatal(1, "bad WLAST");
        for (int lane = 0; lane < 4; lane++)
          if (m_wstrb_o[lane])
            memory[data_index(write_address) + write_index][lane*8 +: 8] <= m_wdata_o[lane*8 +: 8];
        if (m_wlast_o) begin write_active <= 0; pending_b <= 1; end
        else write_index <= write_index + 1;
      end
      if (pending_b && !hold_responses && cycles % 5 == 0) begin
        pending_b <= 0; m_bvalid_i <= 1; m_bresp_i <= error_data ? 2'b10 : 0;
      end
      if (m_bvalid_i && m_bready_o) m_bvalid_i <= 0;
    end
  end

  task automatic tick;
    @(posedge clk_i); #1;
  endtask
  task automatic launch(input logic [31:0] addr, input logic [8:0] words, input bit wr);
    @(negedge clk_i);
    if (!req_ready_o || busy_o || poisoned_o) $fatal(1, "bridge not idle");
    req_addr_i = addr; req_words_i = words; req_write_i = wr; req_valid_i = 1;
    tick();
    @(negedge clk_i); req_valid_i = 0;
  endtask
  task automatic finish(input logic [3:0] fault);
    int watchdog = 0;
    while (!done_valid_o) begin
      tick(); watchdog++;
      if (watchdog > 3000)
        $fatal(1, "missing bridge completion: addr=%h words=%0d read=%b write=%b pending_b=%b",
               req_addr_i, req_words_i, read_active, write_active, pending_b);
    end
    if (done_fault_o != fault || !busy_o || poisoned_o)
      $fatal(1, "bridge fault %0d expected %0d", done_fault_o, fault);
    repeat (3) begin
      tick();
      if (!done_valid_o || done_fault_o != fault || req_ready_o)
        $fatal(1, "bridge completion changed under backpressure");
    end
    @(negedge clk_i); done_ready_i = 1;
    tick();
    @(negedge clk_i); done_ready_i = 0;
    if (busy_o) $fatal(1, "bridge completion not retired");
    cases++;
  endtask
  task automatic read_test(input logic [31:0] addr, input int words);
    int watchdog = 0;
    launch(addr, 9'(words), 0);
    while (!out_valid_o) begin
      tick(); watchdog++;
      if (watchdog > 3000 || done_valid_o) $fatal(1, "read payload missing");
    end
    for (int i = 0; i < words; i++) begin
      repeat (1 + i % 3) begin
        tick();
        if (!out_valid_o || out_last_o != (i == words - 1) ||
            out_data_o != expected[expected_index(addr) + i])
          $fatal(1, "translated read mismatch at %h word %0d", addr, i);
      end
      @(negedge clk_i); out_ready_i = 1;
      tick();
      @(negedge clk_i); out_ready_i = 0;
    end
    finish(0);
  endtask
  task automatic send_write(input logic [31:0] addr, input int words);
    int watchdog = 0;
    launch(addr, 9'(words), 1);
    while (!in_ready_o) begin
      tick(); watchdog++;
      if (watchdog > 200 || done_valid_o) $fatal(1, "write payload admission missing");
    end
    for (int i = 0; i < words; i++) begin
      repeat (i % 2) tick();
      @(negedge clk_i);
      in_valid_i = 1; in_data_i = payload(i); in_strb_i = 4'(i);
      if (!in_ready_o) $fatal(1, "write producer lost readiness");
      for (int lane = 0; lane < 4; lane++)
        if (in_strb_i[lane]) expected[expected_index(addr) + i][lane*8 +: 8] = in_data_i[lane*8 +: 8];
      tick();
      @(negedge clk_i); in_valid_i = 0;
    end
  endtask
  task automatic flush_cache;
    @(negedge clk_i); cfg_flush_i = 1;
    if (!flush_ready_o) $fatal(1, "flush not idle");
    tick();
    if (req_ready_o) $fatal(1, "request admitted during flush");
    @(negedge clk_i); cfg_flush_i = 0;
  endtask
  task automatic await_quiescence;
    int watchdog = 0;
    while (!quiesced_o) begin
      tick(); watchdog++;
      if (watchdog > 3000) $fatal(1, "abort did not drain");
    end
    repeat (4) begin
      tick();
      if (req_ready_o || busy_o || !quiesced_o) $fatal(1, "abort boundary unstable");
    end
    @(negedge clk_i); abort_i = 0;
    cases++;
  endtask
  task automatic check_no_data(input logic [31:0] addr, input logic [8:0] words,
                               input bit wr, input logic [3:0] fault);
    int reads_before = data_reads, writes_before = writes;
    launch(addr, words, wr);
    finish(fault);
    if (data_reads != reads_before || writes != writes_before)
      $fatal(1, "denied virtual access reached data AXI");
  endtask

  initial begin
    int before_count;
    for (int i = 0; i < 4096; i++) begin
      memory[i] = 32'h7165abcd ^ (32'(i) * 32'h10204081);
      expected[i] = memory[i];
    end
    ptes[0] = 32'h10003003; ptes[1] = 32'h10000003;
    ptes[2] = 32'h10002001; ptes[3] = 0;
    tick(); tick();
    @(negedge clk_i); rst_ni = 1;
    read_test(32'h40000000, 1);
    before_count = table_reads;
    send_write(32'h40000c00, 256); finish(0);
    read_test(32'h40000c00, 256);
    if (table_reads != before_count) $fatal(1, "PTE cache hit failed");
    for (int i = 0; i < 100; i++) begin
      logic [31:0] addr;
      addr = 32'h40000000 + (32'(i % 2) << 12) + (32'(i * 28) & 32'hbfc);
      send_write(addr, 1 + i % 64); finish(0);
      read_test(addr, 1 + i % 64);
    end
    read_test(32'h40002000, 256);
    check_no_data(32'h40002000, 256, 1, 7);
    check_no_data(32'h40003000, 1, 0, 6);
    ptes[3] = 32'h10001005;
    check_no_data(32'h40003000, 1, 0, 8);
    ptes[3] = 32'h10001003; error_table = 1;
    check_no_data(32'h40003000, 1, 0, 9);
    error_table = 0;
    read_test(32'h40003ffc, 1);
    check_no_data(32'h10000000, 1, 0, 3); // no physical-address escape
    check_no_data(32'h40004000, 1, 0, 3);
    check_no_data(32'h40000ffc, 2, 0, 5);
    cfg_enable_i = 0;
    check_no_data(32'h40000000, 1, 0, 1);
    ptes[0] = 32'h10001003;
    flush_cache(); cfg_enable_i = 1;
    read_test(32'h40000000, 1);
    error_data = 1;
    launch(32'h40000000, 3, 0); finish(12);
    send_write(32'h40000000, 3); finish(12);
    error_data = 0;
    read_test(32'h40000000, 3);

    // Abort before translator acceptance: no PTE request may appear.
    before_count = table_reads + data_reads;
    launch(32'h40000000, 1, 0); abort_i = 1;
    await_quiescence();
    if (table_reads + data_reads != before_count) $fatal(1, "early abort issued read");
    // Abort an accepted PTE read while the slave supplies no response.
    flush_cache(); hold_responses = 1;
    launch(32'h40000000, 1, 0);
    wait (read_active);
    @(negedge clk_i); abort_i = 1;
    repeat (12) begin tick(); if (quiesced_o || !busy_o) $fatal(1, "PTE abort lost ownership"); end
    @(negedge clk_i); hold_responses = 0;
    await_quiescence();
    // The drained translation cached its PTE; abort a data read instead.
    hold_responses = 1;
    launch(32'h40000000, 17, 0);
    wait (read_active);
    if (is_table(read_address)) $fatal(1, "expected cached data read");
    @(negedge clk_i); abort_i = 1;
    repeat (12) begin tick(); if (quiesced_o || !busy_o) $fatal(1, "data abort lost ownership"); end
    @(negedge clk_i); hold_responses = 0;
    await_quiescence();
    // All W beats have independent buffered supply even after client abort.
    hold_responses = 1;
    send_write(32'h40000000, 17);
    wait (write_active);
    @(negedge clk_i); abort_i = 1;
    wait (pending_b);
    repeat (12) begin tick(); if (quiesced_o || !busy_o) $fatal(1, "B abort lost ownership"); end
    @(negedge clk_i); hold_responses = 0;
    await_quiescence();
    read_test(32'h40000000, 17);
    // Flush cannot invalidate an active translation/data path.
    launch(32'h40000000, 1, 0);
    cfg_flush_i = 1;
    while (!out_valid_o) begin tick(); if (flush_ready_o) $fatal(1, "busy flush accepted"); end
    @(negedge clk_i); out_ready_i = 1;
    tick();
    @(negedge clk_i); out_ready_i = 0;
    finish(0);
    if (!flush_ready_o) $fatal(1, "pending flush not ready after completion");
    tick();
    @(negedge clk_i); cfg_flush_i = 0;
    read_test(32'h40000000, 1);

    // A poisoned child cannot be hidden by parent state or abort.
    flush_cache(); bad_read_id = 1;
    launch(32'h40000000, 1, 0);
    wait (poisoned_o);
    @(negedge clk_i); abort_i = 1;
    repeat (20) begin
      tick();
      if (!busy_o || quiesced_o || req_ready_o || done_valid_o) $fatal(1, "poison hidden");
    end
    @(negedge clk_i); rst_ni = 0; // coordinated master + memory-model reset
    tick();
    @(negedge clk_i); rst_ni = 1; abort_i = 0; bad_read_id = 0;
    read_test(32'h40000000, 17);
    $display("M5 TRANSLATED AXI RTL PASS cases=%0d table_reads=%0d data_reads=%0d writes=%0d",
             cases, table_reads, data_reads, writes);
    $finish;
  end
  initial begin
    #5000000;
    $fatal(1, "global timeout");
  end
endmodule
