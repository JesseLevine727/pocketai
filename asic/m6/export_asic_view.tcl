# Render the actual retained OpenDB checkpoint without saving design changes.
read_db $::env(M6_FIGURE_ODB)
if {![gui::enabled]} { error "Use OpenROAD -gui so display controls take effect" }
gui::set_display_controls "Layers/*" visible false
gui::set_display_controls "Instances/Macro" visible true
gui::set_display_controls "Instances/StdCells/*" visible false
gui::set_display_controls "Misc/Instances/*" visible false
set macro_count 0
set macro_file [open [file join [file dirname $::env(M6_FIGURE_IMAGE)] macros.tsv] w]
puts $macro_file "instance\towner\thighlight_group\tx_min_dbu\ty_min_dbu\tx_max_dbu\ty_max_dbu"
foreach inst [[ord::get_db_block] getInsts] {
    if {[[$inst getMaster] getName] ne "sram22_512x32m4w8"} { continue }
    set name [$inst getName]
    set owner other
    set group 5
    foreach {needle label number} {
        u_gemm gemm 0 u_sfpu sfpu 1 startup_instruction_mem instruction_mirror 2
        startup_data_read_mem data_mirror 3 u_ram scratchpad 4
    } {
        if {[string first $needle $name] >= 0} { set owner $label; set group $number; break }
    }
    gui::highlight_inst $name $group
    set box [$inst getBBox]
    puts $macro_file "$name\t$owner\t$group\t[$box xMin]\t[$box yMin]\t[$box xMax]\t[$box yMax]"
    incr macro_count
}
close $macro_file
if {$macro_count != 292} { error "Expected the retained complete 292-macro floorplan" }
gui::fit
save_image $::env(M6_FIGURE_IMAGE) -width 2400 -area {0 0 9100 9900}
if {![file exists $::env(M6_FIGURE_IMAGE)] || [file size $::env(M6_FIGURE_IMAGE)] < 1000} {
    error "OpenROAD did not create the requested implementation view"
}
puts "M6 ASIC ACTUAL DATABASE VIEW EXPORTED"
exit
