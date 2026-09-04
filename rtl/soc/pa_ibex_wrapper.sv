// PocketAI-T M1a -- ibex_core wrapper
//
// Wraps lowRISC ibex_top in an FPGA-oriented RV32IMC configuration (iterative
// M extension, staged LSU request, writeback stage, two-cycle branch handling,
// no I-cache, no
// branch predictor, no PMP, no
// Secure/CHERI). It exposes only the plain instruction
// and data memory ports (ibex "immediate grant, 1-cycle latency" protocol),
// the interrupt lines and reset, and hides all the optional/RVFI/trvk/
// lockstep/scramble/debug plumbing that is unused here.
//
// The reset vector is {boot_addr_i[31:8], 8'h80}. We boot from address 0 so
// the first instruction executed is at 0x0000_0080.

module pa_ibex_wrapper
# (
  // Hardware thread id, reported by the mhartid CSR
  parameter logic [31:0] HART_ID = 32'h0
) (
  input  logic        clk_i,
  input  logic        rst_ni,

  input  logic [31:0] boot_addr_i,

  // Instruction fetch port (slave: drives addr, waits for rvalid)
  output logic        instr_req_o,
  input  logic        instr_gnt_i,
  input  logic        instr_rvalid_i,
  output logic [31:0] instr_addr_o,
  input  logic [31:0] instr_rdata_i,
  input  logic        instr_err_i,

  // Data port (slave: drives addr/we/be/wdata, waits for rvalid)
  output logic        data_req_o,
  input  logic        data_gnt_i,
  input  logic        data_rvalid_i,
  output logic        data_we_o,
  output logic [3:0]  data_be_o,
  output logic [31:0] data_addr_o,
  output logic [31:0] data_wdata_o,
  input  logic [31:0] data_rdata_i,
  input  logic        data_err_i,

  // Interrupts (only external is wired up by the SoC)
  input  logic        irq_external_i,
  input  logic        irq_software_i,
  input  logic        irq_timer_i,

  // Diagnostics
  output logic        alert_major_internal_o,
  output logic        alert_major_bus_o
);

  // ---- FPGA-oriented configuration -----------------------------------------
  // RVFI is only enabled when RISCV_FORMAL is defined, so the rvfi_* ports do
  // not exist in this build. CHERI/Secure are off, so the cheriot/trvk paths
  // are tied to constant-off values.
  ibex_top #(
    .BaseIsa           (ibex_pkg::BaseIsaRV32I),
    .PMPEnable         (1'b0),
    .PMPGranularity    (0),
    .PMPNumRegions     (4),
    .MHPMCounterNum    (0),
    .MHPMCounterWidth  (40),
    .RV32E             (1'b0),
    // The iterative unit avoids both DSP48 inference and the long soft
    // multiplier path of RV32MFast at the board's fixed 100 MHz PL clock.
    .RV32M             (ibex_pkg::RV32MSlow),
    .RV32B             (ibex_pkg::RV32BNone),
    .RV32ZC            (ibex_pkg::RV32Zca),
    // The FPGA register file maps the two asynchronous read ports into
    // RAM32M primitives instead of a pair of deep 32:1 flip-flop mux trees.
    .RegFile           (ibex_pkg::RegFileFPGA),
    // Branch decisions and targets use the second execute cycle; this removes
    // the decode/compare/redirect path from the board clock period.
    .BranchTargetALU   (1'b0),
    .WritebackStage    (1'b1),
    .ICache            (1'b0),
    .ICacheECC         (1'b0),
    .ICacheScramble    (1'b0),
    .BranchPredictor   (1'b0),
    .DbgTriggerEn      (1'b0),
    .SecureIbex        (1'b0)
  ) u_ibex (
    .clk_i                     (clk_i),
    .rst_ni                    (rst_ni),

    .test_en_i                 (1'b0),
    .scan_rst_ni               (1'b1),
    .ram_cfg_icache_tag_i      ('{default: prim_ram_1p_pkg::RAM_1P_CFG_REQ_DEFAULT}),
    .ram_cfg_icache_tag_o      (),
    .ram_cfg_icache_data_i     ('{default: prim_ram_1p_pkg::RAM_1P_CFG_REQ_DEFAULT}),
    .ram_cfg_icache_data_o     (),

    .cheriot_enable_i          (ibex_pkg::IbexMuBiOff),
    .hart_id_i                 (HART_ID),
    .boot_addr_i               (boot_addr_i),

    .trvk_heap_base_addr_i     (32'h0),

    .instr_req_o               (instr_req_o),
    .instr_gnt_i               (instr_gnt_i),
    .instr_rvalid_i            (instr_rvalid_i),
    .instr_addr_o              (instr_addr_o),
    .instr_rdata_i             (instr_rdata_i),
    .instr_rdata_intg_i        (7'b0),
    .instr_err_i               (instr_err_i),

    .data_req_o                (data_req_o),
    .data_gnt_i                (data_gnt_i),
    .data_rvalid_i             (data_rvalid_i),
    .data_we_o                 (data_we_o),
    .data_be_o                 (data_be_o),
    .data_addr_o               (data_addr_o),
    .data_wdata_o              (data_wdata_o),
    .data_wdata_intg_o         (),
    .data_tag_o                (),
    .data_rdata_i              (data_rdata_i),
    .data_rdata_intg_i         (7'b0),
    .data_tag_i                (1'b0),
    .data_err_i                (data_err_i),

    .trvk_revbm_req_o          (),
    .trvk_revbm_gnt_i          (1'b0),
    .trvk_revbm_rvalid_i       (1'b0),
    .trvk_revbm_addr_o         (),
    .trvk_revbm_rdata_i        ('0),
    .trvk_revbm_rdata_intg_i   ('0),
    .trvk_revbm_err_i          (1'b0),

    .irq_software_i            (irq_software_i),
    .irq_timer_i               (irq_timer_i),
    .irq_external_i            (irq_external_i),
    .irq_fast_i                (15'b0),
    .irq_nm_i                  (1'b0),

    .scramble_key_valid_i      (1'b0),
    .scramble_key_i            ('0),
    .scramble_nonce_i          ('0),
    .scramble_req_o            (),

    .debug_req_i               (1'b0),
    .crash_dump_o              (),
    .double_fault_seen_o       (),

    .fetch_enable_i            (ibex_pkg::IbexMuBiOn),
    .mcounteren_writable_i     (ibex_pkg::IbexMuBiOn),
    .alert_minor_o             (),
    .alert_major_internal_o    (alert_major_internal_o),
    .alert_major_bus_o         (alert_major_bus_o),
    .core_sleep_o              (),

    .lockstep_cmp_en_o         (),

    .data_req_shadow_o         (),
    .data_we_shadow_o          (),
    .data_be_shadow_o          (),
    .data_addr_shadow_o        (),
    .data_wdata_shadow_o       (),
    .data_wdata_intg_shadow_o  (),

    .instr_req_shadow_o        (),
    .instr_addr_shadow_o       ()
  );

endmodule
