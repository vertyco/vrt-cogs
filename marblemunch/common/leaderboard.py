"""The global leaderboard's numbers: adding a finished round to a player, and ranking everyone"""

from dataclasses import dataclass

TOP = 10
USER_DEFAULTS = {"wins": 0, "marbles": 0, "rounds": 0, "name": ""}


@dataclass(frozen=True)
class Result:
    """One person's part in a finished round"""

    user_id: int
    name: str
    marbles: int
    won: bool


def add_result(entry: dict, result: Result) -> dict:
    """A player's saved numbers with one more round added. The name is refreshed, since people rename"""
    return {
        "wins": entry["wins"] + int(result.won),
        "marbles": entry["marbles"] + result.marbles,
        "rounds": entry["rounds"] + 1,
        "name": result.name,
    }


def rank(users: dict[int, dict], user_id: int) -> dict:
    """The top players by wins, total marbles breaking ties, and where this player stands"""
    order = sorted(users.items(), key=lambda item: (-item[1]["wins"], -item[1]["marbles"], item[0]))
    rows = [row(place, uid, entry) for place, (uid, entry) in enumerate(order, start=1)]
    you = next((entry for entry in rows if entry["id"] == str(user_id)), None)
    return {"top": rows[:TOP], "you": you}


def row(place: int, user_id: int, entry: dict) -> dict:
    # Discord ids go out as text, since JavaScript rounds whole numbers this big
    return {
        "rank": place,
        "id": str(user_id),
        "name": entry["name"] or "Unknown player",
        "wins": entry["wins"],
        "marbles": entry["marbles"],
        "rounds": entry["rounds"],
    }
