"""Pinned Classic flow with an explicit, auditable CTS root selection.

No installed tool files are modified. All non-CTS steps remain unchanged.
"""
from pathlib import Path
import hashlib

from openlane.flows import Flow
from openlane.flows.classic import Classic
from openlane.steps import Step, OpenROAD


@Step.factory.register()
class M6CTS(OpenROAD.CTS):
    id = "M6.CTS"
    name = "M6 Clock Tree Synthesis (explicit real clock nets)"

    def get_script_path(self):
        original = Path(super().get_script_path())
        assert hashlib.sha256(original.read_bytes()).hexdigest() == \
            "8fe238688009ffddcacd59fd6de2a61c5fd65b2c4b7acd8d849fe5a5002c3314", \
            "Pinned CTS script changed; review the M6 adaptation"
        return str(Path(__file__).with_name("cts.tcl"))


@Flow.factory.register()
class M6Classic(Classic):
    Steps = [M6CTS if step is OpenROAD.CTS else step for step in Classic.Steps]


if __name__ == "__main__":
    # The CLI constructs its flow-name choices at import time.
    from openlane.__main__ import cli
    cli()
