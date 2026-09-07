# Read-only timing diagnosis of an existing checkpoint; never reroute it.
if {$argc != 2} { error "expected checkpoint and fresh report directory" }
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {[file exists $output]} { error "use a fresh report directory" }
file mkdir $output
open_checkpoint $checkpoint
report_timing -delay_type max -max_paths 20 -nworst 1 -file "$output/worst.rpt"
report_timing_summary -file "$output/summary.rpt"
close_design
