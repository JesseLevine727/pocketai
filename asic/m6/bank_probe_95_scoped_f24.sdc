# Diagnostic-only variant of bank_probe_95_scoped.sdc that raises the global
# fanout limit from 16 to 24. Used solely to test whether the fanout rule is
# what limits antenna closure; it is not a promoted constraint and no result
# produced with it is a qualified pass. All other limits are unchanged.
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
set_max_fanout 24 [current_design]
set_max_transition 0.75 [current_design]
if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
