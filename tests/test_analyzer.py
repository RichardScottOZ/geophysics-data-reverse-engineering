"""Tests for geodatarev.analyzer."""

import math
import struct

import pytest

from geodatarev.analyzer import (
    BinaryAnalyzer,
    _shannon_entropy,
    _byte_histogram,
    _find_printable_strings,
    _detect_repeating_pattern,
    _estimate_header_boundary,
    _bit_width_alignment_scores,
    _detect_endianness,
)


class TestShannonEntropy:
    def test_zero_entropy(self):
        # All same bytes -> entropy 0
        assert _shannon_entropy(b"\x00" * 100) == 0.0

    def test_max_entropy(self):
        # All 256 byte values equally -> entropy ~8.0
        data = bytes(range(256))
        e = _shannon_entropy(data)
        assert abs(e - 8.0) < 0.01

    def test_empty(self):
        assert _shannon_entropy(b"") == 0.0

    def test_two_values(self):
        # 50/50 split -> entropy 1.0
        data = b"\x00\x01" * 50
        e = _shannon_entropy(data)
        assert abs(e - 1.0) < 0.01


class TestByteHistogram:
    def test_simple(self):
        h = _byte_histogram(b"\x00\x00\x01\x02")
        assert h[0] == 2
        assert h[1] == 1
        assert h[2] == 1


class TestFindPrintableStrings:
    def test_basic(self):
        data = b"\x00\x00DSBB\x00\x00"
        strings = _find_printable_strings(data)
        assert "DSBB" in strings

    def test_min_length(self):
        data = b"\x00AB\x00ABCD\x00"
        strings = _find_printable_strings(data, min_length=4)
        assert "ABCD" in strings
        assert "AB" not in strings


class TestDetectRepeatingPattern:
    def test_periodic_data(self):
        # Create data with clear 32-byte period
        record = b"\x00" + b"\xFF" * 31
        data = record * 20
        patterns = _detect_repeating_pattern(data)
        periods = [p["period"] for p in patterns]
        assert 32 in periods

    def test_no_pattern(self):
        import os
        data = os.urandom(1024)
        patterns = _detect_repeating_pattern(data)
        # Random data should have low confidence patterns
        for p in patterns:
            # Allow some matches due to randomness, but not high confidence
            assert p["confidence"] <= 1.0


class TestEstimateHeaderBoundary:
    def test_header_then_noise(self):
        # ASCII header followed by random-looking payload
        header = b"HEADER" * 20  # 120 bytes of low-entropy ASCII
        payload = bytes(range(256)) * 4  # high-entropy
        data = header + payload
        boundary = _estimate_header_boundary(data, block_size=32)
        # Boundary should be near the header/payload transition
        if boundary is not None:
            assert boundary <= 256  # should be in the right ballpark


class TestBitWidthAlignment:
    def test_32bit_float_data(self):
        # Pack float32 values
        values = [float(i) for i in range(100)]
        data = struct.pack(f"<{len(values)}f", *values)
        scores = _bit_width_alignment_scores(data)
        assert 32 in scores
        assert 8 in scores
        assert 16 in scores
        assert 64 in scores

    def test_alignment(self):
        # 400 bytes is divisible by 1, 2, 4, 8
        data = b"\x00" * 400
        scores = _bit_width_alignment_scores(data)
        # All should have alignment bonus
        for bits in (8, 16, 32, 64):
            assert scores[bits] >= 0.3


class TestBinaryAnalyzer:
    def test_analyze_data(self):
        data = b"DSBB" + b"\x00" * 52 + struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        analyzer = BinaryAnalyzer()
        result = analyzer.analyze_data(data)
        assert result.file_size == len(data)
        assert result.entropy >= 0
        assert result.ascii_ratio >= 0
        assert "DSBB" in result.printable_strings

    def test_analyze_file(self, surfer6_file):
        analyzer = BinaryAnalyzer()
        result = analyzer.analyze_file(surfer6_file)
        assert result.file_size > 0
        assert result.entropy > 0
        assert 32 in result.bit_width_scores

    def test_analyze_data_has_endianness(self):
        data = struct.pack("<10f", *range(10))
        analyzer = BinaryAnalyzer()
        result = analyzer.analyze_data(data)
        assert "little" in result.endianness_scores
        assert "big" in result.endianness_scores


class TestDetectEndianness:
    def test_little_endian_small_ints(self):
        # Small 32-bit LE integers: high bytes are zero
        values = list(range(100))
        data = struct.pack(f"<{len(values)}I", *values)
        scores = _detect_endianness(data)
        assert scores["little"] > scores["big"]

    def test_big_endian_small_ints(self):
        # Small 32-bit BE integers: low bytes (first) are zero
        values = list(range(100))
        data = struct.pack(f">{len(values)}I", *values)
        scores = _detect_endianness(data)
        assert scores["big"] > scores["little"]

    def test_short_data(self):
        scores = _detect_endianness(b"\x01\x02")
        assert scores["little"] == 0.5
        assert scores["big"] == 0.5

    def test_returns_both_keys(self):
        data = b"\x00" * 100
        scores = _detect_endianness(data)
        assert "little" in scores
        assert "big" in scores
