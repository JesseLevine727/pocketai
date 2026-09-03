// PocketAI-T M1b -- two-hart Ibex cluster top
//
// Two Ibex "small-config" cores (hart 0 and hart 1, via `pa_ibex_wrapper`)
// sharing one bus, one RAM, one UART byte-capture, the inter-hart mailbox
// and an external AXI4-Lite slave port into the same address space.
//
// Memory map (RAM, UART and MBOX are shared by both harts and by the AXI
// slave port):
//   0x0000_0000  RAM    (64 KB)
//   0x0001_1000  UART   (SIM_CTRL_BASE; +0 = char out, +8 = halt)
//   0x0001_2000  MBOX   (0x0 mbox0_to_1 W, 0x4 mbox1_to_0 W, 0x8 status R)
//
// Interrupts (level lines from `pa_mailbox`):
//   hart 0 <-- mbox_irq0 (mbox1_to_0 pending, i.e. the hart1 -> hart0 mailbox)
//   hart 1 <-- mbox_irq1 (mbox0_to_1 pending, i.e. the hart0 -> hart1 mailbox)
// The firmware (sim/cluster_test) polls the status register with mstatus.MIE
// left at 0, so the IRQ lines are wired but unused by the test (a pending
// external interrupt is simply never taken).
//
// Reset note (IMPORTANT, learned the hard way in M1b): the testbench must
// never hold the cores in reset before the first clock edge.  In our
// simulation harness, asserting reset before any clocking corrupts the
// cores' CSR state (CSR reads then decode as illegal instructions).  The
// TB therefore clocks a few cycles with IO_RST_N released first, applies a
// short reset, and then releases the cores; the AXI self-test runs while
// the cores boot (it only touches RAM at 0xF000, which the firmware never
// uses).
//
// UART interleave caveat: both harts share the one `simulator_ctrl` capture
// register, so their byte streams interleave in pa_cluster.log.  Each
// character is one full bus write and is therefore never torn, but bytes
// from the two harts may interleave in the middle of a word if both harts
// print at the same time.  The firmware prints short single-line tokens and
// the deterministic simulation never interleaves them in practice.

module pa_cluster_top (
  input IO_CLK,
  input IO_RST_N,

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
  input  logic        rready_i
);

  localparam logic [31:0] RamBytes = 64*1024;
  localparam int unsigned RamWords = RamBytes/4;

  logic clk_sys, rst_sys_n;
  assign clk_sys   = IO_CLK;
  assign rst_sys_n = IO_RST_N;

  // --- Bus host/device wiring (mirrors dv/riscv_compliance) ---
  // NOTE: the lowRISC demo `bus` arbiter is strictly priority based
  // (host 0 wins).  The AXI slave port is therefore given top priority:
  // its transactions are short (a few cycles each), so the cores only lose
  // a few cycles per external transfer.  (If the GEMM/SFPU hosts of M2
  // onward need fair access, replace the arbiter with a round-robin one.)
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
    Mbox
  } bus_device_e;

  localparam int unsigned NrDevices = 3;
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

  // Device address map: RAM @0x0 (64 KB), UART @0x11000 (1 KB), MBOX @0x12000
  // (1 KB).  The masks implement the device decode in `bus`.
  logic [31:0] cfg_device_addr_base [NrDevices];
  logic [31:0] cfg_device_addr_mask [NrDevices];
  assign cfg_device_addr_base[Ram]  = 32'h0;
  assign cfg_device_addr_mask[Ram]  = ~32'(RamBytes - 1);
  assign cfg_device_addr_base[Uart] = 32'h00011000;
  assign cfg_device_addr_mask[Uart] = ~32'h3FF;
  assign cfg_device_addr_base[Mbox] = 32'h00012000;
  assign cfg_device_addr_mask[Mbox] = ~32'h3FF;

  bus #(
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
  logic mbox_irq0, mbox_irq1;

  // --- Core 0 (hart 0), external IRQ = mbox1_to_0 pending ---
  pa_ibex_wrapper #(
    .HART_ID(32'h0)
  ) u_core0 (
    .clk_i                 (clk_sys),
    .rst_ni                (rst_sys_n),
    .boot_addr_i           (32'h0),
    .instr_req_o           (host_req[Core0I]),
    .instr_gnt_i           (host_gnt[Core0I]),
    .instr_rvalid_i        (host_rvalid[Core0I]),
    .instr_addr_o          (host_addr[Core0I]),
    .instr_rdata_i         (host_rdata[Core0I]),
    .data_req_o            (host_req[Core0D]),
    .data_gnt_i            (host_gnt[Core0D]),
    .data_rvalid_i         (host_rvalid[Core0D]),
    .data_we_o             (host_we[Core0D]),
    .data_be_o             (host_be[Core0D]),
    .data_addr_o           (host_addr[Core0D]),
    .data_wdata_o          (host_wdata[Core0D]),
    .data_rdata_i          (host_rdata[Core0D]),
    .irq_external_i        (mbox_irq0),
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
    .rst_ni                (rst_sys_n),
    .boot_addr_i           (32'h0),
    .instr_req_o           (host_req[Core1I]),
    .instr_gnt_i           (host_gnt[Core1I]),
    .instr_rvalid_i        (host_rvalid[Core1I]),
    .instr_addr_o          (host_addr[Core1I]),
    .instr_rdata_i         (host_rdata[Core1I]),
    .data_req_o            (host_req[Core1D]),
    .data_gnt_i            (host_gnt[Core1D]),
    .data_rvalid_i         (host_rvalid[Core1D]),
    .data_we_o             (host_we[Core1D]),
    .data_be_o             (host_be[Core1D]),
    .data_addr_o           (host_addr[Core1D]),
    .data_wdata_o          (host_wdata[Core1D]),
    .data_rdata_i          (host_rdata[Core1D]),
    .irq_external_i        (mbox_irq1),
    .irq_software_i        (1'b0),
    .irq_timer_i           (1'b0),
    .alert_major_internal_o(),
    .alert_major_bus_o     ()
  );


  // --- Shared RAM (64 KB) ---
  ram_1p #(
      .Depth(RamWords)
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

  // --- Shared UART byte-capture register (+ software halt) ---
  simulator_ctrl #(
    .LogName("pa_cluster.log"),
    .FlushOnChar(1)
  ) u_uart (
    .clk_i   (clk_sys),
    .rst_ni  (rst_sys_n),
    .req_i   (device_req[Uart]),
    .we_i    (device_we[Uart]),
    .be_i    (device_be[Uart]),
    .addr_i  (device_addr[Uart]),
    .wdata_i (device_wdata[Uart]),
    .rvalid_o(device_rvalid[Uart]),
    .rdata_o (device_rdata[Uart])
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
