"""Whole-number math both simulations share. web/sim/mathx.js gives the same answers."""

import math
import struct


def idiv(a: int, b: int) -> int:
    """Floor division for b > 0."""
    return a // b


def isqrt(n: int) -> int:
    """Exact integer square root of n >= 0."""
    return math.isqrt(n)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def f32(x: float) -> float:
    """Round to the nearest float32, as the original's float math does."""
    return struct.unpack("f", struct.pack("f", x))[0]


def seconds_to_ticks(seconds: float) -> int:
    return math.floor(seconds * 60 + 0.5)
