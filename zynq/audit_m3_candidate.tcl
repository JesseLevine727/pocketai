# Read-only reset/clock provenance for a final timing-qualified checkpoint.
# Output is an audit log, never an accepted bitstream.
open_checkpoint $::env(M3_DIAGNOSTIC_DCP)
foreach name {
    system_i/pa_cluster_m3_0/rvalid_o_i_2
    {system_i/pa_cluster_m3_0/valid_q[2]_i_5__0}
} {
    set cell [get_cells -hierarchical -filter [list NAME == $name]]
    if {[llength $cell] != 1} {
        error "Expected one reviewed reset LUT: $name"
    }
    puts "M3 RESET LUT name=$name ref=[get_property REF_NAME $cell] init=[get_property INIT $cell]"
    foreach pin [get_pins -of_objects $cell -filter {DIRECTION == IN}] {
        set net [get_nets -of_objects $pin]
        set drivers [get_pins -leaf -of_objects $net -filter {DIRECTION == OUT}]
        puts "M3 RESET INPUT pin=$pin net=$net drivers=$drivers"
        puts "M3 RESET ORIGINS [all_fanin -flat -startpoints_only -to $pin]"
    }
}
foreach clock [get_clocks] {
    puts "M3 CLOCK name=$clock period=[get_property PERIOD $clock] source=[get_property SOURCE_PINS $clock]"
}
puts "M3 AUDIT PASS"
