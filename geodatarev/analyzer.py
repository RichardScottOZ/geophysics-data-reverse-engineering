"""Binary file analysis utilities.

Provides entropy calculation, byte-frequency histograms, repeating-pattern
detection, and bit-width heuristics for reverse engineering unknown formats.
"""

from __future__ import annotations

import math
import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO


@dataclass
class AnalysisResult:
    """Container for binary analysis results."""

    file_size: int = 0
    entropy: float = 0.0
    byte_histogram: dict[int, int] = field(default_factory=dict)
    ascii_ratio: float = 0.0
    null_ratio: float = 0.0
    high_byte_ratio: float = 0.0
    printable_strings: list[str] = field(default_factory=list)
    detected_patterns: list[dict] = field(default_factory=list)
    header_boundary: int | None = None
    bit_width_scores: dict[int, float] = field(default_factory=dict)
    endianness_scores: dict[str, float] = field(default_factory=dict)


def _shannon_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of a byte sequence (0.0-8.0)."""
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def _byte_histogram(data: bytes) -> dict[int, int]:
    """Build a frequency histogram of all 256 byte values."""
    return dict(Counter(data))


def _find_printable_strings(data: bytes, min_length: int = 4) -> list[str]:
    """Extract runs of printable ASCII characters."""
    strings: list[str] = []
    current: list[str] = []
    for byte in data:
        if 0x20 <= byte <= 0x7E:
            current.append(chr(byte))
        else:
            if len(current) >= min_length:
                strings.append("".join(current))
            current = []
    if len(current) >= min_length:
        strings.append("".join(current))
    return strings


def _detect_repeating_pattern(data: bytes, window_sizes: list[int] | None = None) -> list[dict]:
    """Detect repeating byte patterns indicative of fixed-width records.

    Looks for periodicity by checking if blocks at regular intervals are
    structurally similar (e.g. share delimiter bytes).

    Parameters
    ----------
    data : bytes
        Binary data to analyse.
    window_sizes : list[int], optional
        Candidate record sizes to test.  Defaults to common powers of two
        and small multiples.

    Returns
    -------
    list[dict]
        Each entry has ``period`` (int) and ``confidence`` (float 0-1).
    """
    if window_sizes is None:
        window_sizes = [
            4, 8, 12, 16, 20, 24, 32, 48, 56, 64,
            80, 96, 128, 240, 256, 512, 1024,
        ]

    results: list[dict] = []
    data_len = len(data)

    for ws in window_sizes:
        if ws >= data_len or ws == 0:
            continue
        n_blocks = data_len // ws
        if n_blocks < 3:
            continue

        # Compare first byte of each block for repetition
        first_bytes = [data[i * ws] for i in range(min(n_blocks, 64))]
        most_common_val, most_common_count = Counter(first_bytes).most_common(1)[0]
        confidence = most_common_count / len(first_bytes)
        if confidence >= 0.6:
            results.append({"period": ws, "confidence": round(confidence, 3)})

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def _estimate_header_boundary(data: bytes, block_size: int = 64) -> int | None:
    """Estimate where a metadata header ends and payload begins.

    Uses a sliding-window entropy approach: the header region typically has
    lower entropy (structured ASCII or small integers) compared to the
    high-entropy floating-point payload.

    Returns the byte offset of the estimated boundary, or None.
    """
    if len(data) < block_size * 3:
        return None

    n_blocks = len(data) // block_size
    entropies: list[float] = []
    for i in range(n_blocks):
        chunk = data[i * block_size:(i + 1) * block_size]
        entropies.append(_shannon_entropy(chunk))

    if not entropies:
        return None

    mean_e = sum(entropies) / len(entropies)

    # Walk from the start until entropy exceeds the mean – that transition
    # is a good heuristic for the header / payload boundary.
    for idx, e in enumerate(entropies):
        if e > mean_e and idx > 0:
            return idx * block_size

    return None


def _bit_width_alignment_scores(data: bytes) -> dict[int, float]:
    """Score how well the data aligns to different bit widths.

    For each candidate width (8, 16, 32, 64 bits) we check if the file
    size is an exact multiple and whether null-byte patterns match expected
    padding for that width.

    Returns
    -------
    dict[int, float]
        Mapping of bit width to a heuristic score (higher is better).
    """
    scores: dict[int, float] = {}
    length = len(data)

    for bits in (8, 16, 32, 64):
        byte_width = bits // 8
        score = 0.0

        # File size alignment
        if length % byte_width == 0:
            score += 0.3

        # Check null-byte padding patterns typical for wider types
        if byte_width > 1 and length >= byte_width * 4:
            sample_size = min(length, 4096)
            sample = data[:sample_size]
            # Count zero bytes that appear at expected padding positions
            aligned_zeros = 0
            total_checks = 0
            for i in range(0, len(sample) - byte_width + 1, byte_width):
                word = sample[i:i + byte_width]
                total_checks += 1
                # For wider types, high bytes are often zero in small values
                if byte_width >= 2 and word[-1] == 0:
                    aligned_zeros += 1

            if total_checks > 0:
                score += 0.3 * (aligned_zeros / total_checks)

        # Entropy-based heuristic: wider types produce different entropy
        if byte_width <= len(data):
            chunk = data[:min(len(data), 2048)]
            e = _shannon_entropy(chunk)
            # Floating-point data typically has entropy 5-7
            if bits == 32 and 4.5 < e < 7.5:
                score += 0.4
            elif bits == 64 and 5.0 < e < 7.8:
                score += 0.35
            elif bits == 16 and 3.0 < e < 6.5:
                score += 0.25
            elif bits == 8:
                score += 0.1

        scores[bits] = round(score, 3)

    return scores


def _detect_endianness(data: bytes) -> dict[str, float]:
    """Heuristically score byte-order likelihood for 16/32-bit words.

    Examines null-byte positions within 16-bit and 32-bit word
    boundaries.  In little-endian data containing small integer or
    float values the *high* bytes are more often zero; in big-endian
    data the *low* bytes are more often zero.

    Parameters
    ----------
    data : bytes
        Binary data to analyse (at least a few hundred bytes).

    Returns
    -------
    dict[str, float]
        Scores for ``"little"`` and ``"big"`` (0.0-1.0, higher is
        more likely).
    """
    if len(data) < 4:
        return {"little": 0.5, "big": 0.5}

    sample = data[:min(len(data), 4096)]
    # Trim to 4-byte alignment
    usable = len(sample) - (len(sample) % 4)
    if usable < 4:
        return {"little": 0.5, "big": 0.5}
    sample = sample[:usable]

    le_score = 0
    be_score = 0
    n_words = usable // 4

    for i in range(0, usable, 4):
        word = sample[i:i + 4]
        # Little-endian small values: high bytes (word[2], word[3]) tend to be zero
        if word[3] == 0:
            le_score += 1
        if word[2] == 0:
            le_score += 0.5
        # Big-endian small values: low bytes (word[2], word[3]) tend to be zero
        if word[0] == 0:
            be_score += 1
        if word[1] == 0:
            be_score += 0.5

    total = le_score + be_score
    if total == 0:
        return {"little": 0.5, "big": 0.5}

    return {
        "little": round(le_score / total, 3),
        "big": round(be_score / total, 3),
    }


class BinaryAnalyzer:
    """Analyse binary files for reverse engineering.

    Parameters
    ----------
    max_sample : int
        Maximum bytes to read for analysis (default 1 MB).
    """

    def __init__(self, max_sample: int = 1_048_576):
        self.max_sample = max_sample

    def analyze_data(self, data: bytes) -> AnalysisResult:
        """Run all analyses on raw bytes.

        Parameters
        ----------
        data : bytes
            Binary data to analyse.

        Returns
        -------
        AnalysisResult
        """
        sample = data[:self.max_sample]
        length = len(data)

        histogram = _byte_histogram(sample)
        ascii_count = sum(v for k, v in histogram.items() if 0x20 <= k <= 0x7E)
        null_count = histogram.get(0, 0)
        high_count = sum(v for k, v in histogram.items() if k >= 0x80)
        total = len(sample) or 1

        return AnalysisResult(
            file_size=length,
            entropy=round(_shannon_entropy(sample), 4),
            byte_histogram=histogram,
            ascii_ratio=round(ascii_count / total, 4),
            null_ratio=round(null_count / total, 4),
            high_byte_ratio=round(high_count / total, 4),
            printable_strings=_find_printable_strings(sample),
            detected_patterns=_detect_repeating_pattern(sample),
            header_boundary=_estimate_header_boundary(sample),
            bit_width_scores=_bit_width_alignment_scores(data),
            endianness_scores=_detect_endianness(sample),
        )

    def analyze_file(self, path: str | Path) -> AnalysisResult:
        """Analyse a binary file on disk.

        Parameters
        ----------
        path : str or Path
            Path to the file.

        Returns
        -------
        AnalysisResult
        """
        path = Path(path)
        with open(path, "rb") as fh:
            data = fh.read(self.max_sample)
        result = self.analyze_data(data)
        result.file_size = path.stat().st_size
        return result
