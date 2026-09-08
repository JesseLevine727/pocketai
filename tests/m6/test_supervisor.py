import struct
import unittest
from scripts.m6_spi_host import SpiError, Supervisor


class Endpoint:
    def __init__(self):
        self.control=0x10
        self.response=(0,0)
        self.writes=[]
        self.registers={0x20004:0,0x20008:0x10000000,0x20010:217}
        self.frames=[]
    def transfer(self, frame):
        self.frames.append(frame)
        previous=bytes([self.response[0]])+self.response[1].to_bytes(4,"big")+bytes(4)
        command,address,data=struct.unpack(">BII",frame)
        if command==0: return previous
        value=self.control if address==0x20000 else 5 if address==0x2000c else self.registers.get(address,0)
        if command&0xf0==0x90:
            self.writes.append((address,data,command&15))
            if address==0x20000: self.control=data
            else: self.registers[address]=data
        self.response=(0x80,value)
        return previous


class SupervisorTests(unittest.TestCase):
    def test_single_write_not_repeated_by_polling(self):
        endpoint=Endpoint(); supervisor=Supervisor(endpoint.transfer)
        supervisor.prepare(); supervisor.write_mmio(0x80,0x12345678)
        self.assertEqual([x for x in endpoint.writes if x[0]==0x80],[(0x80,0x12345678,15)])
        self.assertEqual(supervisor.read_mmio(0x80),0x12345678)

    def test_start_uses_reset_flush_then_release(self):
        endpoint=Endpoint(); supervisor=Supervisor(endpoint.transfer)
        supervisor.prepare(); supervisor.configure_memory(0x2000000,266289152)
        supervisor.configure_uart(217)
        endpoint.writes.clear(); supervisor.start()
        self.assertEqual(endpoint.writes,[(0x20000,0x24,15),(0x20000,0x2d,15),
                                         (0x20000,0x25,15),(0x20000,0x27,15)])
        with self.assertRaisesRegex(SpiError,"stopped harts"):
            supervisor.write_mmio(0,1)

    def test_timeout_does_not_retry_command(self):
        calls=[]
        def transfer(frame): calls.append(frame); return bytes(9)
        supervisor=Supervisor(transfer,max_polls=3)
        with self.assertRaisesRegex(SpiError,"timeout"): supervisor._request(0,1)
        self.assertEqual(len(calls),4)
        self.assertEqual([x[0] for x in calls],[0x9f,0,0,0])

    def test_errors_and_short_frames_fail_closed(self):
        for response in (b"",bytes([0xa0])+bytes(8),bytes([0x82])+bytes(8)):
            supervisor=Supervisor(lambda _:response,max_polls=2)
            with self.assertRaises(SpiError): supervisor._request(0)

    def test_invalid_inputs_do_not_reach_transport(self):
        def forbidden(_): raise AssertionError("unexpected transport call")
        supervisor=Supervisor(forbidden)
        for address in (-4,1,0x100000000):
            with self.assertRaises(ValueError): supervisor._request(address)
        for divider in (0,7,65536):
            with self.assertRaises(ValueError): supervisor.configure_uart(divider)


if __name__=="__main__": unittest.main()
