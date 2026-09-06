set root_dir [file normalize [file dirname [file dirname [info script]]]]
set build_dir [file normalize $::env(M5_VIVADO_BUILD_DIR)]
set board_repo [file normalize $::env(PYNQ_BOARD_REPO)]
set source_tcl [file normalize $::env(M5_SOURCE_TCL)]
set reports_dir [file normalize "$build_dir/reports"]
set target_clock_mhz 91.0
set target_period_ns [expr {1000.0 / $target_clock_mhz}]
set implementation_margin_ns [expr {$target_period_ns - 10.0}]

source $source_tcl
# Also reject bypassing the shell build wrapper with unqualified CPU sources.
puts [exec python3 "$root_dir/scripts/check_m5_sources.py" [file dirname $source_tcl]]
file mkdir $build_dir
file mkdir $reports_dir
set_param board.repoPaths [list $board_repo]
create_project m5_pynq $build_dir -part xc7z020clg400-1 -force
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
if {[llength $pocketai_memory_files] != 2} { error "Expected both pinned SFPU ROMs" }
foreach memory_file $pocketai_memory_files {
  file copy -force $memory_file "$build_dir/[file tail $memory_file]"
}
add_files -norecurse $pocketai_memory_files
set_property file_type {Memory Initialization Files} [get_files $pocketai_memory_files]
update_compile_order -fileset sources_1

create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 processing_system7_0
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
  -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
  [get_bd_cells processing_system7_0]
set_property -dict [list \
  CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_USE_M_AXI_GP1 {0} \
  CONFIG.PCW_USE_S_AXI_GP0 {0} CONFIG.PCW_USE_S_AXI_GP1 {0} \
  CONFIG.PCW_USE_S_AXI_HP0 {1} CONFIG.PCW_USE_S_AXI_HP1 {0} \
  CONFIG.PCW_USE_S_AXI_HP2 {0} CONFIG.PCW_USE_S_AXI_HP3 {0} \
  CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_EN_RST0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100.000000}] [get_bd_cells processing_system7_0]

create_bd_cell -type module -reference pa_cluster_m5_board pa_cluster_m5_0
create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz clk_wiz_0
set_property -dict [list CONFIG.PRIM_IN_FREQ {100.000} CONFIG.PRIM_SOURCE {No_buffer} \
  CONFIG.CLKOUT1_REQUESTED_OUT_FREQ $target_clock_mhz CONFIG.USE_LOCKED {true} \
  CONFIG.USE_RESET {true} CONFIG.RESET_TYPE {ACTIVE_LOW}] [get_bd_cells clk_wiz_0]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_fclk0
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect ctrl_smc
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {5}] [get_bd_cells ctrl_smc]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect hp_smc
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells hp_smc]

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio control_gpio
set_property -dict [list CONFIG.C_GPIO_WIDTH {5} CONFIG.C_ALL_OUTPUTS {1} \
  CONFIG.C_DOUT_DEFAULT {0x00000010}] [get_bd_cells control_gpio]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio table_gpio
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_OUTPUTS {1} \
  CONFIG.C_DOUT_DEFAULT {0x00000000}] [get_bd_cells table_gpio]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio arena_gpio
set_property -dict [list CONFIG.C_GPIO_WIDTH {32} CONFIG.C_ALL_OUTPUTS {1} \
  CONFIG.C_DOUT_DEFAULT {0x10000000}] [get_bd_cells arena_gpio]
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio status_gpio
set_property -dict [list CONFIG.C_GPIO_WIDTH {8} CONFIG.C_ALL_INPUTS {1}] [get_bd_cells status_gpio]
for {set bit 0} {$bit < 5} {incr bit} {
  create_bd_cell -type ip -vlnv xilinx.com:ip:xlslice control_slice_$bit
  set_property -dict [list CONFIG.DIN_WIDTH {5} CONFIG.DIN_FROM $bit \
    CONFIG.DIN_TO $bit CONFIG.DOUT_WIDTH {1}] [get_bd_cells control_slice_$bit]
  connect_bd_net [get_bd_pins control_gpio/gpio_io_o] [get_bd_pins control_slice_$bit/Din]
}

