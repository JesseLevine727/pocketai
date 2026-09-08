  // Coherent 64-KiB mirror plus one sequential-lookahead word per hart.
  // Read addresses come ONLY from the router's registered accepted address.
  // Never feed a live CPU branch address through BRAM/grant in one clock.
  logic mirror_req [2], mirror_gnt [2], mirror_valid [2];
  logic [31:0] mirror_data [2];
  logic mirror_write;
  logic predict_valid [2], predict_hit [2], predict_read [2], actual_read [2];
  logic [13:0] predict_tag [2], read_word [2];
  assign mirror_write = device_req[Ram] && device_we[Ram];
  for (genvar h = 0; h < 4; h++) begin : g_local_hosts
    if (h == 0 || h == 2) begin : g_instruction
      localparam int Port = h/2;
      logic selected;
      logic fallback_valid_q, fallback_err_q;
      logic [31:0] fallback_data_q;
      assign selected = local_addr[h][31:16] == 16'b0;
      assign mirror_req[Port] = local_req[h] && selected;
      assign predict_hit[Port] = predict_valid[Port] && mirror_req[Port] &&
          predict_tag[Port] == local_addr[h][15:2] && !mirror_write;
      assign actual_read[Port] = mirror_gnt[Port] && !predict_hit[Port];
      // The unused read slot on an owned instruction's response edge prepares
      // its sequential successor. No prediction crosses the 64-KiB boundary.
      // Denied lookahead is simply a future miss, never a dropped request.
      assign predict_read[Port] = core_rvalid[h] && selected &&
          local_addr[h][15:2] != 14'h3fff && rst_core_n && !memory_abort_i &&
          !mirror_write && !actual_read[Port];
      assign read_word[Port] = predict_read[Port] ? local_addr[h][15:2]+14'd1 :
                                                               local_addr[h][15:2];
      assign host_req[h+1] = local_req[h] && !selected;
      assign local_gnt[h] = selected ? mirror_gnt[Port] : host_gnt[h+1];
      assign local_rvalid[h] = mirror_valid[Port] || predict_hit[Port] || fallback_valid_q;
      assign local_rdata[h] = (mirror_valid[Port] || predict_hit[Port]) ?
                              mirror_data[Port] : fallback_data_q;
      assign local_err[h] = !(mirror_valid[Port] || predict_hit[Port]) && fallback_err_q;
      always_ff @(posedge clk_sys or negedge rst_sys_n) begin
        if (!rst_sys_n) begin
          fallback_valid_q <= 0; fallback_err_q <= 0; fallback_data_q <= 0;
          predict_valid[Port] <= 0; predict_tag[Port] <= 0;
        end else begin
          fallback_valid_q <= host_rvalid[h+1];
          if (host_rvalid[h+1]) begin
            fallback_data_q <= host_rdata[h+1]; fallback_err_q <= host_err[h+1];
          end
          // Any local write conservatively invalidates both lookahead words.
          // In particular, Port A's write-first/read-first output cannot be
          // mistaken for a previously cached instruction after a write.
          if (mirror_write || actual_read[Port]) predict_valid[Port] <= 0;
          else if (predict_read[Port]) begin
            predict_valid[Port] <= 1; predict_tag[Port] <= read_word[Port];
          end
          assert (!(mirror_valid[Port] && predict_hit[Port]));
          assert (!((mirror_valid[Port] || predict_hit[Port]) && fallback_valid_q));
        end
      end
    end else begin : g_data
      assign host_req[h+1] = local_req[h];
      assign local_gnt[h] = host_gnt[h+1];
      assign local_rvalid[h] = host_rvalid[h+1];
      assign local_rdata[h] = host_rdata[h+1];
      assign local_err[h] = host_err[h+1];
    end
    assign host_addr[h+1] = local_addr[h];
    assign host_we[h+1] = local_we[h];
    assign host_be[h+1] = local_be[h];
    assign host_wdata[h+1] = local_wdata[h];
  end
  (* ram_style = "block" *) logic [31:0] startup_instruction_mem [RamWords];
  logic [13:0] mirror_port_a_addr;
  assign mirror_port_a_addr = mirror_write ? device_addr[Ram][15:2] : read_word[0];
  assign mirror_gnt[0] = mirror_req[0] && !mirror_write;
  assign mirror_gnt[1] = mirror_req[1] && !mirror_write;
  always @(posedge clk_sys) begin
    if (mirror_write || actual_read[0] || predict_read[0]) begin
      mirror_data[0] <= startup_instruction_mem[mirror_port_a_addr];
      if (mirror_write)
        for (int lane=0; lane<4; lane++)
          if (device_be[Ram][lane])
            startup_instruction_mem[mirror_port_a_addr][lane*8+:8] <= device_wdata[Ram][lane*8+:8];
    end
  end
  always @(posedge clk_sys) begin
    if (actual_read[1] || predict_read[1]) mirror_data[1] <= startup_instruction_mem[read_word[1]];
  end
  always_ff @(posedge clk_sys or negedge rst_sys_n) begin
    if (!rst_sys_n) begin mirror_valid[0] <= 0; mirror_valid[1] <= 0; end
    else begin mirror_valid[0] <= actual_read[0]; mirror_valid[1] <= actual_read[1]; end
  end
