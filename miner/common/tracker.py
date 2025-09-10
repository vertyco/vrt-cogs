from __future__ import annotations

import random
import typing as t
from collections import defaultdict, deque
from time import perf_counter

from . import constants


class ActivityTracker:
    """Track message activity for spawning rocks.

    In-memory sliding window per guild using a deque of timestamps.
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
        """Record a message event for a guild."""
        now = perf_counter()
        self.messages[key].append(now)
        self._trim(key)

    def maybe_get_rock(self, key: int) -> t.Optional[constants.RockTierName]:
        """Determine if a rock should spawn in this guild, and return its tier if so."""
        spawn_probability = self.get_spawn_probability(key)
        if random.random() >= spawn_probability:
            return None

        # Determine rock tier with activity-biased rarity
        rock_types = list(constants.ROCK_TYPES.keys())

        weights = []
        max_rarity = max(rt.rarity for rt in constants.ROCK_TYPES.values())
        # Normalise activity to [0, 1] to smoothly shift bias from common -> rare
        msg_count = len(self.messages[key])
        activity_level = min(msg_count * constants.SCALE_PER_MESSAGE, constants.SPAWN_BONUS_MAX)
        activity_bias = min(1.0, activity_level / constants.SPAWN_BONUS_MAX)

        for rocktype in rock_types:
            rarity: int = constants.ROCK_TYPES[rocktype].rarity  # 1 (common) .. N (rarest)
            inv_rarity_weight = 1.0 / rarity if rarity > 0 else 1.0
            rare_bias_weight = rarity / max_rarity  # higher for rarer rocks
            # Blend: low activity -> inverse rarity; high activity -> rarity-proportional
            weight = (1.0 - activity_bias) * inv_rarity_weight + activity_bias * rare_bias_weight
            weights.append(weight)

        # Use random.choices for weighted selection, guarding against zero-weight cases
        if not any(weights):
            return None

        self.last_spawns[key] = perf_counter()
        return random.choices(rock_types, weights=weights, k=1)[0]

    def get_spawn_probability(self, key: int, force: bool = False) -> float:
        """Get the current spawn probability for a guild based on activity."""
        self._trim(key)
        msg_count = len(self.messages[key])
        last_spawn = self.last_spawns.get(key, 0)
        now = perf_counter()
        if last_spawn and now - last_spawn < constants.MIN_TIME_BETWEEN_SPAWNS and not force:
            return 0.0
        msg_count = len(self.messages[key])
        if msg_count < constants.SPAWN_ACTIVITY_THRESHOLD and not force:
            return 0.0
        # Calculate spawn probability based on message activity
        base_spawn_prob = constants.SPAWN_PROB_MIN
        time_since_last_spawn = now - last_spawn if last_spawn else float("inf")
        # If its been twice as long as the activity window since last spawn, double chance
        if time_since_last_spawn > 2 * constants.ACTIVITY_WINDOW_SECONDS:
            base_spawn_prob *= 2  # Double chance if no spawn in a while
        # Add bonus based on message count, capped at SPAWN_BONUS_MAX
        base_spawn_prob += min(msg_count * constants.SCALE_PER_MESSAGE, constants.SPAWN_BONUS_MAX)
        final_spawn_prob = min(base_spawn_prob, constants.SPAWN_PROB_MAX)
        return final_spawn_prob
