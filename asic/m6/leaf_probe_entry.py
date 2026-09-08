"""Isolated eight-macro experiment. Never used by the historical full-core flow."""
import hashlib
from pathlib import Path

from openlane.flows import Flow
from openlane.flows.classic import Classic
from openlane.steps import OpenROAD, Step


@Step.factory.register()
class M6LeafCTS(OpenROAD.CTS):
    id = "M6Leaf.CTS"
    name = "M6 experimental local SRAM clock leaves"

    def get_script_path(self):
        original = Path(super().get_script_path())
        if hashlib.sha256(original.read_bytes()).hexdigest() != \
                "8fe238688009ffddcacd59fd6de2a61c5fd65b2c4b7acd8d849fe5a5002c3314":
            raise ValueError("Pinned CTS changed: review before using this experiment")
        return str(Path(__file__).with_name("leaf_probe_cts.tcl"))


@Flow.factory.register()
class M6LeafProbe(Classic):
    Steps = [M6LeafCTS if step is OpenROAD.CTS else step for step in Classic.Steps]


if __name__ == "__main__":
    from openlane.__main__ import cli
    cli()
