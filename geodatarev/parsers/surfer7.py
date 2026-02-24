"""Parser for the Golden Software Surfer 7 binary grid format.

Surfer 7 uses a tag-based extensible architecture:
  - Each section starts with a tag: id (uint32) + size (uint32)
  - Tag 0x42525344: Header section
  - Tag 0x44495247: Grid section (contains grid parameters + data)
"""

from __future__ import annotations

import struct

from geodatarev.config import FormatConfig
from geodatarev.parsers import BaseParser, ParseResult

SURFER7_MAGIC = b"DSRB"
TAG_HEADER = 0x42525344
TAG_GRID = 0x44495247


def _read_tag(data: bytes, offset: int) -> tuple[int, int, int]:
    """Read a tag id and size, return (id, size, next_offset)."""
    if offset + 8 > len(data):
        return 0, 0, len(data)
    tag_id, tag_size = struct.unpack_from("<II", data, offset)
    return tag_id, tag_size, offset + 8


class Surfer7Parser(BaseParser):
    name = "surfer7"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        return len(data) >= 8 and data[:4] == SURFER7_MAGIC

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        result = ParseResult(format_name="Surfer 7 Binary Grid")

        if len(data) < 8 or data[:4] != SURFER7_MAGIC:
            result.errors.append("Not a valid Surfer 7 file")
            return result

        offset = 0
        while offset + 8 <= len(data):
            tag_id, tag_size, content_offset = _read_tag(data, offset)

            if tag_id == TAG_GRID and content_offset + tag_size <= len(data):
                self._parse_grid_section(data, content_offset, tag_size, result)

            offset = content_offset + tag_size
            if tag_size == 0:
                break

        return result

    @staticmethod
    def _parse_grid_section(data: bytes, offset: int, size: int,
                            result: ParseResult) -> None:
        """Parse the grid data section."""
        if size < 72:
            result.errors.append("Grid section too small")
            return

        # Grid section header (72 bytes):
        # ny(4) + nx(4) + xlo(8) + ylo(8) + xsize(8) + ysize(8) +
        # zmin(8) + zmax(8) + rotation(8) + blank_value(8)
        ny, nx = struct.unpack_from("<II", data, offset)
        xlo, ylo, xsize, ysize, zmin, zmax, rotation, blank_value = struct.unpack_from(
            "<8d", data, offset + 8,
        )

        result.header = {
            "nx": nx, "ny": ny,
            "xlo": xlo, "ylo": ylo,
            "xsize": xsize, "ysize": ysize,
            "zmin": zmin, "zmax": zmax,
            "rotation": rotation, "blank_value": blank_value,
        }
        result.shape = (ny, nx)

        payload_offset = offset + 72
        expected_bytes = nx * ny * 8  # 64-bit doubles
        payload = data[payload_offset:payload_offset + expected_bytes]

        n_values = len(payload) // 8
        if n_values > 0:
            values = list(struct.unpack_from(f"<{n_values}d", payload))
            result.data = values

        if len(payload) < expected_bytes:
            result.errors.append("Grid payload truncated")
