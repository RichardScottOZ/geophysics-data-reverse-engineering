"""Tests for geodatarev.identifier."""

import struct

import pytest

from geodatarev.config import FormatConfig
from geodatarev.identifier import FileIdentifier


class TestFileIdentifier:
    def test_identify_surfer6_bytes(self):
        configs = [
            FormatConfig(name="Surfer 6", magic_bytes=b"DSBB", magic_offset=0),
            FormatConfig(name="Other", magic_bytes=b"XXXX", magic_offset=0),
        ]
        ident = FileIdentifier(configs)
        # Surfer 6 magic + dummy data
        data = b"DSBB" + b"\x00" * 100
        matches = ident.identify_bytes(data)
        assert len(matches) == 1
        assert matches[0].name == "Surfer 6"

    def test_no_match(self):
        configs = [
            FormatConfig(name="Surfer 6", magic_bytes=b"DSBB", magic_offset=0),
        ]
        ident = FileIdentifier(configs)
        data = b"\x00" * 100
        matches = ident.identify_bytes(data)
        assert len(matches) == 0

    def test_identify_with_offset(self):
        configs = [
            FormatConfig(name="Encom", magic_bytes=b"GRID", magic_offset=168),
        ]
        ident = FileIdentifier(configs)
        data = b"\x00" * 168 + b"GRID" + b"\x00" * 100
        matches = ident.identify_bytes(data)
        assert len(matches) == 1
        assert matches[0].name == "Encom"

    def test_identify_file(self, surfer6_file):
        ident = FileIdentifier()
        matches = ident.identify_file(surfer6_file)
        names = [m.name for m in matches]
        assert "Surfer 6 Binary Grid" in names

    def test_identify_by_extension(self, tmp_path):
        configs = [
            FormatConfig(name="GRD Format", extensions=[".grd"]),
        ]
        ident = FileIdentifier(configs)
        p = tmp_path / "test.grd"
        p.write_bytes(b"\x00" * 10)
        matches = ident.identify_by_extension(p)
        assert len(matches) == 1
        assert matches[0].name == "GRD Format"

    def test_multiple_matches_sorted_by_length(self):
        configs = [
            FormatConfig(name="Short", magic_bytes=b"DS", magic_offset=0),
            FormatConfig(name="Long", magic_bytes=b"DSBB", magic_offset=0),
        ]
        ident = FileIdentifier(configs)
        data = b"DSBB" + b"\x00" * 100
        matches = ident.identify_bytes(data)
        assert len(matches) == 2
        # Longest magic first
        assert matches[0].name == "Long"
