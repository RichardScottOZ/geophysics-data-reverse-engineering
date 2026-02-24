"""Tests for format parsers."""

import struct

import pytest

from geodatarev.parsers.surfer6 import Surfer6Parser
from geodatarev.parsers.surfer7 import Surfer7Parser
from geodatarev.parsers.ermapper import ERMapperParser, _parse_ers_header


class TestSurfer6Parser:
    def test_can_parse(self, surfer6_bytes):
        parser = Surfer6Parser()
        assert parser.can_parse(surfer6_bytes)

    def test_cannot_parse_wrong_magic(self):
        parser = Surfer6Parser()
        assert not parser.can_parse(b"\x00" * 100)

    def test_cannot_parse_short(self):
        parser = Surfer6Parser()
        assert not parser.can_parse(b"DSBB")

    def test_parse(self, surfer6_bytes):
        parser = Surfer6Parser()
        result = parser.parse(surfer6_bytes)
        assert result.format_name == "Surfer 6 Binary Grid"
        assert result.header["nx"] == 3
        assert result.header["ny"] == 2
        assert result.shape == (2, 3)
        assert len(result.data) == 6
        assert abs(result.data[0] - 0.1) < 1e-5
        assert not result.errors

    def test_parse_file(self, surfer6_file):
        parser = Surfer6Parser()
        result = parser.parse_file(surfer6_file)
        assert result.header["nx"] == 3
        assert len(result.data) == 6

    def test_parse_invalid_magic(self):
        parser = Surfer6Parser()
        result = parser.parse(b"\x00" * 100)
        assert result.errors

    def test_parse_truncated(self):
        header = b"DSBB" + struct.pack("<HH6d", 10, 10, 0, 1, 0, 1, 0, 1)
        # Only provide a few bytes of payload instead of 10*10*4 = 400
        result = Surfer6Parser().parse(header + b"\x00" * 8)
        assert any("truncated" in e.lower() or "Payload" in e for e in result.errors)


class TestSurfer7Parser:
    def test_can_parse(self, surfer7_bytes):
        parser = Surfer7Parser()
        assert parser.can_parse(surfer7_bytes)

    def test_cannot_parse_wrong_magic(self):
        parser = Surfer7Parser()
        assert not parser.can_parse(b"\x00" * 100)

    def test_parse(self, surfer7_bytes):
        parser = Surfer7Parser()
        result = parser.parse(surfer7_bytes)
        assert result.format_name == "Surfer 7 Binary Grid"
        assert result.header["nx"] == 2
        assert result.header["ny"] == 2
        assert result.shape == (2, 2)
        assert len(result.data) == 4
        assert abs(result.data[0] - 1.0) < 1e-10

    def test_parse_file(self, surfer7_file):
        parser = Surfer7Parser()
        result = parser.parse_file(surfer7_file)
        assert result.header["nx"] == 2


class TestERMapperParser:
    def test_can_parse(self, ers_header_bytes):
        parser = ERMapperParser()
        assert parser.can_parse(ers_header_bytes)

    def test_cannot_parse_binary(self):
        parser = ERMapperParser()
        assert not parser.can_parse(b"\x00\x01\x02\x03" * 64)

    def test_parse(self, ers_header_bytes):
        parser = ERMapperParser()
        result = parser.parse(ers_header_bytes)
        assert result.format_name == "ER Mapper"
        assert result.shape == (200, 100)
        assert result.metadata["datum"] == "WGS84"
        assert result.metadata["projection"] == "GEODETIC"

    def test_parse_file(self, ers_file):
        parser = ERMapperParser()
        result = parser.parse_file(ers_file)
        assert result.shape == (200, 100)


class TestERSHeaderParser:
    def test_parse_simple(self):
        text = """\
DatasetHeader Begin
    Version = 1.0
DatasetHeader End
"""
        result = _parse_ers_header(text)
        assert "DatasetHeader" in result
        assert result["DatasetHeader"]["Version"] == 1.0

    def test_nested_blocks(self):
        text = """\
Outer Begin
    Inner Begin
        Key = Value
    Inner End
Outer End
"""
        result = _parse_ers_header(text)
        assert result["Outer"]["Inner"]["Key"] == "Value"

    def test_numeric_conversion(self):
        text = """\
Block Begin
    IntVal = 42
    FloatVal = 3.14
    StrVal = hello
Block End
"""
        result = _parse_ers_header(text)
        assert result["Block"]["IntVal"] == 42
        assert abs(result["Block"]["FloatVal"] - 3.14) < 0.001
        assert result["Block"]["StrVal"] == "hello"
