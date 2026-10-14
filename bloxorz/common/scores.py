"""The leaderboard: recording a cleared stage, and ranking players across every stage or on one stage"""

TOP = 10
USER_DEFAULTS = {"best": {}, "name": "", "reached": 0.0}


def record(entry: dict, stage: int, moves: int, name: str, now: float) -> tuple[dict, bool]:
    """A player's entry after clearing a stage, and whether their overall standing changed.

    Only fewer moves (or a first clear) change the standing. An equal score keeps the older time, so ties go to
    whoever got there first. The name is refreshed either way, since people rename.
    """
    entry = {**USER_DEFAULTS, **entry}
    best = dict(entry["best"])
    key = str(stage)
    old = best.get(key)
    improved = old is None or moves < old[0]
    if improved:
        best[key] = [moves, now]
    entry = {**entry, "best": best, "name": name}
    if improved:
        entry["reached"] = now
    return entry, improved


def row_for(place: int, uid: int, entry: dict, **fields) -> dict:
    # Discord ids go out as text, since JavaScript rounds whole numbers this big
    return {"rank": place, "id": str(uid), "name": entry.get("name") or "Unknown player", **fields}


def finish(rows: list[dict], user_id: int) -> dict:
    you = next((row for row in rows if row["id"] == str(user_id)), None)
    return {"top": rows[:TOP], "you": you}


def rank_all(users: dict[int, dict], user_id: int) -> dict:
    """Players by stages cleared (more first), then total moves (fewer first), then who got there first"""
    players = []
    for uid, entry in users.items():
        best = entry.get("best") or {}
        if best:
            total = sum(moves for moves, _ in best.values())
            players.append((uid, entry, len(best), total))
    players.sort(key=lambda item: (-item[2], item[3], item[1].get("reached", 0), item[0]))
    rows = [
        row_for(place, uid, entry, cleared=cleared, moves=total)
        for place, (uid, entry, cleared, total) in enumerate(players, start=1)
    ]
    return finish(rows, user_id)


def rank_stage(users: dict[int, dict], stage: int, user_id: int) -> dict:
    """Players by their fewest moves on one stage, then who reached that score first"""
    key = str(stage)
    players = [(uid, entry, entry["best"][key]) for uid, entry in users.items() if key in (entry.get("best") or {})]
    players.sort(key=lambda item: (item[2][0], item[2][1], item[0]))
    rows = [row_for(place, uid, entry, moves=score[0]) for place, (uid, entry, score) in enumerate(players, start=1)]
    return finish(rows, user_id)
