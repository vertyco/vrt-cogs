from __future__ import annotations

import random
import typing as t
from collections import defaultdict, deque
from time import perf_counter

from .constants import (
    ACTIVITY_WINDOW_SECONDS,
    ROCK_TYPES,
    SCALE_PER_MESSAGE,
    SPAWN_ACTIVITY_THRESHOLD,
    SPAWN_BONUS_MAX,
    SPAWN_BONUS_TIME,
    SPAWN_PROB_MAX,
    SPAWN_PROB_MIN,
)


class ActivityTracker:
    """Track message activity in channels for spawning rocks.

    In-memory sliding window per channel using a deque of timestamps.
    Single-process only; resets on restart.
    """

    def __init__(self):
        """Initialize the tracker with a sliding window size in seconds."""
        self._msgs: dict[int, t.Deque[float]] = defaultdict(deque)
        self._last_spawns: dict[int, float] = {}

    def note(self, channel_id: int) -> None:
        """Record a message event for a channel"""
        self._msgs[channel_id].append(perf_counter())
        self._trim(channel_id)

    def count(self, channel_id: int) -> int:
        """Return the number of messages in the window for a channel."""
        self._trim(channel_id)
        return len(self._msgs[channel_id])

    def counts(self, channel_ids: t.Iterable[int]) -> dict[int, int]:
        """Return a mapping of channel_id to message count for each channel in the window."""
        out: dict[int, int] = {}
        for cid in channel_ids:
            out[cid] = self.count(cid)
        return out

    def purge(self, channel_id: int) -> None:
        """Remove all tracked activity for a specific channel."""
        self._msgs.pop(channel_id, None)

    def clear(self) -> None:
        """Clear all tracked activity for all channels."""
        self._msgs.clear()

    def should_spawn(self, channel_id: int) -> bool:
        """Return True if a rock should spawn in this channel (no cooldown logic)."""
        count = self.count(channel_id)
        if count < SPAWN_ACTIVITY_THRESHOLD:
            return False

        # Always use a large value for time_since_last, so time bonus is maxed
        last_spawn = self._last_spawns.get(channel_id, 0.0)
        p = spawn_probability(count, time_since_last=perf_counter() - last_spawn)
        if random.random() < p:
            # Update last spawn time
            self._last_spawns[channel_id] = perf_counter()
            return True

        return False

    def get_rock(self, channel_id: int) -> str:
        """Return the rock tier name for this channel based on rarity and activity (weighted random)."""
        count = self.count(channel_id)
        rock_keys = list(ROCK_TYPES.keys())
        weights = []
        for key in rock_keys:
            rarity = ROCK_TYPES[key].rarity
            # Avoid division by zero, treat rarity 0 as most common
            base_weight = 1.0 / rarity if rarity > 0 else 1.0
            # Activity-based bonus
            if key == "large" and count > 10:
                base_weight *= 1.10  # Increase large rock weight by 10%
            if key == "medium" and count > 5:
                base_weight *= 1.10  # Increase medium rock weight by 10%
            weights.append(base_weight)

        chosen = random.choices(rock_keys, weights=weights, k=1)[0]
        return chosen

    # Internal
    def _trim(self, channel_id: int) -> None:
        """Remove events outside the sliding window for a channel."""
        dq = self._msgs[channel_id]
        if not dq:
            return
        cutoff = perf_counter() - ACTIVITY_WINDOW_SECONDS
        while dq and dq[0] < cutoff:
            dq.popleft()


def spawn_probability(activity_count: int, time_since_last: float = 0.0) -> float:
    """Compute spawn probability p in [SPAWN_PROB_MIN, SPAWN_PROB_MAX].

    p = clamp(scale_per_msg * activity_count + time_bonus, SPAWN_PROB_MIN, SPAWN_PROB_MAX)
    The longer since last spawn, the higher the bonus.
    """
    # If last spawn is more than twice the ROCK_TTL_SECONDS then return double the max spawn chance
    if time_since_last > 2 * SPAWN_BONUS_TIME:
        return SPAWN_PROB_MAX * 2
    # Bonus increases up to SPAWN_BONUS_MAX after SPAWN_BONUS_TIME seconds without a spawn
    bonus_scale = min(time_since_last / SPAWN_BONUS_TIME, 1.0)  # 0 to 1 over SPAWN_BONUS_TIME
    time_bonus = SPAWN_BONUS_MAX * bonus_scale
    p = SCALE_PER_MESSAGE * max(0, int(activity_count)) + time_bonus
    if p < SPAWN_PROB_MIN:
        return SPAWN_PROB_MIN
    if p > SPAWN_PROB_MAX:
        return SPAWN_PROB_MAX
    return p
