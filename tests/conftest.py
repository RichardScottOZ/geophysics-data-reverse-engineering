"""Shared test fixtures for geodatarev."""

import os
import struct
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory Path."""
    return tmp_path


@pytest.fixture
def surfer6_bytes():
    """Build a minimal Surfer 6 binary grid (3x2)."""
    nx, ny = 3, 2
    xlo, xhi = 0.0, 10.0
    ylo, yhi = 0.0, 5.0
    zlo, zhi = -1.0, 1.0
    header = b"DSBB" + struct.pack("<HH6d", nx, ny, xlo, xhi, ylo, yhi, zlo, zhi)
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    payload = struct.pack(f"<{len(values)}f", *values)
    return header + payload


@pytest.fixture
def surfer6_file(tmp_dir, surfer6_bytes):
    """Write a Surfer 6 grid to a temp file and return its path."""
    p = tmp_dir / "sample.grd"
    p.write_bytes(surfer6_bytes)
    return p


@pytest.fixture
def surfer7_bytes():
    """Build a minimal Surfer 7 binary grid (2x2)."""
    nx, ny = 2, 2
    xlo, ylo = 0.0, 0.0
    xsize, ysize = 1.0, 1.0
    zmin, zmax = 0.0, 4.0
    rotation = 0.0
    blank = 1.70141e+38
    grid_header = struct.pack("<II8d", ny, nx, xlo, ylo, xsize, ysize,
                              zmin, zmax, rotation, blank)
    values = [1.0, 2.0, 3.0, 4.0]
    payload = struct.pack(f"<{len(values)}d", *values)
    grid_content = grid_header + payload

    # Surfer 7 structure: DSRB header tag (id=0x42525344, size=4, version)
    # followed by GRID tag (id=0x44495247, size=N, grid data)
    header_tag_id = 0x42525344   # "DSRB" as LE uint32
    grid_tag_id = 0x44495247     # "GRID" as LE uint32
    version = struct.pack("<I", 2)
    file_data = (
        struct.pack("<II", header_tag_id, len(version)) + version
        + struct.pack("<II", grid_tag_id, len(grid_content)) + grid_content
    )
    return file_data


@pytest.fixture
def surfer7_file(tmp_dir, surfer7_bytes):
    p = tmp_dir / "sample7.grd"
    p.write_bytes(surfer7_bytes)
    return p


@pytest.fixture
def ers_header_bytes():
    """Build a minimal ER Mapper .ers header."""
    text = """\
DatasetHeader Begin
    Version = 1.0
    DataType = Raster
    RasterInfo Begin
        NrOfCellsPerLine = 100
        NrOfLines = 200
        CellType = IEEE4ByteReal
    RasterInfo End
    CoordinateSpace Begin
        Datum = WGS84
        Projection = GEODETIC
    CoordinateSpace End
DatasetHeader End
"""
    return text.encode("ascii")


@pytest.fixture
def ers_file(tmp_dir, ers_header_bytes):
    p = tmp_dir / "raster.ers"
    p.write_bytes(ers_header_bytes)
    return p
