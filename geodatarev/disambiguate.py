"""Heuristic disambiguation for overloaded file extensions.

The ``.dat`` and ``.grd`` extensions are used by many incompatible formats.
This module provides a heuristic chain that inspects file content to
determine the most likely format.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def classify_dat(data: bytes, path: Path | None = None) -> str:
    """Classify a ``.dat`` file by inspecting its content.

    Returns a format label string. Checks are ordered from most
    specific to least specific.
    """
    text = data[:4096].decode("ascii", errors="ignore")

    # ASEG-GDF2: companion .dfn file
    if path is not None:
        dfn = path.with_suffix(".dfn")
        if dfn.exists():
            return "ASEG-GDF2"

    # ZMap+: @ delimiters and ! comments
    if "@" in text[:2048] and ("!" in text[:512] or "HEADER" in text[:2048].upper()):
        return "ZMap+"

    # Res2DInv: first non-blank line is a title, second is an integer (array type)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 3:
        try:
            int(lines[1])
            float(lines[2].split()[0])
            return "Res2DInv"
        except (ValueError, IndexError):
            pass

    # ReflexW: binary with specific header
    if data[:4] == b"RFLX" or data[:6] == b"REFLEXW":
        return "ReflexW"

    # Tab/comma/space delimited numeric columns (generic XYZ)
    numeric_lines = 0
    for line in lines[:20]:
        tokens = line.replace(",", " ").split()
        try:
            [float(t) for t in tokens]
            numeric_lines += 1
        except ValueError:
            pass
    if numeric_lines >= 10:
        return "Generic ASCII XYZ"

    return "Unknown .dat"


def classify_grd(data: bytes, path: Path | None = None) -> str:
    """Classify a ``.grd`` file by inspecting magic bytes and companions.

    Returns a format label string.
    """
    if len(data) < 4:
        return "Unknown .grd (too small)"

    magic4 = data[:4]

    if magic4 == b"DSAA":
        return "Surfer ASCII Grid"
    if magic4 == b"DSBB":
        return "Surfer 6 Binary Grid"
    if magic4 == b"DSRB":
        return "Surfer 7 Binary Grid"

    # Geosoft: companion .grd.gi file
    if path is not None:
        gi = Path(str(path) + ".gi")
        if gi.exists():
            return "Geosoft Binary Grid"

    # Encom ModelVision: GRID at offset 168
    if len(data) > 172 and data[168:172] == b"GRID":
        return "Encom ModelVision Grid"

    # Geosoft heuristic: 512-byte header with valid ES/SF/KX
    if len(data) >= 512:
        import struct
        try:
            es, sf, ne, nv, kx = struct.unpack_from("<5i", data, 0)
            if (es in (1, 2, 4, 8, 1025, 1026, 1028, 1032)
                    and sf in (0, 1, 2)
                    and kx in (-1, 1)
                    and 0 < ne < 1_000_000
                    and 0 < nv < 1_000_000):
                zmult = struct.unpack_from("<d", data, 68)[0]
                if zmult != 0:
                    return "Geosoft Binary Grid"
        except struct.error:
            pass

    # Vertical Mapper: check for .mig companion
    if path is not None:
        mig = path.with_suffix(".mig")
        if mig.exists():
            return "Vertical Mapper Grid"

    return "Unknown .grd"
