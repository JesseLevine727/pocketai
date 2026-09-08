define_corners min_ff_n40C_1v95 nom_tt_025C_1v80 max_ss_100C_1v60
read_liberty -corner min_ff_n40C_1v95 /pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__ff_n40C_1v95.lib
read_liberty -corner min_ff_n40C_1v95 /candidate/sram22_512x32m4w8_ff_n40C_1v95.lib
read_liberty -corner nom_tt_025C_1v80 /pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
read_liberty -corner nom_tt_025C_1v80 /candidate/sram22_512x32m4w8_tt_025C_1v80.lib
read_liberty -corner max_ss_100C_1v60 /pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__ss_100C_1v60.lib
read_liberty -corner max_ss_100C_1v60 /candidate/sram22_512x32m4w8_ss_100C_1v60.lib
read_db /candidate/runs/ss_repair_route_v1/12-odb-cellfrequencytables/pa_m6_bank_probe.odb
read_sdc /work/bank_probe.sdc
read_spef -corner min_ff_n40C_1v95 /candidate/runs/ss_repair_route_v1/13-openroad-rcx/min/pa_m6_bank_probe.min.spef
read_spef -corner nom_tt_025C_1v80 /candidate/runs/ss_repair_route_v1/13-openroad-rcx/nom/pa_m6_bank_probe.nom.spef
read_spef -corner max_ss_100C_1v60 /candidate/runs/ss_repair_route_v1/13-openroad-rcx/max/pa_m6_bank_probe.max.spef
set_propagated_clock [all_clocks]
report_checks -path_delay max
set macros [get_cells -hierarchical -filter {ref_name == sram22_512x32m4w8}]
if {[llength $macros] != 8} { error "expected 8 SRAMs" }
set stream [open /diagnostic/pins.tsv w]
puts $stream "corner\tpin\tdirection\trise_min_ns\trise_max_ns\tfall_min_ns\tfall_max_ns\tload_min_pf\tload_max_pf"
foreach corner_name {min_ff_n40C_1v95 nom_tt_025C_1v80 max_ss_100C_1v60} {
    set corner [sta::find_corner $corner_name]
    foreach macro $macros {
        foreach pin [get_pins -of_objects $macro] {
            set direction [sta::pin_direction $pin]
            if {$direction ni {input output}} { continue }
            set vertices [$pin vertices]
            if {[llength $vertices] != 1} { error "unexpected SRAM pin vertices" }
            set vertex [lindex $vertices 0]
            set row [list $corner_name [get_full_name $pin] $direction]
            foreach edge {rise fall} {
                foreach check {min max} {
                    lappend row [expr {[$vertex slew_corner $edge $corner $check]*1e9}]
                }
            }
            set net [$pin net]
            foreach check {min max} { lappend row [expr {[$net capacitance $corner $check]*1e12}] }
            puts $stream [join $row "\t"]
        }
    }
}
close $stream
puts "M6 SRAM PIN REPORT COMPLETE; envelope acceptance is checked separately"

