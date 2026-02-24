# geodatarev

A Python framework for analysing and reverse engineering legacy binary geophysics data formats.

---

## Overview

`geodatarev` helps you identify, inspect, and decode binary files produced by historical mineral
exploration software (Surfer, Geosoft Oasis montaj, ER Mapper, Encom ModelVision, SEG-Y, and
more).  It provides:

- **Magic-byte & extension-based format identification**
- **Low-level binary analysis** — Shannon entropy, byte histograms, bit-width and endianness
  heuristics, repeating-pattern detection, and printable-string extraction
- **Format-specific parsers** that decode headers and data payloads into structured results
- **Directory scanning** — batch-process entire data stores in one command
- **Optional GDAL integration** — check whether files are readable by the installed GDAL version
  and obtain strategies for accessing files that require older GDAL builds

A detailed background on the methodology behind this work — including software genealogy,
floating-point architectures, and legal considerations — is available in
[OVERVIEW.md](OVERVIEW.md).

---

## Installation

```bash
pip install geodatarev
```

Optional extras:

```bash
pip install "geodatarev[fast]"   # enables NumPy-accelerated paths
pip install "geodatarev[dev]"    # adds pytest for running the test suite
```

Requires Python ≥ 3.9.

---

## Supported formats

| Format | Extension(s) | Identification |
|---|---|---|
| Surfer 6 Binary Grid | `.grd` | Magic `DSBB` |
| Surfer 7 Binary Grid | `.grd` | Magic `DSRB` |
| ER Mapper Header | `.ers` | Magic `Dataset` |
| Encom ModelVision Grid | `.grd` | Magic `GRID` at offset 168 |
| ESRI ArcInfo Binary Grid | `.adf` | Magic `00 00 27 0A FF FF` |
| TIFF (big- and little-endian) | `.tif`, `.tiff` | Magic `MM.*` / `II*.` |
| SEG-Y Rev 0 | `.sgy`, `.segy` | 3 600-byte header heuristic |
| Geosoft Binary Grid | `.grd` | 512-byte header heuristic |
| ZMap+ ASCII Grid | `.zmap`, `.dat` | Structural pattern (`!` / `@`) |

Custom formats can be added via a YAML configuration file (see [Configuration](#configuration)).

---

## Command-line usage

```
geodatarev <command> [options]
```

### `scan` — batch analyse a directory or file

```bash
# Scan a directory recursively, show results as JSON
geodatarev scan /data/surveys --json

# Restrict to specific extensions and also run GDAL checks
geodatarev scan /data/surveys -e .grd .ers --gdal

# Scan a single file
geodatarev scan /data/surveys/anomaly.grd
```

### `identify` — identify the format of a single file

```bash
geodatarev identify anomaly.grd
```

### `analyze` — low-level binary analysis

```bash
geodatarev analyze anomaly.grd
geodatarev analyze anomaly.grd --json
```

Reports entropy, ASCII / null / high-byte ratios, bit-width scores, endianness scores,
detected repeating patterns, and extracted printable strings.

### `gdal-check` — check GDAL readability

```bash
geodatarev gdal-check anomaly.grd --json
```

### `gdal-strategy` — list approaches for obtaining old GDAL builds

```bash
geodatarev gdal-strategy
```

---

## Python API

### Identify a file

```python
from geodatarev import FileIdentifier, load_config

configs = load_config()                  # loads built-in format definitions
identifier = FileIdentifier(configs)

matches = identifier.identify_file("anomaly.grd")
for m in matches:
    print(m.name, m.magic_bytes.hex(" "))

ext_matches = identifier.identify_by_extension("anomaly.grd")
```

### Analyse binary content

```python
from geodatarev import BinaryAnalyzer

analyzer = BinaryAnalyzer()
result = analyzer.analyze_file("anomaly.grd")

print(f"Entropy:       {result.entropy:.4f}")
print(f"ASCII ratio:   {result.ascii_ratio:.2%}")
print(f"Bit-width scores: {result.bit_width_scores}")
print(f"Endianness:    {result.endianness_scores}")
```

### Scan a directory

```python
from geodatarev import DirectoryScanner

scanner = DirectoryScanner(extensions={".grd", ".ers"}, check_gdal=True)
reports = scanner.scan_directory("/data/surveys", recursive=True)

for report in reports:
    print(report.path, report.identified_formats)
    if report.parse_result:
        print("  header:", report.parse_result.header)
        print("  shape:",  report.parse_result.shape)
```

### Disambiguate overloaded extensions

```python
from geodatarev import classify_dat, classify_grd

with open("mystery.grd", "rb") as fh:
    sample = fh.read(8192)

format_name = classify_grd(sample, "mystery.grd")
```

### GDAL compatibility

```python
from geodatarev import check_gdal_available, try_gdal_open, get_old_gdal_strategy

print(check_gdal_available())

result = try_gdal_open("anomaly.grd")
if result.can_read:
    print(result.driver_short_name, result.raster_size)

strategy = get_old_gdal_strategy()
```

---

## Configuration

Format definitions live in `geodatarev/configs/default_formats.yaml`.  You can supply
additional or overriding definitions via the `--config` CLI flag or the `load_config` API:

```bash
geodatarev scan /data --config my_formats.yaml
```

```python
from geodatarev import load_config
configs = load_config("my_formats.yaml")
```

A minimal custom format entry:

```yaml
formats:
  - name: "My Legacy Format"
    extensions: [".bin"]
    magic_bytes: "4D 59 46 4D"   # MYFM
    magic_offset: 0
    endian: little
    header_size: 128
    data_dtype: float32
    description: "Custom legacy format with 128-byte header"
```

---

## Running the tests

```bash
pip install "geodatarev[dev]"
pytest
```

---

## License

MIT
