"""
Py-spy based process profiler for comprehensive CPU profiling.

This module runs py-spy as a subprocess to profile the bot's Python process
and generates insights from the collected data.
"""

import asyncio
import logging
import os
import shutil
import sys
import tempfile
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

import orjson
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

log = logging.getLogger("red.vrt.profiler.pyspy")


@dataclass
class StackFrame:
    """Represents a single frame in the call stack."""

    name: str
    file: str
    line: int


@dataclass
class ProfileSample:
    """A sample from py-spy containing stack frames and weight."""

    frames: t.List[StackFrame]
    weight: int  # Number of times this stack was sampled


@dataclass
class FunctionStats:
    """Aggregated statistics for a function."""

    name: str
    file: str
    self_time: int = 0  # Time spent in this function (not children)
    total_time: int = 0  # Time including children
    call_count: int = 0  # Number of samples containing this function


@dataclass
class ProfileResult:
    """The result of a py-spy profiling session."""

    duration: int  # Duration in seconds
    sample_count: int
    functions: t.List[FunctionStats] = field(default_factory=list)
    top_hotspots: t.List[FunctionStats] = field(default_factory=list)
    error: t.Optional[str] = None
    raw_data: t.Optional[dict] = None


def parse_speedscope_json(data: dict) -> t.Tuple[t.List[FunctionStats], int]:
    """
    Parse speedscope JSON format and extract function statistics.

    Parameters
    ----------
    data : dict
        The parsed JSON data from py-spy speedscope output.

    Returns
    -------
    tuple
        A tuple containing (list of FunctionStats, total sample count).
    """
    functions_map: t.Dict[str, FunctionStats] = {}
    total_samples = 0

    # Speedscope format has a shared.frames array and profiles array
    shared = data.get("shared", {})
    frames_list = shared.get("frames", [])
    profiles = data.get("profiles", [])

    # Build frame lookup
    frame_lookup: t.Dict[int, StackFrame] = {}
    for idx, frame_data in enumerate(frames_list):
        name = frame_data.get("name", "unknown")
        file_path = frame_data.get("file", "unknown")
        line = frame_data.get("line", 0)
        frame_lookup[idx] = StackFrame(name=name, file=file_path, line=line)

    for profile in profiles:
        profile_type = profile.get("type", "")
        if profile_type == "sampled":
            samples = profile.get("samples", [])
            weights = profile.get("weights", [])

            for sample_idx, (stack, weight) in enumerate(zip(samples, weights)):
                total_samples += weight

                # Track which functions we've seen at which positions in THIS sample
                seen_in_sample: t.Set[str] = set()

                for frame_idx, frame_id in enumerate(stack):
                    frame = frame_lookup.get(frame_id)
                    if not frame:
                        continue

                    key = f"{frame.name}|{frame.file}"
                    if key not in functions_map:
                        functions_map[key] = FunctionStats(name=frame.name, file=frame.file)

                    func_stats = functions_map[key]

                    # Self time: only the bottom of the stack (first in list for py-spy)
                    if frame_idx == 0:
                        func_stats.self_time += weight

                    # Total time: any appearance in the stack
                    func_stats.total_time += weight

                    # Count unique appearances per sample
                    if key not in seen_in_sample:
                        func_stats.call_count += 1
                        seen_in_sample.add(key)

    functions = list(functions_map.values())
    # Sort by self_time descending
    functions.sort(key=lambda f: f.self_time, reverse=True)

    return functions, total_samples


