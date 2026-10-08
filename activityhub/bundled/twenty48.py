import typing as t

from .rng import Rng

# Rules mirrored in web/2048/rules.js. A round is replayed move by move from its seed
SIZE = 4
MAX_MOVES = 100_000
# Faster than anyone can press keys, slow enough to stop a script that plays thousands of moves at once
MIN_SECONDS_PER_MOVE = 0.03
MOVES = "ULDR"


def lines(direction: str) -> list[list[int]]:
    """Cell indexes of each row or column, starting from the edge the tiles slide toward"""
    rows = [[r * SIZE + c for c in range(SIZE)] for r in range(SIZE)]
    cols = [[r * SIZE + c for r in range(SIZE)] for c in range(SIZE)]
    if direction == "L":
        return rows
    if direction == "R":
        return [row[::-1] for row in rows]
    if direction == "U":
        return cols
    return [col[::-1] for col in cols]


# Worked out once, since a replay slides thousands of times
LINES = {direction: lines(direction) for direction in MOVES}


class Board:
    def __init__(self, seed: int):
        self.rng = Rng(seed)
        self.cells = [0] * (SIZE * SIZE)
        self.score = 0
        self.spawn()
        self.spawn()

    def spawn(self) -> None:
        free = [i for i, value in enumerate(self.cells) if not value]
        cell = free[self.rng.pick(len(free))]
        self.cells[cell] = 4 if self.rng.pick(10) == 0 else 2

    def move(self, direction: str) -> bool:
        """Slide every tile, merging equal pairs once. Returns False when nothing moved"""
        before = list(self.cells)
        for line in LINES[direction]:
            values = [self.cells[i] for i in line if self.cells[i]]
            merged = []
            while values:
                if len(values) > 1 and values[0] == values[1]:
                    merged.append(values[0] * 2)
                    self.score += values[0] * 2
                    values = values[2:]
                else:
                    merged.append(values.pop(0))
            merged += [0] * (SIZE - len(merged))
            for i, value in zip(line, merged, strict=True):
                self.cells[i] = value
        if self.cells == before:
            return False
        self.spawn()
        return True


def replay(seed: int, moves: t.Any) -> int | None:
    """The score a round's moves reach, or None when a move is unknown or slides nothing"""
    if not isinstance(moves, str) or len(moves) > MAX_MOVES:
        return None
    board = Board(seed)
    for direction in moves:
        if direction not in MOVES or not board.move(direction):
            return None
    return board.score