set ps_fclk [get_bd_pins processing_system7_0/FCLK_CLK0]
set fabric_clk [get_bd_pins clk_wiz_0/clk_out1]
set frstn [get_bd_pins processing_system7_0/FCLK_RESET0_N]
set rstn [get_bd_pins rst_fclk0/peripheral_aresetn]
connect_bd_net $ps_fclk [get_bd_pins clk_wiz_0/clk_in1]
connect_bd_net $frstn [get_bd_pins clk_wiz_0/resetn]
connect_bd_net [get_bd_pins clk_wiz_0/locked] [get_bd_pins rst_fclk0/dcm_locked]
connect_bd_net $frstn [get_bd_pins rst_fclk0/ext_reset_in]
foreach pin [list processing_system7_0/M_AXI_GP0_ACLK processing_system7_0/S_AXI_HP0_ACLK \
  pa_cluster_m5_0/s_axi_aclk ctrl_smc/aclk hp_smc/aclk control_gpio/s_axi_aclk \
  table_gpio/s_axi_aclk arena_gpio/s_axi_aclk status_gpio/s_axi_aclk \
  rst_fclk0/slowest_sync_clk] { connect_bd_net $fabric_clk [get_bd_pins $pin] }
foreach pin [list pa_cluster_m5_0/s_axi_aresetn ctrl_smc/aresetn hp_smc/aresetn \
  control_gpio/s_axi_aresetn table_gpio/s_axi_aresetn arena_gpio/s_axi_aresetn \
  status_gpio/s_axi_aresetn] { connect_bd_net $rstn [get_bd_pins $pin] }

connect_bd_net [get_bd_pins control_slice_0/Dout] [get_bd_pins pa_cluster_m5_0/cluster_aresetn]
connect_bd_net [get_bd_pins control_slice_1/Dout] [get_bd_pins pa_cluster_m5_0/core_aresetn]
connect_bd_net [get_bd_pins control_slice_2/Dout] [get_bd_pins pa_cluster_m5_0/cfg_enable]
connect_bd_net [get_bd_pins control_slice_3/Dout] [get_bd_pins pa_cluster_m5_0/cfg_flush]
connect_bd_net [get_bd_pins control_slice_4/Dout] [get_bd_pins pa_cluster_m5_0/memory_abort]
connect_bd_net [get_bd_pins table_gpio/gpio_io_o] [get_bd_pins pa_cluster_m5_0/cfg_table_base]
connect_bd_net [get_bd_pins arena_gpio/gpio_io_o] [get_bd_pins pa_cluster_m5_0/cfg_arena_bytes]
connect_bd_net [get_bd_pins pa_cluster_m5_0/status] [get_bd_pins status_gpio/gpio_io_i]

connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] [get_bd_intf_pins ctrl_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ctrl_smc/M00_AXI] [get_bd_intf_pins pa_cluster_m5_0/s_axi]
connect_bd_intf_net [get_bd_intf_pins ctrl_smc/M01_AXI] [get_bd_intf_pins control_gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins ctrl_smc/M02_AXI] [get_bd_intf_pins table_gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins ctrl_smc/M03_AXI] [get_bd_intf_pins arena_gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins ctrl_smc/M04_AXI] [get_bd_intf_pins status_gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins pa_cluster_m5_0/m_axi] [get_bd_intf_pins hp_smc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins hp_smc/M00_AXI] [get_bd_intf_pins processing_system7_0/S_AXI_HP0]

assign_bd_address -offset 0x43C00000 -range 0x00020000 \
  [get_bd_addr_segs -of_objects [get_bd_intf_pins pa_cluster_m5_0/s_axi]]
assign_bd_address -offset 0x41200000 -range 0x00010000 \
  [get_bd_addr_segs -of_objects [get_bd_intf_pins control_gpio/S_AXI]]
assign_bd_address -offset 0x41210000 -range 0x00010000 \
  [get_bd_addr_segs -of_objects [get_bd_intf_pins table_gpio/S_AXI]]
assign_bd_address -offset 0x41220000 -range 0x00010000 \
  [get_bd_addr_segs -of_objects [get_bd_intf_pins arena_gpio/S_AXI]]
assign_bd_address -offset 0x41230000 -range 0x00010000 \
  [get_bd_addr_segs -of_objects [get_bd_intf_pins status_gpio/S_AXI]]
assign_bd_address
validate_bd_design
save_bd_design

set bd_file "$build_dir/m5_pynq.srcs/sources_1/bd/system/system.bd"
set_property SYNTH_CHECKPOINT_MODE None [get_files $bd_file]
generate_target all [get_files $bd_file]
set wrapper [make_wrapper -files [get_files $bd_file] -top]
add_files -norecurse $wrapper
set_property top system_wrapper [current_fileset]
update_compile_order -fileset sources_1

