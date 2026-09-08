# Read-only actual-netlist review, including the new fallback response flops.
if {$argc < 1 || $argc > 2} { error "expected qualified startup build directory and reviewed warning count" }
set build_dir [file normalize [lindex $argv 0]]
set expected_count 9
if {$argc == 2} { set expected_count [lindex $argv 1] }
if {![string is integer -strict $expected_count] || $expected_count < 2 || $expected_count > 64} {
  error "invalid explicit review count"
}
if {![string match m5_startup_* [file tail $build_dir]]} { error "startup scope required" }
open_checkpoint "$build_dir/m5_pynq_final.dcp"
set report_file [open "$build_dir/reports/m5_methodology.rpt" r]
set report_text [read $report_file]
close $report_file
set matches [regexp -all -inline {LUT cell ([^,]+),} $report_text]
set count 0
foreach {whole name} $matches {
  set cell [get_cells -quiet $name]
  if {[llength $cell] != 1} { error "missing warned cell $name" }
  puts "RESET_CELL $cell INIT=[get_property INIT $cell]"
  foreach pin [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
    puts "RESET_INPUT $pin NET=[get_nets -of_objects $pin] STARTS=[all_fanin -flat -startpoints_only -to $pin]"
  }
  incr count
}
if {$count != $expected_count} { error "unexpected reset warning count $count" }
puts "M5_STARTUP_RESET_REVIEW_COMPLETE cells=$count"
close_design
