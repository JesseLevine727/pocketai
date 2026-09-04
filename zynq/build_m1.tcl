set root_dir [file normalize [file dirname [file dirname [info script]]]]
set build_dir [file normalize $::env(M1_VIVADO_BUILD_DIR)]
set board_repo [file normalize $::env(PYNQ_BOARD_REPO)]
set source_tcl [file normalize $::env(M1_SOURCE_TCL)]
set reports_dir [file normalize "$build_dir/reports"]
set target_clock_mhz 95.0
set target_period_ns [expr {1000.0 / $target_clock_mhz}]
set implementation_margin_ns [expr {$target_period_ns - 10.0}]

source $source_tcl
file mkdir $build_dir
file mkdir $reports_dir

set_param board.repoPaths [list $board_repo]
create_project m1_pynq $build_dir -part xc7z020clg400-1 -force
set_property board_part www.digilentinc.com:pynq-z1:part0:1.0 [current_project]

add_files -norecurse $pocketai_rtl_files
set_property file_type SystemVerilog [get_files $pocketai_rtl_files]
if {[llength $pocketai_verilog_files] != 0} {
    add_files -norecurse $pocketai_verilog_files
    set_property file_type Verilog [get_files $pocketai_verilog_files]
}
if {[llength $pocketai_include_files] != 0} {
    add_files -norecurse $pocketai_include_files
    set_property file_type {SystemVerilog Header} [get_files $pocketai_include_files]
}
set_property include_dirs $pocketai_include_dirs [current_fileset]
update_compile_order -fileset sources_1

create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 processing_system7_0
apply_bd_automation \
    -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
    [get_bd_cells processing_system7_0]

set_property -dict [list \
    CONFIG.PCW_USE_M_AXI_GP0 {1} \
    CONFIG.PCW_USE_M_AXI_GP1 {0} \
    CONFIG.PCW_USE_S_AXI_GP0 {0} \
    CONFIG.PCW_USE_S_AXI_GP1 {0} \
    CONFIG.PCW_USE_S_AXI_HP0 {0} \
    CONFIG.PCW_USE_S_AXI_HP1 {0} \
    CONFIG.PCW_USE_S_AXI_HP2 {0} \
    CONFIG.PCW_USE_S_AXI_HP3 {0} \
    CONFIG.PCW_EN_CLK0_PORT {1} \
    CONFIG.PCW_EN_RST0_PORT {1} \
    CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000} \
] [get_bd_cells processing_system7_0]

create_bd_cell -type module -reference pa_cluster_board pa_cluster_0
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz clk_wiz_0
set_property -dict [list \
    CONFIG.PRIM_IN_FREQ {100.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ $target_clock_mhz \
    CONFIG.USE_LOCKED {true} \
    CONFIG.USE_RESET {true} \
    CONFIG.RESET_TYPE {ACTIVE_LOW} \
] [get_bd_cells clk_wiz_0]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect axi_smc
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {2}] [get_bd_cells axi_smc]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio core_reset_gpio
set_property -dict [list \
    CONFIG.C_GPIO_WIDTH {1} \
    CONFIG.C_ALL_OUTPUTS {1} \
    CONFIG.C_DOUT_DEFAULT {0x00000000} \
] [get_bd_cells core_reset_gpio]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_fclk0

set ps_fclk [get_bd_pins processing_system7_0/FCLK_CLK0]
set fabric_clk [get_bd_pins clk_wiz_0/clk_out1]
set frstn [get_bd_pins processing_system7_0/FCLK_RESET0_N]
set rstn [get_bd_pins rst_fclk0/peripheral_aresetn]

connect_bd_net $ps_fclk [get_bd_pins clk_wiz_0/clk_in1]
connect_bd_net $frstn [get_bd_pins clk_wiz_0/resetn]
connect_bd_net [get_bd_pins clk_wiz_0/locked] [get_bd_pins rst_fclk0/dcm_locked]
connect_bd_net $fabric_clk [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK]
connect_bd_net $fabric_clk [get_bd_pins pa_cluster_0/s_axi_aclk]
connect_bd_net $fabric_clk [get_bd_pins axi_smc/aclk]
connect_bd_net $fabric_clk [get_bd_pins core_reset_gpio/s_axi_aclk]
connect_bd_net $fabric_clk [get_bd_pins rst_fclk0/slowest_sync_clk]
connect_bd_net $frstn [get_bd_pins rst_fclk0/ext_reset_in]
connect_bd_net $rstn [get_bd_pins pa_cluster_0/s_axi_aresetn]
connect_bd_net $rstn [get_bd_pins axi_smc/aresetn]
connect_bd_net $rstn [get_bd_pins core_reset_gpio/s_axi_aresetn]
connect_bd_net [get_bd_pins core_reset_gpio/gpio_io_o] \
               [get_bd_pins pa_cluster_0/core_aresetn]

connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] \
                    [get_bd_intf_pins axi_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_smc/M00_AXI] \
                    [get_bd_intf_pins pa_cluster_0/S_AXI_CTRL]
connect_bd_intf_net [get_bd_intf_pins axi_smc/M01_AXI] \
                    [get_bd_intf_pins core_reset_gpio/S_AXI]

assign_bd_address
set cluster_seg [get_bd_addr_segs -of_objects [get_bd_intf_pins pa_cluster_0/S_AXI_CTRL]]
set gpio_seg [get_bd_addr_segs -of_objects [get_bd_intf_pins core_reset_gpio/S_AXI]]
assign_bd_address -offset 0x43C00000 -range 0x00020000 $cluster_seg
assign_bd_address -offset 0x43C20000 -range 0x00010000 $gpio_seg

validate_bd_design
set ext_reset_polarity [get_property CONFIG.POLARITY \
    [get_bd_pins rst_fclk0/ext_reset_in]]
if {$ext_reset_polarity ne "ACTIVE_LOW"} {
    error "Reset polarity propagation failed: rst_fclk0/ext_reset_in is $ext_reset_polarity"
}
save_bd_design

set bd_file "$build_dir/m1_pynq.srcs/sources_1/bd/system/system.bd"
# Synthesize the module-reference RTL in the top-level run.  A hierarchical
# checkpoint would otherwise optimize pa_cluster without the 100 MHz clock
# constraint, producing an area-oriented netlist that cannot meet timing.
set_property SYNTH_CHECKPOINT_MODE None [get_files $bd_file]
generate_target all [get_files $bd_file]
set wrapper [make_wrapper -files [get_files $bd_file] -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1

# The physical design is optimized against a 100 MHz setup target, while the
# generated fabric clock remains exactly 95 MHz. This implementation-only
# margin keeps routing from stopping as soon as WNS first becomes positive.
# It is removed before qualification reports and final artifact generation.
set margin_xdc "$build_dir/m1_implementation_margin.xdc"
set margin_fd [open $margin_xdc w]
puts $margin_fd "set m1_margin_clocks \[get_clocks -quiet -filter {PERIOD > 10.52 && PERIOD < 10.54}\]"
puts $margin_fd "set_clock_uncertainty -setup $implementation_margin_ns \$m1_margin_clocks"
close $margin_fd
add_files -fileset constrs_1 -norecurse $margin_xdc

# The project contract requires soft logic for every multiply, including the
# two Ibex M-extension units. Prevent Vivado from inferring DSP48 primitives.
set_property strategy Flow_PerfOptimized_high [get_runs synth_1]
set_property STEPS.SYNTH_DESIGN.ARGS.MAX_DSP 0 [get_runs synth_1]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY full [get_runs synth_1]
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} \
    -value {-fanout_limit 16} -objects [get_runs synth_1]
set_property strategy Performance_NetDelay_high [get_runs impl_1]
# NetDelay_high improves the 7-series routing-dominated Ibex paths. Retain a
# normal post-route Explore pass, then run one deterministic aggressive pass
# below before accepting timing and emitting the final bitstream.
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]
set_property STEPS.POST_ROUTE_PHYS_OPT_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]

launch_runs synth_1 -jobs 8
wait_on_run synth_1
set synth_status [get_property STATUS [get_runs synth_1]]
if {[string match "*ERROR*" $synth_status] || [string match "*Failed*" $synth_status]} {
    error "Synthesis failed: $synth_status"
}

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
set impl_status [get_property STATUS [get_runs impl_1]]
if {![string match "*write_bitstream Complete*" $impl_status]} {
    error "Implementation/bitstream failed: $impl_status"
}

