"""Tests for geodatarev.float_formats."""

import math
import struct

import pytest

from geodatarev.float_formats import (
    swap_middle_endian_32,
    swap_middle_endian_64,
    reorder_bytes,
    vax_f_to_ieee,
    vax_d_to_ieee,
    vax_g_to_ieee,
    ibm_float32_to_ieee,
    ibm_float64_to_ieee,
    decode_value,
    decode_array,
)


class TestEndianness:
    def test_swap_middle_endian_32(self):
        # Middle-endian (2,3,0,1) -> little-endian (0,1,2,3)
        data = bytes([2, 3, 0, 1])
        result = swap_middle_endian_32(data)
        assert result == bytes([0, 1, 2, 3])

    def test_swap_middle_endian_32_wrong_size(self):
        with pytest.raises(ValueError):
            swap_middle_endian_32(b"\x00\x01\x02")

    def test_swap_middle_endian_64(self):
        data = bytes([2, 3, 0, 1, 6, 7, 4, 5])
        result = swap_middle_endian_64(data)
        assert result == bytes([0, 1, 2, 3, 4, 5, 6, 7])

    def test_reorder_little(self):
        data = b"\x01\x02\x03\x04"
        assert reorder_bytes(data, "little") == data

    def test_reorder_big(self):
        data = b"\x01\x02\x03\x04"
        assert reorder_bytes(data, "big") == b"\x04\x03\x02\x01"

    def test_reorder_middle(self):
        data = bytes([2, 3, 0, 1])
        assert reorder_bytes(data, "middle") == bytes([0, 1, 2, 3])

    def test_reorder_middle_16bit_pdp11(self):
        # PDP-11 was 16-bit; native 16-bit words are little-endian
        data = b"\x01\x00"  # value 1 in little-endian
        assert reorder_bytes(data, "middle") == data

    def test_reorder_middle_8bit(self):
        # Single bytes are unaffected by endianness
        data = b"\x42"
        assert reorder_bytes(data, "middle") == data

    def test_reorder_unknown(self):
        with pytest.raises(ValueError):
            reorder_bytes(b"\x00\x00\x00\x00", "xyz")


class TestVAXFloat:
    def test_vax_f_zero(self):
        assert vax_f_to_ieee(b"\x00\x00\x00\x00") == 0.0

    def test_vax_f_wrong_size(self):
        with pytest.raises(ValueError):
            vax_f_to_ieee(b"\x00\x00")

    def test_vax_d_zero(self):
        assert vax_d_to_ieee(b"\x00" * 8) == 0.0

    def test_vax_d_wrong_size(self):
        with pytest.raises(ValueError):
            vax_d_to_ieee(b"\x00" * 4)

    def test_vax_g_zero(self):
        assert vax_g_to_ieee(b"\x00" * 8) == 0.0

    def test_vax_g_wrong_size(self):
        with pytest.raises(ValueError):
            vax_g_to_ieee(b"\x00" * 4)


class TestIBMFloat:
    def test_ibm_float32_zero(self):
        assert ibm_float32_to_ieee(b"\x00\x00\x00\x00") == 0.0

    def test_ibm_float32_one(self):
        # IBM: sign=0, exponent=65 (bias 64, so 16^1), fraction=0.0625 (1/16)
        # value = 0.0625 * 16^1 = 1.0
        raw = (65 << 24) | (0x100000)  # fraction = 1/16 in 24 bits
        data = struct.pack(">I", raw)
        result = ibm_float32_to_ieee(data)
        assert abs(result - 1.0) < 1e-6

    def test_ibm_float32_negative(self):
        # -1.0: sign=1
        raw = (1 << 31) | (65 << 24) | (0x100000)
        data = struct.pack(">I", raw)
        result = ibm_float32_to_ieee(data)
        assert abs(result - (-1.0)) < 1e-6

    def test_ibm_float32_wrong_size(self):
        with pytest.raises(ValueError):
            ibm_float32_to_ieee(b"\x00\x00")

    def test_ibm_float64_zero(self):
        assert ibm_float64_to_ieee(b"\x00" * 8) == 0.0

    def test_ibm_float64_wrong_size(self):
        with pytest.raises(ValueError):
            ibm_float64_to_ieee(b"\x00" * 4)


class TestDecodeValue:
    def test_uint8(self):
        assert decode_value(b"\xff", "uint8") == 255

    def test_int8(self):
        assert decode_value(b"\xff", "int8") == -1

    def test_uint16_little(self):
        assert decode_value(b"\x01\x00", "uint16", "little") == 1

    def test_uint16_big(self):
        assert decode_value(b"\x00\x01", "uint16", "big") == 1

    def test_int32(self):
        data = struct.pack("<i", -42)
        assert decode_value(data, "int32", "little") == -42

    def test_float32(self):
        data = struct.pack("<f", 3.14)
        result = decode_value(data, "float32", "little")
        assert abs(result - 3.14) < 1e-5

    def test_float64(self):
        data = struct.pack("<d", 2.718281828)
        result = decode_value(data, "float64", "little")
        assert abs(result - 2.718281828) < 1e-9

    def test_uint64(self):
        data = struct.pack("<Q", 2**40)
        assert decode_value(data, "uint64", "little") == 2**40

    def test_vax_f_dispatch(self):
        result = decode_value(b"\x00\x00\x00\x00", "vax_f")
        assert result == 0.0

    def test_ibm_float32_dispatch(self):
        result = decode_value(b"\x00\x00\x00\x00", "ibm_float32")
        assert result == 0.0

    def test_unsupported_dtype(self):
        with pytest.raises(ValueError, match="Unsupported dtype"):
            decode_value(b"\x00", "complex128")

    def test_wrong_size(self):
        with pytest.raises(ValueError):
            decode_value(b"\x00", "float32")

    def test_middle_endian_int32(self):
        # Pack 1 as little-endian, then rearrange to middle-endian
        le = struct.pack("<I", 1)  # 01 00 00 00
        middle = bytes([le[2], le[3], le[0], le[1]])  # 00 00 01 00
        result = decode_value(middle, "uint32", "middle")
        assert result == 1

    def test_middle_endian_uint16_pdp11(self):
        # PDP-11 16-bit words are natively little-endian
        data = struct.pack("<H", 42)
        result = decode_value(data, "uint16", "middle")
        assert result == 42


class TestDecodeArray:
    def test_float32_array(self):
        values = [1.0, 2.0, 3.0, 4.0]
        data = struct.pack(f"<{len(values)}f", *values)
        result = decode_array(data, "float32", "little")
        assert len(result) == 4
        for expected, actual in zip(values, result):
            assert abs(expected - actual) < 1e-6

    def test_uint16_array(self):
        data = struct.pack("<3H", 10, 20, 30)
        result = decode_array(data, "uint16", "little")
        assert result == [10, 20, 30]

    def test_misaligned_raises(self):
        with pytest.raises(ValueError, match="not a multiple"):
            decode_array(b"\x00\x01\x02", "float32")

    def test_unsupported_dtype(self):
        with pytest.raises(ValueError, match="Unsupported dtype"):
            decode_array(b"\x00", "complex128")
