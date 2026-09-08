"""One bounded 95-MHz input-locality trial; not full-system closure."""
from pathlib import Path

from contract_probe_entry import M6ContractCTS
from openlane.flows import Flow
from openlane.flows.classic import Classic
from openlane.steps import OpenROAD, Step


@Step.factory.register()
class M6Local95CTS(M6ContractCTS):
    id = "M6Local95.CTS"
    name = "M6 local command and output buffers"

    def get_script_path(self):
        super().get_script_path()  # Preserve the pinned upstream CTS check.
        return str(Path(__file__).with_name("local95_probe_cts.tcl"))


@Flow.factory.register()
class M6Local95Probe(Classic):
    Steps = [M6Local95CTS if step is OpenROAD.CTS else step for step in Classic.Steps]


if __name__ == "__main__":
    from openlane.__main__ import cli
    cli()
