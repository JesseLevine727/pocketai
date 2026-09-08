# One final post-route optimization of the corrected mirror implementation.
# Accept only through the unchanged full 91-MHz guard tail; no seed sweep.
if {$argc < 4 || $argc > 5} { error "expected source build, checkpoint, fresh output, guard tail, optional optimization margin" }
set source_build [file normalize [lindex $argv 0]]
set checkpoint [file normalize [lindex $argv 1]]
set build_dir [file normalize [lindex $argv 2]]
set guard_tail [file normalize [lindex $argv 3]]
if {![string match m5_startup_* [file tail $source_build]] ||
    ![string match m5_startup_* [file tail [file dirname $checkpoint]]] ||
    ![string match m5_startup_* [file tail $build_dir]] ||
    [file exists $build_dir]} { error "fresh startup output required" }
file mkdir $build_dir
set reports_dir "$build_dir/reports"
file mkdir $reports_dir
set target_clock_mhz 91.0
set target_period_ns [expr {1000.0 / $target_clock_mhz}]
open_project "$source_build/m5_pynq.xpr"
open_checkpoint $checkpoint
set fabric_clocks [get_clocks -quiet -filter "PERIOD > [expr {$target_period_ns - 0.01}] && PERIOD < [expr {$target_period_ns + 0.01}]" ]
if {[llength $fabric_clocks] != 1} { error "wrong fabric clock" }
set optimization_margin_ns [expr {$target_period_ns - 10.0}]
if {$argc == 5} {
  set optimization_margin_ns [lindex $argv 4]
  if {![string is double -strict $optimization_margin_ns] ||
      $optimization_margin_ns < 0.250 || $optimization_margin_ns > 0.9891} {
    error "invalid implementation-only optimization margin"
  }
}
# This is only the optimizer's target. The unchanged guard tail restores the
# qualified zero additional user uncertainty and still requires WNS >= +.250.
set_clock_uncertainty -setup $optimization_margin_ns $fabric_clocks
phys_opt_design -directive AggressiveExplore
write_checkpoint "$build_dir/after_polish.dcp"
file copy "$source_build/reports/m5_fast_synth_configuration.rpt" "$reports_dir/"
source $guard_tail
