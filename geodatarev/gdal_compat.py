"""GDAL compatibility checking for binary geophysics data files.

Provides utilities to check whether GDAL can read a given file, maps
known format signatures to GDAL driver names, and documents a strategy
for obtaining old GDAL builds that still support deprecated format
drivers.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# GDAL driver mapping
# ---------------------------------------------------------------------------

#: Maps internal format config names to GDAL short driver names.
GDAL_DRIVER_MAP: dict[str, str] = {
    "Surfer 6 Binary Grid": "GS7BG",
    "Surfer 7 Binary Grid": "GS7BG",
    "ER Mapper Header": "ERS",
    "Encom ModelVision Grid": "",  # No native GDAL driver
    "ESRI ArcInfo Binary Grid": "AIG",
    "TIFF (Big-Endian)": "GTiff",
    "TIFF (Little-Endian)": "GTiff",
    "SEG-Y Rev 0": "",  # No native GDAL driver (seismic, not raster)
    "Geosoft Binary Grid": "GSBG",
}

#: Mapping of file extensions to likely GDAL driver names for quick lookup.
EXTENSION_DRIVER_MAP: dict[str, list[str]] = {
    ".grd": ["GS7BG", "GSBG"],
    ".ers": ["ERS"],
    ".adf": ["AIG"],
    ".tif": ["GTiff"],
    ".tiff": ["GTiff"],
    ".img": ["HFA"],
    ".bil": ["EHdr"],
    ".bsq": ["EHdr"],
    ".bip": ["EHdr"],
    ".nc": ["netCDF"],
    ".hdf": ["HDF4", "HDF5"],
    ".hdf5": ["HDF5"],
    ".h5": ["HDF5"],
    ".e00": ["AVCE00"],
    ".ecw": ["ECW"],
    ".sid": ["MrSID"],
    ".dt0": ["DTED"],
    ".dt1": ["DTED"],
    ".dt2": ["DTED"],
}


# ---------------------------------------------------------------------------
# Deprecated format driver history
# ---------------------------------------------------------------------------

@dataclass
class DeprecatedDriverInfo:
    """Information about a GDAL driver that has been deprecated or removed."""

    driver_name: str
    description: str
    last_supported_version: str
    removal_version: str = ""
    alternatives: list[str] = field(default_factory=list)
    notes: str = ""


#: Formats whose GDAL drivers have been deprecated or removed over time.
#: Use :func:`get_old_gdal_strategy` to get guidance on reading these.
DEPRECATED_FORMAT_GDAL_VERSIONS: dict[str, DeprecatedDriverInfo] = {
    "PCIDSK_OLD": DeprecatedDriverInfo(
        driver_name="PCIDSK",
        description="Old-style PCI Geomatics PCIDSK database format",
        last_supported_version="3.5",
        notes="The PCIDSK driver was rewritten; very old files may need the legacy SDK.",
    ),
    "FIT": DeprecatedDriverInfo(
        driver_name="FIT",
        description="FIT raster format",
        last_supported_version="3.4",
        removal_version="3.5",
        notes="Removed in GDAL 3.5. Use GDAL <= 3.4 to read these files.",
    ),
    "E00GRID": DeprecatedDriverInfo(
        driver_name="E00GRID",
        description="Arc/Info Export E00 GRID format",
        last_supported_version="3.2",
        removal_version="3.3",
        alternatives=["AIG"],
        notes="Removed in GDAL 3.3. Convert to AIG or use GDAL <= 3.2.",
    ),
    "GRASS_RASTER": DeprecatedDriverInfo(
        driver_name="GRASS",
        description="GRASS GIS raster format",
        last_supported_version="2.4",
        removal_version="3.0",
        alternatives=["GTiff"],
        notes="GRASS raster driver removed in GDAL 3.0. Export via GRASS tools.",
    ),
    "IDA": DeprecatedDriverInfo(
        driver_name="IDA",
        description="Image Display and Analysis (IDA) format",
        last_supported_version="3.4",
        removal_version="3.5",
        notes="Removed in GDAL 3.5. Use GDAL <= 3.4 to read these files.",
    ),
}


# ---------------------------------------------------------------------------
# GDAL availability check
# ---------------------------------------------------------------------------

def check_gdal_available() -> dict[str, Any]:
    """Check whether the GDAL Python bindings (``osgeo``) are installed.

    Returns
    -------
    dict
        ``{"available": bool, "version": str | None, "error": str | None}``
    """
    try:
        osgeo_gdal = importlib.import_module("osgeo.gdal")
        version = getattr(osgeo_gdal, "__version__", None)
        if version is None:
            version = getattr(osgeo_gdal, "VersionInfo", lambda _: "unknown")("RELEASE_NAME")
        return {"available": True, "version": str(version), "error": None}
    except ImportError:
        return {"available": False, "version": None,
                "error": "GDAL Python bindings (osgeo) are not installed"}
    except Exception as exc:  # pragma: no cover
        return {"available": False, "version": None, "error": str(exc)}


@dataclass
class GDALCheckResult:
    """Result of attempting to open a file with GDAL."""

    can_read: bool = False
    driver_short_name: str = ""
    driver_long_name: str = ""
    gdal_version: str = ""
    raster_size: tuple[int, int] | None = None
    band_count: int = 0
    band_dtypes: list[str] = field(default_factory=list)
    projection: str = ""
    geotransform: tuple[float, ...] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    error: str = ""


def try_gdal_open(path: str | Path) -> GDALCheckResult:
    """Attempt to open a file with GDAL and return driver/metadata info.

    This is the primary "can GDAL read it?" function.  If GDAL is not
    installed the result's ``error`` field explains the situation.

    Parameters
    ----------
    path : str or Path
        Path to the file to test.

    Returns
    -------
    GDALCheckResult
    """
    result = GDALCheckResult()
    path = Path(path)

    if not path.is_file():
        result.error = f"File not found: {path}"
        return result

    try:
        osgeo_gdal = importlib.import_module("osgeo.gdal")
    except ImportError:
        result.error = "GDAL Python bindings (osgeo) are not installed"
        return result

    # Suppress GDAL error messages during probing
    osgeo_gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        ds = osgeo_gdal.Open(str(path))
        if ds is None:
            result.error = "GDAL could not open the file"
            return result

        result.can_read = True
        drv = ds.GetDriver()
        result.driver_short_name = drv.ShortName
        result.driver_long_name = drv.LongName
        version = getattr(osgeo_gdal, "__version__", None)
        if version is None:
            version = osgeo_gdal.VersionInfo("RELEASE_NAME")
        result.gdal_version = str(version)
        result.raster_size = (ds.RasterXSize, ds.RasterYSize)
        result.band_count = ds.RasterCount

        for i in range(1, ds.RasterCount + 1):
            band = ds.GetRasterBand(i)
            result.band_dtypes.append(
                osgeo_gdal.GetDataTypeName(band.DataType)
            )

        result.projection = ds.GetProjection() or ""
        gt = ds.GetGeoTransform()
        if gt:
            result.geotransform = tuple(gt)

        md = ds.GetMetadata() or {}
        result.metadata = dict(md)

        ds = None  # close
    except Exception as exc:
        result.error = str(exc)
    finally:
        osgeo_gdal.PopErrorHandler()

    return result


# ---------------------------------------------------------------------------
# Old GDAL build strategy
# ---------------------------------------------------------------------------

def get_old_gdal_strategy() -> dict[str, Any]:
    """Return a strategy guide for obtaining old GDAL builds.

    Legacy geophysics files sometimes rely on format drivers that have
    been deprecated or removed from modern GDAL releases.  This function
    documents practical approaches for accessing those older drivers.

    Returns
    -------
    dict
        A structured guide with keys ``"approaches"`` (list of dicts,
        each with ``"method"``, ``"description"``, ``"commands"``),
        ``"deprecated_formats"`` (the :data:`DEPRECATED_FORMAT_GDAL_VERSIONS`
        mapping), and ``"notes"`` (general advice).
    """
    approaches: list[dict[str, Any]] = [
        {
            "method": "conda_version_pin",
            "description": (
                "Create an isolated conda environment with a specific "
                "GDAL version pinned.  This is the easiest cross-platform "
                "approach."
            ),
            "commands": [
                "conda create -n gdal_old -c conda-forge gdal=3.4 python=3.9",
                "conda activate gdal_old",
            ],
        },
        {
            "method": "docker_osgeo",
            "description": (
                "Use an official OSGeo Docker image tagged with the "
                "required GDAL version.  Useful for CI pipelines and "
                "reproducible batch processing."
            ),
            "commands": [
                "docker pull ghcr.io/osgeo/gdal:ubuntu-small-3.4.3",
                "docker run --rm -v /data:/data ghcr.io/osgeo/gdal:ubuntu-small-3.4.3 "
                "gdalinfo /data/legacy.e00",
            ],
        },
        {
            "method": "pip_version_pin",
            "description": (
                "Install an older GDAL wheel via pip inside a virtual "
                "environment.  Requires a matching system GDAL library "
                "on Linux; pre-built wheels are available on some "
                "platforms."
            ),
            "commands": [
                "python -m venv gdal_old_env",
                "gdal_old_env/bin/pip install GDAL==3.4.3",
            ],
        },
        {
            "method": "compile_from_source",
            "description": (
                "Build GDAL from a release tarball or git tag when "
                "binary packages are not available.  Most control, "
                "but the most effort."
            ),
            "commands": [
                "git clone --branch v3.4.3 --depth 1 https://github.com/OSGeo/gdal.git",
                "cd gdal && mkdir build && cd build && cmake .. && make -j$(nproc)",
            ],
        },
    ]

    notes = (
        "When working with legacy geophysics data, always try opening "
        "the file with your current GDAL installation first "
        "(use try_gdal_open or 'geodatarev gdal-check <file>').  "
        "If GDAL cannot read it, check the deprecated formats list "
        "to identify which older version may still support the driver.  "
        "Pinning an old GDAL version in an isolated environment is "
        "generally the fastest path.  For formats that GDAL never "
        "supported (e.g. Encom ModelVision grids, SEG-Y seismic), "
        "this library's built-in parsers and reverse-engineering "
        "tools are the recommended approach."
    )

    return {
        "approaches": approaches,
        "deprecated_formats": {
            k: {
                "driver": v.driver_name,
                "description": v.description,
                "last_supported": v.last_supported_version,
                "removal_version": v.removal_version,
                "alternatives": v.alternatives,
                "notes": v.notes,
            }
            for k, v in DEPRECATED_FORMAT_GDAL_VERSIONS.items()
        },
        "notes": notes,
    }
