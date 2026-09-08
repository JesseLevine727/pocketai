  // One additional coherent 64-KiB bank gives both harts independent local
  // DATA READ ports. Writes and all non-RAM accesses keep their original bus.
  // The data routers retain their original registered Respond stage.
  logic startup_data_gnt [2], startup_data_valid [2];
  logic [31:0] startup_data_rdata [2];
  (* ram_style = "block" *) logic [31:0] startup_data_read_mem [RamWords];
  logic [13:0] startup_data_port_a_addr;
  assign startup_data_port_a_addr = mirror_write ? device_addr[Ram][15:2] :
                                                                 local_addr[1][15:2];
  always @(posedge clk_sys) begin
    if (mirror_write || startup_data_gnt[0]) begin
      startup_data_rdata[0] <= startup_data_read_mem[startup_data_port_a_addr];
      if (mirror_write)
        for (int lane=0; lane<4; lane++)
          if (device_be[Ram][lane])
            startup_data_read_mem[startup_data_port_a_addr][lane*8+:8] <=
                device_wdata[Ram][lane*8+:8];
    end
  end
  always @(posedge clk_sys) begin
    if (startup_data_gnt[1])
      startup_data_rdata[1] <= startup_data_read_mem[local_addr[3][15:2]];
  end
  always_ff @(posedge clk_sys) begin
    if (!startup_reset_release_q[1]) begin
      startup_data_valid[0] <= 0; startup_data_valid[1] <= 0;
    end else begin
      startup_data_valid[0] <= startup_data_gnt[0];
      startup_data_valid[1] <= startup_data_gnt[1];
    end
  end
