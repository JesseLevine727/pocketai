# The divider Q is both a generated clock and the SRAM read/write phase data.
# Stop only CLOCK propagation at data-only branches. Do not disable timing
# arcs, false-path endpoints, or suppress setup/hold checks on that data.
# This classifier is specific to the pinned HD cells and two qualified Ibex
# clock gates. Its sink counts are checked against the complete design.
proc pa_m6_stop_clock_data {root_pin} {
    set queue [list [sta::Pin_net $root_pin]]
    set visited [dict create]
    set stopped [list]
    set clock_sinks 0
    while {[llength $queue]} {
        set net [lindex $queue end]
        set queue [lreplace $queue end end]
        if {[dict exists $visited $net]} { continue }
        dict set visited $net 1
        foreach pin [sta::net_load_pins $net] {
            if {[sta::Pin_is_top_level_port $pin]} { continue }
            set port [sta::Pin_port_name $pin]
            set inst [sta::Pin_instance $pin]
            set libcell [sta::Instance_liberty_cell $inst]
            set name [get_full_name $inst]
            if {$port in {CLK GATE GATE_N clk}} {
                incr clock_sinks
            } elseif {[sta::LibertyCell_is_buffer $libcell] ||
                      [sta::LibertyCell_is_inverter $libcell] ||
                      [string match *core_clock_gate_i* $name]} {
                foreach output [get_pins -of_objects $inst -filter {direction == output}] {
                    lappend queue [sta::Pin_net $output]
                }
            } else {
                lappend stopped $pin
            }
        }
    }
    # With the separate set-high phase-data register, only the divider's
    # feedback D branch remains. The older direct-clock-as-phase trial has
    # many data branches. Both require complete sequential clock coverage.
    if {$clock_sinks < 30000 || [llength $stopped] < 1} {
        error "M6 clock/data classification incomplete: $clock_sinks clock sinks, [llength $stopped] data branches"
    }
    set_sense -type clock -stop_propagation $stopped
    puts "M6 CLOCK DATA BOUNDARY: clock_sinks=$clock_sinks stopped_data_branches=[llength $stopped] no_data_arcs_disabled=1"
}
