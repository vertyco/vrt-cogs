"""Who is watching whom.

A watcher's page runs the friend's level itself, from the level's seed and the friend's accepted taps, so the bot
only passes those along: the friend's LevelStart once, then each accepted tap, each tick the friend's page reached
and the result. Each player watches at most one friend at a time.
"""

import typing as t

# The friend's page reached a tick: {"fat": tick}
TICK = "fat"
# One accepted tap: {"ftap": [tick, tap]}
TAP = "ftap"
# The friend's level ended: {"fover": over}
OVER = "fover"
# The friend started another level: {"flevel": LevelStart}
LEVEL = "flevel"
# The friend left, or is no longer playing a level: {"fgone": true}
GONE = {"fgone": True}


def read_watch(name: str, value: t.Any) -> tuple[str, t.Any] | None:
    """{"watch": "<user id>"} as ("watch", id) and {"unwatch": true} as ("unwatch", True), or None"""
    if name == "watch" and isinstance(value, str) and value.isdigit() and 0 < len(value) <= 20:
        return "watch", int(value)
    if name == "unwatch" and value is True:
        return "unwatch", True
    return None


class Watchers:
    """Each watcher's friend, by user id."""

    def __init__(self):
        self.friend_of: dict[int, int] = {}

    def add(self, watcher: int, friend: int) -> None:
        self.friend_of[watcher] = friend

    def remove(self, watcher: int) -> int | None:
        """Stop `watcher` watching. Returns the friend they watched, if any"""
        return self.friend_of.pop(watcher, None)

    def of(self, friend: int) -> list[int]:
        """Everyone watching `friend`"""
        return [watcher for watcher, watched in self.friend_of.items() if watched == friend]

    def drop_friend(self, friend: int) -> list[int]:
        """Stop everyone watching `friend`. Returns who they were"""
        watchers = self.of(friend)
        for watcher in watchers:
            del self.friend_of[watcher]
        return watchers
