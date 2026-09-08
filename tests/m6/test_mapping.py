"""Memory mapper rejection tests: no silent changes to port semantics or scope."""
import copy
import unittest

from scripts.m6_map_memories import TOP, memory_spec, transform


def ram(reads=2):
    p = dict(WIDTH=32, SIZE=512, RD_PORTS=reads, WR_PORTS=1, ABITS=9, OFFSET=0,
        INIT="x"*(512*32), RD_CLK_ENABLE=(1 << reads)-1,
        RD_CLK_POLARITY=(1 << reads)-1, WR_CLK_ENABLE=1, WR_CLK_POLARITY=1,
        RD_TRANSPARENCY_MASK=0, RD_COLLISION_X_MASK=0, RD_WIDE_CONTINUATION=0,
        WR_WIDE_CONTINUATION=0, WR_PRIORITY_MASK=0, RD_INIT_VALUE="x"*(reads*32))
    c = dict(RD_CLK=[2]*reads, WR_CLK=[2], RD_ARST=["0"]*reads, RD_SRST=["0"]*reads,
        RD_EN=[3]*reads, RD_ADDR=list(range(4, 4+9*reads)),
        RD_DATA=list(range(40, 40+32*reads)), WR_ADDR=list(range(120,129)),
        WR_DATA=list(range(140,172)), WR_EN=[180]*8+[181]*8+[182]*8+[183]*8)
    return {"type": "$mem_v2", "parameters": p, "connections": c,
        "port_directions": {k: "output" if k=="RD_DATA" else "input" for k in c}}


class MappingTests(unittest.TestCase):
    def test_physical_read_replication_and_byte_masks(self):
        spec, reason = memory_spec(ram())
        self.assertIsNone(reason)
        self.assertEqual(spec["logical_bits"], 16384)
        self.assertEqual(spec["physical_bits"], 32768)
        self.assertEqual(spec["macros"], 2)
        self.assertEqual(spec["mask_bits"], [180,181,182,183])

    def test_transparent_read_rejected(self):
        cell = ram()
        cell["parameters"]["RD_TRANSPARENCY_MASK"] = 1
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_dont_care_collision_can_return_old_data(self):
        cell = ram()
        cell["parameters"]["RD_COLLISION_X_MASK"] = 1
        self.assertEqual(memory_spec(cell)[0]["source_collision_x_mask"], 1)

    def test_initialized_writable_ram_rejected(self):
        cell = ram()
        cell["parameters"]["INIT"] = "0"*(512*32)
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_subbyte_writes_rejected(self):
        cell = ram()
        cell["connections"]["WR_EN"][1] = 999
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_different_clocks_rejected(self):
        cell = ram()
        cell["connections"]["RD_CLK"][1] = 999
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_read_reset_rejected(self):
        cell = ram()
        cell["connections"]["RD_SRST"][1] = 999
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_bulk_async_cannot_become_registers(self):
        cell = ram()
        cell["parameters"]["RD_CLK_ENABLE"] = 0
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_extra_write_port_rejected(self):
        cell = ram()
        cell["parameters"]["WR_PORTS"] = 2
        with self.assertRaises(AssertionError): memory_spec(cell)

    def test_hierarchy_scope_and_source_immutable(self):
        source = {"modules": {
            TOP: {"ports": {"s_axi_aclk": {"direction":"input", "bits":[2]}},
                "cells": {"impl": {"type":"pa_m5_cluster_top", "connections":{"clk":[2]},
                    "port_directions":{"clk":"input"}, "parameters":{}}}},
            "pa_m5_cluster_top": {"ports":{"clk":{"direction":"input", "bits":[2]}},
                "cells": {"mem": ram()}}}}
        before = copy.deepcopy(source)
        mapped, _, instances, exceptions = transform(source)
        self.assertEqual(source, before)
        self.assertEqual(len(instances), 1)
        self.assertFalse(exceptions)
        self.assertIn("pa_m6_portable", mapped["modules"])
        core = mapped["modules"]["pa_m6_cluster_core"]
        self.assertEqual(core["cells"]["mem"]["connections"]["clk_mem_i"], core["ports"]["m6_clk_mem_i"]["bits"])
        self.assertNotEqual(core["ports"]["m6_clk_mem_i"]["bits"], core["ports"]["m6_mem_rst_ni"]["bits"])


if __name__ == "__main__": unittest.main()
