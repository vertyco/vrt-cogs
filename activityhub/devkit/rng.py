"""
Mulberry32, a small random number generator. rng.js gives the same numbers for the same seed, so the bot can
replay a round the page played: the bot picks a seed, the page rolls with it, and the bot rolls the same.

Copy both files into your game: this one next to your cog's Python, rng.js into web_dir.
"""

MASK = 0xFFFFFFFF


def imul(a: int, b: int) -> int:
    """JavaScript's Math.imul: multiply, keeping the low 32 bits"""
    return (a * b) & MASK


class Rng:
    def __init__(self, seed: int):
        self.state = seed & MASK

    def next(self) -> int:
        """A whole number from 0 up to, not including, 2**32"""
        self.state = (self.state + 0x6D2B79F5) & MASK
        t = self.state
        t = imul(t ^ (t >> 15), t | 1)
        t = ((t + imul(t ^ (t >> 7), t | 61)) & MASK) ^ t
        return (t ^ (t >> 14)) & MASK

    def pick(self, count: int) -> int:
        """A whole number from 0 up to, not including, count. rng.js matches it for counts up to about 2 million"""
        return (self.next() * count) >> 32
