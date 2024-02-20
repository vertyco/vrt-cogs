import typing as t
from dataclasses import dataclass
from datetime import datetime

from pydantic import Field

from . import Base


@dataclass
class Method:
    is_coro: bool
    func_type: t.Literal["command", "hybrid", "slash", "method", "task", "listener"]
    cog_name: str
    command_name: t.Optional[str] = None


class FunctionProfile(Base):
    ncalls: str  # Number of calls to the function
    tottime: float  # Total time spent in the function
    percall_tottime: float  # Time spent per call
    cumtime: float  # Cumulative time spent in the function
    percall_cumtime: float  # Cumulative time per call
    file_name: str  # File name where the function is defined
    line_number: int  # Line number where the function is defined


class StatsProfile(Base):
    total_tt: float  # Execution time in seconds
    func_type: str  # Function type (command, slash, method, task)
    is_coro: bool  # Async if True
    func_profiles: t.Dict[str, FunctionProfile] = {}  # Empty if not verbose
    timestamp: datetime = Field(default_factory=datetime.now)  # Time the profile was recorded


class DB(Base):
    save_stats: bool = False  # Save stats persistently
    delta: int = 1  # Data retention in hours

    # Profiling entire cogs's methods on a high level (No verbosity)
    tracked_cogs: t.List[str] = []  # List of cogs to track
    track_methods: bool = True  # Track method execution time
    track_commands: bool = True  # Track command execution time (Including Slash)
    track_listeners: bool = True  # Track listener execution time
    track_tasks: bool = True  # Track task execution time

    # For tracking specific methods independent of the watched cogs
    tracked_methods: t.List[str] = []  # List of specific methods to track verbosely
    tracked_threshold: float = 0.0  # Minimum execution delta to record a profile of tracked methods

    # For both tracked_cogs and tracked_methods
    verbose: bool = False  # If true, ALL recorded methods calls will be verbosely profiled

    # {cog_name: {method_key: [StatsProfile]}}
    stats: t.Dict[str, t.Dict[str, t.List[StatsProfile]]] = {}

    def get_methods(self) -> t.Set[str]:
        keys = set()
        for methods in self.stats.values():
            for method in methods:
                keys.add(method)
        return keys