open_run impl_1
phys_opt_design -directive AggressiveExplore
set fabric_clocks [get_clocks -quiet -filter {PERIOD > 10.52 && PERIOD < 10.54}]
if {[llength $fabric_clocks] != 1} {
    error "Expected one 95 MHz fabric timing clock, found [llength $fabric_clocks]"
}
# Qualify the routed design at the true generated-clock constraint, not the
# tighter implementation target used to guide placement and routing.
set_clock_uncertainty -setup 0.0 $fabric_clocks
report_utilization -file "$reports_dir/m1_utilization.rpt"
report_timing_summary -file "$reports_dir/m1_timing_summary.rpt"
report_route_status -file "$reports_dir/m1_route_status.rpt"
report_drc -file "$reports_dir/m1_drc.rpt"
report_timing -delay_type max -max_paths 100 -nworst 1 \
    -file "$reports_dir/m1_worst_paths.rpt"

set worst_path [get_timing_paths -delay_type max -max_paths 1]
set worst_slack [get_property SLACK $worst_path]
set minimum_setup_slack 0.250
if {$worst_slack < $minimum_setup_slack} {
    error "$target_clock_mhz MHz setup margin failed: worst slack $worst_slack ns; require at least $minimum_setup_slack ns"
}
set worst_hold_path [get_timing_paths -delay_type min -max_paths 1]
set worst_hold_slack [get_property SLACK $worst_hold_path]
if {$worst_hold_slack < 0.0} {
    error "$target_clock_mhz MHz hold timing failed: worst hold slack $worst_hold_slack ns"
}
set fabric_period [get_property PERIOD $fabric_clocks]
if {[expr {abs($fabric_period - $target_period_ns)}] > 0.001} {
    error "Fabric clock period is $fabric_period ns; expected $target_period_ns ns ($target_clock_mhz MHz)"
}

set dsp_cells [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}]
if {[llength $dsp_cells] != 0} {
    error "DSP-free contract failed: [llength $dsp_cells] DSP primitives"
}

set drc_errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
if {[llength $drc_errors] != 0} {
    error "DRC failed: [llength $drc_errors] error violations"
}
set drc_critical [get_drc_violations -quiet -filter {SEVERITY == {Critical Warning}}]
if {[llength $drc_critical] != 0} {
    error "DRC failed: [llength $drc_critical] critical-warning violations"
}
# Vivado 2025.1 leaves reset-pipeline nets without routable loads inside its
# generated SmartConnect. Accept that single vendor-IP warning, but fail the
# build if any different or additional DRC warning appears.
set drc_warnings [get_drc_violations -quiet -filter {SEVERITY == Warning}]
if {[llength $drc_warnings] > 1 ||
    ([llength $drc_warnings] == 1 &&
     ![string match "RTSTAT-10#*" [lindex $drc_warnings 0]])} {
    error "DRC failed: unexpected warning violations: $drc_warnings"
}

set bit_src "$build_dir/m1_pynq.runs/impl_1/system_wrapper.bit"
# The implementation run wrote a pre-final bitstream before the additional
# aggressive pass. Replace it with the timing-qualified in-memory design.
write_checkpoint -force "$build_dir/m1_pynq_final.dcp"
write_bitstream -force $bit_src
file copy -force $bit_src "$build_dir/m1_pynq.bit"
set hwh_src "$build_dir/m1_pynq.gen/sources_1/bd/system/hw_handoff/system.hwh"
if {![file exists $hwh_src]} {
    error "PYNQ hardware handoff missing: $hwh_src"
}
file copy -force $hwh_src "$build_dir/m1_pynq.hwh"
write_hw_platform -fixed -include_bit -force -file "$build_dir/m1_pynq.xsa"
set preferred_margin_met [expr {$worst_slack >= 0.500}]
puts "M1 VIVADO PASS clock_mhz=$target_clock_mhz setup_wns_ns=$worst_slack setup_tns_ns=0 min_setup_slack_ns=$minimum_setup_slack hold_wns_ns=$worst_hold_slack dsp48=0 drc_errors=0 reviewed_drc_warnings=[llength $drc_warnings] preferred_margin_0p500ns=$preferred_margin_met"
