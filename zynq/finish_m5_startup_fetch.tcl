# One bounded physical correction of the measured high-fanout paths. No RTL,
# frequency, timing exceptions or acceptance thresholds are changed.
if {$argc < 3 || $argc > 4} { error "expected source build, fresh output, guard tail, optional startup checkpoint" }
set source_build [file normalize [lindex $argv 0]]
set build_dir [file normalize [lindex $argv 1]]
set guard_tail [file normalize [lindex $argv 2]]
set source_checkpoint "$source_build/m5_candidate.dcp"
if {$argc == 4} {
  set source_checkpoint [file normalize [lindex $argv 3]]
  if {![string match m5_startup_* [file tail [file dirname $source_checkpoint]]]} {
    error "checkpoint must be an isolated startup result"
  }
}
if {![string match m5_startup_* [file tail $source_build]] ||
    ![string match m5_startup_* [file tail $build_dir]] ||
    [file exists $build_dir]} { error "fresh startup output required" }
if {![file exists "$source_build/resolved_sources/M5_STARTUP_DIRECT_RETURN"]} {
  error "expected the verified direct-return mirror candidate"
}
file mkdir $build_dir
set reports_dir "$build_dir/reports"
file mkdir $reports_dir
set target_clock_mhz 91.0
set target_period_ns [expr {1000.0 / $target_clock_mhz}]
open_project "$source_build/m5_pynq.xpr"
open_checkpoint $source_checkpoint
set fabric_clocks [get_clocks -quiet -filter "PERIOD > [expr {$target_period_ns - 0.01}] && PERIOD < [expr {$target_period_ns + 0.01}]" ]
if {[llength $fabric_clocks] != 1} { error "wrong fabric clock" }
set_clock_uncertainty -setup 0.0 $fabric_clocks
set paths [get_timing_paths -delay_type max -max_paths 100 -nworst 1 -slack_lesser_than 0.350]
set nets {}
set record [open "$reports_dir/targeted_replication.rpt" w]
puts $record "source_checkpoint=$source_checkpoint"
foreach path $paths {
  set cell [get_cells -quiet -of_objects [get_pins -quiet [get_property STARTPOINT_PIN $path]]]
  set pin [get_pins -quiet -of_objects $cell -filter {DIRECTION == OUT && REF_PIN_NAME == Q}]
  set net [get_nets -quiet -of_objects $pin]
  if {[llength $net] != 1} { continue }
  if {[llength [get_clocks -quiet -of_objects $net]] != 0} { error "refusing clock replication" }
  set sinks [get_pins -quiet -leaf -of_objects $net -filter {DIRECTION == IN}]
  if {[llength $sinks] > 16 && [lsearch -exact $nets $net] == -1} {
    lappend nets $net
    puts $record "net=$net sinks=[llength $sinks] path_slack=[get_property SLACK $path]"
  }
}
close $record
if {[llength $nets] == 0} { error "no measured high-fanout correction target" }
set_clock_uncertainty -setup [expr {$target_period_ns - 10.0}] $fabric_clocks
# Forced replication requires unrouted mode in this Vivado version. Only this
# in-memory copy is unrouted. The source checkpoint remains immutable.
route_design -unroute
phys_opt_design -force_replication_on_nets $nets
route_design -directive Explore
phys_opt_design -directive Explore
write_checkpoint -force "$build_dir/after_replication.dcp"
file copy "$source_build/reports/m5_fast_synth_configuration.rpt" "$reports_dir/"
source $guard_tail
