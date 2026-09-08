# Run the pinned OpenLane CTS script with one explicit argument addition.
# OpenROAD's automatic net discovery traverses the system clock's second
# role as SRAM phase DATA, despite STA stop-propagation constraints. Its
# macro sink test treats every block input as a possible clock sink.
# Select the four real trees: memory, divider Q, and two Ibex gated outputs.
# This changes tree construction only; it does not disable any timing arcs.
proc pa_m6_cts_clock_nets {} {
    set roots [get_pins -hierarchical {u_clock.*/Q}]
    set gates [get_cells -hierarchical {*core_clock_gate_i.*}]
    foreach gate $gates {
        if {[string match sky130_fd_sc_hd__and2_* [get_property $gate ref_name]]} {
            lappend roots {*}[get_pins -of_objects $gate -filter {direction == output}]
        }
    }
    if {[llength $roots] != 3} { error "M6 expected system and two gated clock output pins" }
    set memory_net [get_nets clk_mem_i]
    if {[llength $memory_net] != 1} { error "M6 expected one input memory clock net" }
    set names [list [get_full_name [lindex $memory_net 0]]]
    foreach pin $roots {
        lappend names [get_full_name [sta::Pin_net $pin]]
    }
    puts "M6 EXPLICIT CTS ROOTS: $names"
    return $names
}
set original_path $::env(SCRIPTS_DIR)/openroad/cts.tcl
set stream [open $original_path r]
set original [read $stream]
close $stream
set needle {clock_tree_synthesis {*}$arg_list}
if {[string first $needle $original] < 0 || [string first $needle $original] != [string last $needle $original]} {
    error "Unexpected pinned CTS script; review the adaptation before use"
}
set replacement {clock_tree_synthesis -clk_nets [pa_m6_cts_clock_nets] {*}$arg_list}
eval [string map [list $needle $replacement] $original]
