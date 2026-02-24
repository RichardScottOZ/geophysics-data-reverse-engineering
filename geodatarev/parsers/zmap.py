"""Parser for ZMap+ ASCII grid format.

ZMap+ grids (Landmark/Zycor) use ``!`` for comment lines and ``@``
delimiters around a structured header section. The data follows as
space-separated values in fixed-width columns.

Example header::

    ! ZIMS FILE NAME : example
    @example HEADER, GRID, 5
    15, 1.0E+30, , 7, 1
    473, 325, 401310.0, 417510.0, 6819260.0, 6842860.0
    0.0, 0.0, 0.0
    @
    <data values ...>
"""

from __future__ import annotations

import re
from pathlib import Path

from geodatarev.config import FormatConfig
from geodatarev.parsers import BaseParser, ParseResult


def _is_zmap(text: str) -> bool:
    """Quick check for ZMap+ structure."""
    # Must have @ delimiters and typically ! comments
    return "@" in text[:2048] and ("!" in text[:512] or "HEADER" in text[:2048].upper())


class ZMapParser(BaseParser):
    name = "zmap"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        try:
            text = data[:2048].decode("ascii", errors="ignore")
        except Exception:
            return False
        return _is_zmap(text)

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        result = ParseResult(format_name="ZMap+ ASCII Grid")
        try:
            text = data.decode("ascii", errors="replace")
        except Exception:
            result.errors.append("Could not decode as ASCII")
            return result

        lines = text.splitlines()
        header: dict = {}
        data_start = 0
        in_header = False

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("!"):
                # Comment line — extract label if present
                if ":" in stripped:
                    key, _, val = stripped[1:].partition(":")
                    header[key.strip()] = val.strip()
                continue
            if stripped.startswith("@") and not in_header:
                in_header = True
                # First @ line: may contain name, HEADER, GRID, n_per_line
                parts = stripped[1:].split(",")
                if len(parts) >= 3:
                    header["grid_name"] = parts[0].strip().split()[0] if parts[0].strip() else ""
                    try:
                        header["values_per_line"] = int(parts[-1].strip())
                    except ValueError:
                        pass
                continue
            if stripped.startswith("@") and in_header:
                # Closing @ — data starts next line
                in_header = False
                data_start = i + 1
                continue
            if in_header:
                # Parse header rows
                parts = [p.strip() for p in stripped.split(",")]
                if "null_value" not in header and len(parts) >= 2:
                    # Row 1: n_per_line, null_value, ?, n_cols_data, 1
                    try:
                        header["null_value"] = float(parts[1]) if parts[1] else 1e30
                        header["n_data_columns"] = int(parts[3]) if len(parts) > 3 else 0
                    except (ValueError, IndexError):
                        pass
                elif "ny" not in header and len(parts) >= 6:
                    # Row 2: ny, nx, xmin, xmax, ymin, ymax
                    try:
                        header["ny"] = int(parts[0])
                        header["nx"] = int(parts[1])
                        header["xmin"] = float(parts[2])
                        header["xmax"] = float(parts[3])
                        header["ymin"] = float(parts[4])
                        header["ymax"] = float(parts[5])
                    except (ValueError, IndexError):
                        pass

        result.header = header
        nx = header.get("nx", 0)
        ny = header.get("ny", 0)
        if nx and ny:
            result.shape = (ny, nx)

        # Parse data values
        null_val = header.get("null_value", 1e30)
        values: list[float | None] = []
        for line in lines[data_start:]:
            stripped = line.strip()
            if not stripped or stripped.startswith("!") or stripped.startswith("@"):
                continue
            for token in stripped.split():
                try:
                    v = float(token)
                    values.append(None if abs(v) >= abs(null_val) * 0.99 else v)
                except ValueError:
                    continue

        result.data = values
        result.metadata["null_count"] = sum(1 for v in values if v is None)
        return result
