module pa_m5_core_memory_tb;
  localparam int Cores = 4, Clients = 5;
  logic clk = 0, rst_n = 0, stop = 0, abort_run = 0;
  always #5 clk <= ~clk;
  logic host_req [Cores], host_gnt [Cores], host_we [Cores];
  logic [31:0] host_addr [Cores], host_wdata [Cores], host_rdata [Cores];
  logic [3:0] host_be [Cores];
  logic host_rvalid [Cores], host_err [Cores], router_busy [Cores], adapter_busy [Cores];
  logic target_req [Cores][2], target_gnt [Cores][2], target_rvalid [Cores][2], target_err [Cores][2];
  logic [31:0] target_addr [Cores], target_wdata [Cores], target_rdata [Cores][2];
  logic target_we [Cores];
  logic [3:0] target_be [Cores];
  logic req_valid [Clients], req_ready [Clients], req_write [Clients];
  logic [31:0] req_addr [Clients];
  logic [8:0] req_words [Clients];
  logic [8:0] bulk_words = 0;
  // Keep all elements structurally driven: mixed constant module outputs and
  // a procedurally driven final unpacked-array element are misclassified as a
  // static whole-array port by this simulator's optimizer.
  assign req_words[4] = bulk_words;
  logic in_valid [Clients], in_ready [Clients], out_valid [Clients], out_ready [Clients];
  logic [31:0] in_data [Clients], out_data [Clients];
  logic [3:0] in_strb [Clients], done_fault [Clients];
  logic out_last [Clients], done_valid [Clients], done_ready [Clients];
  logic bulk_req = 0, bulk_write = 0, bulk_in_valid = 0, bulk_out_ready = 0, bulk_done_ready = 0;
  logic [31:0] bulk_addr = 0, bulk_data = 0;
  logic [3:0] bulk_strb = 0;
  assign req_valid[4] = bulk_req;
  assign req_addr[4] = bulk_addr;
  assign req_write[4] = bulk_write;
  assign in_valid[4] = bulk_in_valid;
  assign in_data[4] = bulk_data;
  assign in_strb[4] = bulk_strb;
  assign out_ready[4] = bulk_out_ready;
  assign done_ready[4] = bulk_done_ready;
  logic arb_busy, arb_quiet;
  logic mem_abort, mem_req, mem_ready, mem_write, mem_in_valid, mem_in_ready;
  logic [31:0] mem_addr, mem_in_data, mem_out_data;
  logic [8:0] mem_words;
  logic [3:0] mem_in_strb, mem_fault;
  logic mem_out_valid, mem_out_ready, mem_out_last, mem_done, mem_done_ready, mem_busy, mem_quiet;
  int cycles = 0, grants = 0, local_grants = 0, completed = 0, local_events;
  int waiting_grants [Clients];
  bit local_pending [Cores];
  int local_delay [Cores];
  logic [31:0] local_addr [Cores];
  bit hold_memory = 0, hold_admission = 0;

  for (genvar h = 0; h < Cores; h++) begin : g_core
    pa_m5_obi_router u_router (
      .clk_i(clk), .rst_ni(rst_n), .stop_i(stop),
      .host_req_i(host_req[h]), .host_gnt_o(host_gnt[h]), .host_addr_i(host_addr[h]),
      .host_we_i(host_we[h]), .host_be_i(host_be[h]), .host_wdata_i(host_wdata[h]),
      .host_rvalid_o(host_rvalid[h]), .host_rdata_o(host_rdata[h]), .host_err_o(host_err[h]),
      .busy_o(router_busy[h]), .target_req_o(target_req[h]), .target_gnt_i(target_gnt[h]),
      .target_addr_o(target_addr[h]), .target_we_o(target_we[h]), .target_be_o(target_be[h]),
      .target_wdata_o(target_wdata[h]), .target_rvalid_i(target_rvalid[h]),
      .target_rdata_i(target_rdata[h]), .target_err_i(target_err[h])
    );
    pa_m5_obi_ddr u_adapter (
      .clk_i(clk), .rst_ni(rst_n), .req_i(target_req[h][1]), .gnt_o(target_gnt[h][1]),
      .addr_i(target_addr[h]), .we_i(target_we[h]), .be_i(target_be[h]), .wdata_i(target_wdata[h]),
      .rvalid_o(target_rvalid[h][1]), .rdata_o(target_rdata[h][1]), .err_o(target_err[h][1]),
      .busy_o(adapter_busy[h]), .cmd_valid_o(req_valid[h]), .cmd_ready_i(req_ready[h]),
      .cmd_addr_o(req_addr[h]), .cmd_words_o(req_words[h]), .cmd_write_o(req_write[h]),
      .in_valid_o(in_valid[h]), .in_ready_i(in_ready[h]), .in_data_o(in_data[h]), .in_strb_o(in_strb[h]),
      .out_valid_i(out_valid[h]), .out_ready_o(out_ready[h]), .out_data_i(out_data[h]),
      .out_last_i(out_last[h]), .done_valid_i(done_valid[h]), .done_ready_o(done_ready[h]),
      .done_fault_i(done_fault[h])
    );
    assign target_gnt[h][0] = target_req[h][0] && !local_pending[h] && cycles % 3 != h % 3;
    assign target_err[h][0] = 0;
  end
  pa_m5_memory_arbiter #(.Clients(Clients)) u_arb (
    .clk_i(clk), .rst_ni(rst_n), .abort_i(abort_run), .pause_i(1'b0),
    .req_valid_i(req_valid), .req_ready_o(req_ready), .req_addr_i(req_addr),
    .req_words_i(req_words), .req_write_i(req_write), .in_valid_i(in_valid), .in_ready_o(in_ready),
    .in_data_i(in_data), .in_strb_i(in_strb), .out_valid_o(out_valid), .out_ready_i(out_ready),
    .out_data_o(out_data), .out_last_o(out_last), .done_valid_o(done_valid),
    .done_ready_i(done_ready), .done_fault_o(done_fault), .busy_o(arb_busy), .quiesced_o(arb_quiet),
    .m_abort_o(mem_abort), .m_req_valid_o(mem_req), .m_req_ready_i(mem_ready),
    .m_req_addr_o(mem_addr), .m_req_words_o(mem_words), .m_req_write_o(mem_write),
    .m_in_valid_o(mem_in_valid), .m_in_ready_i(mem_in_ready), .m_in_data_o(mem_in_data),
    .m_in_strb_o(mem_in_strb), .m_out_valid_i(mem_out_valid), .m_out_ready_o(mem_out_ready),
    .m_out_data_i(mem_out_data), .m_out_last_i(mem_out_last), .m_done_valid_i(mem_done),
    .m_done_ready_o(mem_done_ready), .m_done_fault_i(mem_fault), .m_busy_i(mem_busy),
    .m_quiesced_i(mem_quiet)
  );

  function automatic logic [31:0] read_value(input logic [31:0] addr, input int word_index);
    return addr ^ 32'h6529caf0 ^ (32'(word_index) * 32'h10201);
  endfunction
  function automatic logic [31:0] write_value(input int client, input int word_index);
    return 32'hcafef012 ^ (32'(client) << 20) ^ (32'(word_index) * 32'h30701);
  endfunction

  // Independent variable-latency memory-interface model. Actual AXI/bounds are
  // qualified separately; this test targets routing, ownership and core stop.
  typedef enum logic [2:0] {MIdle, MWrite, MWait, MRead, MDone, MDrain} mem_state_e;
  mem_state_e mem_state = MIdle;
  logic [31:0] saved_addr = 0;
  int saved_words = 0, word_q = 0, delay_q = 0;
  logic saved_write = 0;
  assign mem_ready = mem_state == MIdle && !mem_abort && !hold_admission && cycles % 3 != 0;
  assign mem_in_ready = mem_state == MWrite && !mem_abort && cycles % 3 != 1;
  assign mem_out_valid = mem_state == MRead && !mem_abort;
  assign mem_out_data = read_value(saved_addr, word_q);
  assign mem_out_last = word_q == saved_words - 1;
  assign mem_done = mem_state == MDone && !mem_abort;
  assign mem_fault = 0;
  assign mem_busy = mem_state != MIdle;
  assign mem_quiet = mem_abort && !mem_busy;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      cycles <= 0; mem_state <= MIdle;
      saved_addr <= 0; saved_words <= 0; saved_write <= 0; word_q <= 0; delay_q <= 0;
      for (int h = 0; h < Cores; h++) begin
        local_pending[h] <= 0; local_delay[h] <= 0; local_addr[h] <= 0;
        target_rvalid[h][0] <= 0; target_rdata[h][0] <= 0;
      end
      for (int c = 0; c < Clients; c++) waiting_grants[c] <= 0;
    end else begin
      cycles <= cycles + 1;
      for (int h = 0; h < Cores; h++) begin
        target_rvalid[h][0] <= 0;
        if (target_gnt[h][0]) begin
          local_pending[h] <= 1; local_delay[h] <= 1 + h;
          local_addr[h] <= target_addr[h];
          // Captured local write lanes/data must not follow changed host pins.
          if (target_we[h] && (target_wdata[h] != write_value(h, int'(target_addr[h][11:2])) ||
                               target_be[h] != 4'(1 << (int'(target_addr[h][11:2]) % 4))))
            $fatal(1, "local write capture mismatch");
        end
        if (local_pending[h]) begin
          if (local_delay[h] != 0) local_delay[h] <= local_delay[h] - 1;
          else begin
            target_rvalid[h][0] <= 1;
            target_rdata[h][0] <= read_value(local_addr[h], 0);
            local_pending[h] <= 0;
          end
        end
      end
      for (int c = 0; c < Clients; c++) begin
        if (!req_valid[c] || req_ready[c]) waiting_grants[c] <= 0;
        else for (int d = 0; d < Clients; d++)
          if (req_valid[d] && req_ready[d]) waiting_grants[c] <= waiting_grants[c] + 1;
        if (waiting_grants[c] >= Clients) $fatal(1, "round-robin starvation");
      end
      if (mem_abort && mem_state != MIdle && mem_state != MDrain) begin
        mem_state <= MDrain; delay_q <= 7;
      end else case (mem_state)
        MIdle: if (mem_req && mem_ready) begin
          if (mem_addr[31:28] != 4'h4 || mem_addr[1:0] != 0 || mem_words == 0)
            $fatal(1, "bad memory command from core/bulk client addr=%h words=%0d write=%b",
                   mem_addr, mem_words, mem_write);
          saved_addr <= mem_addr; saved_words <= int'(mem_words); saved_write <= mem_write;
          word_q <= 0; delay_q <= 5;
          mem_state <= mem_write ? MWrite : MWait;
        end
        MWrite: if (mem_in_valid && mem_in_ready) begin
          if (saved_addr[23]) begin
            if (mem_in_data != write_value(4, word_q) || mem_in_strb != 4'(word_q))
              $fatal(1, "bulk payload routed from wrong owner: word=%0d data=%h strb=%h expected=%h/%h",
                     word_q, mem_in_data, mem_in_strb, write_value(4, word_q), 4'(word_q));
          end else if (mem_in_data != write_value(int'(saved_addr[19:16]), int'(saved_addr[11:2])) ||
                       mem_in_strb != 4'(1 << (int'(saved_addr[11:2]) % 4)))
            $fatal(1, "core write payload/strobes not captured");
          if (word_q == saved_words - 1) begin mem_state <= MWait; word_q <= 0; end
          else word_q <= word_q + 1;
        end
        MWait: if (!hold_memory) begin
          if (delay_q != 0) delay_q <= delay_q - 1;
          else mem_state <= saved_write ? MDone : MRead;
        end
        MRead: if (mem_out_ready) begin
          if (word_q == saved_words - 1) mem_state <= MDone;
          else word_q <= word_q + 1;
        end
        MDone: if (mem_done_ready) mem_state <= MIdle;
        MDrain: begin
          if (delay_q != 0) delay_q <= delay_q - 1;
          else mem_state <= MIdle;
        end
        default: $fatal(1, "bad memory-model state");
      endcase
    end
  end

  // Event counters are monitors, not transaction scheduling or data oracles.
  always_comb begin
    local_events = 0;
    for (int h = 0; h < Cores; h++) if (target_gnt[h][0]) local_events++;
  end
  always_ff @(posedge clk) if (rst_n) begin
    for (int c = 0; c < Clients; c++) begin
      if (req_valid[c] && req_ready[c]) begin
        grants <= grants + 1;
        if ($test$plusargs("debug"))
          $display("grant t=%0t client=%0d addr=%h words=%0d", $time, c, req_addr[c], req_words[c]);
      end
      if (done_valid[c] && (done_ready[c] || abort_run)) completed <= completed + 1;
    end
    local_grants <= local_grants + local_events;
  end
  task automatic tick;
    @(posedge clk); #1;
  endtask
  task automatic core_one(input int h, input int index, input bit only_ddr = 0,
                          input bit expect_abort = 0);
    logic [31:0] address;
    bit wr;
    int watchdog = 0;
    address = ((only_ddr || index % 2 != 0) ? 32'h40000000 : 32'h00001000) |
              (32'(h) << 16) | (32'(index) << 2) | 32'(index % 4);
    wr = !expect_abort && index % 3 == 1;
    @(negedge clk);
    host_req[h] = 1; host_addr[h] = address; host_we[h] = wr;
    host_be[h] = 4'(1 << (index % 4)); host_wdata[h] = write_value(h, index);
    #1;
    while (!host_gnt[h]) begin
      @(negedge clk); #1;
      watchdog++;
      if (watchdog > 5000) $fatal(1, "core grant timeout");
    end
    tick();
    @(negedge clk);
    host_req[h] = 0; host_addr[h] = ~address; host_wdata[h] = 0; host_be[h] = 0; host_we[h] = !wr;
    while (!host_rvalid[h]) begin
      tick(); watchdog++;
      if (watchdog > 5000) $fatal(1, "core response timeout");
      if (host_gnt[h]) $fatal(1, "core duplicate grant");
    end
    if (host_err[h] != expect_abort) $fatal(1, "core error routing mismatch h=%0d", h);
    if (!wr && !expect_abort && host_rdata[h] != read_value(
        address[31:28] == 4'h4 ? (address & 32'hfffffffc) : address, 0))
      $fatal(1, "core response routing/address mismatch h=%0d index=%0d", h, index);
    tick();
  endtask
  task automatic core_work(input int h);
    for (int i = 0; i < 80; i++) core_one(h, i);
  endtask
  task automatic bulk_work;
    for (int job = 0; job < 40; job++) begin
      int words, watchdog;
      bit wr;
      logic [31:0] address;
      words = 1 + job % 32; wr = 1'(job); address = 32'h40800000 + (32'(job) << 12);
      @(negedge clk);
      bulk_req = 1; bulk_addr = address; bulk_words = 9'(words); bulk_write = wr;
      watchdog = 0;
      #1;
      while (!req_ready[4]) begin
        @(negedge clk); #1; watchdog++;
        if (watchdog > 5000) $fatal(1, "bulk command grant timeout");
      end
      tick();
      @(negedge clk); bulk_req = 0; bulk_addr = ~address;
      if (wr) for (int i = 0; i < words; i++) begin
        @(negedge clk); bulk_in_valid = 1; bulk_data = write_value(4, i); bulk_strb = 4'(i);
        #1;
        while (!in_ready[4]) begin @(negedge clk); #1; end
        tick();
        @(negedge clk); bulk_in_valid = 0;
        repeat (i % 3) tick();
      end else for (int i = 0; i < words; i++) begin
        wait (out_valid[4]);
        repeat (1 + i % 3) begin
          tick();
          if (!out_valid[4] || out_data[4] != read_value(address, i) || out_last[4] != (i == words - 1))
            $fatal(1, "bulk read routed from wrong owner");
        end
        @(negedge clk); bulk_out_ready = 1;
        tick();
        @(negedge clk); bulk_out_ready = 0;
      end
      wait (done_valid[4]);
      repeat (3) begin tick(); if (done_fault[4] != 0 || !done_valid[4]) $fatal(1, "bulk completion bad"); end
      @(negedge clk); bulk_done_ready = 1;
      tick();
      @(negedge clk); bulk_done_ready = 0;
    end
  endtask

  initial begin
    for (int h = 0; h < Cores; h++) begin
      host_req[h] = 0; host_addr[h] = 0; host_we[h] = 0; host_be[h] = 0; host_wdata[h] = 0;
    end
    bulk_req = 0; bulk_addr = 0; bulk_words = 0; bulk_write = 0;
    bulk_in_valid = 0; bulk_data = 0; bulk_strb = 0; bulk_out_ready = 0; bulk_done_ready = 0;
    tick(); tick();
    @(negedge clk); rst_n = 1;
    fork
      core_work(0);
      core_work(1);
      core_work(2);
      core_work(3);
      bulk_work();
    join
    // A missing DDR response on one port must not stop another port's local
    // instruction/data traffic. Ten local operations finish before DDR abort.
    hold_memory = 1;
    fork
      core_one(0, 94, 1, 1);
      begin
        wait (mem_busy);
        for (int i = 0; i < 10; i++) core_one(1, 2 * i);
        @(negedge clk); stop = 1; abort_run = 1;
      end
    join
    tick();
    if (!arb_quiet || router_busy[0] || adapter_busy[0])
      $fatal(1, "isolated DDR abort did not retire");
    @(negedge clk); stop = 0; abort_run = 0; hold_memory = 0;
    // Cancel a granted client command that has not yet reached the bridge.
    hold_admission = 1;
    fork
      core_one(2, 96, 1, 1);
      begin
        wait (mem_req);
        @(negedge clk); stop = 1; abort_run = 1;
      end
    join
    tick();
    if (mem_busy || !arb_quiet) $fatal(1, "pre-bridge cancellation leaked a request");
    @(negedge clk); stop = 0; abort_run = 0; hold_admission = 0;
    // All four routers accepted a request before stop. One is in memory;
    // others are waiting for arbitration and must retire with abort errors.
    hold_memory = 1;
    fork
      core_one(0, 90, 1, 1);
      core_one(1, 90, 1, 1);
      core_one(2, 90, 1, 1);
      core_one(3, 90, 1, 1);
      begin
        wait (mem_busy);
        @(negedge clk); stop = 1; abort_run = 1;
        repeat (5) begin tick(); if (arb_quiet) $fatal(1, "abort did not wait for drain"); end
      end
    join
    tick();
    if (!arb_quiet || arb_busy) $fatal(1, "arbiter failed to quiesce");
    for (int h = 0; h < Cores; h++)
      if (router_busy[h] || adapter_busy[h]) $fatal(1, "core request lost during stop");
    @(negedge clk); host_req[0] = 1;
    repeat (4) begin
      tick();
      if (host_gnt[0] || router_busy[0]) $fatal(1, "stopped core accepted a new request");
    end
    @(negedge clk); host_req[0] = 0;
    @(negedge clk); stop = 0; abort_run = 0; hold_memory = 0;
    fork
      core_one(0, 92, 1);
      core_one(1, 92, 1);
      core_one(2, 92, 1);
      core_one(3, 92, 1);
    join
    if (grants != 210 || completed != 210 || local_grants != 170)
      $fatal(1, "accepted/completed/local command count mismatch");
    $display("M5 CORE/MEMORY OWNERSHIP RTL PASS core_requests=340 bulk_requests=40 grants=%0d completions=%0d local_grants=%0d",
             grants, completed, local_grants);
    $finish;
  end
  initial begin
    #5000000;
    $fatal(1, "global timeout");
  end
endmodule
