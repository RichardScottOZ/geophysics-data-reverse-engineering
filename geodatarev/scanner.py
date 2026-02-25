"""Directory scanner for batch binary file analysis.

Recursively walks data folders, identifies files by magic numbers and
extensions, runs binary analysis, and optionally applies format-specific
parsers.  Cloud object stores (AWS S3 and Azure Blob Storage) are also
supported via ``s3://`` and ``az://`` URIs.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from geodatarev.analyzer import AnalysisResult, BinaryAnalyzer
from geodatarev.cloud_storage import (
    CloudStorageProvider,
    is_cloud_uri,
    parse_cloud_uri,
    get_provider,
)
from geodatarev.config import FormatConfig, load_config
from geodatarev.disambiguate import classify_dat, classify_grd
from geodatarev.gdal_compat import GDALCheckResult, try_gdal_open
from geodatarev.identifier import FileIdentifier
from geodatarev.parsers import BaseParser, ParseResult
from geodatarev.parsers.surfer6 import Surfer6Parser
from geodatarev.parsers.surfer7 import Surfer7Parser
from geodatarev.parsers.ermapper import ERMapperParser
from geodatarev.parsers.geosoft import GeosoftParser
from geodatarev.parsers.encom import EncomParser
from geodatarev.parsers.zmap import ZMapParser


@dataclass
class FileReport:
    """Analysis report for a single file."""

    path: str
    size: int = 0
    identified_formats: list[str] = field(default_factory=list)
    analysis: AnalysisResult | None = None
    parse_result: ParseResult | None = None
    gdal_result: GDALCheckResult | None = None
    errors: list[str] = field(default_factory=list)


# Built-in parser registry
_BUILTIN_PARSERS: list[BaseParser] = [
    Surfer6Parser(),
    Surfer7Parser(),
    ERMapperParser(),
    EncomParser(),
    GeosoftParser(),
    ZMapParser(),
]


class DirectoryScanner:
    """Scan directories for binary data files and analyse them.

    Supports local directories as well as cloud object stores via
    ``s3://bucket/prefix`` and ``az://container/prefix`` URIs.

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
    cloud_provider : CloudStorageProvider or None
        A pre-configured cloud storage provider.  When *None*, one is
        created automatically from the URI scheme when a cloud path is
        scanned.
    """

    def __init__(
        self,
        configs: list[FormatConfig] | None = None,
        parsers: list[BaseParser] | None = None,
        extensions: set[str] | None = None,
        max_sample: int = 1_048_576,
        check_gdal: bool = False,
        cloud_provider: CloudStorageProvider | None = None,
    ):
        self.configs = configs if configs is not None else load_config()
        self.identifier = FileIdentifier(self.configs)
        self.analyzer = BinaryAnalyzer(max_sample=max_sample)
        self.parsers: list[BaseParser] = list(_BUILTIN_PARSERS)
        if parsers:
            self.parsers.extend(parsers)
        self.extensions = extensions
        self.check_gdal = check_gdal
        self.cloud_provider = cloud_provider

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

        # Disambiguate overloaded extensions when magic-byte ID is inconclusive
        if not report.identified_formats:
            try:
                with open(path, "rb") as fh:
                    sample = fh.read(min(report.size, 8192))
                ext = path.suffix.lower()
                if ext == ".dat":
                    report.identified_formats = [classify_dat(sample, path)]
                elif ext == ".grd":
                    report.identified_formats = [classify_grd(sample, path)]
            except Exception as exc:
                report.errors.append(f"Disambiguation error: {exc}")

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

        # GDAL compatibility check
        if self.check_gdal:
            try:
                report.gdal_result = try_gdal_open(path)
            except Exception as exc:
                report.errors.append(f"GDAL check error: {exc}")

        return report

    def scan_directory(self, root: str | Path, recursive: bool = True) -> list[FileReport]:
        """Scan a directory tree for binary data files.

        *root* may be a local path **or** a cloud URI (``s3://…`` /
        ``az://…``).  When a cloud URI is given the objects are
        downloaded to a temporary directory, analysed, and the
        temporary files are cleaned up afterwards.

        Parameters
        ----------
        root : str or Path
            Root directory or cloud URI to scan.
        recursive : bool
            Whether to recurse into subdirectories.

        Returns
        -------
        list[FileReport]
            Reports for every file examined.
        """
        if isinstance(root, str) and is_cloud_uri(root):
            return self.scan_cloud(root, recursive=recursive)

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

    def scan_cloud(self, uri: str, recursive: bool = True) -> list[FileReport]:
        """Scan a cloud storage location for binary data files.

        Objects are downloaded to a temporary directory one at a time,
        analysed, and then cleaned up.  The ``path`` field of each
        :class:`FileReport` records the original cloud key.

        Parameters
        ----------
        uri : str
            Cloud URI, e.g. ``s3://my-bucket/surveys/`` or
            ``az://my-container/data/``.
        recursive : bool
            Whether to list objects recursively.

        Returns
        -------
        list[FileReport]
        """
        scheme, bucket, prefix = parse_cloud_uri(uri)
        provider = self.cloud_provider or get_provider(scheme)

        objects = provider.list_objects(
            bucket, prefix, recursive=recursive, extensions=self.extensions
        )

        reports: list[FileReport] = []
        for obj in objects:
            cloud_path = f"{scheme}://{bucket}/{obj.key}"
            report = FileReport(path=cloud_path)
            report.size = obj.size

            if report.size == 0:
                report.errors.append("Empty file")
                reports.append(report)
                continue

            try:
                with tempfile.TemporaryDirectory() as td:
                    local = provider.download(bucket, obj.key, Path(td) / obj.name)
                    inner = self.scan_file(local)

                # Keep the cloud path, but copy everything else
                report.identified_formats = inner.identified_formats
                report.analysis = inner.analysis
                report.parse_result = inner.parse_result
                report.gdal_result = inner.gdal_result
                report.errors = inner.errors
            except Exception as exc:
                report.errors.append(f"Cloud download/analysis error: {exc}")

            reports.append(report)

        return reports
