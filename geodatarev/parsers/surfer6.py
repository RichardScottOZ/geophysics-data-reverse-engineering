"""Parser for the Golden Software Surfer 6 binary grid format.

Surfer 6 layout:
  - 4 bytes: magic ``DSBB`` (0x44534242)
  - 2 bytes: nx (uint16, number of columns)
  - 2 bytes: ny (uint16, number of rows)
  - 8 bytes: xlo (float64)
  - 8 bytes: xhi (float64)
  - 8 bytes: ylo (float64)
  - 8 bytes: yhi (float64)
  - 8 bytes: zlo (float64)
  - 8 bytes: zhi (float64)
  - nx*ny float32 values, row-major from ylo to yhi
"""

from __future__ import annotations

import struct

from geodatarev.config import FormatConfig
from geodatarev.parsers import BaseParser, ParseResult

SURFER6_MAGIC = b"DSBB"
HEADER_SIZE = 56


class Surfer6Parser(BaseParser):
    name = "surfer6"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        return len(data) >= HEADER_SIZE and data[:4] == SURFER6_MAGIC

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        result = ParseResult(format_name="Surfer 6 Binary Grid")

        if len(data) < HEADER_SIZE:
            result.errors.append("File too small for Surfer 6 header")
            return result

        magic = data[:4]
        if magic != SURFER6_MAGIC:
            result.errors.append(f"Invalid magic: {magic!r}")
            return result

        nx, ny = struct.unpack_from("<HH", data, 4)
        xlo, xhi, ylo, yhi, zlo, zhi = struct.unpack_from("<6d", data, 8)

        result.header = {
            "nx": nx, "ny": ny,
            "xlo": xlo, "xhi": xhi,
            "ylo": ylo, "yhi": yhi,
            "zlo": zlo, "zhi": zhi,
        }
        result.shape = (ny, nx)

        payload_offset = HEADER_SIZE
        expected_bytes = nx * ny * 4
        payload = data[payload_offset:payload_offset + expected_bytes]

        if len(payload) < expected_bytes:
            result.errors.append(
                f"Payload truncated: expected {expected_bytes} bytes, got {len(payload)}"
            )

        n_values = len(payload) // 4
        values = list(struct.unpack_from(f"<{n_values}f", payload))
        result.data = values
        return result
