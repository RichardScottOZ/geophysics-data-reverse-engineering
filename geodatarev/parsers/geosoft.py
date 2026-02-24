"""Parser for the Geosoft Oasis montaj binary grid (.grd) format.

Reads version 2 of the Geosoft Grid File Format. The 512-byte header
contains data storage parameters, geographic info, and scaling factors.
The payload may be uncompressed or zlib-compressed (ES > 1024).

Inspired by fatiando/harmonica's ``load_oasis_montaj_grid`` and
Loop3D/geosoft_grid, reimplemented here without external dependencies
beyond the standard library.
"""

from __future__ import annotations

import array
import struct
import zlib
from pathlib import Path

from geodatarev.config import FormatConfig
from geodatarev.parsers import BaseParser, ParseResult

HEADER_SIZE = 512

# Dummy (NoData) sentinel values per array type code
_DUMMIES = {
    "b": -127,
    "B": 255,
    "h": -32767,
    "H": 65535,
    "i": -2147483647,
    "I": 4294967295,
    "f": -1e32,
    "d": -1e32,
}

VALID_ES = (1, 2, 4, 8, 1025, 1026, 1028, 1032)


def _data_type_code(es: int, sf: int) -> str:
    """Map element size + sign flag to Python array type code."""
    if es > 1024:
        es -= 1024
    mapping = {
        (1, 0): "B", (1, 1): "b",
        (2, 0): "H", (2, 1): "h",
        (4, 0): "I", (4, 1): "i", (4, 2): "f",
        (8, 0): "d", (8, 1): "d", (8, 2): "d",
    }
    return mapping.get((es, sf), "f")


def _decompress(payload: bytes) -> bytes:
    """Decompress a Geosoft zlib-compressed grid payload."""
    n_blocks = struct.unpack_from("<i", payload, 8)[0]
    _vecs_per_block = struct.unpack_from("<i", payload, 12)[0]
    off = 16
    block_offsets = struct.unpack_from(f"<{n_blocks}q", payload, off)
    off += n_blocks * 8
    block_sizes = struct.unpack_from(f"<{n_blocks}i", payload, off)

    parts: list[bytes] = []
    for i in range(n_blocks):
        start = block_offsets[i] - HEADER_SIZE + 16
        end = start + block_sizes[i]
        parts.append(zlib.decompress(payload[start:end]))
    return b"".join(parts)


def _read_header(hdr: bytes) -> dict:
    """Parse the 512-byte Geosoft grid header."""
    es, sf, ne, nv, kx = struct.unpack_from("<5i", hdr, 0)
    de, dv, x0, y0, rot = struct.unpack_from("<5d", hdr, 20)
    zbase, zmult = struct.unpack_from("<2d", hdr, 60)
    return {
        "n_bytes_per_element": es,
        "sign_flag": sf,
        "shape_e": ne,
        "shape_v": nv,
        "ordering": kx,
        "spacing_e": de,
        "spacing_v": dv,
        "x_origin": x0,
        "y_origin": y0,
        "rotation": rot,
        "base_value": zbase,
        "data_factor": zmult,
    }


class GeosoftParser(BaseParser):
    name = "geosoft"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        """Heuristic: 512-byte header with valid ES, SF, KX and sane dimensions."""
        if len(data) < HEADER_SIZE:
            return False
        # Reject files that match other known .grd magics
        if data[:4] in (b"DSBB", b"DSRB", b"DSAA"):
            return False
        try:
            hdr = _read_header(data[:HEADER_SIZE])
        except Exception:
            return False
        if hdr["n_bytes_per_element"] not in VALID_ES:
            return False
        if hdr["ordering"] not in (-1, 1):
            return False
        if hdr["sign_flag"] not in (0, 1, 2, 3):
            return False
        if hdr["sign_flag"] == 3:
            return False  # colour grids unsupported
        ne, nv = hdr["shape_e"], hdr["shape_v"]
        if ne <= 0 or nv <= 0 or ne > 1_000_000 or nv > 1_000_000:
            return False
        if hdr["data_factor"] == 0:
            return False
        return True

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        result = ParseResult(format_name="Geosoft Binary Grid")
        if len(data) < HEADER_SIZE:
            result.errors.append("File too small for Geosoft header")
            return result

        hdr = _read_header(data[:HEADER_SIZE])
        result.header = hdr

        es = hdr["n_bytes_per_element"]
        sf = hdr["sign_flag"]
        ne, nv = hdr["shape_e"], hdr["shape_v"]
        result.shape = (nv, ne)

        tc = _data_type_code(es, sf)
        payload = data[HEADER_SIZE:]

        if es > 1024:
            try:
                payload = _decompress(payload)
            except Exception as exc:
                result.errors.append(f"Decompression failed: {exc}")
                return result

        try:
            values = array.array(tc, payload)
        except Exception as exc:
            result.errors.append(f"Array decode failed: {exc}")
            return result

        # Replace dummies with None, apply scaling
        dummy = _DUMMIES.get(tc)
        scaled: list[float | None] = []
        zmult = hdr["data_factor"]
        zbase = hdr["base_value"]
        for v in values:
            if dummy is not None:
                if tc in ("f", "d") and v <= dummy:
                    scaled.append(None)
                    continue
                elif tc not in ("f", "d") and v == dummy:
                    scaled.append(None)
                    continue
            scaled.append(v / zmult + zbase)

        result.data = scaled
        result.metadata["null_count"] = sum(1 for v in scaled if v is None)
        return result
