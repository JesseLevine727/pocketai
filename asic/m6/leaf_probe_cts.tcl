# Bounded experiment: two inversions retain the macro's rising-edge clock.
# No library, clock constraint, timing arc or electrical check is changed.
# This is not a general macro placement algorithm or a qualified CTS solution.
proc pa_m6_local_clock_leaves {} {
    set block [ord::get_db_block]
    if {[$block getName] ne "pa_m6_bank_probe"} { error "eight-macro probe only" }
    set macros {}
    foreach inst [$block getInsts] {
        if {[[$inst getMaster] getName] eq "sram22_512x32m4w8"} { lappend macros $inst }
    }
    if {[llength $macros] != 8} { error "expected exactly eight SRAM instances" }
    set index 0
    foreach macro $macros {
        if {[$macro getOrient] ne "R0"} { error "local leaf experiment requires N macros" }
        set clock_pin [$macro findITerm clk]
        set old_net [[$clock_pin getNet] getName]
        set pin_name "[$macro getName]/clk"
        set pre "m6_leaf_${index}_pre"
        set leaf "m6_leaf_${index}_drive"
        set inverted "m6_leaf_${index}_inverted"
        set local "m6_leaf_${index}_local"
        make_instance $pre sky130_fd_sc_hd__clkinv_2
        make_instance $leaf sky130_fd_sc_hd__clkinv_16
        make_net $inverted
        make_net $local
        disconnect_pin $old_net $pin_name
        connect_pin $old_net $pre/A
        connect_pin $inverted $pre/Y
        connect_pin $inverted $leaf/A
        connect_pin $local $leaf/Y
        connect_pin $local $pin_name
        lassign [$macro getOrigin] dbx dby
        set units [$block getDbUnitsPerMicron]
        set x [expr {double($dbx)/$units}]
        set y [expr {double($dby)/$units}]
        # The pinned N-oriented macro clk pin is at x=208.04, y=0.16 um.
        # Initial sites are outside its bottom edge; normal DPL legalizes them.
        place_cell -inst_name $pre -origin [list [expr {$x+192}] [expr {$y-5.44}]] -orient R0 -status PLACED
        place_cell -inst_name $leaf -origin [list [expr {$x+202}] [expr {$y-5.44}]] -orient R0 -status PLACED
        # make_instance does not populate PG terminals. Connect before applying
        # dont_touch (which prevents later automatic global-connection repair).
        foreach name [list $pre $leaf] {
            set instance [$block findInst $name]
            foreach {pin supply} {VPWR vdd VPB vdd VGND vss VNB vss} {
                set terminal [$instance findITerm $pin]
                set net [$block findNet $supply]
                if {$terminal eq "NULL" || $net eq "NULL"} { error "missing clock-leaf PG terminal/net" }
                $terminal connect $net
                if {[$terminal getNet] ne $net} { error "clock-leaf PG connection failed" }
            }
        }
        set_dont_touch [list $pre $leaf $inverted $local]
        puts "M6 LOCAL CLOCK LEAF: $pin_name via $pre and $leaf from $old_net"
        incr index
    }
}
set original_path $::env(SCRIPTS_DIR)/openroad/cts.tcl
set stream [open $original_path r]
set original [read $stream]
close $stream
set needle {clock_tree_synthesis {*}$arg_list}
if {[string first $needle $original] < 0 || [string first $needle $original] != [string last $needle $original]} {
    error "Unexpected pinned CTS script"
}
set replacement "${needle}\npa_m6_local_clock_leaves"
eval [string map [list $needle $replacement] $original]
