MASK = 0xFFFFFFFF


def imul(a: int, b: int) -> int:
    return (a * b) & MASK


class Rng:
    """
    Mulberry32, the same random number generator the bundled game pages use (mirrored in their rules.js).

    One seed gives the page and the bot the same rolls, so the bot can replay a round from its moves.
    """

    def __init__(self, seed: int):
        self.state = seed & MASK

    def next(self) -> int:
        self.state = (self.state + 0x6D2B79F5) & MASK
        t = self.state
        t = imul(t ^ (t >> 15), t | 1)
        t = ((t + imul(t ^ (t >> 7), t | 61)) & MASK) ^ t
        return (t ^ (t >> 14)) & MASK

    def pick(self, count: int) -> int:
        """A whole number from 0 up to, not including, count"""
        return (self.next() * count) >> 32
