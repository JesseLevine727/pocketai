"""Bounded post-extraction electrical repair using the actual retained SPEFs."""
import hashlib
from pathlib import Path

from openlane.config import Variable
from openlane.flows import Flow
from openlane.flows.classic import Classic
from openlane.state import DesignFormat
from openlane.steps import OpenROAD, Step


@Step.factory.register()
class M6ExtractedRepair(OpenROAD.RepairDesignPostGRT):
    id = "M6Repair.Extracted"
    name = "M6 extracted-vs-estimated electrical repair"
    inputs = [*OpenROAD.RepairDesignPostGRT.inputs, DesignFormat.SPEF]
    config_vars = OpenROAD.RepairDesignPostGRT.config_vars + [Variable(
        "M6_REPAIR_USE_SPEF", bool, "Repair against retained extracted parasitics", default=True),
        Variable("M6_REPAIR_PRIME_ESTIMATE", bool,
                 "Enable incremental placement RC updates before reading SPEF", default=False),
        Variable("M6_REPAIR_CLOCK_PREDRIVER", str,
                 "Explicit paired-clock predriver replacement, or empty", default=""),
        Variable("M6_REPAIR_NEW_BUFFER_MIN8", bool,
                 "Use at least drive-8 for newly inserted long-wire buffers", default=False),
        Variable("M6_REPAIR_TIMING", bool,
                 "Bounded setup and hold repair after electrical repair", default=False),
        Variable("M6_REPAIR_ELECTRICAL", bool,
                 "Run electrical cell/buffer repair", default=True),
        Variable("M6_LOCAL_CLOCK_NDR", bool,
                 "Double local SRAM clock metal width to reduce extracted wire resistance", default=False),
        Variable("M6_REPAIR_SELECTIVE", bool,
                 "Repair measured data drivers without global timing downsizing", default=False),
        Variable("M6_REPAIR_PREFIX", str,
                 "Fresh prefix for each selective repair pass", default="m6_drv"),
        Variable("M6_REPAIR_MACRO_LOADS", bool,
                 "Reduce only overloaded local SRAM receiver input capacitance", default=False),
        Variable("M6_REPAIR_READ_CHAINS", bool,
                 "Compress redundant low-strength read-return buffers only", default=False),
        Variable("M6_REPAIR_RETURN_CHAINS", bool,
                 "Upsize read-return buffer chains to drive-16 only", default=False),
        Variable("M6_REPAIR_CLOCK_LEAF_CELL", str,
                 "Replace both local clock leaf cells with this reviewed cell, or empty",
                 default=""),
        Variable("M6_REPAIR_SPLIT_FANOUT", bool,
                 "Split single-driver nets whose fanout exceeds 16", default=False),
        Variable("M6_REPAIR_ANTENNA", bool,
                 "Insert antenna diodes after the rip-up and re-global-route", default=False)]

    def get_script_path(self):
        original = Path(super().get_script_path())
        if hashlib.sha256(original.read_bytes()).hexdigest() != \
                "fc42121182c245ca85630bb3432f9d8a4bde994abc71fdb5b0786a3739b6bd0b":
            raise ValueError("pinned repair script changed")
        return str(Path(__file__).with_name("extracted_repair.tcl"))

    def run(self, state_in, **kwargs):
        kwargs, env = self.extract_env(kwargs)
        for corner in self.config["RSZ_CORNERS"] or self.config["STA_CORNERS"]:
            key = corner.split("_", 1)[0]+"_*"
            env["M6_REPAIR_SPEF_"+corner] = str(state_in[DesignFormat.SPEF][key])
        return super().run(state_in, env=env, **kwargs)


@Flow.factory.register()
class M6ExtractedFlow(Classic):
    Steps = [M6ExtractedRepair if step is OpenROAD.RepairDesignPostGRT else step for step in Classic.Steps]


if __name__ == "__main__":
    from openlane.__main__ import cli
    cli()
