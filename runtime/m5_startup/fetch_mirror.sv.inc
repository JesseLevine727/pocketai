  // Dedicated instruction reads of the same 64-KiB local RAM contents. The
  // existing per-port routers still own every accepted request through response
  // and drain; non-RAM instruction accesses keep their original bus/DDR route.
  logic mirror_req [2], mirror_gnt [2], mirror_valid [2];
  logic [31:0] mirror_addr [2], mirror_data [2];
  logic mirror_write;
  assign mirror_write = device_req[Ram] && device_we[Ram];
  for (genvar h = 0; h < 4; h++) begin : g_local_hosts
    if (h == 0 || h == 2) begin : g_instruction
      localparam int Port = h/2;
      logic selected;
      assign selected = local_addr[h][31:16] == 16'b0;
      assign mirror_req[Port] = local_req[h] && selected;
      assign mirror_addr[Port] = local_addr[h];
      assign host_req[h+1] = local_req[h] && !selected;
      assign local_gnt[h] = selected ? mirror_gnt[Port] : host_gnt[h+1];
      assign local_rvalid[h] = mirror_valid[Port] || host_rvalid[h+1];
      assign local_rdata[h] = mirror_valid[Port] ? mirror_data[Port] : host_rdata[h+1];
      assign local_err[h] = !mirror_valid[Port] && host_err[h+1];
      always @(posedge clk_sys or negedge rst_sys_n) begin
        if (!rst_sys_n) begin end
        else assert (!(mirror_valid[Port] && host_rvalid[h+1]));
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
  // One extra true-dual-port 64-KiB BRAM, not two copies. Port A mirrors
  // every accepted original RAM write (including byte lanes); writes take
  // priority over both reads to avoid mixed-port read/write collisions.
  (* ram_style = "block" *) logic [31:0] startup_instruction_mem [RamWords];
  logic [13:0] mirror_port_a_addr;
  assign mirror_port_a_addr = mirror_write ? device_addr[Ram][15:2] : mirror_addr[0][15:2];
  assign mirror_gnt[0] = mirror_req[0] && !mirror_write;
  assign mirror_gnt[1] = mirror_req[1] && !mirror_write;
  always @(posedge clk_sys) begin
    // Explicitly share Port A's address for read/write. Separate expressions
    // infer three logical ports and can replicate the entire bank in Vivado.
    // The read-first value on a write is invalid/ignored by the interface.
    if (mirror_write || mirror_gnt[0]) begin
      mirror_data[0] <= startup_instruction_mem[mirror_port_a_addr];
      if (mirror_write)
        for (int lane=0; lane<4; lane++)
          if (device_be[Ram][lane])
            startup_instruction_mem[mirror_port_a_addr][lane*8+:8] <=
                device_wdata[Ram][lane*8+:8];
    end
  end
  always @(posedge clk_sys) begin
    if (mirror_gnt[1]) mirror_data[1] <= startup_instruction_mem[mirror_addr[1][15:2]];
  end
  always_ff @(posedge clk_sys or negedge rst_sys_n) begin
    if (!rst_sys_n) begin mirror_valid[0] <= 0; mirror_valid[1] <= 0; end
    else begin mirror_valid[0] <= mirror_gnt[0]; mirror_valid[1] <= mirror_gnt[1]; end
  end
