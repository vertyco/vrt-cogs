"""The global leaderboard's numbers: adding a finished match to a player, and ranking everyone"""

from dataclasses import dataclass

TOP = 10
USER_DEFAULTS = {"wins": 0, "kills": 0, "matches": 0, "name": ""}


@dataclass(frozen=True)
class Result:
    """One person's part in a finished match"""

    user_id: int
    name: str
    kills: int
    won: bool


def add_result(entry: dict, result: Result) -> dict:
    """A player's saved numbers with one more match added. The name is refreshed, since people rename. A match where
    they blew themselves up more than they hit others adds no kills, rather than taking some away"""
    return {
        "wins": entry["wins"] + int(result.won),
        "kills": entry["kills"] + max(0, result.kills),
        "matches": entry["matches"] + 1,
        "name": result.name,
    }


def rank(users: dict[int, dict], user_id: int) -> dict:
    """The top players by wins, kills breaking ties, and where this player stands"""
    order = sorted(users.items(), key=lambda item: (-item[1]["wins"], -item[1]["kills"], item[0]))
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
        "kills": entry["kills"],
        "matches": entry["matches"],
    }