def generate_profiling_charts(result: ProfileResult) -> bytes:
    """
    Generate visualization charts from profiling results.

    Creates a multi-panel figure with:
    - Top functions by self time (horizontal bar chart)
    - Top functions by total time (horizontal bar chart)

    Parameters
    ----------
    result : ProfileResult
        The profiling result containing function statistics.

    Returns
    -------
    bytes
        PNG image data of the generated charts.
    """
    if not result.functions:
        # Return empty placeholder
        fig = go.Figure()
        fig.add_annotation(
            text="No profiling data available", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False
        )
        return pio.to_image(fig, format="png", width=1200, height=400)

    # Get top 15 functions by self time
    top_self = sorted(result.functions, key=lambda f: f.self_time, reverse=True)[:15]
    # Get top 15 by total time
    top_total = sorted(result.functions, key=lambda f: f.total_time, reverse=True)[:15]

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Top Functions by Self Time (CPU)", "Top Functions by Total Time (Including Callees)"),
        horizontal_spacing=0.15,
    )

    # Truncate long function names for display
    def truncate_name(name: str, max_len: int = 40) -> str:
        if len(name) > max_len:
            return name[: max_len - 3] + "..."
        return name

    # Self time chart
    self_names = [truncate_name(f.name) for f in reversed(top_self)]
    self_times = [f.self_time for f in reversed(top_self)]
    total_samples = result.sample_count or 1
    self_percentages = [(t / total_samples) * 100 for t in self_times]

    fig.add_trace(
        go.Bar(
            y=self_names,
            x=self_percentages,
            orientation="h",
            marker_color="rgb(255, 127, 14)",
            text=[f"{p:.1f}%" for p in self_percentages],
            textposition="outside",
            name="Self Time",
        ),
        row=1,
        col=1,
    )

    # Total time chart
    total_names = [truncate_name(f.name) for f in reversed(top_total)]
    total_times = [f.total_time for f in reversed(top_total)]
    total_percentages = [(t / total_samples) * 100 for t in total_times]

    fig.add_trace(
        go.Bar(
            y=total_names,
            x=total_percentages,
            orientation="h",
            marker_color="rgb(44, 160, 44)",
            text=[f"{p:.1f}%" for p in total_percentages],
            textposition="outside",
            name="Total Time",
        ),
        row=1,
        col=2,
    )

    fig.update_layout(
        title=dict(
            text=f"CPU Profile Analysis ({result.duration}s, {result.sample_count:,} samples)",
            x=0.5,
            xanchor="center",
        ),
        template="plotly_dark",
        showlegend=False,
        height=max(500, 40 * len(top_self)),
        width=1600,
        margin=dict(l=300, r=100, t=80, b=50),
    )

    fig.update_xaxes(title_text="% of CPU Time", row=1, col=1)
    fig.update_xaxes(title_text="% of Total Time", row=1, col=2)

    return pio.to_image(fig, format="png")


def format_profiling_insights(result: ProfileResult) -> t.List[str]:
    """
    Format profiling results into human-readable pages.

    Parameters
    ----------
    result : ProfileResult
        The profiling result containing function statistics.

    Returns
    -------
    list
        List of formatted message strings.
    """
    if result.error:
        return [f"Profiling Failed\n{result.error}"]

    if not result.functions:
        return ["Profiling Complete\nNo samples collected. The process may have been idle."]

    pages = []
    total = result.sample_count or 1

    # Overview page
    overview = [
        f"CPU Profile ({result.duration}s • {result.sample_count:,} samples • {len(result.functions):,} functions)",
        "",
        "Top Hotspots (Self Time):",
    ]

    top_hotspots = sorted(result.functions, key=lambda f: f.self_time, reverse=True)[:10]
    for idx, func in enumerate(top_hotspots, 1):
        pct = (func.self_time / total) * 100
        # Simplify file path for display
        file_display = func.file
        if "/" in file_display:
            file_display = "/".join(file_display.split("/")[-2:])
        elif "\\" in file_display:
            file_display = "\\".join(file_display.split("\\")[-2:])
        overview.append(f"{idx}. {pct:.1f}% `{func.name}` ({file_display})")

    overview.append("")
    overview.append("-# See attached chart for visual breakdown")
    pages.append("\n".join(overview))

    # Detailed breakdown page - by total time (inclusive)
    detail_page = [
        "Inclusive Time Analysis",
        "Functions by total time (including callees):",
        "",
    ]

    top_total = sorted(result.functions, key=lambda f: f.total_time, reverse=True)[:15]
    for idx, func in enumerate(top_total, 1):
        total_pct = (func.total_time / total) * 100
        self_pct = (func.self_time / total) * 100
        # Simplify file path for display
        file_display = func.file
        if "/" in file_display:
            file_display = "/".join(file_display.split("/")[-2:])
        elif "\\" in file_display:
            file_display = "\\".join(file_display.split("\\")[-2:])
        detail_page.append(
            f"{idx}. `{func.name}` ({file_display}) • total {total_pct:.1f}% • self {self_pct:.1f}% • {func.call_count:,} samples"
        )

    pages.append("\n".join(detail_page))

    # Analysis suggestions page
    suggestions = [
        "Analysis Tips",
        "Self = CPU in function only • Total = includes callees",
        "",
    ]

    # Analyze patterns
    hottest = top_hotspots[0] if top_hotspots else None
    if hottest:
        pct = (hottest.self_time / total) * 100
        if pct > 20:
            suggestions.append(f"⚠️ Hot Spot: `{hottest.name}` uses {pct:.1f}% CPU")

    # Check for common patterns
    json_funcs = [f for f in result.functions if "json" in f.name.lower() or "load" in f.name.lower()]
    if json_funcs:
        json_total = sum(f.self_time for f in json_funcs)
        json_pct = (json_total / total) * 100
        if json_pct > 5:
            suggestions.append(f"📄 JSON/Serialization: {json_pct:.1f}% - try orjson")

    regex_funcs = [f for f in result.functions if "regex" in f.name.lower() or "match" in f.name.lower()]
    if regex_funcs:
        regex_total = sum(f.self_time for f in regex_funcs)
        regex_pct = (regex_total / total) * 100
        if regex_pct > 5:
            suggestions.append(f"🔍 Regex: {regex_pct:.1f}% - compile patterns")

    db_funcs = [f for f in result.functions if any(x in f.name.lower() for x in ["sql", "query", "execute", "fetch"])]
    if db_funcs:
        db_total = sum(f.self_time for f in db_funcs)
        db_pct = (db_total / total) * 100
        if db_pct > 5:
            suggestions.append(f"💾 Database: {db_pct:.1f}% - optimize queries")

    if len(suggestions) == 3:  # Only headers, no patterns found
        suggestions.append("✅ No obvious bottleneck patterns detected")

    pages.append("\n".join(suggestions))

    return pages


