"""Generate the project's original geometric icon without external dependencies."""
from pathlib import Path
import struct
import zlib


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


size = 140
rows = bytearray()
for y in range(size):
    rows.append(0)
    for x in range(size):
        triangle = 40 <= x <= 104 and abs(y - 70) <= (104 - x) * 0.65
        rows.extend((245, 245, 245) if triangle else (170, 26, 38))
png = b'\x89PNG\r\n\x1a\n'
png += chunk(b'IHDR', struct.pack('>2I5B', size, size, 8, 2, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b'')
target = Path(__file__).resolve().parents[1] / 'apps/shjeladze_jltube/shjeladze_jltube@0.3.0/rhmiData/variantGroups/Common/images/jltube.png'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_bytes(png)
