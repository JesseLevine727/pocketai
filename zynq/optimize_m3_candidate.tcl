# Exploratory physical optimization only; never exports an accepted bitstream.
# Preserve the source checkpoint and final-build gating separately.
open_checkpoint $::env(M3_DIAGNOSTIC_DCP)
set clocks [get_clocks -quiet -filter {PERIOD > 10.52 && PERIOD < 10.54}]
if {[llength $clocks] != 1} { error "expected one 95 MHz fabric clock" }
if {[info exists ::env(M3_POSTOPT_PINS)]} {
    set experiments {critical_pin_opt routing_opt placement_opt restruct_opt clock_opt}
} else {
    set experiments {AlternateReplication Explore AggressiveExplore}
}
foreach directive $experiments {
    if {[info exists ::env(M3_POSTOPT_PINS)]} {
        phys_opt_design -$directive
    } else {
        phys_opt_design -directive $directive
    }
    set slack [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
    puts "M3 PHYSICAL EXPERIMENT directive=$directive constrained_wns=$slack"
    write_checkpoint -force "$::env(M3_DIAGNOSTIC_OUTPUT)/$directive.dcp"
}
set_clock_uncertainty -setup 0.0 $clocks
report_timing_summary -file "$::env(M3_DIAGNOSTIC_OUTPUT)/timing.rpt"
report_timing -delay_type max -max_paths 100 -file "$::env(M3_DIAGNOSTIC_OUTPUT)/paths.rpt"
puts "M3 PHYSICAL EXPERIMENT final_wns=[get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]"