def _find_pyspy() -> t.Optional[str]:
    """Find py-spy executable, checking venv bin directory first."""
    # First check system PATH
    pyspy_path = shutil.which("py-spy")
    if pyspy_path:
        return pyspy_path

    # Check in the same directory as the Python executable (venv bin/Scripts)
    python_dir = Path(sys.executable).parent
    if sys.platform == "win32":
        pyspy_in_venv = python_dir / "py-spy.exe"
    else:
        pyspy_in_venv = python_dir / "py-spy"

    if pyspy_in_venv.exists():
        return str(pyspy_in_venv)

    return None


async def run_pyspy_profile(duration: int = 30, subprocesses: bool = False) -> ProfileResult:
    """
    Run py-spy profiler on the current Python process.

    Parameters
    ----------
    duration : int
        How long to profile in seconds (default 30).
    subprocesses : bool
        Whether to profile subprocesses too.

    Returns
    -------
    ProfileResult
        The profiling result with statistics and any errors.
    """
    pid = os.getpid()
    result = ProfileResult(duration=duration, sample_count=0)

    # Check if py-spy is available
    pyspy_path = _find_pyspy()
    if not pyspy_path:
        result.error = (
            "py-spy is not installed or not in PATH. "
            "Install it with: `pip install py-spy` "
            "(may require sudo/admin for installation)"
        )
        return result

    # Create a temp file for the output
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as json_file:
        json_path = json_file.name

    try:
        # Build the command
        # py-spy record outputs speedscope JSON format when using --format speedscope
        json_cmd = [
            pyspy_path,
            "record",
            "--format",
            "speedscope",
            "--output",
            json_path,
            "--duration",
            str(duration),
            "--pid",
            str(pid),
            "--rate",
            "100",  # 100 samples per second
        ]

        if subprocesses:
            json_cmd.append("--subprocesses")

        # On Windows, py-spy may need elevated permissions
        if sys.platform == "win32":
            log.info("Running py-spy on Windows (may require admin privileges)")

        log.info(f"Starting py-spy profiling for {duration} seconds on PID {pid}")

        # Run py-spy as a subprocess (JSON output)
        # We run it asynchronously to not block the bot
        json_process = await asyncio.create_subprocess_exec(
            *json_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for it to complete
        stdout, stderr = await json_process.communicate()

        if json_process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            if "permissions" in error_msg.lower() or "ptrace" in error_msg.lower():
                result.error = (
                    f"Permission denied. py-spy requires elevated privileges.\n\n"
                    f"**Linux:** Run with sudo or set ptrace scope:\n"
                    f"`echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope`\n\n"
                    f"**Windows:** Run as Administrator.\n\n"
                    f"**macOS:** Requires SIP to be partially disabled.\n\n"
                    f"Raw error: {error_msg[:500]}"
                )
            else:
                result.error = f"py-spy failed with exit code {json_process.returncode}: {error_msg[:500]}"
            return result

        # Parse the JSON output
        json_path_obj = Path(json_path)
        if json_path_obj.exists() and json_path_obj.stat().st_size > 0:
            with open(json_path, "rb") as f:
                data = orjson.loads(f.read())
                result.raw_data = data
                functions, sample_count = parse_speedscope_json(data)
                result.functions = functions
                result.sample_count = sample_count
                result.top_hotspots = sorted(functions, key=lambda f: f.self_time, reverse=True)[:20]
        else:
            result.error = "py-spy completed but produced no output. The process may have been idle."

    except FileNotFoundError:
        result.error = "py-spy executable not found. Ensure it's installed and in your PATH."
    except PermissionError as e:
        result.error = f"Permission error: {e}. py-spy may require elevated privileges."
    except Exception as e:
        log.exception("Error running py-spy profile")
        result.error = f"Unexpected error: {type(e).__name__}: {e}"
    finally:
        # Cleanup temp files
        try:
            Path(json_path).unlink(missing_ok=True)
        except Exception:
            pass

    return result
