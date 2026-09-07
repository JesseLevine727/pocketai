# Read-only review of the exact accepted checkpoint's remaining methodology warnings.
if {$argc != 1} { error "expected qualified build directory" }
set build_dir [file normalize [lindex $argv 0]]
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
if {$count != 6} { error "unexpected reset warning count $count" }
puts "M5_FAST_RESET_REVIEW_COMPLETE cells=$count"
close_design
