"""
File I/O profiler using watchdog to monitor filesystem write activity.

Monitors the bot's data directory for file writes and reports which files
are being written to, how often, and how much data is changing.
"""

import asyncio
import logging
import os
import time
import typing as t
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer

    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

log = logging.getLogger("red.vrt.profiler.io")


@dataclass
class FileWriteEvent:
    """A single file write event."""

    path: str
    size: int  # File size after write in bytes
    timestamp: float


@dataclass
class FileWriteStats:
    """Aggregated stats for a single file."""

    path: str
    write_count: int = 0
    total_bytes_written: int = 0  # Sum of file sizes at each write
    last_size: int = 0
    first_write: float = 0.0
    last_write: float = 0.0


@dataclass
class IOProfileResult:
    """The result of an I/O profiling session."""

    duration: int
    base_path: str
    total_events: int = 0
    total_bytes: int = 0
    file_stats: t.List[FileWriteStats] = field(default_factory=list)
    dir_stats: t.Dict[str, int] = field(default_factory=dict)  # dir -> write count
    error: t.Optional[str] = None
    timeline: t.List[t.Tuple[float, int]] = field(default_factory=list)  # (timestamp, cumulative_events)


class _WriteHandler(FileSystemEventHandler):
    """Watchdog handler that tracks close_write events."""

    def __init__(self, base_path: str):
        super().__init__()
        self.base_path = base_path
        self.events: t.List[FileWriteEvent] = []
        self.lock = asyncio.Lock()

    def _record(self, event: FileSystemEvent):
        if event.is_directory:
            return
        path = event.src_path
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        self.events.append(FileWriteEvent(path=path, size=size, timestamp=time.monotonic()))

    def on_modified(self, event: FileSystemEvent):
        self._record(event)

    def on_created(self, event: FileSystemEvent):
        self._record(event)

    def on_closed(self, event: FileSystemEvent):
        # Some platforms emit close events after writes
        self._record(event)


