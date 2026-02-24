"""Directory scanner for batch binary file analysis.

Recursively walks data folders, identifies files by magic numbers and
extensions, runs binary analysis, and optionally applies format-specific
parsers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geodatarev.analyzer import AnalysisResult, BinaryAnalyzer
from geodatarev.config import FormatConfig, load_config
from geodatarev.identifier import FileIdentifier
from geodatarev.parsers import BaseParser, ParseResult
from geodatarev.parsers.surfer6 import Surfer6Parser
from geodatarev.parsers.surfer7 import Surfer7Parser
from geodatarev.parsers.ermapper import ERMapperParser


@dataclass
class FileReport:
    """Analysis report for a single file."""

    path: str
    size: int = 0
    identified_formats: list[str] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    parse_result: ParseResult | None = None
    errors: list[str] = field(default_factory=list)


# Built-in parser registry
_BUILTIN_PARSERS: list[BaseParser] = [
    Surfer6Parser(),
    Surfer7Parser(),
    ERMapperParser(),
]


class DirectoryScanner:
    """Scan directories for binary data files and analyse them.

    Parameters
    ----------
    configs : list[FormatConfig] or None
        Format definitions.  Defaults to built-in formats.
    parsers : list[BaseParser] or None
        Additional parsers beyond the built-ins.
    extensions : set[str] or None
        Restrict scanning to these file extensions (e.g. ``{".grd", ".ers"}``).
        When *None* all files are considered.
    max_sample : int
        Maximum bytes to read per file for analysis.
    """

    def __init__(
        self,
        configs: list[FormatConfig] | None = None,
        parsers: list[BaseParser] | None = None,
        extensions: set[str] | None = None,
        max_sample: int = 1_048_576,
    ):
        self.configs = configs if configs is not None else load_config()
        self.identifier = FileIdentifier(self.configs)
        self.analyzer = BinaryAnalyzer(max_sample=max_sample)
        self.parsers: list[BaseParser] = list(_BUILTIN_PARSERS)
        if parsers:
            self.parsers.extend(parsers)
        self.extensions = extensions

    def scan_file(self, path: str | Path) -> FileReport:
        """Analyse a single file.

        Parameters
        ----------
        path : str or Path
            File to analyse.

        Returns
        -------
        FileReport
        """
        path = Path(path)
        report = FileReport(path=str(path))

        if not path.is_file():
            report.errors.append("Not a file")
            return report

        report.size = path.stat().st_size
        if report.size == 0:
            report.errors.append("Empty file")
            return report

        # Identify
        try:
            matches = self.identifier.identify_file(path)
            report.identified_formats = [m.name for m in matches]
        except Exception as exc:
            report.errors.append(f"Identification error: {exc}")

        # Analyse
        try:
            report.analysis = self.analyzer.analyze_file(path)
        except Exception as exc:
            report.errors.append(f"Analysis error: {exc}")

        # Parse with first matching parser
        try:
            with open(path, "rb") as fh:
                head = fh.read(self.analyzer.max_sample)
            for parser in self.parsers:
                if parser.can_parse(head):
                    report.parse_result = parser.parse_file(path)
                    break
        except Exception as exc:
            report.errors.append(f"Parse error: {exc}")

        return report

    def scan_directory(self, root: str | Path, recursive: bool = True) -> list[FileReport]:
        """Scan a directory tree for binary data files.

        Parameters
        ----------
        root : str or Path
            Root directory to scan.
        recursive : bool
            Whether to recurse into subdirectories.

        Returns
        -------
        list[FileReport]
            Reports for every file examined.
        """
        root = Path(root)
        reports: list[FileReport] = []

        if not root.is_dir():
            return reports

        iterator = root.rglob("*") if recursive else root.glob("*")

        for entry in sorted(iterator):
            if not entry.is_file():
                continue
            if self.extensions is not None:
                if entry.suffix.lower() not in self.extensions:
                    continue
            reports.append(self.scan_file(entry))

        return reports
