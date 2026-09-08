# Read-only extraction from the qualified routed FPGA design. Never write back
# to its frozen directory. The output directory must be new and M6-specific.
if {$argc != 2} { error "usage: checkpoint new_build_m6_directory" }
set checkpoint [file normalize [lindex $argv 0]]
set output [file normalize [lindex $argv 1]]
if {![string match m6_* [file tail $output]] || [file exists $output]} {
  error "expected a new M6 output directory"
}
file mkdir $output
open_checkpoint $checkpoint
report_utilization -hierarchical -hierarchical_depth 8 -file "$output/hierarchy.rpt"
report_clocks -file "$output/clocks.rpt"
set fp [open "$output/primitives.tsv" w]
puts $fp "instance\tprimitive\tparent"
foreach cell [lsort [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}]] {
  puts $fp "$cell\t[get_property REF_NAME $cell]\t[get_property PARENT $cell]"
}
close $fp
array set blocks {}
foreach cell [get_cells -hierarchical -filter {IS_PRIMITIVE == 1}] {
  if {![string match "system_i/pa_cluster_m5_0/*" $cell]} {
    set group platform_shell
  } elseif {[string match "*/u_core0/*" $cell]} {
    set group hart0
  } elseif {[string match "*/u_core1/*" $cell]} {
    set group hart1
  } elseif {[string match "*/u_gemm/*" $cell]} {
    set group gemm
  } elseif {[string match "*/u_sfpu/*" $cell]} {
    set group sfpu
  } elseif {[string match "*/u_ram/*" $cell]} {
    set group scratchpad
  } elseif {[string match "*startup_instruction_mem*" $cell]} {
    set group instruction_mirror_storage
  } elseif {[string match "*startup_data_read_mem*" $cell]} {
    set group data_mirror_storage
  } else {
    set group other_portable_control
  }
  lappend blocks($group) $cell
}
foreach group [lsort [array names blocks]] {
  report_utilization -cells $blocks($group) -file "$output/$group.rpt"
}
puts "M6 FPGA INVENTORY PASS: read-only qualified checkpoint extraction"
close_design
