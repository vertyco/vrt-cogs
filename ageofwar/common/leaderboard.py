"""The global leaderboard: each player's fastest win against the computer on each difficulty"""

from dataclasses import dataclass

from .data import DIFFICULTIES

TOP = 10
USER_DEFAULTS = {"name": "", "best": {}, "wins": {}}


@dataclass(frozen=True)
class Result:
    """One person's win against the computer"""

    user_id: int
    name: str
    difficulty: str
    # Game time the win took, in frames of the 40 a second clock. Paused time doesn't count
    frames: int


def add_result(entry: dict, result: Result) -> dict:
    """A player's saved numbers with one more win. The name is refreshed, since people rename"""
    best = dict(entry.get("best") or {})
    wins = dict(entry.get("wins") or {})
    old = best.get(result.difficulty)
    if old is None or result.frames < old:
        best[result.difficulty] = result.frames
    wins[result.difficulty] = wins.get(result.difficulty, 0) + 1
    return {"name": result.name, "best": best, "wins": wins}


def rank(users: dict[int, dict], user_id: int) -> dict:
    """For each difficulty, the fastest players and where this player stands"""
    boards = {}
    for difficulty in DIFFICULTIES:
        timed = [(uid, entry) for uid, entry in users.items() if (entry.get("best") or {}).get(difficulty)]
        order = sorted(timed, key=lambda item: (item[1]["best"][difficulty], item[0]))
        rows = [row(place, uid, entry, difficulty) for place, (uid, entry) in enumerate(order, start=1)]
        you = next((entry for entry in rows if entry["id"] == str(user_id)), None)
        boards[difficulty] = {"top": rows[:TOP], "you": you}
    return boards


def row(place: int, user_id: int, entry: dict, difficulty: str) -> dict:
    # Discord ids go out as text, since JavaScript rounds whole numbers this big
    return {
        "rank": place,
        "id": str(user_id),
        "name": entry.get("name") or "Unknown player",
        "frames": entry["best"][difficulty],
        "wins": (entry.get("wins") or {}).get(difficulty, 0),
    }
