"""PvP records for the global leaderboard: each player's wins, losses and draws across every server"""

TOP = 10
DEFAULTS = {"name": "", "wins": 0, "losses": 0, "draws": 0}
COUNTS = {"win": "wins", "loss": "losses", "draw": "draws"}


def add(entry: dict | None, outcome: str, name: str) -> dict:
    """A player's record with one more fight. The name is refreshed, since people rename"""
    entry = {**DEFAULTS, **(entry or {})}
    entry[COUNTS[outcome]] += 1
    entry["name"] = name
    return entry


def fought(entry: dict | None) -> bool:
    return bool(entry) and entry["wins"] + entry["losses"] + entry["draws"] > 0


def rank(users: dict[int, dict], user_id: int) -> dict:
    played = [(uid, data["pvp"]) for uid, data in users.items() if fought(data.get("pvp"))]
    order = sorted(played, key=lambda item: (-item[1]["wins"], item[1]["losses"], item[0]))
    rows = [
        {
            "rank": place,
            # Discord ids go out as text, since JavaScript rounds whole numbers this big
            "id": str(uid),
            "name": entry["name"] or "Unknown player",
            "wins": entry["wins"],
            "losses": entry["losses"],
            "draws": entry["draws"],
        }
        for place, (uid, entry) in enumerate(order, start=1)
    ]
    you = next((row for row in rows if row["id"] == str(user_id)), None)
    return {"top": rows[:TOP], "you": you}
