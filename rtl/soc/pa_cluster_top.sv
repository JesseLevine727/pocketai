// PocketAI-T two-hart Ibex cluster plus M2 GEMM
//
// Two Ibex "small-config" cores (hart 0 and hart 1, via `pa_ibex_wrapper`)
// sharing one fair bus, one BRAM-inferable scratchpad, one console FIFO, the
// inter-hart mailbox
// and an external AXI4-Lite slave port into the same address space.
//
// Memory map (RAM, UART and MBOX are shared by both harts and by the AXI
// slave port):
//   0x0000_0000  RAM      (64 KB shared scratchpad)
//   0x0001_1000  CONSOLE  (+0 data, +4 status, +8 control/done)
//   0x0001_2000  MBOX     (+0/+4 data, +8 status, +c W1C acknowledge)
//   0x0001_3000  GEMM     (descriptor/control/status; see M2 architecture)
//
// Interrupts (level lines from `pa_mailbox`):
//   hart 0 <-- mbox_irq0 (mbox1_to_0 pending, i.e. the hart1 -> hart0 mailbox)
//   hart 1 <-- mbox_irq1 (mbox0_to_1 pending, i.e. the hart0 -> hart1 mailbox)
// Reset contract: IO_RST_N is asserted before the first active clock edge and
// held low for normal power-on reset. The Verilator testbench creates an
// explicit high-to-low transition at clock-low so async reset logic observes
// the same assertion event a physical device receives at power-on.
// CORE_RST_N resets only the Ibex cores and core-facing peripherals; the bus,
// AXI bridge, and scratchpad stay live so the A9 can load firmware under reset.

module pa_cluster_top #(
  parameter bit EnableGemm = 1'b1
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
  output logic        software_done_o
);

  localparam logic [31:0] RamBytes = 64*1024;
  localparam int unsigned RamWords = RamBytes/4;

  logic clk_sys, rst_sys_n, rst_core_n;
  assign clk_sys   = IO_CLK;
  assign rst_sys_n = IO_RST_N;
  assign rst_core_n = IO_RST_N & CORE_RST_N;

  // --- Round-robin shared bus host/device wiring ---
  typedef enum logic [2:0] {
    AxI,
    Core0I,
    Core0D,
    Core1I,
    Core1D
  } bus_host_e;

  typedef enum logic [1:0] {
    Ram,
    Uart,
    Mbox,
    Gemm
  } bus_device_e;

  localparam int unsigned NrDevices = EnableGemm ? 4 : 3;
  localparam int unsigned NrHosts   = 5;

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
  logic mbox_irq0, mbox_irq1, gemm_irq;

  // --- Core 0 (hart 0), external IRQ = mbox1_to_0 pending ---
  pa_ibex_wrapper #(
    .HART_ID(32'h0)
  ) u_core0 (
    .clk_i                 (clk_sys),
    .rst_ni                (rst_core_n),
    .boot_addr_i           (32'h0),
    .instr_req_o           (host_req[Core0I]),
    .instr_gnt_i           (host_gnt[Core0I]),
    .instr_rvalid_i        (host_rvalid[Core0I]),
    .instr_addr_o          (host_addr[Core0I]),
    .instr_rdata_i         (host_rdata[Core0I]),
    .instr_err_i           (host_err[Core0I]),
    .data_req_o            (host_req[Core0D]),
    .data_gnt_i            (host_gnt[Core0D]),
    .data_rvalid_i         (host_rvalid[Core0D]),
    .data_we_o             (host_we[Core0D]),
    .data_be_o             (host_be[Core0D]),
    .data_addr_o           (host_addr[Core0D]),
    .data_wdata_o          (host_wdata[Core0D]),
    .data_rdata_i          (host_rdata[Core0D]),
    .data_err_i            (host_err[Core0D]),
    .irq_external_i        (mbox_irq0 | gemm_irq),
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
    .instr_req_o           (host_req[Core1I]),
    .instr_gnt_i           (host_gnt[Core1I]),
    .instr_rvalid_i        (host_rvalid[Core1I]),
    .instr_addr_o          (host_addr[Core1I]),
    .instr_rdata_i         (host_rdata[Core1I]),
    .instr_err_i           (host_err[Core1I]),
    .data_req_o            (host_req[Core1D]),
    .data_gnt_i            (host_gnt[Core1D]),
    .data_rvalid_i         (host_rvalid[Core1D]),
    .data_we_o             (host_we[Core1D]),
    .data_be_o             (host_be[Core1D]),
    .data_addr_o           (host_addr[Core1D]),
    .data_wdata_o          (host_wdata[Core1D]),
    .data_rdata_i          (host_rdata[Core1D]),
    .data_err_i            (host_err[Core1D]),
    .irq_external_i        (mbox_irq1 | gemm_irq),
    .irq_software_i        (1'b0),
    .irq_timer_i           (1'b0),
    .alert_major_internal_o(),
    .alert_major_bus_o     ()
  );

  // Instruction hosts never write. Drive every bus field explicitly so
  // four-state simulation and synthesis cannot infer unknown controls.
  assign host_we[Core0I]    = 1'b0;
  assign host_be[Core0I]    = 4'b0000;
  assign host_wdata[Core0I] = 32'h00000000;
  assign host_we[Core1I]    = 1'b0;
  assign host_be[Core1I]    = 4'b0000;
  assign host_wdata[Core1I] = 32'h00000000;


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
    .rst_ni  (rst_core_n),
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
    .rst_ni   (rst_core_n),
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
    pa_gemm u_gemm (
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
      .s_axis_valid_i    (gemm_s_axis_valid_i),
      .s_axis_ready_o    (gemm_s_axis_ready_o),
      .m_axis_data_o     (gemm_m_axis_data_o),
      .m_axis_keep_o     (gemm_m_axis_keep_o),
      .m_axis_last_o     (gemm_m_axis_last_o),
      .m_axis_valid_o    (gemm_m_axis_valid_o),
      .m_axis_ready_i    (gemm_m_axis_ready_i),
      .irq_o             (gemm_irq)
    );
  end else begin : g_no_gemm
    assign gemm_s_axis_ready_o = 1'b0;
    assign gemm_m_axis_data_o = 32'h0;
    assign gemm_m_axis_keep_o = 4'h0;
    assign gemm_m_axis_last_o = 1'b0;
    assign gemm_m_axis_valid_o = 1'b0;
    assign gemm_irq = 1'b0;
  end

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
