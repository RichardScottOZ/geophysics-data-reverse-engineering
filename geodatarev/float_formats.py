"""Converters for legacy floating-point formats.

Implements VAX F_floating, D_floating, G_floating and IBM Hexadecimal
Floating-Point conversion to IEEE 754, plus endianness helpers for
little-endian, big-endian, and middle-endian (PDP-11) byte orders.
"""

from __future__ import annotations

import struct


# ---------------------------------------------------------------------------
# Endianness helpers
# ---------------------------------------------------------------------------

def swap_middle_endian_32(data: bytes) -> bytes:
    """Convert a 32-bit value from PDP-11 middle-endian to little-endian.

    PDP-11 / VAX stores 32-bit words in byte order 2, 3, 0, 1 where byte 0
    is the least significant.  This function re-orders to standard
    little-endian (0, 1, 2, 3).
    """
    if len(data) != 4:
        raise ValueError("Expected exactly 4 bytes")
    return bytes([data[2], data[3], data[0], data[1]])


def swap_middle_endian_64(data: bytes) -> bytes:
    """Convert a 64-bit value from PDP-11 middle-endian to little-endian."""
    if len(data) != 8:
        raise ValueError("Expected exactly 8 bytes")
    return bytes([data[2], data[3], data[0], data[1],
                  data[6], data[7], data[4], data[5]])


def reorder_bytes(data: bytes, endian: str) -> bytes:
    """Re-order bytes according to the specified endianness.

    Parameters
    ----------
    data : bytes
        Raw bytes (length 1, 2, 4, or 8).
    endian : str
        One of ``"little"``, ``"big"``, or ``"middle"``.

        The ``"middle"`` (PDP-11) byte order only affects multi-word values.
        The PDP-11 was a 16-bit architecture whose native word order is
        little-endian; the idiosyncratic middle-endian ordering only
        manifests when two or more 16-bit words are combined into 32-bit
        or 64-bit quantities.  Therefore 8-bit and 16-bit values are
        returned unchanged (equivalent to little-endian).

    Returns
    -------
    bytes
        Bytes in little-endian order.
    """
    if endian == "little":
        return data
    if endian == "big":
        return data[::-1]
    if endian == "middle":
        if len(data) <= 2:
            # PDP-11 native 16-bit words are little-endian
            return data
        if len(data) == 4:
            return swap_middle_endian_32(data)
        if len(data) == 8:
            return swap_middle_endian_64(data)
        raise ValueError(f"Middle-endian reorder not supported for {len(data)}-byte values")
    raise ValueError(f"Unknown endian: {endian!r}")


# ---------------------------------------------------------------------------
# VAX floating-point conversion
# ---------------------------------------------------------------------------

def vax_f_to_ieee(data: bytes) -> float:
    """Convert a 4-byte VAX F_floating value to an IEEE 754 float.

    VAX F_floating layout (32-bit):
      - Bit 15: sign
      - Bits 14-7: biased exponent (bias 128)
      - Bits 6-0 + bits 31-16: 23-bit fraction with hidden bit
      - Byte order is middle-endian (2, 3, 0, 1)

    Returns 0.0 for the VAX reserved operand (exponent == 0, sign == 1).
    """
    if len(data) != 4:
        raise ValueError("Expected exactly 4 bytes")

    # Convert from VAX middle-endian to little-endian
    le = swap_middle_endian_32(data)
    raw = struct.unpack("<I", le)[0]

    sign = (raw >> 15) & 1
    exponent = (raw >> 7) & 0xFF
    fraction = ((raw & 0x7F) << 16) | ((raw >> 16) & 0xFFFF)

    if exponent == 0:
        return 0.0  # true zero or reserved operand

    # VAX bias is 128; IEEE bias is 127.  VAX fraction is in [0.5, 1.0),
    # IEEE fraction is in [1.0, 2.0), so we subtract 2 from the exponent
    # (one for bias difference, one for the normalisation shift).
    ieee_exp = exponent - 2
    if ieee_exp <= 0:
        return 0.0  # underflow to zero
    if ieee_exp >= 0xFF:
        ieee_exp = 0xFE  # clamp to max finite

    ieee_raw = (sign << 31) | (ieee_exp << 23) | fraction
    return struct.unpack("<f", struct.pack("<I", ieee_raw))[0]


