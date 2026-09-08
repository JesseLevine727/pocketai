"""Fast preflight checks; these do not qualify the ASIC or SRAM timing."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.m6_memory_inventory import inventory, number
from scripts import m6_stage_rtl
from scripts.m6_preflight_evidence import drc_result


def memory():
    return {"type": "$mem_v2", "parameters": {
        "WIDTH": "00001000", "SIZE": "00000010", "RD_PORTS": "10",
        "WR_PORTS": "1", "RD_CLK_ENABLE": "10", "INIT": "xxxxxxxx00000000"}}


class MemoryInventoryTests(unittest.TestCase):
    def test_repeated_instances_and_port_masks(self):
        netlist = {"modules": {
            "top": {"cells": {"a": {"type": "bank"}, "b": {"type": "bank"}}},
            "bank": {"cells": {"ram": memory(), "logic": {"type": "$and"}}}}}
        rows = inventory(netlist, "top")
        self.assertEqual({r["instance"] for r in rows}, {"top/a/ram", "top/b/ram"})
        self.assertEqual(sum(r["bits"] for r in rows), 32)
        self.assertEqual(rows[0]["read_ports"], 2)
        self.assertEqual(rows[0]["clocked_read_mask"], 2)
        self.assertEqual(rows[0]["initialized_bits"], 8)

    def test_unknown_cell_rejected(self):
        with self.assertRaisesRegex(ValueError, "unresolved"):
            inventory({"modules": {"top": {"cells": {"x": {"type": "missing"}}}}}, "top")

    def test_opaque_declared_module_rejected(self):
        for tag in ("blackbox", "whitebox"):
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "opaque"):
                inventory({"modules": {"top": {"attributes": {tag: "1"}}}}, "top")

    def test_recursive_hierarchy_rejected(self):
        with self.assertRaisesRegex(AssertionError, "recursive"):
            inventory({"modules": {"top": {"cells": {"x": {"type": "top"}}}}}, "top")

    def test_unknown_parameter_rejected(self):
        with self.assertRaises(ValueError):
            number("10x0")


class DrcEvidenceTests(unittest.TestCase):
    def test_missing_items_is_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.xml"
            path.write_text("<report-database/>")
            with self.assertRaisesRegex(ValueError, "missing"):
                drc_result(path)

    def test_violation_count_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.xml"
            path.write_text("<report-database><top-cell>test</top-cell><items>"
                "<item><category>rule1</category></item></items></report-database>")
            value = drc_result(path)
            self.assertEqual(value["violation_items"], 1)
            self.assertEqual(value["categories_with_violations"], {"rule1": 1})


class SourceStageTests(unittest.TestCase):
    def test_output_namespace_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m6_stage_rtl, "ROOT", Path(tmp)), patch("sys.argv", [
                "stage", str(Path(tmp) / "build/m5_startup_forbidden")]):
                with self.assertRaises(SystemExit):
                    m6_stage_rtl.main()
            self.assertFalse((Path(tmp) / "build").exists())

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "build/m6_existing"
            output.mkdir(parents=True)
            sentinel = output / "sentinel"
            sentinel.write_text("keep")
            with patch.object(m6_stage_rtl, "ROOT", Path(tmp)), patch("sys.argv", [
                "stage", str(output)]), self.assertRaises(SystemExit):
                m6_stage_rtl.main()
            self.assertEqual(sentinel.read_text(), "keep")

    def test_qualified_staged_sources_unchanged(self):
        root = m6_stage_rtl.ROOT
        trial = root / "build/m6_elaboration_v4"
        if not trial.exists():
            self.skipTest("retained M6 elaboration artifacts required for this integration check")
        manifest = json.loads((trial / "manifest.json").read_text())
        self.assertFalse(manifest["asic_memory_mapping"])
        self.assertFalse(manifest["chip_pads"])
        for relative, record in manifest["sources"].items():
            self.assertEqual(m6_stage_rtl.digest(root / record["source"]), record["sha256"])
            expected = manifest["syntax_changes"].get(relative,
                manifest["technology_bindings"].get(relative, record))
            self.assertEqual(m6_stage_rtl.digest(trial / relative), expected["sha256"])


try:
    import klayout.db as db
    from scripts.m6_add_pr_boundary import fingerprint, main as add_boundary
except ImportError:
    db = None


@unittest.skipIf(db is None, "run with build/m6_tools_venv/bin/python for GDS tests")
class BoundaryTests(unittest.TestCase):
    def test_fingerprint_excludes_only_boundary(self):
        layout = db.Layout()
        top = layout.create_cell("macro")
        metal = layout.layer(68, 20)
        top.shapes(metal).insert(db.Box(0, 0, 50, 50))
        baseline = fingerprint(layout)
        top.shapes(layout.layer(235, 4)).insert(db.Box(0, 0, 100, 100))
        self.assertEqual(baseline, fingerprint(layout))
        top.shapes(layout.layer(22, 21)).insert(db.Box(0, 0, 10, 10))
        self.assertNotEqual(baseline, fingerprint(layout))

    def test_instance_change_detected(self):
        layout = db.Layout()
        top = layout.create_cell("macro")
        child = layout.create_cell("child")
        child.shapes(layout.layer(68, 20)).insert(db.Box(0, 0, 50, 50))
        top.insert(db.CellInstArray(child.cell_index(), db.Trans(10, 20)))
        baseline = fingerprint(layout)
        top.insert(db.CellInstArray(child.cell_index(), db.Trans(20, 20)))
        self.assertNotEqual(baseline, fingerprint(layout))

    def test_add_boundary_preserves_source_and_masks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, lef, output = (Path(tmp) / name for name in ("source.gds", "macro.lef", "out.gds"))
            layout = db.Layout()
            layout.dbu = 0.001
            top = layout.create_cell("macro")
            top.shapes(layout.layer(33, 43)).insert(db.Box(0, 0, 50, 50))
            layout.write(str(source))
            before = source.read_bytes()
            lef.write_text("MACRO macro\n SIZE 10.0 BY 20.0 ;\nEND macro\n")
            with patch("sys.argv", ["boundary", str(source), str(lef), str(output)]):
                add_boundary()
            self.assertEqual(before, source.read_bytes())
            result = db.Layout()
            result.read(str(output))
            self.assertEqual(fingerprint(layout), fingerprint(result))
            with patch("sys.argv", ["boundary", str(source), str(lef), str(output)]):
                with self.assertRaises(SystemExit):
                    add_boundary()


if __name__ == "__main__":
    unittest.main()
