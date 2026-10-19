"""mulberry32 on a 32-bit seed. web/sim/rng.js gives the same numbers for the same seed."""

from .mathx import idiv

MASK = 0xFFFFFFFF


def imul(a: int, b: int) -> int:
    """The low 32 bits of a * b, like JavaScript's Math.imul (unsigned here)."""
    return (a * b) & MASK


class Rng:
    """Plain data (one whole number), so copy.deepcopy copies it."""

    def __init__(self, seed: int):
        self.state = seed & MASK

    def next_u32(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & MASK
        t = imul(self.state ^ (self.state >> 15), self.state | 1)
        t = ((t + imul(t ^ (t >> 7), t | 61)) & MASK) ^ t
        return t ^ (t >> 14)

    def rand_int(self, n: int) -> int:
        """A whole number from 0 to n - 1."""
        return idiv(self.next_u32() * n, 2**32)