def vax_d_to_ieee(data: bytes) -> float:
    """Convert an 8-byte VAX D_floating value to an IEEE 754 double.

    VAX D_floating (64-bit): sign(1) + exponent(8, bias 128) + fraction(55).
    Middle-endian byte order.
    """
    if len(data) != 8:
        raise ValueError("Expected exactly 8 bytes")

    le = swap_middle_endian_64(data)
    raw = int.from_bytes(le, "little")

    sign = (raw >> 15) & 1
    exponent = (raw >> 7) & 0xFF
    # Fraction: bits 6-0 of word0 + remaining 48 bits
    frac_hi = raw & 0x7F
    frac_lo = (raw >> 16) & 0xFFFFFFFFFFFF  # 48 bits
    fraction = (frac_hi << 48) | frac_lo  # 55 bits total

    if exponent == 0:
        return 0.0

    # Adjust exponent: VAX bias 128 -> IEEE bias 1023, plus normalisation
    ieee_exp = exponent - 128 + 1023 - 1
    if ieee_exp <= 0:
        return 0.0
    if ieee_exp >= 0x7FF:
        ieee_exp = 0x7FE

    # IEEE double has 52-bit fraction; VAX D has 55-bit fraction
    ieee_frac = fraction >> 3  # truncate to 52 bits

    ieee_raw = (sign << 63) | (ieee_exp << 52) | ieee_frac
    return struct.unpack("<d", ieee_raw.to_bytes(8, "little"))[0]


def vax_g_to_ieee(data: bytes) -> float:
    """Convert an 8-byte VAX G_floating value to an IEEE 754 double.

    VAX G_floating (64-bit): sign(1) + exponent(11, bias 1024) + fraction(52).
    """
    if len(data) != 8:
        raise ValueError("Expected exactly 8 bytes")

    le = swap_middle_endian_64(data)
    raw = int.from_bytes(le, "little")

    sign = (raw >> 15) & 1
    exponent = (raw >> 4) & 0x7FF
    frac_hi = raw & 0xF
    frac_lo = (raw >> 16) & 0xFFFFFFFFFFFF
    fraction = (frac_hi << 48) | frac_lo

    if exponent == 0:
        return 0.0

    # VAX G bias 1024 -> IEEE bias 1023, minus 1 for normalisation
    ieee_exp = exponent - 2
    if ieee_exp <= 0:
        return 0.0
    if ieee_exp >= 0x7FF:
        ieee_exp = 0x7FE

    ieee_raw = (sign << 63) | (ieee_exp << 52) | fraction
    return struct.unpack("<d", ieee_raw.to_bytes(8, "little"))[0]


# ---------------------------------------------------------------------------
# IBM Hexadecimal Floating-Point conversion
# ---------------------------------------------------------------------------

def ibm_float32_to_ieee(data: bytes) -> float:
    """Convert a 4-byte IBM hexadecimal float to IEEE 754.

    IBM format: sign(1) + exponent(7, bias 64, base-16) + fraction(24).
    Big-endian byte order.
    """
    if len(data) != 4:
        raise ValueError("Expected exactly 4 bytes")

    raw = struct.unpack(">I", data)[0]
    sign = (raw >> 31) & 1
    exponent = (raw >> 24) & 0x7F
    fraction = raw & 0x00FFFFFF

    if fraction == 0:
        return 0.0

    # IBM: value = (-1)^sign * (fraction / 2^24) * 16^(exponent - 64)
    value = (fraction / (1 << 24)) * (16.0 ** (exponent - 64))
    return -value if sign else value


def ibm_float64_to_ieee(data: bytes) -> float:
    """Convert an 8-byte IBM hexadecimal float to IEEE 754 double.

    IBM format: sign(1) + exponent(7, bias 64, base-16) + fraction(56).
    Big-endian byte order.
    """
    if len(data) != 8:
        raise ValueError("Expected exactly 8 bytes")

    raw = struct.unpack(">Q", data)[0]
    sign = (raw >> 63) & 1
    exponent = (raw >> 56) & 0x7F
    fraction = raw & 0x00FFFFFFFFFFFFFF

    if fraction == 0:
        return 0.0

    value = (fraction / (1 << 56)) * (16.0 ** (exponent - 64))
    return -value if sign else value


