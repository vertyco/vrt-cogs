import typing as t
from dataclasses import dataclass
from datetime import datetime, timedelta

from pydantic import Field

from . import Base

IGNORED_COGS = ["SentryIO", "Profiler"]


@dataclass
class Method:
    is_coro: bool
    func_type: t.Literal["command", "hybrid", "slash", "method", "task", "listener"]
    cog_name: str
    command_name: t.Optional[str] = None


class StatsProfile(Base):
    total_tt: float  # Execution time in seconds
    func_type: str  # Function type (command, slash, method, task)
    is_coro: bool  # Async if True
    exception_thrown: t.Optional[str] = None  # Exception thrown if any
    timestamp: datetime = Field(default_factory=datetime.now)  # Time the profile was recorded


class DB(Base):
    save_stats: bool = False  # Save stats persistently
    delta: int = 1  # Data retention in hours

    sentry_profiler: bool = False  # Enable Sentry profiling

    # Profiling entire cogs's methods on a high level (No verbosity)
    tracked_cogs: t.List[str] = []  # List of cogs to track
    track_methods: bool = True  # Track method execution time
    track_commands: bool = True  # Track command execution time (Including Slash)
    track_listeners: bool = True  # Track listener execution time
    track_tasks: bool = True  # Track task execution time
    ignored_methods: t.List[str] = []  # List of methods to ignore

    # For tracking specific methods independent of the watched cogs
    tracked_methods: t.List[str] = []  # List of specific methods to track
    tracked_threshold: float = 0.0  # Minimum execution delta to record a profile of tracked methods

    # {cog_name: {method_key: [StatsProfile]}}
    stats: t.Dict[str, t.Dict[str, t.List[StatsProfile]]] = {}

    def get_methods(self) -> t.Set[str]:
        keys = set()
        for methods in self.stats.values():
            for method in methods:
                keys.add(method)
        return keys

    def discard_method(self, method: str) -> None:
        for methods in self.stats.values():
            methods.pop(method, None)

    def cleanup(self) -> int:
        oldest_time = datetime.now() - timedelta(hours=self.delta)
        cleaned = 0
        keys = list(self.stats.keys())
        for cog_name in keys:
            methods = self.stats[cog_name].copy()
            for method_key, profiles in methods.items():
                invalid = [
                    profiles[0].func_type in ["command", "hybrid", "slash"] and not self.track_commands,
                    profiles[0].func_type == "listener" and not self.track_listeners,
                    profiles[0].func_type == "task" and not self.track_tasks,
                    profiles[0].func_type == "method" and not self.track_methods,
                ]
                if any(invalid):
                    self.stats[cog_name].pop(method_key)
                    cleaned += 1
                    continue

                indexes_to_remove = []
                for idx, profile in enumerate(profiles):
                    if method_key in self.tracked_methods and (profile.total_tt * 1000) < self.tracked_threshold:
                        indexes_to_remove.append(idx)
                    elif cog_name not in self.tracked_cogs and method_key not in self.tracked_methods:
                        indexes_to_remove.append(idx)
                    elif profile.timestamp < oldest_time:
                        indexes_to_remove.append(idx)

                if indexes_to_remove:
                    self.stats[cog_name][method_key] = [
                        p for idx, p in enumerate(profiles) if idx not in indexes_to_remove
                    ]
                    cleaned += 1

                if not self.stats[cog_name][method_key]:
                    self.stats[cog_name].pop(method_key)
                    cleaned += 1

            if not self.stats[cog_name]:
                self.stats.pop(cog_name)
                cleaned += 1

        return cleaned
