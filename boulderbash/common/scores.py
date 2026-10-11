"""Each server's high score table: adding a finished game, and ranking players by their best score"""

TOP = 10
MEMBER_DEFAULTS = {"best": 0, "name": ""}


def add_score(entry: dict, score: int, name: str) -> tuple[dict, bool]:
    """A player's saved best after one more finished game, and whether it beat their old best"""
    if score <= entry.get("best", 0):
        return entry, False
    return {**entry, "best": score, "name": name}, True


def rank(members: dict[int, dict], user_id: int) -> dict:
    """The top players by best score, and where this player stands. Players without a score aren't ranked"""
    scored = [(uid, entry) for uid, entry in members.items() if entry.get("best", 0) > 0]
    # Ties go to whoever has the lower id, so the order never changes between looks
    order = sorted(scored, key=lambda item: (-item[1]["best"], item[0]))
    rows = [
        # Discord ids go out as text, since JavaScript rounds whole numbers this big
        {"rank": place, "id": str(uid), "name": entry.get("name") or "Unknown player", "best": entry["best"]}
        for place, (uid, entry) in enumerate(order, start=1)
    ]
    you = next(({"rank": row["rank"], "best": row["best"]} for row in rows if row["id"] == str(user_id)), None)
    return {"top": rows[:TOP], "you": you}