set margin_xdc "$build_dir/m5_implementation_margin.xdc"
set margin_fd [open $margin_xdc w]
puts $margin_fd "set m5_margin_clocks \[get_clocks -quiet -filter {PERIOD > [expr {$target_period_ns - 0.01}] && PERIOD < [expr {$target_period_ns + 0.01}]}\]"
puts $margin_fd "set_clock_uncertainty -setup $implementation_margin_ns \$m5_margin_clocks"
close $margin_fd
add_files -fileset constrs_1 -norecurse $margin_xdc
set_property strategy Flow_PerfOptimized_high [get_runs synth_1]
set_property STEPS.SYNTH_DESIGN.ARGS.MAX_DSP 0 [get_runs synth_1]
set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY full [get_runs synth_1]
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-fanout_limit 16} -objects [get_runs synth_1]
set_property strategy Performance_ExploreWithRemap [get_runs impl_1]
set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE Explore [get_runs impl_1]
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
  error "Implementation failed: $impl_status"
}
open_run impl_1
phys_opt_design -directive AggressiveExplore
write_checkpoint -force "$build_dir/m5_candidate.dcp"
set fabric_clocks [get_clocks -quiet -filter "PERIOD > [expr {$target_period_ns - 0.01}] && PERIOD < [expr {$target_period_ns + 0.01}]" ]
if {[llength $fabric_clocks] != 1} { error "Expected one $target_clock_mhz MHz fabric clock" }
set_clock_uncertainty -setup 0.0 $fabric_clocks
report_utilization -file "$reports_dir/m5_utilization.rpt"
report_timing_summary -file "$reports_dir/m5_timing_summary.rpt"
report_route_status -file "$reports_dir/m5_route_status.rpt"
report_drc -file "$reports_dir/m5_drc.rpt"
report_methodology -file "$reports_dir/m5_methodology.rpt"
report_timing -delay_type max -max_paths 100 -nworst 1 -file "$reports_dir/m5_worst_paths.rpt"

set timing_fd [open "$reports_dir/m5_timing_summary.rpt" r]
set timing_report [read $timing_fd]
close $timing_fd
foreach check {no_clock constant_clock pulse_width_clock unconstrained_internal_endpoints \
               no_input_delay no_output_delay multiple_clock generated_clocks loops \
               partial_input_delay partial_output_delay latch_loops} {
  set pattern [format {checking %s \(([0-9]+)\)} $check]
  if {![regexp $pattern $timing_report -> count] || $count != 0} {
    error "Timing constraint check failed: $check"
  }
}
set route_fd [open "$reports_dir/m5_route_status.rpt" r]
set route_report [read $route_fd]
close $route_fd
if {![regexp {# of nets with routing errors\.+\s*:\s*([0-9]+)} $route_report -> route_errors] || $route_errors != 0} {
  error "Final design is not fully routed"
}
set methodology_fd [open "$reports_dir/m5_methodology.rpt" r]
set methodology_report [read $methodology_fd]
close $methodology_fd
if {[regexp {Critical Warning|\|\s*Error\s*\|} $methodology_report]} {
  error "Methodology report contains errors or critical warnings"
}
set worst_slack [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set hold_slack [get_property SLACK [get_timing_paths -delay_type min -max_paths 1]]
if {$worst_slack < 0.250} { error "$target_clock_mhz MHz WNS $worst_slack ns is below +0.250 ns" }
if {$hold_slack <= 0.0} { error "Hold slack $hold_slack ns is not positive" }
if {[expr {abs([get_property PERIOD $fabric_clocks] - $target_period_ns)}] > 0.001} {
  error "Fabric clock period mismatch"
}
set dsp_cells [get_cells -quiet -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}]
if {[llength $dsp_cells] != 0} { error "DSP-free contract failed" }
set drc_errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
set drc_critical [get_drc_violations -quiet -filter {SEVERITY == {Critical Warning}}]
if {[llength $drc_errors] || [llength $drc_critical]} { error "Final DRC failed" }
set drc_warnings [get_drc_violations -quiet -filter {SEVERITY == Warning}]
foreach warning $drc_warnings {
  if {![string match "RTSTAT-10#*" $warning]} { error "Unexpected DRC warning: $warning" }
}

set bit_src "$build_dir/m5_pynq.runs/impl_1/system_wrapper.bit"
write_checkpoint -force "$build_dir/m5_pynq_final.dcp"
write_bitstream -force $bit_src
file copy -force $bit_src "$build_dir/m5_pynq.bit"
set hwh_src "$build_dir/m5_pynq.gen/sources_1/bd/system/hw_handoff/system.hwh"
if {![file exists $hwh_src]} { error "PYNQ hardware handoff missing" }
file copy -force $hwh_src "$build_dir/m5_pynq.hwh"
write_hw_platform -fixed -force -file "$build_dir/m5_pynq.xsa"
puts "M5 VIVADO PASS clock_mhz=$target_clock_mhz setup_wns_ns=$worst_slack setup_tns_ns=0 hold_wns_ns=$hold_slack dsp48=0 drc_errors=0 reviewed_drc_warnings=[llength $drc_warnings]"
