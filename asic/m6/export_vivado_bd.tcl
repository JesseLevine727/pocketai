# Actual qualified-release block design, opened read-only. No source/BD saves.
if {$argc != 3} { error "usage: project.xpr system.bd new_build_m6_output" }
set project [file normalize [lindex $argv 0]]
set bd [file normalize [lindex $argv 1]]
set output [file normalize [lindex $argv 2]]
if {![string match m6_* [file tail $output]] || [file exists $output]} {
  error "expected a fresh M6 output directory"
}
file mkdir $output
start_gui
open_project -read_only $project
open_bd_design $bd
# Preserve the stored layout: regenerating it is a design modification and is
# correctly rejected for a read-only project.
write_bd_layout -format svg -orientation portrait "$output/vivado_system.svg"
write_bd_layout -format pdf -orientation portrait "$output/vivado_system.pdf"
foreach name {vivado_system.svg vivado_system.pdf} {
  if {![file exists "$output/$name"] || [file size "$output/$name"] < 1000} {
    error "Vivado did not produce a usable $name; no figure pass"
  }
}
set fp [open "$output/cells.tsv" w]
puts $fp "cell\tvlnv\treference"
foreach cell [lsort [get_bd_cells -hierarchical]] {
  puts $fp "$cell\t[get_property VLNV $cell]\t[get_property REF_NAME $cell]"
}
close $fp
set fp [open "$output/export.txt" w]
puts $fp "Actual Vivado block-design export; not an ASIC implementation."
puts $fp "Vivado: [version -short]"
puts $fp "Read-only project: $project"
puts $fp "Block design: $bd"
puts $fp "Logical BD view of qualified FPGA release; final timing is established separately by its routed DCP."
close $fp
close_project
stop_gui
puts "M6 VIVADO BD FIGURE EXPORTED"
