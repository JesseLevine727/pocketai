// M5 two-Ibex cluster with independent local/translated DDR paths.
// Based on the frozen M4 cluster; old milestones retain their original top.
// Core-only reset does not reset accepted bus requests or MMIO responders.
// Protected configuration is top-level only; see M5_ARCHITECTURE.md.

module pa_m5_cluster_top #(
  parameter bit EnableGemm = 1'b1,
  parameter bit EnableSfpu = 1'b1
) (
  input IO_CLK,
  input IO_RST_N,
  input CORE_RST_N,

  // AXI4-Lite slave port (single transfers, no bursts; see pa_axi_lite_bridge)
  input  logic [31:0] awaddr_i,
  input  logic        awvalid_i,
  output logic        awready_o,
  input  logic [31:0] wdata_i,
  input  logic [ 3:0] wstrb_i,
  input  logic        wvalid_i,
  output logic        wready_o,
  output logic [ 1:0] bresp_o,
  output logic        bvalid_o,
  input  logic        bready_i,
  input  logic [31:0] araddr_i,
  input  logic        arvalid_i,
  output logic        arready_o,
  output logic [31:0] rdata_o,
  output logic [ 1:0] rresp_o,
  output logic        rvalid_o,
  input  logic        rready_i,

  // M2 GEMM payload streams. Packets and numerical semantics are defined in
  // docs/NUMERICS.md. The PYNQ wrapper connects these to AXI DMA.
  input  logic [31:0] gemm_s_axis_data_i,
  input  logic [ 3:0] gemm_s_axis_keep_i,
  input  logic        gemm_s_axis_last_i,
  input  logic        gemm_s_axis_valid_i,
  output logic        gemm_s_axis_ready_o,
  output logic [31:0] gemm_m_axis_data_o,
  output logic [ 3:0] gemm_m_axis_keep_o,
  output logic        gemm_m_axis_last_o,
  output logic        gemm_m_axis_valid_o,
  input  logic        gemm_m_axis_ready_i,

  // Console observability for simulation/logic analysis. The A9 normally
  // reads the same bytes from the console FIFO through AXI.
  output logic        console_char_valid_o,
  output logic [ 7:0] console_char_o,
  output logic        software_done_o,
  input logic cfg_enable_i,
  input logic [31:0] cfg_table_base_i,
  input logic [31:0] cfg_arena_bytes_i,
  input logic cfg_flush_i,
  output logic flush_ready_o,
  input logic memory_abort_i,
  output logic memory_busy_o,
  output logic memory_quiesced_o,
  output logic memory_poisoned_o,
  input logic bulk_busy_i,
  input logic bulk_req_valid_i,
  output logic bulk_req_ready_o,
  input logic [31:0] bulk_req_addr_i,
  input logic [8:0] bulk_req_words_i,
  input logic bulk_req_write_i,
  input logic bulk_in_valid_i,
  output logic bulk_in_ready_o,
  input logic [31:0] bulk_in_data_i,
  input logic [3:0] bulk_in_strb_i,
  output logic bulk_out_valid_o,
  input logic bulk_out_ready_i,
  output logic [31:0] bulk_out_data_o,
  output logic bulk_out_last_o,
  output logic bulk_done_valid_o,
  input logic bulk_done_ready_i,
  output logic [3:0] bulk_done_fault_o,
  output logic [31:0] m_awaddr_o,
  output logic [7:0] m_awlen_o,
  output logic [2:0] m_awsize_o,
  output logic [1:0] m_awburst_o,
  output logic [3:0] m_awcache_o,
  output logic [2:0] m_awprot_o,
  output logic m_awid_o,
  output logic m_awvalid_o,
  input logic m_awready_i,
  output logic [31:0] m_wdata_o,
  output logic [3:0] m_wstrb_o,
  output logic m_wlast_o,
  output logic m_wvalid_o,
  input logic m_wready_i,
  input logic [1:0] m_bresp_i,
  input logic m_bid_i,
  input logic m_bvalid_i,
  output logic m_bready_o,
  output logic [31:0] m_araddr_o,
  output logic [7:0] m_arlen_o,
  output logic [2:0] m_arsize_o,
  output logic [1:0] m_arburst_o,
  output logic [3:0] m_arcache_o,
  output logic [2:0] m_arprot_o,
  output logic m_arid_o,
  output logic m_arvalid_o,
  input logic m_arready_i,
  input logic [31:0] m_rdata_i,
  input logic [1:0] m_rresp_i,
  input logic m_rid_i,
  input logic m_rlast_i,
  input logic m_rvalid_i,
  output logic m_rready_o
);

  localparam logic [31:0] RamBytes = 64*1024;
  localparam int unsigned RamWords = RamBytes/4;

  logic clk_sys, rst_sys_n, rst_core_n;
  assign clk_sys   = IO_CLK;
  assign rst_sys_n = IO_RST_N;
  assign rst_core_n = IO_RST_N & CORE_RST_N;

  // --- Round-robin shared bus host/device wiring ---
  localparam int AxI = 0;

  // Constant indices work for both the legacy four-device and extended
  // five-device arrays without widening a legacy packed enum selector.
  localparam int Ram = 0, Uart = 1, Mbox = 2, Gemm = 3, Sfpu = 4;

  localparam int unsigned NrDevices = EnableSfpu ? 5 : EnableGemm ? 4 : 3;
  localparam int unsigned NrHosts   = 5;
  initial assert (!EnableSfpu || EnableGemm);

  logic         host_req    [NrHosts];
  logic         host_gnt    [NrHosts];
  logic [31:0]  host_addr   [NrHosts];
  logic         host_we     [NrHosts];
  logic [ 3:0]  host_be     [NrHosts];
  logic [31:0]  host_wdata  [NrHosts];
  logic         host_rvalid [NrHosts];
  logic [31:0]  host_rdata  [NrHosts];
  logic         host_err    [NrHosts];

  logic         device_req    [NrDevices];
  logic [31:0]  device_addr   [NrDevices];
  logic         device_we     [NrDevices];
  logic [ 3:0]  device_be     [NrDevices];
  logic [31:0]  device_wdata  [NrDevices];
  logic         device_rvalid [NrDevices];
  logic [31:0]  device_rdata  [NrDevices];
  logic         device_err    [NrDevices];

  // Device address map: RAM @0x0 (64 KB), console @0x11000, mailbox @0x12000,
  // and M2 GEMM control @0x13000. Peripheral windows are 1 KiB.
  logic [31:0] cfg_device_addr_base [NrDevices];
  logic [31:0] cfg_device_addr_mask [NrDevices];
  assign cfg_device_addr_base[Ram]  = 32'h0;
  assign cfg_device_addr_mask[Ram]  = ~32'(RamBytes - 1);
  assign cfg_device_addr_base[Uart] = 32'h00011000;
  assign cfg_device_addr_mask[Uart] = ~32'h3FF;
  assign cfg_device_addr_base[Mbox] = 32'h00012000;
  assign cfg_device_addr_mask[Mbox] = ~32'h3FF;
  if (EnableGemm) begin : g_gemm_decode
    assign cfg_device_addr_base[Gemm] = 32'h00013000;
    assign cfg_device_addr_mask[Gemm] = ~32'h3FF;
  end
  if (EnableSfpu) begin : g_sfpu_decode
    assign cfg_device_addr_base[Sfpu] = 32'h00014000;
    assign cfg_device_addr_mask[Sfpu] = ~32'h3FF;
  end

  pa_shared_bus #(
    .NrDevices   (NrDevices),
    .NrHosts     (NrHosts  ),
    .DataWidth   (32       ),
    .AddressWidth(32       )
  ) u_bus (
    .clk_i              (clk_sys),
    .rst_ni             (rst_sys_n),

    .host_req_i         (host_req    ),
    .host_gnt_o         (host_gnt    ),
    .host_addr_i        (host_addr   ),
    .host_we_i          (host_we     ),
    .host_be_i          (host_be     ),
    .host_wdata_i       (host_wdata  ),
    .host_rvalid_o      (host_rvalid ),
    .host_rdata_o       (host_rdata  ),
    .host_err_o         (host_err    ),

    .device_req_o       (device_req  ),
    .device_addr_o      (device_addr ),
    .device_we_o        (device_we   ),
    .device_be_o        (device_be   ),
    .device_wdata_o     (device_wdata),
    .device_rvalid_i    (device_rvalid),
    .device_rdata_i     (device_rdata ),
    .device_err_i       (device_err  ),

    .cfg_device_addr_base,
    .cfg_device_addr_mask
  );

  // Mailbox level IRQs (see `pa_mailbox`): irq0 -> hart 0, irq1 -> hart 1
  logic mbox_irq0, mbox_irq1, gemm_irq, sfpu_irq;
  logic stream_route, gemm_busy;
  logic gemm_input_ready, sfpu_input_ready;
  logic [31:0] gemm_output_data, sfpu_output_data;
  logic [3:0] gemm_output_keep, sfpu_output_keep;
  logic gemm_output_valid, gemm_output_last, sfpu_output_valid, sfpu_output_last;

  // --- Core 0 (hart 0), external IRQ = mbox1_to_0 pending ---
  pa_ibex_wrapper #(
    .HART_ID(32'h0)
  ) u_core0 (
    .clk_i                 (clk_sys),
    .rst_ni                (rst_core_n),
    .boot_addr_i           (32'h0),
    .instr_req_o           (core_req[0]),
    .instr_gnt_i           (core_gnt[0]),
    .instr_rvalid_i        (core_rvalid[0]),
    .instr_addr_o          (core_addr[0]),
    .instr_rdata_i         (core_rdata[0]),
    .instr_err_i           (core_err[0]),
    .data_req_o            (core_req[1]),
    .data_gnt_i            (core_gnt[1]),
    .data_rvalid_i         (core_rvalid[1]),
    .data_we_o             (core_we[1]),
    .data_be_o             (core_be[1]),
    .data_addr_o           (core_addr[1]),
    .data_wdata_o          (core_wdata[1]),
    .data_rdata_i          (core_rdata[1]),
    .data_err_i            (core_err[1]),
    .irq_external_i        (mbox_irq0 | gemm_irq | sfpu_irq),
    .irq_software_i        (1'b0),
    .irq_timer_i           (1'b0),
    .alert_major_internal_o(),
    .alert_major_bus_o     ()
  );

  // --- Core 1 (hart 1), external IRQ = mbox0_to_1 pending ---
  pa_ibex_wrapper #(
    .HART_ID(32'h1)
  ) u_core1 (
    .clk_i                 (clk_sys),
    .rst_ni                (rst_core_n),
    .boot_addr_i           (32'h0),
    .instr_req_o           (core_req[2]),
    .instr_gnt_i           (core_gnt[2]),
    .instr_rvalid_i        (core_rvalid[2]),
    .instr_addr_o          (core_addr[2]),
    .instr_rdata_i         (core_rdata[2]),
    .instr_err_i           (core_err[2]),
    .data_req_o            (core_req[3]),
    .data_gnt_i            (core_gnt[3]),
    .data_rvalid_i         (core_rvalid[3]),
    .data_we_o             (core_we[3]),
    .data_be_o             (core_be[3]),
    .data_addr_o           (core_addr[3]),
    .data_wdata_o          (core_wdata[3]),
    .data_rdata_i          (core_rdata[3]),
    .data_err_i            (core_err[3]),
    .irq_external_i        (mbox_irq1 | gemm_irq | sfpu_irq),
    .irq_software_i        (1'b0),
    .irq_timer_i           (1'b0),
    .alert_major_internal_o(),
    .alert_major_bus_o     ()
  );

  // Instruction hosts never write. Drive every bus field explicitly so
  // four-state simulation and synthesis cannot infer unknown controls.
  assign core_we[0]    = 1'b0;
  assign core_be[0]    = 4'b0000;
  assign core_wdata[0] = 32'h00000000;
  assign core_we[2]    = 1'b0;
  assign core_be[2]    = 4'b0000;
  assign core_wdata[2] = 32'h00000000;



  logic core_req [4], core_gnt [4], core_we [4], core_rvalid [4], core_err [4];
  logic [31:0] core_addr [4], core_wdata [4], core_rdata [4];
  logic [3:0] core_be [4];
  logic local_req [4], local_gnt [4], local_we [4], local_rvalid [4], local_err [4];
  logic [31:0] local_addr [4], local_wdata [4], local_rdata [4];
  logic [3:0] local_be [4];
  for (genvar h = 0; h < 4; h++) begin : g_local_hosts
    assign host_req[h+1] = local_req[h];
    assign local_gnt[h] = host_gnt[h+1];
    assign host_addr[h+1] = local_addr[h];
    assign host_we[h+1] = local_we[h];
    assign host_be[h+1] = local_be[h];
    assign host_wdata[h+1] = local_wdata[h];
    assign local_rvalid[h] = host_rvalid[h+1];
    assign local_rdata[h] = host_rdata[h+1];
    assign local_err[h] = host_err[h+1];
  end
  pa_m5_memory_system u_memory (
    .clk_i(clk_sys), .rst_ni(rst_sys_n), .stop_i(!CORE_RST_N), .abort_i(memory_abort_i),
    .cfg_enable_i, .cfg_table_base_i, .cfg_arena_bytes_i, .cfg_flush_i, .flush_ready_o,
    .busy_o(memory_busy_o), .quiesced_o(memory_quiesced_o), .poisoned_o(memory_poisoned_o),
    .core_req_i(core_req), .core_gnt_o(core_gnt), .core_addr_i(core_addr), .core_we_i(core_we),
    .core_be_i(core_be), .core_wdata_i(core_wdata), .core_rvalid_o(core_rvalid),
    .core_rdata_o(core_rdata), .core_err_o(core_err),
    .local_req_o(local_req), .local_gnt_i(local_gnt), .local_addr_o(local_addr),
    .local_we_o(local_we), .local_be_o(local_be), .local_wdata_o(local_wdata),
    .local_rvalid_i(local_rvalid), .local_rdata_i(local_rdata), .local_err_i(local_err),
    .bulk_busy_i, .bulk_req_valid_i, .bulk_req_ready_o, .bulk_req_addr_i, .bulk_req_words_i,
    .bulk_req_write_i, .bulk_in_valid_i, .bulk_in_ready_o, .bulk_in_data_i, .bulk_in_strb_i,
    .bulk_out_valid_o, .bulk_out_ready_i, .bulk_out_data_o, .bulk_out_last_o,
    .bulk_done_valid_o, .bulk_done_ready_i, .bulk_done_fault_o,
    .m_awaddr_o, .m_awlen_o, .m_awsize_o, .m_awburst_o, .m_awcache_o, .m_awprot_o,
    .m_awid_o, .m_awvalid_o, .m_awready_i, .m_wdata_o, .m_wstrb_o, .m_wlast_o,
    .m_wvalid_o, .m_wready_i, .m_bresp_i, .m_bid_i, .m_bvalid_i, .m_bready_o,
    .m_araddr_o, .m_arlen_o, .m_arsize_o, .m_arburst_o, .m_arcache_o, .m_arprot_o,
    .m_arid_o, .m_arvalid_o, .m_arready_i, .m_rdata_i, .m_rresp_i, .m_rid_i,
    .m_rlast_i, .m_rvalid_i, .m_rready_o
  );

  // --- Shared RAM (64 KB) ---
  pa_scratchpad #(
      .DepthWords(RamWords)
    ) u_ram (
      .clk_i    (clk_sys),
      .rst_ni   (rst_sys_n),
      .req_i    (device_req[Ram]),
      .we_i     (device_we[Ram]),
      .be_i     (device_be[Ram]),
      .addr_i   (device_addr[Ram]),
      .wdata_i  (device_wdata[Ram]),
      .rvalid_o (device_rvalid[Ram]),
      .rdata_o  (device_rdata[Ram])
    );

  // --- Shared synthesizable console FIFO (+ software-done latch) ---
  pa_console u_console (
    .clk_i   (clk_sys),
    .rst_ni  (rst_sys_n),
    .req_i   (device_req[Uart]),
    .we_i    (device_we[Uart]),
    .be_i    (device_be[Uart]),
    .addr_i  (device_addr[Uart]),
    .wdata_i (device_wdata[Uart]),
    .rvalid_o(device_rvalid[Uart]),
    .rdata_o (device_rdata[Uart]),
    .char_valid_o(console_char_valid_o),
    .char_data_o(console_char_o),
    .done_o(software_done_o)
  );

  // --- Inter-hart mailbox (level IRQs to the cores) ---
  pa_mailbox u_mbox (
    .clk_i    (clk_sys),
    .rst_ni   (rst_sys_n),
    .req_i    (device_req[Mbox]),
    .we_i     (device_we[Mbox]),
    .be_i     (device_be[Mbox]),
    .addr_i   (device_addr[Mbox]),
    .wdata_i  (device_wdata[Mbox]),
    .rvalid_o (device_rvalid[Mbox]),
    .rdata_o  (device_rdata[Mbox]),
    .irq0_o   (mbox_irq0),
    .irq1_o   (mbox_irq1)
  );

  // --- Optional M2 double-buffered GEMM accelerator ---
  if (EnableGemm) begin : g_gemm
    pa_gemm #(.EnableWide(EnableSfpu)) u_gemm (
      .clk_i             (clk_sys),
      .rst_ni            (rst_sys_n),
      .req_i             (device_req[Gemm]),
      .we_i              (device_we[Gemm]),
      .be_i              (device_be[Gemm]),
      .addr_i            (device_addr[Gemm]),
      .wdata_i           (device_wdata[Gemm]),
      .rvalid_o          (device_rvalid[Gemm]),
      .rdata_o           (device_rdata[Gemm]),
      .err_o             (device_err[Gemm]),
      .s_axis_data_i     (gemm_s_axis_data_i),
      .s_axis_keep_i     (gemm_s_axis_keep_i),
      .s_axis_last_i     (gemm_s_axis_last_i),
      .s_axis_valid_i    (gemm_s_axis_valid_i && !stream_route),
      .s_axis_ready_o    (gemm_input_ready),
      .m_axis_data_o     (gemm_output_data),
      .m_axis_keep_o     (gemm_output_keep),
      .m_axis_last_o     (gemm_output_last),
      .m_axis_valid_o    (gemm_output_valid),
      .m_axis_ready_i    (gemm_m_axis_ready_i && !stream_route),
      .irq_o             (gemm_irq),
      .busy_o            (gemm_busy)
    );
  end else begin : g_no_gemm
    assign gemm_input_ready = 1'b0;
    assign gemm_output_data = 32'h0;
    assign gemm_output_keep = 4'h0;
    assign gemm_output_last = 1'b0;
    assign gemm_output_valid = 1'b0;
    assign gemm_irq = 1'b0;
    assign gemm_busy = 1'b0;
  end

  if (EnableSfpu) begin : g_sfpu
    pa_sfpu u_sfpu (
      .clk_i(clk_sys), .rst_ni(rst_sys_n),
      .req_i(device_req[Sfpu]), .we_i(device_we[Sfpu]), .be_i(device_be[Sfpu]),
      .addr_i(device_addr[Sfpu]), .wdata_i(device_wdata[Sfpu]),
      .rvalid_o(device_rvalid[Sfpu]), .rdata_o(device_rdata[Sfpu]), .err_o(device_err[Sfpu]),
      .s_axis_data_i(gemm_s_axis_data_i), .s_axis_keep_i(gemm_s_axis_keep_i),
      .s_axis_last_i(gemm_s_axis_last_i), .s_axis_valid_i(gemm_s_axis_valid_i && stream_route),
      .s_axis_ready_o(sfpu_input_ready), .m_axis_data_o(sfpu_output_data),
      .m_axis_keep_o(sfpu_output_keep), .m_axis_last_o(sfpu_output_last),
      .m_axis_valid_o(sfpu_output_valid), .m_axis_ready_i(gemm_m_axis_ready_i && stream_route),
      .gemm_busy_i(gemm_busy), .stream_route_o(stream_route), .busy_o(), .irq_o(sfpu_irq)
    );
  end else begin : g_no_sfpu
    assign stream_route = 1'b0;
    assign sfpu_input_ready = 1'b0;
    assign sfpu_output_data = 32'h0;
    assign sfpu_output_keep = 4'h0;
    assign sfpu_output_last = 1'b0;
    assign sfpu_output_valid = 1'b0;
    assign sfpu_irq = 1'b0;
    // gemm_busy is used only by the optional SFPU route interlock.
    logic unused_gemm_busy;
    assign unused_gemm_busy = gemm_busy;
  end
  assign gemm_s_axis_ready_o = stream_route ? sfpu_input_ready : gemm_input_ready;
  assign gemm_m_axis_data_o = stream_route ? sfpu_output_data : gemm_output_data;
  assign gemm_m_axis_keep_o = stream_route ? sfpu_output_keep : gemm_output_keep;
  assign gemm_m_axis_last_o = stream_route ? sfpu_output_last : gemm_output_last;
  assign gemm_m_axis_valid_o = stream_route ? sfpu_output_valid : gemm_output_valid;

  // --- AXI4-Lite slave port -> bus host ---
  pa_axi_lite_bridge u_axi (
    .clk_i    (clk_sys),
    .rst_ni   (rst_sys_n),
    .awaddr_i (awaddr_i),
    .awvalid_i(awvalid_i),
    .awready_o(awready_o),
    .wdata_i  (wdata_i),
    .wstrb_i  (wstrb_i),
    .wvalid_i (wvalid_i),
    .wready_o (wready_o),
    .bresp_o  (bresp_o),
    .bvalid_o (bvalid_o),
    .bready_i (bready_i),
    .araddr_i (araddr_i),
    .arvalid_i(arvalid_i),
    .arready_o(arready_o),
    .rdata_o  (rdata_o),
    .rresp_o  (rresp_o),
    .rvalid_o (rvalid_o),
    .rready_i (rready_i),
    .req_o    (host_req[AxI]),
    .gnt_i    (host_gnt[AxI]),
    .we_o     (host_we[AxI]),
    .be_o     (host_be[AxI]),
    .addr_o   (host_addr[AxI]),
    .wdata_o  (host_wdata[AxI]),
    .rvalid_i (host_rvalid[AxI]),
    .rdata_i  (host_rdata[AxI]),
    .err_i    (host_err[AxI])
  );

  assign device_err[Ram]  = 1'b0;
  assign device_err[Uart] = 1'b0;
  assign device_err[Mbox] = 1'b0;
endmodule