def _humanize_bytes(n: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _shorten_path(path: str, base: str) -> str:
    """Make a path relative to the base data directory."""
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return path


def _aggregate_results(events: t.List[FileWriteEvent], base_path: str, duration: int) -> IOProfileResult:
    """Aggregate raw events into an IOProfileResult."""
    result = IOProfileResult(duration=duration, base_path=base_path)
    result.total_events = len(events)

    if not events:
        return result

    # Per-file stats
    file_map: t.Dict[str, FileWriteStats] = {}
    dir_counts: t.Dict[str, int] = defaultdict(int)

    for evt in events:
        rel = _shorten_path(evt.path, base_path)

        if rel not in file_map:
            file_map[rel] = FileWriteStats(path=rel, first_write=evt.timestamp)

        stats = file_map[rel]
        stats.write_count += 1
        stats.total_bytes_written += evt.size
        stats.last_size = evt.size
        stats.last_write = evt.timestamp

        # Track directory
        parent = str(Path(rel).parent)
        dir_counts[parent] += 1

    result.file_stats = sorted(file_map.values(), key=lambda s: s.write_count, reverse=True)
    result.dir_stats = dict(sorted(dir_counts.items(), key=lambda kv: kv[1], reverse=True))
    result.total_bytes = sum(s.total_bytes_written for s in result.file_stats)

    # Build timeline (1-second buckets)
    if events:
        start = events[0].timestamp
        cumulative = 0
        bucket_size = max(1, duration // 60)  # At least 1 second buckets
        timeline: t.List[t.Tuple[float, int]] = []
        current_bucket_start = start
        bucket_count = 0

        for evt in events:
            while evt.timestamp >= current_bucket_start + bucket_size:
                cumulative += bucket_count
                elapsed = current_bucket_start - start
                timeline.append((elapsed, cumulative))
                current_bucket_start += bucket_size
                bucket_count = 0
            bucket_count += 1

        cumulative += bucket_count
        elapsed = current_bucket_start - start
        timeline.append((elapsed, cumulative))
        result.timeline = timeline

    return result


def generate_io_charts(result: IOProfileResult) -> bytes:
    """Generate charts showing I/O activity breakdown."""
    if not result.file_stats:
        fig = go.Figure()
        fig.add_annotation(text="No I/O activity recorded", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return pio.to_image(fig, format="png", width=1200, height=400)

    has_timeline = len(result.timeline) > 2
    cols = 2 if has_timeline else 1
    subtitles = ["Top Files by Write Count"]
    if has_timeline:
        subtitles.append("Cumulative Writes Over Time")

    fig = make_subplots(
        rows=1,
        cols=cols,
        subplot_titles=subtitles,
        horizontal_spacing=0.2 if has_timeline else 0,
    )

    # Top files bar chart
    top_files = result.file_stats[:15]
    names = [_truncate(s.path, 50) for s in reversed(top_files)]
    counts = [s.write_count for s in reversed(top_files)]

    fig.add_trace(
        go.Bar(
            y=names,
            x=counts,
            orientation="h",
            marker_color="rgb(99, 110, 250)",
            text=[str(c) for c in counts],
            textposition="outside",
            name="Writes",
        ),
        row=1,
        col=1,
    )

    # Timeline
    if has_timeline:
        times = [t[0] for t in result.timeline]
        cumulative = [t[1] for t in result.timeline]
        fig.add_trace(
            go.Scatter(
                x=times,
                y=cumulative,
                mode="lines+markers",
                marker_color="rgb(239, 85, 59)",
                name="Cumulative",
                fill="tozeroy",
            ),
            row=1,
            col=2,
        )
        fig.update_xaxes(title_text="Seconds Elapsed", row=1, col=2)
        fig.update_yaxes(title_text="Total Writes", row=1, col=2)

    fig.update_layout(
        title=dict(
            text=f"File I/O Activity ({result.duration}s, {result.total_events:,} events)",
            x=0.5,
            xanchor="center",
        ),
        template="plotly_dark",
        showlegend=False,
        height=max(500, 35 * len(top_files)),
        width=1600,
        margin=dict(l=400, r=100, t=80, b=50),
    )

    fig.update_xaxes(title_text="Write Count", row=1, col=1)

    return pio.to_image(fig, format="png")


def format_io_insights(result: IOProfileResult) -> t.List[str]:
    """Format I/O profiling results into pages."""
    if result.error:
        return [f"I/O Profiling Failed\n{result.error}"]

    if not result.file_stats:
        return [f"I/O Profile ({result.duration}s)\nNo file write activity detected in the data directory."]

    pages = []

    # Page 1: Overview
    overview = [
        f"I/O Profile ({result.duration}s • {result.total_events:,} writes • {len(result.file_stats):,} files)",
        "",
        "Top Files by Write Count:",
    ]

    for idx, stats in enumerate(result.file_stats[:12], 1):
        avg_size = stats.total_bytes_written // max(stats.write_count, 1)
        rate = stats.write_count / max(result.duration, 1)
        overview.append(
            f"{idx}. `{_truncate(stats.path, 60)}` • {stats.write_count:,} writes • "
            f"{_humanize_bytes(avg_size)} avg • {rate:.1f}/s"
        )

    overview.append("")
    overview.append(f"-# Total data written: {_humanize_bytes(result.total_bytes)}")
    overview.append("-# See attached chart for visual breakdown")
    pages.append("\n".join(overview))

    # Page 2: Directory breakdown
    if result.dir_stats:
        dir_page = [
            "Directory Breakdown",
            f"Write activity by directory ({len(result.dir_stats):,} dirs):",
            "",
        ]

        for idx, (dirname, count) in enumerate(list(result.dir_stats.items())[:15], 1):
            pct = (count / max(result.total_events, 1)) * 100
            dir_page.append(f"{idx}. `{_truncate(dirname, 60)}` • {count:,} writes ({pct:.1f}%)")

        pages.append("\n".join(dir_page))

    # Page 3: Analysis
    analysis = [
        "I/O Analysis",
        "",
    ]

    # High frequency writers
    high_freq = [s for s in result.file_stats if s.write_count / max(result.duration, 1) > 1.0]
    if high_freq:
        analysis.append(f"⚠️ {len(high_freq)} file(s) written more than 1x/second:")
        for s in high_freq[:5]:
            rate = s.write_count / max(result.duration, 1)
            analysis.append(f"  {rate:.1f}/s `{_truncate(s.path, 50)}`")
        analysis.append("")

    # Large files
    large = sorted(result.file_stats, key=lambda s: s.last_size, reverse=True)
    large = [s for s in large if s.last_size > 1024 * 100]  # > 100KB
    if large:
        analysis.append(f"📦 {len(large)} large file(s) (>100KB):")
        for s in large[:5]:
            analysis.append(f"  {_humanize_bytes(s.last_size)} `{_truncate(s.path, 50)}`")
        analysis.append("")

    # JSON config churn
    json_files = [s for s in result.file_stats if s.path.endswith(".json")]
    if json_files:
        json_writes = sum(s.write_count for s in json_files)
        json_bytes = sum(s.total_bytes_written for s in json_files)
        analysis.append(
            f"📄 JSON files: {len(json_files)} files, {json_writes:,} writes, {_humanize_bytes(json_bytes)} total"
        )

    db_files = [
        s
        for s in result.file_stats
        if any(s.path.endswith(ext) for ext in (".db", ".sqlite", ".sqlite3", "-wal", "-shm", "-journal"))
    ]
    if db_files:
        db_writes = sum(s.write_count for s in db_files)
        db_bytes = sum(s.total_bytes_written for s in db_files)
        analysis.append(
            f"💾 SQLite files: {len(db_files)} files, {db_writes:,} writes, {_humanize_bytes(db_bytes)} total"
        )

    if len(analysis) == 2:
        analysis.append("✅ No unusual I/O patterns detected")

    pages.append("\n".join(analysis))

    return pages


def _truncate(s: str, max_len: int = 50) -> str:
    return s if len(s) <= max_len else "..." + s[-(max_len - 3) :]


async def run_io_profile(data_path: str, duration: int = 60) -> IOProfileResult:
    """
    Monitor file write activity in the bot's data directory.

    Parameters
    ----------
    data_path : str
        The root data path to monitor.
    duration : int
        How long to monitor in seconds.

    Returns
    -------
    IOProfileResult
        Aggregated I/O profiling results.
    """
    if not HAS_WATCHDOG:
        result = IOProfileResult(duration=duration, base_path=data_path)
        result.error = "watchdog is not installed. Install it with: `pip install watchdog`"
        return result

    if not Path(data_path).is_dir():
        result = IOProfileResult(duration=duration, base_path=data_path)
        result.error = f"Data path does not exist: {data_path}"
        return result

    handler = _WriteHandler(data_path)
    observer = Observer()
    observer.schedule(handler, data_path, recursive=True)

    loop = asyncio.get_running_loop()

    try:
        await loop.run_in_executor(None, observer.start)
        await asyncio.sleep(duration)
    finally:
        observer.stop()
        await loop.run_in_executor(None, observer.join)

    return await loop.run_in_executor(None, _aggregate_results, handler.events, data_path, duration)
