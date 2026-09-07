# Bounded correction of measured high-fanout paths, not a timing seed sweep.
# Continue the one source-pinned implementation without resynthesizing it.
if {$argc != 3} { error "expected source build, fresh output, qualified guard tail" }
set source_build [file normalize [lindex $argv 0]]
set build_dir [file normalize [lindex $argv 1]]
set guard_tail [file normalize [lindex $argv 2]]
if {[file exists $build_dir]} { error "use a fresh correction directory" }
file mkdir $build_dir
set reports_dir "$build_dir/reports"
file mkdir $reports_dir
set target_clock_mhz 91.0
set target_period_ns [expr {1000.0 / $target_clock_mhz}]
open_project "$source_build/m5_pynq.xpr"
open_checkpoint "$source_build/m5_candidate.dcp"
set fabric_clocks [get_clocks -quiet -filter "PERIOD > [expr {$target_period_ns - 0.01}] && PERIOD < [expr {$target_period_ns + 0.01}]" ]
if {[llength $fabric_clocks] != 1} { error "wrong fabric clock" }
set_clock_uncertainty -setup 0.0 $fabric_clocks
set paths [get_timing_paths -delay_type max -max_paths 100 -nworst 1 -slack_lesser_than 0.350]
set nets {}
set record [open "$reports_dir/targeted_replication.rpt" w]
puts $record "source_checkpoint=$source_build/m5_candidate.dcp"
foreach path $paths {
  set start [get_property STARTPOINT_PIN $path]
  # STARTPOINT_PIN is a sequential cell's clock pin, not its data output.
  # Resolve that cell's Q explicitly and reject clocks before any mutation.
  set cell [get_cells -quiet -of_objects [get_pins -quiet $start]]
  set pin [get_pins -quiet -of_objects $cell -filter {DIRECTION == OUT && REF_PIN_NAME == Q}]
  set net [get_nets -quiet -of_objects $pin]
  if {[llength $net] != 1} { continue }
  if {[llength [get_clocks -quiet -of_objects $net]] != 0} { error "refusing to replicate a clock" }
  set sinks [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]
  if {[llength $sinks] > 16 && [lsearch -exact $nets $net] == -1} {
    lappend nets $net
    puts $record "net=$net sinks=[llength $sinks] path_slack=[get_property SLACK $path]"
  }
}
close $record
if {[llength $nets] == 0} { error "no measured high-fanout correction target" }
# Preserve the original implementation-only extra margin while optimizing.
set_clock_uncertainty -setup [expr {$target_period_ns - 10.0}] $fabric_clocks
# This Vivado version disallows forced replication in post-route mode.
# Unroute this in-memory copy only; preserve placement, original checkpoint,
# source identities and the original route directive. Then repair routing.
route_design -unroute
phys_opt_design -force_replication_on_nets $nets
route_design -directive Explore
phys_opt_design -directive Explore
write_checkpoint -force "$build_dir/after_replication.dcp"
# Reuse every original timing/route/DRC/resource acceptance check unchanged.
source $guard_tail
