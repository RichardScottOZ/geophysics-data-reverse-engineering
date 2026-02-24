"""Tests for geodatarev.gdal_compat."""

import json
import struct
from unittest import mock

import pytest

from geodatarev.gdal_compat import (
    DEPRECATED_FORMAT_GDAL_VERSIONS,
    EXTENSION_DRIVER_MAP,
    GDAL_DRIVER_MAP,
    GDALCheckResult,
    check_gdal_available,
    get_old_gdal_strategy,
    try_gdal_open,
)


class TestCheckGdalAvailable:
    def test_returns_dict(self):
        result = check_gdal_available()
        assert isinstance(result, dict)
        assert "available" in result
        assert "version" in result
        assert "error" in result

    def test_unavailable_when_no_osgeo(self):
        with mock.patch.dict("sys.modules", {"osgeo": None, "osgeo.gdal": None}):
            result = check_gdal_available()
            assert result["available"] is False
            assert result["error"] is not None


class TestTryGdalOpen:
    def test_missing_file(self, tmp_path):
        result = try_gdal_open(tmp_path / "nonexistent.tif")
        assert result.can_read is False
        assert "not found" in result.error.lower()

    def test_no_gdal_returns_error(self, tmp_path):
        p = tmp_path / "test.bin"
        p.write_bytes(b"\x00" * 100)
        with mock.patch.dict("sys.modules", {"osgeo": None, "osgeo.gdal": None}):
            result = try_gdal_open(p)
            assert result.can_read is False
            assert "not installed" in result.error.lower()

    def test_result_dataclass_fields(self):
        r = GDALCheckResult()
        assert r.can_read is False
        assert r.driver_short_name == ""
        assert r.band_count == 0
        assert r.band_dtypes == []


class TestGdalDriverMap:
    def test_surfer6_mapped(self):
        assert "Surfer 6 Binary Grid" in GDAL_DRIVER_MAP

    def test_tiff_mapped(self):
        assert GDAL_DRIVER_MAP["TIFF (Big-Endian)"] == "GTiff"
        assert GDAL_DRIVER_MAP["TIFF (Little-Endian)"] == "GTiff"

    def test_extension_map(self):
        assert ".tif" in EXTENSION_DRIVER_MAP
        assert ".ers" in EXTENSION_DRIVER_MAP
        assert "GTiff" in EXTENSION_DRIVER_MAP[".tif"]


class TestDeprecatedFormats:
    def test_has_entries(self):
        assert len(DEPRECATED_FORMAT_GDAL_VERSIONS) > 0

    def test_entry_structure(self):
        for key, info in DEPRECATED_FORMAT_GDAL_VERSIONS.items():
            assert info.driver_name
            assert info.description
            assert info.last_supported_version

    def test_fit_driver(self):
        fit = DEPRECATED_FORMAT_GDAL_VERSIONS["FIT"]
        assert fit.driver_name == "FIT"
        assert fit.removal_version == "3.5"


class TestGetOldGdalStrategy:
    def test_returns_dict(self):
        strategy = get_old_gdal_strategy()
        assert "approaches" in strategy
        assert "deprecated_formats" in strategy
        assert "notes" in strategy

    def test_approaches_present(self):
        strategy = get_old_gdal_strategy()
        methods = [a["method"] for a in strategy["approaches"]]
        assert "conda_version_pin" in methods
        assert "docker_osgeo" in methods
        assert "pip_version_pin" in methods
        assert "compile_from_source" in methods

    def test_approach_has_commands(self):
        strategy = get_old_gdal_strategy()
        for approach in strategy["approaches"]:
            assert "commands" in approach
            assert len(approach["commands"]) > 0

    def test_deprecated_formats_serialisable(self):
        strategy = get_old_gdal_strategy()
        # Should be JSON-serialisable
        json.dumps(strategy)

    def test_notes_not_empty(self):
        strategy = get_old_gdal_strategy()
        assert len(strategy["notes"]) > 0


class TestGdalCheckCLI:
    def test_gdal_strategy_command(self, capsys):
        from geodatarev.cli import main
        ret = main(["gdal-strategy"])
        assert ret == 0
        out = capsys.readouterr().out
        assert "conda" in out.lower()
        assert "docker" in out.lower()
        assert "deprecated" in out.lower()
