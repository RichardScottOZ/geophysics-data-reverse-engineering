"""geodatarev - A framework for analysing and reverse engineering legacy binary geophysics data formats."""

__version__ = "0.1.0"

from geodatarev.config import FormatConfig, load_config
from geodatarev.identifier import FileIdentifier
from geodatarev.analyzer import BinaryAnalyzer
from geodatarev.scanner import DirectoryScanner

__all__ = [
    "FormatConfig",
    "load_config",
    "FileIdentifier",
    "BinaryAnalyzer",
    "DirectoryScanner",
]
