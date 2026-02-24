"""Tests for geodatarev.config."""

from pathlib import Path

import pytest

from geodatarev.config import (
    FormatConfig,
    FieldDefinition,
    load_config,
    _parse_magic_bytes,
)


class TestParseMagicBytes:
    def test_hex_string(self):
        assert _parse_magic_bytes("44 53 42 42") == b"DSBB"

    def test_hex_string_no_spaces(self):
        assert _parse_magic_bytes("44534242") == b"DSBB"

    def test_list_of_ints(self):
        assert _parse_magic_bytes([0x44, 0x53, 0x42, 0x42]) == b"DSBB"

    def test_none(self):
        assert _parse_magic_bytes(None) == b""


class TestFieldDefinition:
    def test_bit_width(self):
        f = FieldDefinition(name="x", offset=0, size=4, dtype="float32")
        assert f.bit_width == 32

    def test_bit_width_8(self):
        f = FieldDefinition(name="x", offset=0, size=1, dtype="uint8")
        assert f.bit_width == 8


class TestFormatConfig:
    def test_data_bit_width_float32(self):
        cfg = FormatConfig(name="test", data_dtype="float32")
        assert cfg.data_bit_width == 32

    def test_data_bit_width_float64(self):
        cfg = FormatConfig(name="test", data_dtype="float64")
        assert cfg.data_bit_width == 64

    def test_data_bit_width_uint16(self):
        cfg = FormatConfig(name="test", data_dtype="uint16")
        assert cfg.data_bit_width == 16

    def test_data_bit_width_uint8(self):
        cfg = FormatConfig(name="test", data_dtype="uint8")
        assert cfg.data_bit_width == 8

    def test_data_bit_width_vax_f(self):
        cfg = FormatConfig(name="test", data_dtype="vax_f")
        assert cfg.data_bit_width == 32

    def test_data_bit_width_ibm_float64(self):
        cfg = FormatConfig(name="test", data_dtype="ibm_float64")
        assert cfg.data_bit_width == 64


class TestLoadConfig:
    def test_default_config_loads(self):
        configs = load_config()
        assert len(configs) > 0
        names = [c.name for c in configs]
        assert "Surfer 6 Binary Grid" in names

    def test_default_config_has_fields(self):
        configs = load_config()
        s6 = [c for c in configs if c.name == "Surfer 6 Binary Grid"][0]
        assert len(s6.fields) > 0
        assert s6.magic_bytes == b"DSBB"
        assert s6.header_size == 56
        assert s6.data_dtype == "float32"

    def test_custom_config(self, tmp_path):
        yaml_content = """\
formats:
  - name: "Test Format"
    extensions: [".tst"]
    magic_bytes: "AA BB"
    magic_offset: 0
    endian: big
    header_size: 16
    data_dtype: uint16
    fields:
      - name: magic
        offset: 0
        size: 2
        dtype: bytes
"""
        p = tmp_path / "test.yaml"
        p.write_text(yaml_content)
        configs = load_config(p)
        assert len(configs) == 1
        assert configs[0].name == "Test Format"
        assert configs[0].magic_bytes == b"\xaa\xbb"
        assert configs[0].data_bit_width == 16
