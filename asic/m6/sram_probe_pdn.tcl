# SRAM22 exposes its existing supply network on met2, not met4. Connect its
# actual LEF supply pins to the default met4/met5 grid; do not waive PSM errors.
source $::env(SCRIPTS_DIR)/openroad/common/pdn_cfg.tcl
add_pdn_connect -grid macro -layers {met2 met4}
