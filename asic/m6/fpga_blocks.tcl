# Separate hierarchy-preserving OOC area experiment. This is NOT the qualified
# 91-MHz routed FPGA build, and none of its timing is a replacement measurement.
if {$argc != 2} { error "usage: staged_m6_source_directory new_m6_output" }
set staging [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
set root [file normalize [file dirname [file dirname [file dirname [info script]]]]]
if {![string match m6_* [file tail $staging]] ||
    ![string match m6_* [file tail $output]] || [file exists $output]} {
  error "M6 source stage and a fresh M6 output required"
}
source "$staging/pocketai_sources.tcl"
# Stage was hash-checked by m6_stage_rtl; the only area-experiment binding
# permitted is an explicit no-DSP attribute on the unchanged fast multiplier.
# Use its local files, never the old absolute paths in the frozen Tcl manifest.
set original_dir [file dirname [lindex $pocketai_memory_files 0]]
foreach variable {pocketai_rtl_files pocketai_verilog_files pocketai_include_files
                  pocketai_include_dirs pocketai_memory_files} {
  set rewritten {}
  foreach path [set $variable] {
    if {![string match "$original_dir/*" $path] && $path != $original_dir} {
      error "unexpected source outside original staged root: $path"
    }
    lappend rewritten [string map [list $original_dir $staging] $path]
  }
  set $variable $rewritten
}
file mkdir $output
cd $output
set_param general.maxThreads 8
create_project -in_memory -part xc7z020clg400-1
add_files -norecurse $pocketai_rtl_files
set_property file_type SystemVerilog [get_files $pocketai_rtl_files]
if {[llength $pocketai_verilog_files]} {
  add_files -norecurse $pocketai_verilog_files
}
add_files -norecurse $pocketai_include_files
set_property file_type {SystemVerilog Header} [get_files $pocketai_include_files]
set_property include_dirs $pocketai_include_dirs [current_fileset]
foreach memory $pocketai_memory_files { file copy $memory [file tail $memory] }
add_files -norecurse $pocketai_memory_files
set_property file_type {Memory Initialization Files} [get_files $pocketai_memory_files]
read_xdc "$root/asic/m6/fpga_blocks.xdc"
set_property top pa_cluster_m5_board [current_fileset]
update_compile_order -fileset sources_1
synth_design -mode out_of_context -top pa_cluster_m5_board -part xc7z020clg400-1 \
  -flatten_hierarchy none -max_dsp 0 -fanout_limit 16
if {[llength [get_cells -quiet -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}]]} {
  error "FPGA area experiment violated the no-DSP contract"
}
report_utilization -file "$output/full.rpt"
report_utilization -hierarchical -hierarchical_depth 12 -file "$output/hierarchy.rpt"
set fp [open "$output/primitives.tsv" w]
puts $fp "instance\tprimitive\tparent"
foreach cell [lsort [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]] {
  puts $fp "$cell\t[get_property REF_NAME $cell]\t[get_property PARENT $cell]"
}
close $fp
write_checkpoint "$output/synthesis.dcp"
puts "M6 FPGA BLOCK AREA EXPERIMENT PASS: hierarchy-preserving synthesis only"
close_design
