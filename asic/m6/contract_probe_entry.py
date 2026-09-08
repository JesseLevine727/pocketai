"""Isolated output-contract/buffer probe with optional pre-CTS local clock pairs."""
import hashlib
from pathlib import Path

from openlane.config import Variable
from openlane.flows import Flow
from openlane.flows.classic import Classic
from openlane.steps import OpenROAD, Step


@Step.factory.register()
class M6ContractCTS(OpenROAD.CTS):
    id = "M6Contract.CTS"
    name = "M6 local output buffers and characterized contract"
    config_vars = OpenROAD.CTS.config_vars + [Variable(
        "M6_CONTRACT_CLOCK_LEAVES", bool, "Include paired local SRAM clock inverters before CTS", default=False)]

    def get_script_path(self):
        original = Path(super().get_script_path())
        if hashlib.sha256(original.read_bytes()).hexdigest() != \
                "8fe238688009ffddcacd59fd6de2a61c5fd65b2c4b7acd8d849fe5a5002c3314":
            raise ValueError("Pinned CTS changed")
        return str(Path(__file__).with_name("contract_probe_cts.tcl"))


@Flow.factory.register()
class M6ContractProbe(Classic):
    Steps = [M6ContractCTS if step is OpenROAD.CTS else step for step in Classic.Steps]


if __name__ == "__main__":
    from openlane.__main__ import cli
    cli()
