"""Tests for geodatarev.scanner."""

import struct
from pathlib import Path

import pytest

from geodatarev.scanner import DirectoryScanner, FileReport


class TestDirectoryScanner:
    def test_scan_file(self, surfer6_file):
        scanner = DirectoryScanner()
        report = scanner.scan_file(surfer6_file)
        assert report.size > 0
        assert "Surfer 6 Binary Grid" in report.identified_formats
        assert report.analysis is not None
        assert report.parse_result is not None
        assert report.parse_result.header["nx"] == 3

    def test_scan_nonexistent(self, tmp_path):
        scanner = DirectoryScanner()
        report = scanner.scan_file(tmp_path / "nope.bin")
        assert report.errors

    def test_scan_empty_file(self, tmp_path):
        empty = tmp_path / "empty.bin"
        empty.write_bytes(b"")
        scanner = DirectoryScanner()
        report = scanner.scan_file(empty)
        assert "Empty file" in report.errors

    def test_scan_directory(self, tmp_path, surfer6_bytes):
        # Write a few files
        (tmp_path / "a.grd").write_bytes(surfer6_bytes)
        (tmp_path / "b.bin").write_bytes(b"\x00" * 100)
        scanner = DirectoryScanner()
        reports = scanner.scan_directory(tmp_path)
        assert len(reports) == 2

    def test_scan_directory_with_extension_filter(self, tmp_path, surfer6_bytes):
        (tmp_path / "a.grd").write_bytes(surfer6_bytes)
        (tmp_path / "b.bin").write_bytes(b"\x00" * 100)
        scanner = DirectoryScanner(extensions={".grd"})
        reports = scanner.scan_directory(tmp_path)
        assert len(reports) == 1
        assert reports[0].path.endswith(".grd")

    def test_scan_directory_recursive(self, tmp_path, surfer6_bytes):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.grd").write_bytes(surfer6_bytes)
        scanner = DirectoryScanner()
        reports = scanner.scan_directory(tmp_path, recursive=True)
        paths = [r.path for r in reports]
        assert any("deep.grd" in p for p in paths)

    def test_scan_directory_nonrecursive(self, tmp_path, surfer6_bytes):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.grd").write_bytes(surfer6_bytes)
        (tmp_path / "top.grd").write_bytes(surfer6_bytes)
        scanner = DirectoryScanner()
        reports = scanner.scan_directory(tmp_path, recursive=False)
        paths = [r.path for r in reports]
        assert any("top.grd" in p for p in paths)
        assert not any("deep.grd" in p for p in paths)