# ---------------------------------------------------------------------------
# Generic decode helper
# ---------------------------------------------------------------------------

_DTYPE_STRUCT = {
    "uint8": ("B", 1),
    "int8": ("b", 1),
    "uint16": ("H", 2),
    "int16": ("h", 2),
    "uint32": ("I", 4),
    "int32": ("i", 4),
    "uint64": ("Q", 8),
    "int64": ("q", 8),
    "float32": ("f", 4),
    "float64": ("d", 8),
}

# Mapping from our endian names to struct format prefixes
_ENDIAN_PREFIX = {
    "little": "<",
    "big": ">",
}


def decode_value(data: bytes, dtype: str, endian: str = "little") -> int | float:
    """Decode a single scalar value from bytes.

    Parameters
    ----------
    data : bytes
        Raw bytes of the value.
    dtype : str
        Data type name (e.g. ``"float32"``, ``"uint16"``).
    endian : str
        ``"little"``, ``"big"``, or ``"middle"``.

    Returns
    -------
    int or float
        Decoded value.
    """
    if dtype == "vax_f":
        return vax_f_to_ieee(data)
    if dtype == "vax_d":
        return vax_d_to_ieee(data)
    if dtype == "vax_g":
        return vax_g_to_ieee(data)
    if dtype == "ibm_float32":
        return ibm_float32_to_ieee(data)
    if dtype == "ibm_float64":
        return ibm_float64_to_ieee(data)

    info = _DTYPE_STRUCT.get(dtype)
    if info is None:
        raise ValueError(f"Unsupported dtype: {dtype!r}")

    fmt_char, expected_size = info
    if len(data) != expected_size:
        raise ValueError(f"Expected {expected_size} bytes for {dtype}, got {len(data)}")

    if endian == "middle":
        data = reorder_bytes(data, "middle")
        endian = "little"

    prefix = _ENDIAN_PREFIX.get(endian, "<")
    return struct.unpack(f"{prefix}{fmt_char}", data)[0]


def decode_array(data: bytes, dtype: str, endian: str = "little") -> list[int | float]:
    """Decode a contiguous array of values from bytes.

    For standard IEEE types uses numpy (if available) or struct bulk
    unpacking for performance. Falls back to per-element decoding for
    legacy formats (VAX, IBM).

    Parameters
    ----------
    data : bytes
        Raw bytes.
    dtype : str
        Data type name.
    endian : str
        Byte order.

    Returns
    -------
    list
        Decoded values.
    """
    # Determine element size
    if dtype in ("vax_f", "ibm_float32"):
        elem_size = 4
    elif dtype in ("vax_d", "vax_g", "ibm_float64"):
        elem_size = 8
    else:
        info = _DTYPE_STRUCT.get(dtype)
        if info is None:
            raise ValueError(f"Unsupported dtype: {dtype!r}")
        elem_size = info[1]

    if len(data) % elem_size != 0:
        raise ValueError(
            f"Data length {len(data)} is not a multiple of element size {elem_size}"
        )

    n = len(data) // elem_size

    # Fast path: standard IEEE types via numpy or struct bulk unpack
    if dtype not in ("vax_f", "vax_d", "vax_g", "ibm_float32", "ibm_float64") and endian != "middle":
        info = _DTYPE_STRUCT[dtype]
        prefix = _ENDIAN_PREFIX.get(endian, "<")
        # Try numpy first for large arrays
        if n > 256:
            try:
                import numpy as np
                np_endian = "<" if endian == "little" else ">"
                np_dtype_map = {
                    "uint8": "u1", "int8": "i1",
                    "uint16": "u2", "int16": "i2",
                    "uint32": "u4", "int32": "i4",
                    "uint64": "u8", "int64": "i8",
                    "float32": "f4", "float64": "f8",
                }
                np_dt = np.dtype(f"{np_endian}{np_dtype_map[dtype]}")
                return np.frombuffer(data, dtype=np_dt).tolist()
            except ImportError:
                pass
        # Fallback: struct bulk unpack
        fmt_char = info[0]
        return list(struct.unpack(f"{prefix}{n}{fmt_char}", data))

    # Slow path: per-element decode for legacy formats
    return [decode_value(data[i * elem_size:(i + 1) * elem_size], dtype, endian) for i in range(n)]
