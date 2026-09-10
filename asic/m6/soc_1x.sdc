# Single-clock native-AXI core at 95 MHz (10.526315789474 ns). clk_mem_i is the
# system clock and is bound directly to the SRAM clock (no divider or phase).
# Native AXI remains the explicit external-memory boundary; this is an
# intermediate core contract, not a pad/package/board constraint.
create_clock -name sys_clk -period 10.526315789474 [get_ports clk_mem_i]
set data_inputs [all_inputs]
set clock_index [lsearch -exact $data_inputs [get_ports clk_mem_i]]
set data_inputs [lreplace $data_inputs $clock_index $clock_index]
set_input_delay -clock sys_clk -min 0.5 $data_inputs
set_input_delay -clock sys_clk -max 2.0 $data_inputs
set data_outputs [all_outputs]
set clock_index [lsearch -exact $data_outputs [get_ports clk_sys_o]]
set data_outputs [lreplace $data_outputs $clock_index $clock_index]
set_output_delay -clock sys_clk -min 0.5 $data_outputs
set_output_delay -clock sys_clk -max 2.0 $data_outputs
set_load 0.1 $data_outputs
set_load 0.1 [get_ports clk_sys_o]
set_input_transition 0.2 [all_inputs]
set_clock_uncertainty 0.25 [all_clocks]
set_clock_transition 0.15 [all_clocks]
set_max_fanout 16 [current_design]
set_max_transition 1.5 [current_design]
if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
