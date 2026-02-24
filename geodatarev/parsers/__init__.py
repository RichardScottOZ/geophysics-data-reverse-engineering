"""Base class for binary format parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geodatarev.config import FormatConfig
from geodatarev.float_formats import decode_value


@dataclass
class ParseResult:
    """Result of parsing a binary file."""

    format_name: str = ""
    header: dict[str, Any] = field(default_factory=dict)
    data: list = field(default_factory=list)
    shape: tuple[int, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class BaseParser:
    """Base class for format-specific parsers.

    Subclasses should override :meth:`parse` and :meth:`can_parse`.
    """

    name: str = "base"

    def can_parse(self, data: bytes, config: FormatConfig | None = None) -> bool:
        """Return True if this parser can handle the given data."""
        return False

    def parse(self, data: bytes, config: FormatConfig | None = None) -> ParseResult:
        """Parse binary data and return structured result."""
        raise NotImplementedError

    def parse_file(self, path: str | Path, config: FormatConfig | None = None) -> ParseResult:
        """Parse a file from disk."""
        with open(Path(path), "rb") as fh:
            data = fh.read()
        return self.parse(data, config)

    # ------------------------------------------------------------------
    # Helper utilities for subclasses
    # ------------------------------------------------------------------

    @staticmethod
    def _read_field(data: bytes, offset: int, size: int, dtype: str,
                    endian: str = "little") -> Any:
        """Read a single typed field from *data* at *offset*."""
        chunk = data[offset:offset + size]
        if dtype == "ascii":
            return chunk.decode("ascii", errors="replace").rstrip("\x00")
        if dtype == "bytes":
            return chunk
        return decode_value(chunk, dtype, endian)
