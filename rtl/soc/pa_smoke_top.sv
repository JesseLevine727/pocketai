// PocketAI-T M1a boot smoke top
//
// Single-core Ibex (small config: RV32IMC) + 32 KB RAM + a UART byte-capture
// register (reusing lowRISC's proven `simulator_ctrl` module).
//
// Memory map:
//   0x0000_0000  RAM   (32 KB)
//   0x0001_1000  UART  (SIM_CTRL_BASE; +0 = char out, +8 = halt)
//
// The memory interconnect and RAM reuse the exact same lowRISC `bus` / `ram_1p`
// modules the riscv_compliance and simple_system reference designs use, so the
// handshake behaviour is identical to the proven FUSESoC reference builds.
//
// Note for synthesis: `ram_1p` synthesises to a plain array in this smoke
// design; a real SoC would swap it for a BRAM-backed RAM.

module pa_smoke_top (
  input IO_CLK,
  input IO_RST_N
);

  // --- Ibex "small" configuration (see rtl/ibex-orig/util/ibex_config.py small)
  // BaseIsaRV32I + RV32M=Fast + RV32ZC=Zca == RV32IMC, WritebackStage=0, ICache=0
  localparam logic [31:0] RamBytes = 32*1024;
  localparam int unsigned RamWords = RamBytes/4;

  logic clk_sys, rst_sys_n;
  assign clk_sys   = IO_CLK;
  assign rst_sys_n = IO_RST_N;

  // --- Bus host/device wiring (mirrors dv/riscv_compliance) ---
  typedef enum logic {
    CoreI,
    CoreD
  } bus_host_e;

  typedef enum logic {
    Ram,
    Uart
  } bus_device_e;

  localparam int unsigned NrDevices = 2;
  localparam int unsigned NrHosts   = 2;

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

  // Device address map: RAM @0x0 (32 KB), UART @0x11000 (1 KB)
  logic [31:0] cfg_device_addr_base [NrDevices];
  logic [31:0] cfg_device_addr_mask [NrDevices];
  assign cfg_device_addr_base[Ram]  = 32'h0;
  assign cfg_device_addr_mask[Ram]  = ~32'(RamBytes - 1);
  assign cfg_device_addr_base[Uart] = 32'h00011000;
  assign cfg_device_addr_mask[Uart] = ~32'h3FF;

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

  // --- Ibex CPU core (small config) ---
  ibex_top #(
      .BaseIsa         (ibex_pkg::BaseIsaRV32I),
      .RV32E           (1'b0),
      .RV32M           (ibex_pkg::RV32MFast),
      .RV32B           (ibex_pkg::RV32BNone),
      .RV32ZC          (ibex_pkg::RV32Zca),
      .RegFile         (ibex_pkg::RegFileFF),
      .BranchTargetALU (1'b0),
      .WritebackStage  (1'b0),
      .ICache          (1'b0),
      .ICacheECC       (1'b0),
      .BranchPredictor (1'b0),
      .DbgTriggerEn    (1'b0),
      .SecureIbex      (1'b0),
      .ICacheScramble  (1'b0),
      .PMPEnable       (1'b0)
    ) u_core (
      .clk_i              (clk_sys),
      .rst_ni             (rst_sys_n),

      .test_en_i          (1'b0),
      .scan_rst_ni        (1'b1),
      .ram_cfg_icache_tag_i   ('{default: prim_ram_1p_pkg::RAM_1P_CFG_REQ_DEFAULT}),
      .ram_cfg_icache_tag_o   (),
      .ram_cfg_icache_data_i  ('{default: prim_ram_1p_pkg::RAM_1P_CFG_REQ_DEFAULT}),
      .ram_cfg_icache_data_o  (),

      .cheriot_enable_i   (ibex_pkg::IbexMuBiOff),

      .hart_id_i          (32'b0),
      .boot_addr_i        (32'h00000000),
      .trvk_heap_base_addr_i(32'h00000000),

      .instr_req_o        (host_req[CoreI]),
      .instr_gnt_i        (host_gnt[CoreI]),
      .instr_rvalid_i     (host_rvalid[CoreI]),
      .instr_addr_o       (host_addr[CoreI]),
      .instr_rdata_i      (host_rdata[CoreI]),
      .instr_rdata_intg_i ('0),
      .instr_err_i        (host_err[CoreI]),

      .data_req_o         (host_req[CoreD]),
      .data_gnt_i         (host_gnt[CoreD]),
      .data_rvalid_i      (host_rvalid[CoreD]),
      .data_we_o          (host_we[CoreD]),
      .data_be_o          (host_be[CoreD]),
      .data_addr_o        (host_addr[CoreD]),
      .data_wdata_o       (host_wdata[CoreD]),
      .data_wdata_intg_o  (),
      .data_tag_o         (),
      .data_rdata_i       (host_rdata[CoreD]),
      .data_rdata_intg_i  ('0),
      .data_tag_i         (1'b0),
      .data_err_i         (host_err[CoreD]),

      .trvk_revbm_req_o   (),
      .trvk_revbm_gnt_i   (1'b0),
      .trvk_revbm_rvalid_i(1'b0),
      .trvk_revbm_addr_o  (),
      .trvk_revbm_rdata_i ('0),
      .trvk_revbm_rdata_intg_i('0),
      .trvk_revbm_err_i   (1'b0),

      .irq_software_i     (1'b0),
      .irq_timer_i        (1'b0),
      .irq_external_i     (1'b0),
      .irq_fast_i         (15'b0),
      .irq_nm_i           (1'b0),

      .scramble_key_valid_i('0),
      .scramble_key_i       ('0),
      .scramble_nonce_i     ('0),
      .scramble_req_o       (),

      .debug_req_i        (1'b0),
      .crash_dump_o       (),
      .double_fault_seen_o(),

      .fetch_enable_i     (ibex_pkg::IbexMuBiOn),
      .mcounteren_writable_i(ibex_pkg::IbexMuBiOn),
      .alert_minor_o      (),
      .alert_major_internal_o(),
      .alert_major_bus_o  (),
      .core_sleep_o       (),

      .lockstep_cmp_en_o  (),

      .data_req_shadow_o  (),
      .data_we_shadow_o   (),
      .data_be_shadow_o   (),
      .data_addr_shadow_o (),
      .data_wdata_shadow_o(),
      .data_wdata_intg_shadow_o(),

      .instr_req_shadow_o (),
      .instr_addr_shadow_o()
    );

  // --- RAM (32 KB). Note: plain Verilator-friendly array here; synth would use BRAM.
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

  // --- UART byte-capture register (+ software halt). Writes a byte to +0, halt at +8.
  simulator_ctrl #(
    .LogName("pa_smoke.log"),
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

  assign device_err[Ram]  = 1'b0;
  assign device_err[Uart] = 1'b0;
endmodule
