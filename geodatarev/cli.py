"""Command-line interface for geodatarev."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from geodatarev.config import load_config
from geodatarev.scanner import DirectoryScanner


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geodatarev",
        description="Analyse and reverse-engineer binary geophysics data files.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- scan ---
    scan_p = sub.add_parser("scan", help="Scan a directory or file for binary data formats")
    scan_p.add_argument("path", help="File or directory to scan")
    scan_p.add_argument("-r", "--recursive", action="store_true", default=True,
                        help="Recurse into subdirectories (default: True)")
    scan_p.add_argument("--no-recursive", dest="recursive", action="store_false")
    scan_p.add_argument("-e", "--extensions", nargs="*",
                        help="Restrict to these extensions (e.g. .grd .ers)")
    scan_p.add_argument("-c", "--config", default=None,
                        help="Path to a YAML format config file")
    scan_p.add_argument("--json", dest="output_json", action="store_true",
                        help="Output results as JSON")
    scan_p.add_argument("--gdal", dest="check_gdal", action="store_true",
                        help="Also check whether GDAL can read each file")

    # --- identify ---
    id_p = sub.add_parser("identify", help="Identify a single binary file")
    id_p.add_argument("file", help="File to identify")
    id_p.add_argument("-c", "--config", default=None)

    # --- analyze ---
    an_p = sub.add_parser("analyze", help="Run binary analysis on a file")
    an_p.add_argument("file", help="File to analyse")
    an_p.add_argument("--json", dest="output_json", action="store_true")

    # --- gdal-check ---
    gc_p = sub.add_parser("gdal-check", help="Check if GDAL can read a file")
    gc_p.add_argument("file", help="File to check")
    gc_p.add_argument("--json", dest="output_json", action="store_true")

    # --- gdal-strategy ---
    sub.add_parser("gdal-strategy",
                   help="Show strategies for obtaining old GDAL builds")

    return parser


def _report_to_dict(report) -> dict:
    """Convert a FileReport to a JSON-serialisable dict."""
    d: dict = {
        "path": report.path,
        "size": report.size,
        "identified_formats": report.identified_formats,
        "errors": report.errors,
    }
    if report.analysis:
        a = report.analysis
        d["analysis"] = {
            "file_size": a.file_size,
            "entropy": a.entropy,
            "ascii_ratio": a.ascii_ratio,
            "null_ratio": a.null_ratio,
            "high_byte_ratio": a.high_byte_ratio,
            "printable_strings": a.printable_strings[:20],
            "header_boundary": a.header_boundary,
            "bit_width_scores": a.bit_width_scores,
            "endianness_scores": a.endianness_scores,
            "detected_patterns": a.detected_patterns[:10],
        }
    if report.parse_result:
        p = report.parse_result
        d["parsed"] = {
            "format_name": p.format_name,
            "header": p.header,
            "shape": list(p.shape) if p.shape else [],
            "data_points": len(p.data),
            "errors": p.errors,
        }
    if report.gdal_result:
        g = report.gdal_result
        d["gdal"] = {
            "can_read": g.can_read,
            "driver_short_name": g.driver_short_name,
            "driver_long_name": g.driver_long_name,
            "gdal_version": g.gdal_version,
            "raster_size": list(g.raster_size) if g.raster_size else None,
            "band_count": g.band_count,
            "band_dtypes": g.band_dtypes,
            "error": g.error,
        }
    return d


def cmd_scan(args) -> int:
    """Execute the ``scan`` subcommand."""
    configs = load_config(args.config)
    extensions = {e if e.startswith(".") else f".{e}" for e in (args.extensions or [])} or None
    scanner = DirectoryScanner(configs=configs, extensions=extensions,
                               check_gdal=getattr(args, "check_gdal", False))

    target = Path(args.path)
    if target.is_file():
        reports = [scanner.scan_file(target)]
    elif target.is_dir():
        reports = scanner.scan_directory(target, recursive=args.recursive)
    else:
        print(f"Error: {args.path} is not a valid file or directory", file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps([_report_to_dict(r) for r in reports], indent=2))
    else:
        for r in reports:
            _print_report(r)

    return 0


def cmd_identify(args) -> int:
    """Execute the ``identify`` subcommand."""
    from geodatarev.identifier import FileIdentifier

    configs = load_config(args.config)
    identifier = FileIdentifier(configs)
    matches = identifier.identify_file(args.file)
    if matches:
        for m in matches:
            print(f"  {m.name} (magic: {m.magic_bytes.hex(' ')})")
    else:
        ext_matches = identifier.identify_by_extension(args.file)
        if ext_matches:
            print("No magic match.  Extension matches:")
            for m in ext_matches:
                print(f"  {m.name}")
        else:
            print("Unknown format")
    return 0


def cmd_analyze(args) -> int:
    """Execute the ``analyze`` subcommand."""
    from geodatarev.analyzer import BinaryAnalyzer

    analyzer = BinaryAnalyzer()
    result = analyzer.analyze_file(args.file)

    if args.output_json:
        d = {
            "file_size": result.file_size,
            "entropy": result.entropy,
            "ascii_ratio": result.ascii_ratio,
            "null_ratio": result.null_ratio,
            "high_byte_ratio": result.high_byte_ratio,
            "header_boundary": result.header_boundary,
            "bit_width_scores": result.bit_width_scores,
            "endianness_scores": result.endianness_scores,
            "detected_patterns": result.detected_patterns[:10],
            "printable_strings": result.printable_strings[:20],
        }
        print(json.dumps(d, indent=2))
    else:
        print(f"File size:        {result.file_size} bytes")
        print(f"Shannon entropy:  {result.entropy:.4f} bits/byte")
        print(f"ASCII ratio:      {result.ascii_ratio:.2%}")
        print(f"Null ratio:       {result.null_ratio:.2%}")
        print(f"High-byte ratio:  {result.high_byte_ratio:.2%}")
        if result.header_boundary is not None:
            print(f"Header boundary:  ~{result.header_boundary} bytes")
        print("Bit-width scores:")
        for bits, score in sorted(result.bit_width_scores.items()):
            print(f"  {bits:>2}-bit: {score:.3f}")
        print("Endianness scores:")
        for endian, score in sorted(result.endianness_scores.items()):
            print(f"  {endian}: {score:.3f}")
        if result.detected_patterns:
            print("Detected patterns:")
            for p in result.detected_patterns[:5]:
                print(f"  period={p['period']} confidence={p['confidence']:.3f}")
        if result.printable_strings:
            print(f"Printable strings ({len(result.printable_strings)} found):")
            for s in result.printable_strings[:10]:
                print(f"  {s!r}")
    return 0


def _print_report(report) -> None:
    """Pretty-print a FileReport to stdout."""
    print(f"\n{'='*60}")
    print(f"File: {report.path}")
    print(f"Size: {report.size} bytes")
    if report.identified_formats:
        print(f"Identified: {', '.join(report.identified_formats)}")
    if report.analysis:
        a = report.analysis
        print(f"Entropy: {a.entropy:.4f} | ASCII: {a.ascii_ratio:.2%} | "
              f"Null: {a.null_ratio:.2%}")
        print(f"Bit-width scores: {a.bit_width_scores}")
        if a.endianness_scores:
            print(f"Endianness scores: {a.endianness_scores}")
    if report.gdal_result:
        g = report.gdal_result
        if g.can_read:
            print(f"GDAL: readable ({g.driver_short_name} - {g.driver_long_name})")
        elif g.error:
            print(f"GDAL: {g.error}")
    if report.parse_result:
        p = report.parse_result
        print(f"Parsed as: {p.format_name}")
        if p.shape:
            print(f"Shape: {p.shape}")
        if p.header:
            for k, v in p.header.items():
                print(f"  {k}: {v}")
    if report.errors:
        for e in report.errors:
            print(f"  ERROR: {e}")


def cmd_gdal_check(args) -> int:
    """Execute the ``gdal-check`` subcommand."""
    from geodatarev.gdal_compat import try_gdal_open, check_gdal_available

    status = check_gdal_available()
    if not status["available"]:
        print(f"GDAL not available: {status['error']}")
        return 1

    result = try_gdal_open(args.file)

    if args.output_json:
        d = {
            "gdal_version": result.gdal_version,
            "can_read": result.can_read,
            "driver_short_name": result.driver_short_name,
            "driver_long_name": result.driver_long_name,
            "raster_size": list(result.raster_size) if result.raster_size else None,
            "band_count": result.band_count,
            "band_dtypes": result.band_dtypes,
            "projection": result.projection,
            "error": result.error,
        }
        print(json.dumps(d, indent=2))
    else:
        if result.can_read:
            print(f"GDAL can read: YES")
            print(f"  Driver: {result.driver_short_name} ({result.driver_long_name})")
            print(f"  GDAL version: {result.gdal_version}")
            if result.raster_size:
                print(f"  Raster size: {result.raster_size[0]} x {result.raster_size[1]}")
            if result.band_count:
                print(f"  Bands: {result.band_count} ({', '.join(result.band_dtypes)})")
        else:
            print(f"GDAL can read: NO")
            if result.error:
                print(f"  Reason: {result.error}")
    return 0


def cmd_gdal_strategy(args) -> int:
    """Execute the ``gdal-strategy`` subcommand."""
    from geodatarev.gdal_compat import get_old_gdal_strategy

    strategy = get_old_gdal_strategy()

    print("Strategies for obtaining old GDAL builds")
    print("=" * 50)
    for approach in strategy["approaches"]:
        print(f"\n[{approach['method']}]")
        print(f"  {approach['description']}")
        print("  Commands:")
        for cmd in approach["commands"]:
            print(f"    $ {cmd}")

    deprecated = strategy["deprecated_formats"]
    if deprecated:
        print(f"\nDeprecated / removed format drivers")
        print("-" * 40)
        for key, info in deprecated.items():
            print(f"  {key}: {info['description']}")
            print(f"    Driver: {info['driver']}, last in GDAL {info['last_supported']}")
            if info["notes"]:
                print(f"    Note: {info['notes']}")

    print(f"\n{strategy['notes']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    dispatch = {
        "scan": cmd_scan,
        "identify": cmd_identify,
        "analyze": cmd_analyze,
        "gdal-check": cmd_gdal_check,
        "gdal-strategy": cmd_gdal_strategy,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
