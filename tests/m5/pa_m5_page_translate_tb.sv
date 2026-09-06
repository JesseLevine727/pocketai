module pa_m5_page_translate_tb;
  logic clk = 0;
  always #5 clk <= ~clk;
  logic rst_n = 0;
  logic enable = 1, flush = 0, flush_ready;
  logic [31:0] root = 32'h02000000, arena = 32'h10000000;
  logic req_valid = 0, req_ready, req_write = 0;
  logic [31:0] req_addr = 0;
  logic [8:0] req_words = 0;
  logic rsp_valid, rsp_ready = 0, busy;
  logic [31:0] rsp_addr;
  logic [3:0] rsp_fault;
  logic t_valid, t_ready = 0, t_rsp_valid = 0, t_error = 0;
  logic [31:0] t_addr, t_data = 0;
  int checks = 0, walks = 0;
  pa_m5_page_translate dut (
    .clk_i(clk), .rst_ni(rst_n), .cfg_enable_i(enable),
    .cfg_table_base_i(root), .cfg_arena_bytes_i(arena),
    .cfg_flush_i(flush), .flush_ready_o(flush_ready),
    .req_valid_i(req_valid), .req_ready_o(req_ready),
    .req_addr_i(req_addr), .req_words_i(req_words), .req_write_i(req_write),
    .rsp_valid_o(rsp_valid), .rsp_ready_i(rsp_ready),
    .rsp_addr_o(rsp_addr), .rsp_fault_o(rsp_fault), .busy_o(busy),
    .table_req_valid_o(t_valid), .table_req_ready_i(t_ready),
    .table_req_addr_o(t_addr), .table_rsp_valid_i(t_rsp_valid),
    .table_rsp_data_i(t_data), .table_rsp_error_i(t_error)
  );

  task automatic tick;
    @(posedge clk); #1;
  endtask

  task automatic clear_cache;
    @(negedge clk);
    if (!flush_ready) $fatal(1, "flush attempted while busy");
    flush = 1;
    #1;
    if (req_ready) $fatal(1, "request accepted during flush");
    tick();
    @(negedge clk); flush = 0;
  endtask

  // PTE data and expected address/fault are explicit test inputs, not an RTL
  // output copied back as an oracle. Each handshake and stalled value is checked.
  task automatic translate(input logic [31:0] address, input logic [8:0] words,
                           input bit write_access, input logic [31:0] pte,
                           input logic [31:0] expected, input int fault,
                           input bit walk, input bit table_error = 0,
                           input bit pending_flush = 0);
    int watchdog;
    logic [31:0] saved;
    @(negedge clk);
    if (!req_ready || busy) $fatal(1, "translator not idle");
    req_addr = address; req_words = words; req_write = write_access;
    req_valid = 1;
    tick();
    @(negedge clk); req_valid = 0; flush = pending_flush;
    watchdog = 0;
    while (!t_valid && !rsp_valid) begin
      tick();
      watchdog++;
      if (watchdog > 12) $fatal(1, "request failed to progress");
    end
    if (walk) begin
      if (!t_valid || rsp_valid) $fatal(1, "missing expected page walk");
      saved = root + (((address - 32'h40000000) >> 12) * 4);
      if (t_addr != saved) $fatal(1, "wrong PTE address");
      repeat (4) begin
        tick();
        if (!busy || !t_valid || t_addr != saved || req_ready)
          $fatal(1, "table request changed under backpressure");
      end
      @(negedge clk); t_ready = 1;
      tick();
      @(negedge clk); t_ready = 0;
      repeat (5) begin
        tick();
        if (!busy || rsp_valid || t_valid || req_ready || flush_ready)
          $fatal(1, "missing table response incorrectly treated as drained");
      end
      @(negedge clk); t_data = pte; t_error = table_error; t_rsp_valid = 1;
      tick();
      @(negedge clk); t_rsp_valid = 0; t_error = 0;
      walks++;
    end else if (t_valid) $fatal(1, "unexpected page walk");
    watchdog = 0;
    while (!rsp_valid) begin
      tick(); watchdog++;
      if (watchdog > 8) $fatal(1, "missing translation response");
    end
    if (rsp_addr != expected || int'(rsp_fault) != fault)
      $fatal(1, "translation mismatch addr=%h got=%h fault=%0d expected=%h/%0d",
             address, rsp_addr, rsp_fault, expected, fault);
    repeat (4) begin
      tick();
      if (!rsp_valid || rsp_addr != expected || int'(rsp_fault) != fault || !busy || req_ready)
        $fatal(1, "response changed under backpressure");
    end
    @(negedge clk); rsp_ready = 1;
    tick();
    @(negedge clk); rsp_ready = 0;
    if (busy || rsp_valid || !flush_ready || req_ready == pending_flush)
      $fatal(1, "response did not retire / pending flush not respected");
    if (pending_flush) begin
      tick();
      @(negedge clk); flush = 0;
      #1;
      if (!req_ready) $fatal(1, "flush failed to release request port");
    end
    checks++;
  endtask

  initial begin
    tick(); tick();
    @(negedge clk); rst_n = 1;
    translate(32'h40000000, 1, 0, 32'h01000003, 32'h01000000, 0, 1);
    translate(32'h400000fc, 3, 1, 0, 32'h010000fc, 0, 0);
    translate(32'h40000c00, 256, 0, 0, 32'h01000c00, 0, 0);
    translate(32'h40000ffc, 2, 0, 0, 0, 5, 0);
    translate(32'h40001000, 1, 0, 32'h12345001, 32'h12345000, 0, 1);
    translate(32'h40001ffc, 1, 1, 0, 0, 7, 0); // cache hit still checks permission
    translate(32'h40001ffc, 1, 0, 0, 32'h12345ffc, 0, 0);
    translate(32'h40002000, 1, 0, 0, 0, 6, 1);
    translate(32'h40002000, 1, 0, 32'h00000003, 0, 0, 1); // valid DMA address zero
    translate(32'h40003000, 1, 0, 32'h23456005, 0, 8, 1);
    translate(32'h40003000, 1, 0, 32'h23456003, 0, 9, 1, 1);
    translate(32'h40003000, 1, 0, 32'h23456003, 32'h23456000, 0, 1);
    translate(32'h40010000, 1, 0, 32'h0789a003, 32'h0789a000, 0, 1); // cache collision
    translate(32'h40000000, 1, 0, 32'h01234003, 32'h01234000, 0, 1);
    clear_cache();
    translate(32'h40000000, 1, 0, 32'h04567001, 32'h04567000, 0, 1);
    translate(32'h40000000, 1, 1, 0, 0, 7, 0);
    translate(32'h40004000, 1, 0, 32'h02345003, 32'h02345000, 0, 1, 0, 1);
    translate(32'h40004000, 1, 0, 32'h03456003, 32'h03456000, 0, 1);
    // A quiescent reset must invalidate cached translations. Reset is not an
    // abort/drain mechanism for an already issued external memory transaction.
    @(negedge clk); rst_n = 0;
    tick();
    @(negedge clk); rst_n = 1;
    translate(32'h40004000, 1, 0, 32'h05678003, 32'h05678000, 0, 1);
    translate(32'h3ffffffc, 1, 0, 0, 0, 3, 0);
    translate(32'h50000000, 1, 0, 0, 0, 3, 0);
    translate(32'hfffffffc, 2, 0, 0, 0, 3, 0);
    translate(32'h4ffffffc, 2, 0, 0, 0, 3, 0);
    translate(32'h4ffffffc, 1, 1, 32'hfffff003, 32'hfffffffc, 0, 1);
    translate(32'h40000001, 1, 0, 0, 0, 4, 0);
    translate(32'h40000000, 0, 0, 0, 0, 3, 0);
    translate(32'h40000000, 257, 0, 0, 0, 3, 0);
    enable = 0;
    translate(32'h40000000, 1, 0, 0, 0, 1, 0);
    enable = 1; arena = 0;
    translate(32'h40000000, 1, 0, 0, 0, 2, 0);
    arena = 32'h10000001;
    translate(32'h40000000, 1, 0, 0, 0, 2, 0);
    arena = 32'h10001000;
    translate(32'h40000000, 1, 0, 0, 0, 2, 0);
    arena = 4096; root = 3;
    translate(32'h40000000, 1, 0, 0, 0, 2, 0);
    root = 32'hfffffff8; arena = 12288;
    translate(32'h40000000, 1, 0, 0, 0, 2, 0);
    arena = 8192;
    clear_cache();
    translate(32'h40001000, 1, 0, 32'h00456003, 32'h00456000, 0, 1);
    translate(32'h40002000, 1, 0, 0, 0, 3, 0);
    root = 32'h02000000; arena = 32'h10000000;
    clear_cache();
    // Deterministic dispersed pages: covers every cache index/collisions and
    // noncontiguous DMA page bases with varying legal offsets/burst lengths.
    for (int i = 0; i < 1024; i++) begin
      logic [31:0] page, physical, offset;
      page = (32'(i) * 65) & 32'hffff;
      physical = ((page ^ 32'h5aa5) << 12) + 32'h10000000;
      offset = (32'(i) * 28) & 32'hbfc;
      translate(32'h40000000 + (page << 12) + offset, 9'(1 + (i % 64)),
                1'(i), physical | 3, physical + offset, 0, 1);
    end
    $display("M5 PAGE TRANSLATION RTL PASS cases=%0d walks=%0d", checks, walks);
    $finish;
  end

  initial begin
    #1000000;
    $fatal(1, "global test timeout");
  end
endmodule
