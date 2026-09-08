# User-approved 95-MHz probe, 2026-09-08. Only clock period differs from
# bank_probe.sdc; preserve the historical 100-MHz constraints and results.
# Boundary budgets do not qualify pads, a package or the complete chip.
create_clock -name sys_clk -period 10.526315789474 [get_ports clk]
set data_inputs [all_inputs]
set clock_index [lsearch -exact $data_inputs [get_ports clk]]
set data_inputs [lreplace $data_inputs $clock_index $clock_index]
set_input_delay -clock sys_clk -min 0.5 $data_inputs
set_input_delay -clock sys_clk -max 2.0 $data_inputs
set_output_delay -clock sys_clk -min 0.5 [all_outputs]
set_output_delay -clock sys_clk -max 2.0 [all_outputs]
set_input_transition 0.15 [all_inputs]
set_load 0.02 [all_outputs]
set_clock_uncertainty 0.25 [all_clocks]
set_clock_transition 0.15 [all_clocks]
set_max_fanout 16 [current_design]
set_max_transition 0.35 [current_design]
if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
