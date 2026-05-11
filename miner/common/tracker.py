from __future__ import annotations

from collections import defaultdict, deque
from time import perf_counter

from . import constants


class ChannelChatCache:
    """Track recent active players per channel for rock quality scaling.

    Maintains a rolling deque of (user_id, tool_tier, timestamp) tuples per channel.
    Entries older than RECENT_CHATTER_WINDOW_SECONDS are trimmed automatically.
    """

    def __init__(self):
        """Initialize the cache."""
        self.cache: dict[int, deque[tuple[int, str, float]]] = defaultdict(deque)

    def _trim(self, channel_id: int) -> None:
        """Remove entries older than the activity window."""
        dq = self.cache[channel_id]
        cutoff = perf_counter() - constants.RECENT_CHATTER_WINDOW_SECONDS
        while dq and dq[0][2] < cutoff:
            dq.popleft()

    def add_user(self, channel_id: int, user_id: int, tool_tier: str) -> None:
        """Record a user chatting in a channel with their tool tier."""
        now = perf_counter()
        dq = self.cache[channel_id]

        # Remove user's previous entry if they've chatted before (keep only latest)
        dq_filtered = deque((uid, tier, ts) for uid, tier, ts in dq if uid != user_id)
        dq.clear()
        dq.extend(dq_filtered)

        # Add new entry and cap size
        dq.append((user_id, tool_tier, now))
        while len(dq) > constants.RECENT_CHATTER_CACHE_SIZE:
            dq.popleft()

        self._trim(channel_id)

    def get_average_tool_tier(self, channel_id: int) -> float:
        """Get average tool tier of recent chatters (0.0-1.0 scale)."""
        self._trim(channel_id)
        dq = self.cache[channel_id]

        if not dq:
            return 0.5  # Default to middle tier if no one has chatted

        total_tier = sum(constants.TOOL_TIER_VALUES.get(tool, 1) for _, tool, _ in dq)
        avg_tier = total_tier / len(dq)
        max_tier = constants.TOOL_TIER_VALUES["diamond"]
        return avg_tier / max_tier

    def get_recent_player_count(self, channel_id: int) -> int:
        """Get count of unique recent chatters in a channel."""
        self._trim(channel_id)
        unique_users = len(set(uid for uid, _, _ in self.cache[channel_id]))
        return unique_users
