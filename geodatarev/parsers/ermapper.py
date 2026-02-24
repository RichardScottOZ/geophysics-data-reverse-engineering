"""Parser for the ER Mapper (.ers) raster header format.

ER Mapper uses a decoupled architecture with:
  - An ASCII header file (``.ers``) with block-structured metadata
  - A separate raw binary data file (no extension, or ``.bil`` / ``.bsq``)

This parser reads the ``.ers`` header and optionally the companion
binary payload.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any

from geodatarev.config import FormatConfig
from geodatarev.parsers import BaseParser, ParseResult

ERS_MAGIC = b"DatasetHeader"


def _parse_ers_header(text: str) -> dict[str, Any]:
    """Parse an ER Mapper ``.ers`` text header into a nested dict."""
    result: dict[str, Any] = {}
    stack: list[dict[str, Any]] = [result]

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        # Opening a block: ``BlockName  Begin``
        m = re.match(r"^(\w+)\s+Begin\s*$", stripped, re.IGNORECASE)
        if m:
            key = m.group(1)
            child: dict[str, Any] = {}
            stack[-1][key] = child
            stack.append(child)
            continue

        # Closing a block: ``End`` or ``BlockName End``
        if re.match(r"^(\w+\s+)?End\s*$", stripped, re.IGNORECASE):
            if len(stack) > 1:
                stack.pop()
            continue

        # Key = value
        m = re.match(r'^(\w+)\s*=\s*"?([^"]*)"?\s*$', stripped)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            # Try numeric conversion
            try:
                val = int(val)  # type: ignore[assignment]
            except ValueError:
                try:
                    val = float(val)  # type: ignore[assignment]
                except ValueError:
                    pass
            stack[-1][key] = val

    return result


class ERMapperParser(BaseParser):
    name = "ermapper"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        try:
            text = data[:256].decode("ascii", errors="ignore")
        except Exception:
            return False
        return "DatasetHeader" in text

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        """Parse an ER Mapper ``.ers`` header.

        If *data* is the ASCII header, it returns metadata only.
        """
        result = ParseResult(format_name="ER Mapper")

        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            result.errors.append("Could not decode header as ASCII")
            return result

        header = _parse_ers_header(text)
        result.header = header

        # Extract common fields
        raster = header.get("DatasetHeader", header)
        if isinstance(raster, dict):
            raster_info = raster.get("RasterInfo", {})
            if isinstance(raster_info, dict):
                nx = raster_info.get("NrOfCellsPerLine", 0)
                ny = raster_info.get("NrOfLines", 0)
                result.shape = (ny, nx) if nx and ny else ()
                result.metadata["cell_type"] = raster_info.get("CellType", "")
                coord = raster.get("CoordinateSpace", {})
                if isinstance(coord, dict):
                    result.metadata["datum"] = coord.get("Datum", "")
                    result.metadata["projection"] = coord.get("Projection", "")

        return result

    def parse_file(self, path: str | Path, config: FormatConfig | None = None) -> ParseResult:
        """Parse an ``.ers`` header file and optionally its companion binary."""
        path = Path(path)
        with open(path, "rb") as fh:
            header_data = fh.read()
        result = self.parse(header_data, config)

        # Try to locate the companion binary
        bin_path = path.with_suffix("")
        if bin_path.exists() and bin_path.is_file():
            result.metadata["binary_path"] = str(bin_path)
            result.metadata["binary_size"] = bin_path.stat().st_size

        return result
