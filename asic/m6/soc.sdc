# Native-AXI intermediate core, NOT pad/package timing. Units ns and pF.
# Candidate external 25-MHz clock; the falling-edge divider yields 12.5 MHz
# system clock, rising at 20 ns, falling at 60 ns and rising again at 100 ns.
# This is a trial constraint, not an achieved frequency.
create_clock -name mem_clk -period 40 [get_ports clk_mem_i]
# Attach to the actual divider's Q pin, not just its exported output port:
# clocks must propagate to internal system-clock loads as well as off-chip.
# Port buffering can move clk_sys_o onto a new leaf net. Select the divider
# register itself, whose qualified u_clock hierarchy contains exactly one Q.
set divider_q [get_pins -hierarchical {u_clock.*/Q}]
if {[llength $divider_q] != 1} { error "expected exactly one system-clock driver" }
create_generated_clock -name sys_clk -source [get_ports clk_mem_i] \
    -edges {2 4 6} $divider_q
source [file join [file dirname [info script]] clock_data_boundaries.tcl]
pa_m6_stop_clock_data [lindex $divider_q 0]

# A synchronous external controller launches/captures on exported sys_clk.
# Assumptions: 0.5..8 ns input arrival, 0.5..8 ns external output requirement,
# 0.1-pF boundary load; these are a declared interface contract, not a board.
set data_inputs [all_inputs]
set clock_index [lsearch -exact $data_inputs [get_ports clk_mem_i]]
set data_inputs [lreplace $data_inputs $clock_index $clock_index]
set_input_delay -clock sys_clk -min 0.5 $data_inputs
set_input_delay -clock sys_clk -max 8.0 $data_inputs
set data_outputs [all_outputs]
set clock_index [lsearch -exact $data_outputs [get_ports clk_sys_o]]
set data_outputs [lreplace $data_outputs $clock_index $clock_index]
set_output_delay -clock sys_clk -min 0.5 $data_outputs
set_output_delay -clock sys_clk -max 8.0 $data_outputs
set_load 0.1 $data_outputs
set_load 0.1 [get_ports clk_sys_o]
set_input_transition 0.2 [all_inputs]
set_clock_uncertainty 0.25 [all_clocks]
set_clock_transition 0.15 [all_clocks]
set_max_fanout 16 [current_design]
set_max_transition 1.5 [current_design]
# Chip-level reset is asynchronous assertion only. Deassertion must be
# synchronized externally; no blanket reset false-path hides recovery checks.
if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
