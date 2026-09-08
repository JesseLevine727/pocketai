# Read-only, all-corner placed timing diagnostic; no view is overwritten.
set ::env(_TCL_ENV_IN) $::env(M6_DIAG_ENV)
source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
set ::env(CURRENT_ODB) $::env(M6_DIAG_ODB)
set ::env(PNR_SDC_FILE) $::env(M6_DIAG_SDC)
source $::env(SCRIPTS_DIR)/openroad/common/resizer.tcl
load_rsz_corners
read_db $::env(CURRENT_ODB)
set_global_vars
read_sdc $::env(PNR_SDC_FILE)
source $::env(SCRIPTS_DIR)/openroad/common/set_rc.tcl
estimate_parasitics -placement
report_clock_properties [all_clocks]
check_setup -verbose -unconstrained_endpoints -multiple_clock -no_clock -no_input_delay -loops -generated_clocks
foreach name $::env(STA_CORNERS) {
    puts "M6 DIAGNOSTIC CORNER: $name PLACEMENT_ESTIMATE_NOT_ROUTE_SIGNOFF"
    report_checks -corner $name -path_delay max -group_count 3 -format full_clock_expanded
    report_checks -corner $name -path_delay min -group_count 3 -format full_clock_expanded
}
puts "M6 TIMING DIAGNOSTIC COMPLETE; NO QUALIFICATION IMPLIED"
