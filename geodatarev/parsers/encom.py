"""Parser for the Encom ModelVision grid format.

ModelVision grids have a 240-byte header with padded ASCII fields.
The string ``GRID`` appears at byte offset 168. The data payload
is contiguous 32-bit IEEE 754 floats immediately after the header.
"""

from __future__ import annotations

import struct
from pathlib import Path

from geodatarev.config import FormatConfig
from geodatarev.parsers import BaseParser, ParseResult

HEADER_SIZE = 240
GRID_MARKER = b"GRID"
GRID_MARKER_OFFSET = 168


class EncomParser(BaseParser):
    name = "encom"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        if len(data) < HEADER_SIZE:
            return False
        return data[GRID_MARKER_OFFSET:GRID_MARKER_OFFSET + 4] == GRID_MARKER

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        result = ParseResult(format_name="Encom ModelVision Grid")
        if not self.can_parse(data):
            result.errors.append("Not a valid Encom ModelVision grid")
            return result

        # Parse known header fields (ASCII-padded, positions from Tensor docs)
        def _ascii(start: int, length: int) -> str:
            return data[start:start + length].decode("ascii", errors="replace").strip("\x00 ")

        def _f64(offset: int) -> float:
            return struct.unpack_from("<d", data, offset)[0]

        def _i32(offset: int) -> int:
            return struct.unpack_from("<i", data, offset)[0]

        header: dict = {}
        # Dimensions typically at offsets 4-8
        try:
            header["nx"] = _i32(4)
            header["ny"] = _i32(8)
            header["xmin"] = _f64(12)
            header["xmax"] = _f64(20)
            header["ymin"] = _f64(28)
            header["ymax"] = _f64(36)
            header["zmin"] = _f64(44)
            header["zmax"] = _f64(52)
        except struct.error:
            result.errors.append("Could not parse header dimensions")
            return result

        result.header = header
        nx, ny = header.get("nx", 0), header.get("ny", 0)
        if nx > 0 and ny > 0:
            result.shape = (ny, nx)

        # Payload: float32 values after header
        payload = data[HEADER_SIZE:]
        expected = nx * ny * 4
        if len(payload) < expected and nx > 0 and ny > 0:
            result.errors.append(
                f"Payload truncated: expected {expected} bytes, got {len(payload)}"
            )

        n_values = min(len(payload) // 4, nx * ny) if nx > 0 and ny > 0 else len(payload) // 4
        if n_values > 0:
            result.data = list(struct.unpack_from(f"<{n_values}f", payload))

        return result
