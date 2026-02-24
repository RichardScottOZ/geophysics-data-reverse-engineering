"""Configuration system for binary format definitions.

Loads YAML-based format definitions that describe magic numbers,
header structures, data types, and endianness for legacy binary formats.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class FieldDefinition:
    """A single field within a binary header or record."""

    name: str
    offset: int
    size: int
    dtype: str  # e.g. "uint16", "int32", "float32", "float64", "ascii", "bytes"
    description: str = ""

    @property
    def bit_width(self) -> int:
        """Return the bit width of this field."""
        return self.size * 8


@dataclass
class FormatConfig:
    """Complete definition of a binary file format."""

    name: str
    extensions: list[str] = field(default_factory=list)
    magic_bytes: bytes = b""
    magic_offset: int = 0
    endian: str = "little"  # "little", "big", or "middle" (PDP-11/VAX)
    header_size: int = 0
    fields: list[FieldDefinition] = field(default_factory=list)
    data_dtype: str = "float32"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def data_bit_width(self) -> int:
        """Return the bit width of the data payload type."""
        dtype_sizes = {
            "uint8": 8, "int8": 8,
            "uint16": 16, "int16": 16,
            "uint32": 32, "int32": 32,
            "uint64": 64, "int64": 64,
            "float32": 32, "float64": 64,
            "vax_f": 32, "ibm_float32": 32,
            "vax_d": 64, "vax_g": 64, "ibm_float64": 64,
        }
        return dtype_sizes.get(self.data_dtype, 0)


def _parse_magic_bytes(value: str | list | None) -> bytes:
    """Parse magic bytes from a config value.

    Accepts hex string like ``"44 53 42 42"`` or a list of ints.
    """
    if value is None:
        return b""
    if isinstance(value, list):
        return bytes(value)
    if isinstance(value, str):
        return bytes.fromhex(value.replace(" ", ""))
    return b""


def _parse_field(data: dict) -> FieldDefinition:
    """Build a :class:`FieldDefinition` from a dictionary."""
    return FieldDefinition(
        name=data["name"],
        offset=data["offset"],
        size=data["size"],
        dtype=data.get("dtype", "bytes"),
        description=data.get("description", ""),
    )


def _parse_format(data: dict) -> FormatConfig:
    """Build a :class:`FormatConfig` from a dictionary."""
    fields = [_parse_field(f) for f in data.get("fields", [])]
    return FormatConfig(
        name=data["name"],
        extensions=data.get("extensions", []),
        magic_bytes=_parse_magic_bytes(data.get("magic_bytes")),
        magic_offset=data.get("magic_offset", 0),
        endian=data.get("endian", "little"),
        header_size=data.get("header_size", 0),
        fields=fields,
        data_dtype=data.get("data_dtype", "float32"),
        description=data.get("description", ""),
        metadata=data.get("metadata", {}),
    )


def load_config(path: str | Path | None = None) -> list[FormatConfig]:
    """Load format configurations from a YAML file.

    Parameters
    ----------
    path : str or Path, optional
        Path to a YAML configuration file.  When *None* the built-in
        ``default_formats.yaml`` shipped with the package is used.

    Returns
    -------
    list[FormatConfig]
        Parsed format definitions.
    """
    if path is None:
        path = Path(__file__).parent / "configs" / "default_formats.yaml"
    else:
        path = Path(path)

    with open(path, "r") as fh:
        data = yaml.safe_load(fh)

    formats = data.get("formats", [])
    return [_parse_format(f) for f in formats]
