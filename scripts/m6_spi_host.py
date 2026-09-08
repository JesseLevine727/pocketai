"""Reference SPI supervisor; a caller supplies the physical SPI transport.

No device is opened and no hardware operation occurs on import. The transport
must implement mode 0, MSB first, nine bytes/frame, SCLK <= sysclk/8 and at
least eight system cycles with CS high between calls. External RAM provisioning
is performed by the separate native-AXI controller, never by a host tensor worker.
"""
import struct


class SpiError(RuntimeError):
    pass


class Supervisor:
    CONTROL=0x20000
    TABLE=0x20004
    ARENA=0x20008
    STATUS=0x2000c
    UART_DIVIDER=0x20010

    def __init__(self, transfer, max_polls=1024):
        if max_polls < 1:
            raise ValueError("positive bounded poll count required")
        self.transfer=transfer
        self.max_polls=max_polls

    def _frame(self, command=0, address=0, data=0):
        reply=self.transfer(struct.pack(">BII",command,address,data))
        if len(reply)!=9:
            raise SpiError("SPI transport did not return a complete nine-byte frame")
        return reply[0],int.from_bytes(reply[1:5],"big")

    def _request(self, address, data=None, mask=15):
        if address < 0 or address > 0xffffffff or address%4 or not 0 <= mask <= 15:
            raise ValueError("aligned 32-bit address and four-bit mask required")
        if data is not None and not 0 <= data <= 0xffffffff:
            raise ValueError("32-bit unsigned write data required")
        # One accepted request, followed only by non-destructive poll frames.
        status,_=self._frame(0x80 if data is None else 0x90|mask,address,data or 0)
        if status & 0x40:
            raise SpiError("previous command still busy; new request rejected")
        for _ in range(self.max_polls):
            status,value=self._frame()
            if status & 0x20:
                raise SpiError("device rejected a malformed or overlapping command")
            if status & 0x80:
                if status & 0x43:
                    raise SpiError(f"SPI/AXI response error: status 0x{status:02x}")
                return value
        raise SpiError("bounded SPI response timeout; do not retry a write blindly")

    def status(self):
        return self._request(self.STATUS)

    def _wait_status(self, bit):
        for _ in range(self.max_polls):
            value=self.status()
            if value & (1<<bit): return value
        raise SpiError(f"bounded wait for hardware status bit {bit}")

    def prepare(self):
        """Hold both harts, request abort, then wait for actual DMA quiescence."""
        control=self._request(self.CONTROL)
        self._request(self.CONTROL,(control | 0x11) & ~2)
        self._wait_status(2)

    def _require_owned(self):
        if self._request(self.CONTROL)&2 or not self.status()&4:
            raise SpiError("host access requires stopped harts and drained memory; call prepare")

    def write_mmio(self, address, data, mask=15):
        if not 0 <= address < 0x20000: raise ValueError("cluster MMIO address required")
        self._require_owned()
        self._request(address,data,mask)

    def read_mmio(self, address):
        if not 0 <= address < 0x20000: raise ValueError("cluster MMIO address required")
        self._require_owned()
        return self._request(address)

    def configure_memory(self, table_base, arena_bytes, enabled=True):
        self._require_owned()
        if table_base%4 or not 0 < arena_bytes <= 0xffffffff:
            raise ValueError("aligned page table and nonempty 32-bit arena required")
        self._request(self.TABLE,table_base)
        self._request(self.ARENA,arena_bytes)
        control=self._request(self.CONTROL)
        self._request(self.CONTROL,(control&~4)|(4 if enabled else 0))

    def configure_uart(self, divider, enabled=True):
        if not 8 <= divider <= 65535: raise ValueError("UART divider must be 8..65535")
        self._request(self.UART_DIVIDER,divider)
        control=self._request(self.CONTROL)
        self._request(self.CONTROL,(control&~32)|(32 if enabled else 0))

    def start(self):
        """Clear latched cancellation under cluster reset, flush, then release."""
        self._require_owned()
        settings=self._request(self.CONTROL)&0x24
        self._request(self.CONTROL,settings)       # cluster held, abort lowered
        self._request(self.CONTROL,settings|9)     # release cluster + flush
        self._wait_status(0)
        self._request(self.CONTROL,settings|1)     # retire flush, harts held
        self._request(self.CONTROL,settings|3)     # release both harts
