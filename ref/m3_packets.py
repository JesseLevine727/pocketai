"""Read reproducible M3 test packets and connect actual intermediate results.

No PYNQ dependency: the board harness and ordinary host tests use this module.
The references/generators remain responsible for mathematical expected values.
"""
from dataclasses import dataclass
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class Packet:
    kind: int  # 0 GEMM, 1 SFPU
    parameters: tuple
    tag: int
    inputs: np.ndarray
    expected: np.ndarray
    cycles: int
    source: int = 0
    mode: int = 0
    count: int = 0
    destination: int = 0
    offset: int = 0
    result_count: int = 0
    scenario: int = 0

    @property
    def macs(self):
        return int(np.prod(self.parameters[:3])) if self.kind == 0 else 0


def read_packets(path):
    data = memoryview(Path(path).read_bytes())
    cursor = 0

    def words(count):
        nonlocal cursor
        if not 0 <= count <= 100000 or cursor + 4 * count > len(data):
            raise ValueError("invalid/truncated M3 packet")
        result = np.frombuffer(data[cursor:cursor + 4 * count], dtype="<u4").copy()
        cursor += 4 * count
        return result

    magic, count, seed = map(int, words(3))
    if count < 1 or count > 100000:
        raise ValueError("invalid M3 packet count")
    packets = []
    for _ in range(count):
        if magic == 0x334e4843:
            m = list(map(int, words(16)))
            packets.append(Packet(m[0], tuple(m[1:5]), m[5], words(m[6]),
                                  words(m[7]), m[8], *m[9:16]))
        elif magic == 0x33504653:
            op, length, shift, mult, tag, ni, no, cycles = map(int, words(8))
            packets.append(Packet(1, (op, length, shift, mult), tag,
                                  words(ni), words(no), cycles))
        elif magic == 0x324d4547:
            rows, cols, k, tag, flags, ni, no = map(int, words(7))
            cycles = ((rows + 3) // 4) * (k + 6) + rows * (16 if flags else 8)
            packets.append(Packet(0, (rows, cols, k, flags), tag,
                                  words(ni), words(no), cycles))
        else:
            raise ValueError("unknown M3 packet magic")
    if cursor != len(data):
        raise ValueError("trailing M3 packet bytes")
    return packets, seed


def patch_input(packet, source, target):
    """Replace only dependent input lanes; retain weights/bias/mask metadata."""
    n = packet.count
    if len(source) < n:
        raise ValueError("chain source is incomplete")
    if packet.mode == 1:
        target[:n] = source[:n]
    elif packet.mode == 2:
        # Chain A rows have K divisible by four. Padding outside the prefix
        # is unchanged; the byte view makes little-endian packet order explicit.
        target.view(np.uint8)[:n] = (source[:n] & 255).astype(np.uint8)
    elif packet.mode == 3:
        target[:n] = (target[:n] & 0x10000) | (source[:n] & 0xffff)
    else:
        raise ValueError("unknown chain patch mode")


def runtime_requant_parameters(source):
    """A9-side dynamic row reduction, included in dependent-chain wall time.

    Independent vectorized implementation of the frozen int16/probability
    bridge: raw codes can include positive softmax endpoint 32768.
    """
    values = np.asarray(source, dtype="<u4").view("<i4").astype(np.int64)
    maximum = int(np.abs(values).max())
    if not maximum:
        return 0, 24
    quotient, remainder = divmod(127 << 24, maximum)
    quotient += int(2 * remainder > maximum or
                    (2 * remainder == maximum and quotient & 1))
    return quotient, 24
