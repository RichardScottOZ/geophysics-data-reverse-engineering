"""Tests for geodatarev.cli."""

import json

import pytest

from geodatarev.cli import main


class TestCLI:
    def test_help_returns_zero(self):
        assert main([]) == 0

    def test_scan_file(self, surfer6_file, capsys):
        ret = main(["scan", str(surfer6_file)])
        assert ret == 0
        out = capsys.readouterr().out
        assert "Surfer 6" in out

    def test_scan_json(self, surfer6_file, capsys):
        ret = main(["scan", str(surfer6_file), "--json"])
        assert ret == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == 1
        assert data[0]["identified_formats"] == ["Surfer 6 Binary Grid"]

    def test_scan_directory(self, tmp_path, surfer6_bytes, capsys):
        (tmp_path / "a.grd").write_bytes(surfer6_bytes)
        ret = main(["scan", str(tmp_path)])
        assert ret == 0

    def test_scan_invalid_path(self, capsys):
        ret = main(["scan", "/nonexistent/path"])
        assert ret == 1

    def test_identify(self, surfer6_file, capsys):
        ret = main(["identify", str(surfer6_file)])
        assert ret == 0
        out = capsys.readouterr().out
        assert "Surfer 6" in out

    def test_identify_unknown(self, tmp_path, capsys):
        p = tmp_path / "unknown.bin"
        p.write_bytes(b"\xFF" * 100)
        ret = main(["identify", str(p)])
        assert ret == 0
        out = capsys.readouterr().out
        assert "Unknown" in out

    def test_analyze(self, surfer6_file, capsys):
        ret = main(["analyze", str(surfer6_file)])
        assert ret == 0
        out = capsys.readouterr().out
        assert "entropy" in out.lower()
        assert "bit-width" in out.lower()

    def test_analyze_json(self, surfer6_file, capsys):
        ret = main(["analyze", str(surfer6_file), "--json"])
        assert ret == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "entropy" in data
        assert "bit_width_scores" in data
