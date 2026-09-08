# Early, read-only screening of a fresh synthesized startup checkpoint.
# Final routed timing/DRC qualification is still mandatory.
if {$argc != 2} { error "expected startup checkpoint and fresh report directory" }
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {![string match */m5_startup_*/* $checkpoint] ||
    ![string match m5_startup_* [file tail $output]] || [file exists $output]} {
  error "isolated startup input and fresh output required"
}
file mkdir $output
open_checkpoint $checkpoint
set checks [get_drc_checks -quiet REQP-1839]
if {[llength $checks] != 1} { error "missing asynchronous BRAM-control check" }
report_drc -checks $checks -file "$output/bram_control.rpt"
# This report ran only REQP-1839; inspect its complete current violation set.
set violations [get_drc_violations -quiet]
if {[llength $violations] != 0} { error "asynchronous BRAM-control violation remains" }
puts "M5_STARTUP_SYNTH_BRAM_CONTROL_PASS violations=0 (not final qualification)"
close_design
