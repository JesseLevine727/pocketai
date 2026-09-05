# Exploration from a private pre-route checkpoint. Replicate the measured
# Ibex adder-control fanout before routing; no RTL/timing exceptions are added.
open_checkpoint $::env(M3_DIAGNOSTIC_DCP)
set nets [get_nets -hier -filter {NAME =~ *u_ibex_core/ex_block_i/alu_i/adder_in_b00}]
if {[llength $nets] != 2} { error "expected the two measured Ibex adder-control nets: $nets" }
puts "M3 REPLICATION EXPERIMENT nets=$nets"
phys_opt_design -force_replication_on_nets $nets
phys_opt_design -directive AggressiveExplore
route_design -directive Explore
phys_opt_design -directive Explore
phys_opt_design -directive AggressiveExplore
write_checkpoint -force "$::env(M3_DIAGNOSTIC_OUTPUT)/candidate.dcp"
set clocks [get_clocks -quiet -filter {PERIOD > 10.52 && PERIOD < 10.54}]
if {[llength $clocks] != 1} { error "expected one 95 MHz fabric clock" }
set_clock_uncertainty -setup 0.0 $clocks
report_timing_summary -file "$::env(M3_DIAGNOSTIC_OUTPUT)/timing.rpt"
report_timing -delay_type max -max_paths 100 -file "$::env(M3_DIAGNOSTIC_OUTPUT)/paths.rpt"
puts "M3 REPLICATION EXPERIMENT final_wns=[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]"
