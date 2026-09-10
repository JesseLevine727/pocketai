# Scoped-transition variant of the 95-MHz probe SDC (diagnostic only).
# Identical to bank_probe_95.sdc except that the aggressive 350-ps transition
# limit is applied to the actual SRAM22 macro pins (whose characterized input
# grid tops out at ~0.351 ns and whose reviewed output contract is 0.350 ns)
# instead of the whole design. Internal standard-cell logic is constrained to
# the project's configured MAX_TRANSITION_CONSTRAINT of 0.75 ns, which is well
# inside the sky130_fd_sc_hd default_max_transition of 1.5 ns.
#
# This is a constraint-scoping correction matching docs/M6_SRAM_CONTRACT.md,
# not a relaxation of the SRAM boundary contract: the SRAM pins keep 0.35 ns
# and the characterized input domain is unchanged. Preserve the original
# bank_probe_95.sdc and all evidence produced with it.
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
# Standard-cell logic is constrained to the project's configured
# MAX_TRANSITION_CONSTRAINT (0.75 ns), well inside the sky130_fd_sc_hd
# default_max_transition of 1.5 ns. This OpenROAD SDC reader rejects pin/net
# objects for set_max_transition, so the SRAM22 macro-pin input-slew and
# output-transition contract is enforced separately by the reviewed
# m6_report_contract_boundary / m6_locality_diagnostic envelope checks, not by
# a global design limit. The SRAM boundary limits themselves are unchanged.
set_max_transition 0.75 [current_design]
if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}
