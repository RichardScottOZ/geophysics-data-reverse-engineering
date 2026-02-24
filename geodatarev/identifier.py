"""Magic number based file format identification.

Compares the leading bytes of binary files against a registry of known
format signatures to determine file type, independent of extension.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from geodatarev.config import FormatConfig, load_config


class FileIdentifier:
    """Identify binary files using magic number signatures.

    Parameters
    ----------
    configs : list[FormatConfig] or None
        Format definitions to match against.  When *None* the built-in
        defaults are loaded.
    """

    def __init__(self, configs: list[FormatConfig] | None = None):
        self.configs: list[FormatConfig] = configs if configs is not None else load_config()
        self._max_read = self._compute_max_read()

    def _compute_max_read(self) -> int:
        """Determine how many bytes we need to read for identification."""
        if not self.configs:
            return 512
        return max(
            (cfg.magic_offset + len(cfg.magic_bytes) for cfg in self.configs if cfg.magic_bytes),
            default=512,
        )

    def identify_bytes(self, data: bytes) -> list[FormatConfig]:
        """Identify format from raw bytes.

        Parameters
        ----------
        data : bytes
            Initial bytes of a file (at least :pyattr:`_max_read` bytes).

        Returns
        -------
        list[FormatConfig]
            All matching format configs, ordered by match specificity
            (longest magic bytes first).
        """
        matches: list[FormatConfig] = []
        for cfg in self.configs:
            if not cfg.magic_bytes:
                continue
            start = cfg.magic_offset
            end = start + len(cfg.magic_bytes)
            if end <= len(data) and data[start:end] == cfg.magic_bytes:
                matches.append(cfg)
        matches.sort(key=lambda c: len(c.magic_bytes), reverse=True)
        return matches

    def identify_file(self, path: str | Path) -> list[FormatConfig]:
        """Identify format of a file on disk.

        Parameters
        ----------
        path : str or Path
            Path to the binary file.

        Returns
        -------
        list[FormatConfig]
            Matching format configs.
        """
        path = Path(path)
        read_size = max(self._max_read, 512)
        with open(path, "rb") as fh:
            data = fh.read(read_size)
        return self.identify_bytes(data)

    def identify_by_extension(self, path: str | Path) -> list[FormatConfig]:
        """Return configs whose extension list matches the file suffix.

        Parameters
        ----------
        path : str or Path
            File path to check.

        Returns
        -------
        list[FormatConfig]
            Configs with a matching extension.
        """
        ext = Path(path).suffix.lower()
        return [cfg for cfg in self.configs if ext in cfg.extensions]
