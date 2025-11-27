from __future__ import annotations

import random
import typing as t
from collections import defaultdict, deque
from time import perf_counter

from . import constants


class ActivityTracker:
    """Track message activity for spawning rocks.

    In-memory sliding window using a deque of timestamps.
    Single-process only; resets on restart.
    """

    def __init__(self):
        """Initialize the tracker with a sliding window size in seconds."""
        self.messages: dict[int, t.Deque[float]] = defaultdict(deque)  # {key: deque[timestamp]}
        self.last_spawns: dict[int, float] = {}  # {key: timestamp}

    def _trim(self, key: int) -> None:
        dq = self.messages[key]
        cutoff = perf_counter() - constants.ACTIVITY_WINDOW_SECONDS
        while dq and dq[0] < cutoff:
            dq.popleft()

    def update(self, key: int) -> None:
        """Record a message event."""
        now = perf_counter()
        self.messages[key].append(now)
        self._trim(key)

    def maybe_get_rock(
        self,
        key: int,
        min_interval: float,
        max_interval: float,
    ) -> t.Optional[constants.RockTierName]:
        """Determine if a rock should spawn, and return its tier if so.

        The caller provides the global minimum and maximum spawn intervals, in seconds.
        """
        spawn_probability = self.get_spawn_probability(key, min_interval, max_interval)
        if random.random() >= spawn_probability:
            return None

        # Determine rock tier with activity-biased rarity
        rock_types = list(constants.ROCK_TYPES.keys())

        weights = []
        for rocktype in rock_types:
            rarity: int = constants.ROCK_TYPES[rocktype].rarity  # 1 (common) .. N (rarest)
            inv_rarity_weight = 1.0 / rarity if rarity > 0 else 0.1
            weights.append(inv_rarity_weight)

        # Use random.choices for weighted selection, guarding against zero-weight cases
        if not any(weights):
            return None

        self.last_spawns[key] = perf_counter()
        return random.choices(rock_types, weights=weights, k=1)[0]

    def get_spawn_probability(self, key: int, min_interval: float, max_interval: float) -> float:
        """Get the current spawn probability for a key based on activity and timing.

        - Before ``min_interval`` has elapsed since the last spawn, probability is 0.
        - Between ``min_interval`` and ``max_interval``, probability ramps with time and activity.
        - After ``max_interval``, probability is clamped to the global maximum.
        """
        self._trim(key)
        msg_count = len(self.messages[key])
        last_spawn = self.last_spawns.get(key, 0)
        now = perf_counter()

        time_since_last_spawn = now - last_spawn if last_spawn else float("inf")

        # Enforce a hard minimum interval between spawns.
        if time_since_last_spawn < min_interval:
            return 0.0

        base_spawn_prob = constants.SPAWN_PROB_MIN

        # Smoothly ramp probability between min_interval and max_interval.
        if min_interval < max_interval and time_since_last_spawn != float("inf"):
            if time_since_last_spawn >= max_interval:
                # Once we hit the maximum interval, strongly bias towards a spawn.
                base_spawn_prob = constants.SPAWN_PROB_MAX
            else:
                span = max_interval - min_interval
                ratio = (time_since_last_spawn - min_interval) / span
                ratio = max(0.0, min(1.0, ratio))
                # Multiplier from 1x up to 10x as we approach max_interval.
                multiplier = 1.0 + ratio * 9.0
                base_spawn_prob *= multiplier

        # Add bonus based on message count, capped at SPAWN_BONUS_MAX.
        base_spawn_prob += min(msg_count * constants.SCALE_PER_MESSAGE, constants.SPAWN_BONUS_MAX)

        final_spawn_prob = min(base_spawn_prob, constants.SPAWN_PROB_MAX)
        return final_spawn_prob
