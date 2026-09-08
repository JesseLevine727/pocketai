# Local, non-inverting command drivers for the retained eight-macro probe.
# This is a physical-only candidate; no pipeline or memory semantics change.
proc pa_m6_local95_inputs {} {
    set block [ord::get_db_block]
    set index 0
    foreach macro [$block getInsts] {
        if {[[$macro getMaster] getName] ne "sram22_512x32m4w8"} { continue }
        if {[$macro getOrient] ne "R0"} { error "N macros required" }
        lassign [$macro getOrigin] dbx dby
        set units [$block getDbUnitsPerMicron]
        set x [expr {double($dbx)/$units}]
        set y [expr {double($dby)/$units}]
        set ports {}
        # Positions from the pinned LEF. Leave rstb's already-qualified tie
        # network alone. Output buffers occupy the first two bottom rows.
        for {set bit 0} {$bit < 32} {incr bit} {
            lappend ports [list "din\[$bit\]" [expr {234.68+$bit*6.1}] [expr {10.88+($bit%2)*2.72}]]
        }
        for {set bit 0} {$bit < 9} {incr bit} {
            lappend ports [list "addr\[$bit\]" [expr {193.08-$bit*6.12}] 10.88]
        }
        for {set bit 0} {$bit < 4} {incr bit} {
            lappend ports [list "wmask\[$bit\]" [expr {234.33+$bit*48.8}] 16.32]
        }
        lappend ports [list we 205.32 16.32] [list ce 199.20 16.32]
        set count 0
        foreach row $ports {
            lassign $row port offset depth
            set terminal [$macro findITerm $port]
            if {$terminal eq "NULL" || [$terminal getNet] eq "NULL"} { error "missing macro input" }
            set original [[$terminal getNet] getName]
            set pin "[$macro getName]/$port"
            set name "m6_in_${index}_$count"
            set local "${name}_local"
            make_instance $name sky130_fd_sc_hd__buf_4
            make_net $local
            disconnect_pin $original $pin
            connect_pin $original $name/A
            connect_pin $local $name/X
            connect_pin $local $pin
            set bx [expr {floor(($x+$offset-1.84)/0.46)*0.46}]
            set by [expr {floor(($y-$depth)/2.72)*2.72}]
            place_cell -inst_name $name -origin [list $bx $by] -orient R0 -status PLACED
            set instance [$block findInst $name]
            foreach {pg supply} {VPWR vdd VPB vdd VGND vss VNB vss} {
                [$instance findITerm $pg] connect [$block findNet $supply]
            }
            # Preserve the short downstream net, but allow timing repair to
            # reconnect/resize its buffer. Instance dont_touch prevents the
            # pinned resizer's upstream-net repair (retained failed v1).
            set_dont_touch $local
            incr count
        }
        if {$count != 47} { error "expected 47 command/data inputs per macro" }
        incr index
    }
    if {$index != 8} { error "eight-macro probe required" }
    puts "M6 LOCAL95 INPUT BUFFERS: 376 buf_4 cells; rstb ties unchanged"
}
set stream [open /m6_flow/contract_probe_cts.tcl r]
set original [read $stream]
close $stream
set needle "    pa_m6_contract_output_buffers\n"
if {[string first $needle $original] < 0 || [string first $needle $original] != [string last $needle $original]} {
    error "unexpected output-contract CTS helper"
}
eval [string map [list $needle "${needle}    pa_m6_local95_inputs\n"] $original]
