import typing as t
from datetime import datetime

from pydantic import Field

from . import Base


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
    verbose: bool = False  # Include FunctionProfiles in stats
    delta: int = 1  # Data retention in hours

    watching: t.List[str] = []  # List of cogs to profile
    track_methods: bool = True  # Track method execution time
    track_commands: bool = True  # Track command execution time (Including Slash)
    track_listeners: bool = True  # Track listener execution time
    track_tasks: bool = True  # Track task execution time

    # {cog_name: {method_key: [StatsProfile]}}
    stats: t.Dict[str, t.Dict[str, t.List[StatsProfile]]] = {}
