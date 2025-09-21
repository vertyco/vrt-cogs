import math
import statistics
import typing as t
from datetime import datetime, timedelta

from redbot.core.utils.chat_formatting import box
from tabulate import tabulate

from .models import DB, StatsProfile


def format_method_pages(
    method_key: str,
    data: t.List[StatsProfile],
    threshold: float = 0.0,
    sort_by_delta: bool = False,
) -> t.List[str]:
    if threshold:
        data = [i for i in data if (i.total_tt * 1000) >= threshold]

    if not data:
        if threshold:
            return ["No data to display. Come back later or try a lower threshold."]
        else:
            return ["No data to display. Come back later."]

    if sort_by_delta and data:
        data.sort(key=lambda i: i.total_tt, reverse=True)

    runtimes = [profile.total_tt for profile in data]
    max_runtime = max(runtimes)
    min_runtime = min(runtimes)
    avg_runtime = statistics.mean(runtimes)

    max_exe = f"{max_runtime:.4f}s" if max_runtime > 1 else f"{max_runtime * 1000:.2f}ms"
    min_exe = f"{min_runtime:.4f}s" if min_runtime > 1 else f"{min_runtime * 1000:.2f}ms"
    avg_exe = f"{avg_runtime:.4f}s" if avg_runtime > 1 else f"{avg_runtime * 1000:.2f}ms"

    # Now calculate the calls per minute
    oldest_profile = min(data, key=lambda i: i.timestamp)
    timeframe_minutes = (datetime.now() - oldest_profile.timestamp).total_seconds() / 60
    calls_per_minute = len(data) / timeframe_minutes if timeframe_minutes else 0

    total_calls = len(data)
    error_count = len([i for i in data if i.exception_thrown])

    base_page = (
        f"# {method_key}\n"
        "## Overview\n"
        f"- Max Runtime: {max_exe}\n"
        f"- Min Runtime: {min_exe}\n"
        f"- Avg Runtime: {avg_exe}\n"
        f"- Calls/Min: {calls_per_minute:.1f}\n"
        f"- Total Calls: {total_calls}\n"
        f"- Errors: {error_count}\n"
    )

    warning_sign = "⚠️"
    pages = []
    for idx, stats in enumerate(data):
        ts = int(stats.timestamp.timestamp())
        exe_time = f"{stats.total_tt:.4f}s"
        if stats.total_tt < 1:
            exe_time = f"{stats.total_tt * 1000:.2f}ms"

        page = (
            f"{base_page}"
            "### Runtime Instance\n"
            f"- Time Recorded: <t:{ts}:F> (<t:{ts}:R>)\n"
            f"- Type: {stats.func_type.capitalize()}\n"
            f"- Is Coroutine: {stats.is_coro}\n"
            f"- Time: {exe_time}\n"
        )
        if stats.exception_thrown:
            page += f"- {warning_sign} **Exception**: `{stats.exception_thrown}`\n"
        page += "\n"
        if threshold:
            page += f"Filtering by threshold: `{threshold:.2f}ms`\n"
        page += f"Page `{idx + 1}/{len(data)}`"
        pages.append(page)

    return pages


def format_method_error_pages(method_key: str, data: t.List[StatsProfile]) -> t.List[str]:
    """Create pages that show only the errored runs for a given method.

    Parameters
    - method_key: The identifier of the method being inspected.
    - data: The list of StatsProfile entries for this method.

    Returns
    - List of page strings suitable for sending as message content.
    """
    error_profiles = [i for i in data if i.exception_thrown]

    if not error_profiles:
        return ["No errors recorded for this method."]

    pages: list[str] = []
    total_errors = len(error_profiles)

    for idx, stats in enumerate(error_profiles, start=1):
        ts = int(stats.timestamp.timestamp())
        exe_time = f"{stats.total_tt:.4f}s" if stats.total_tt >= 1 else f"{stats.total_tt * 1000:.2f}ms"
        # Keep exception concise; field is expected to be a short string per model
        exc_text = str(stats.exception_thrown).strip()

        page = (
            f"# {method_key}\n"
            "## Error Instance\n"
            f"- Time Recorded: <t:{ts}:F> (<t:{ts}:R>)\n"
            f"- Type: {stats.func_type.capitalize()}\n"
            f"- Is Coroutine: {stats.is_coro}\n"
            f"- Runtime: {exe_time}\n"
            f"- Exception: `{exc_text}`\n\n"
            f"Showing errors only. Page `{idx}/{total_errors}`"
        )
        pages.append(page)

    return pages


def format_runtime_pages(
    db: DB,
    sort_by: str,
    query: str = None,
) -> t.List[str]:
    now = datetime.now()
    stats: t.Dict[str, list] = {}
    keys = list(db.stats.keys())
    for k in keys:
        methodlist = db.stats[k]
        method_keys = list(methodlist.keys())
        for method_key in method_keys:
            profiles = methodlist[method_key]
            if query and query not in method_key:
                continue

            # Calculate the calls per minute and total calls in the last specified delta
            valid_profiles = [i for i in profiles if i.timestamp > (now - timedelta(hours=db.delta))]
            if not valid_profiles:
                # Don't show any results beyond the set delta
                continue

            runtimes = [profile.total_tt for profile in valid_profiles]

            max_runtime = max(runtimes)
            min_runtime = min(runtimes)
            avg_runtime = statistics.mean(runtimes)

            # Now calculate the calls per minute
            oldest_profile = min(valid_profiles, key=lambda i: i.timestamp)
            timeframe_minutes = (now - oldest_profile.timestamp).total_seconds() / 60
            calls_per_minute = len(valid_profiles) / timeframe_minutes if timeframe_minutes else 0

            total_calls = len(valid_profiles)
            error_count = len([i for i in valid_profiles if i.exception_thrown])

            # Calculate impact score
            std_dev = statistics.stdev(runtimes) if len(runtimes) > 1 else 0
            variability_score = std_dev / avg_runtime if avg_runtime > 0 else 0
            impact_score = (avg_runtime * calls_per_minute) * (1 + variability_score)

            name = method_key
            if profiles[0].func_type != "method":
                name = f"{method_key} ({profiles[0].func_type[0].upper()})"

            if method_key in db.tracked_methods:
                name = f"+ {name}"
            elif error_count > 0:
                name = f"- {name}"

            stats[name] = [
                min_runtime,
                max_runtime,
                avg_runtime,
                calls_per_minute,
                total_calls,
                error_count,
                impact_score,
            ]

    per_page = 10
    start = 0
    end = per_page
    page_count = math.ceil(len(stats) / per_page)
    delta_text = f"Last {'Hr' if db.delta == 1 else f'{db.delta}hrs'}"

    if sort_by == "Name":
        cols = ["[Method]", "Min/Max/Avg", "CPM", delta_text, "Err", "Impact"]
        stats = dict(sorted(stats.items()))
    elif sort_by == "Max":
        cols = ["Method", "Min/[Max]/Avg", "CPM", delta_text, "Err", "Impact"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][0], reverse=True))
    elif sort_by == "Min":
        cols = ["Method", "[Min]/Max/Avg", "CPM", delta_text, "Err", "Impact"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][1], reverse=True))
    elif sort_by == "Avg":
        cols = ["Method", "Min/Max/[Avg]", "CPM", delta_text, "Err", "Impact"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][2], reverse=True))
    elif sort_by == "CPM":
        cols = ["Method", "Min/Max/Avg", "[CPM]", delta_text, "Err", "Impact"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][3], reverse=True))
    elif sort_by == "Count":
        cols = ["Method", "Min/Max/Avg", "CPM", f"[{delta_text}]", "Err", "Impact"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][4], reverse=True))
    elif sort_by == "Errors":
        cols = ["Method", "Min/Max/Avg", "CPM", delta_text, "[Err]", "Impact"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][5], reverse=True))
    else:  # sort_by == "Impact"
        cols = ["Method", "Min/Max/Avg", "CPM", delta_text, "Err", "[Impact]"]
        stats = dict(sorted(stats.items(), key=lambda item: item[1][6], reverse=True))

    def _format(value_seconds: float) -> str:
        if value_seconds > 120:
            return f"{value_seconds / 60:.1f}m"
        elif value_seconds < 1:
            return f"{value_seconds * 1000:.0f}ms"
        return f"{value_seconds:.1f}s"

    def _format_cpm(value: float) -> float:
        if value < 0.009:
            return round(value, 4)
        elif value < 0.1:
            return round(value, 3)
        elif value < 1:
            return round(value, 2)
        return round(value, 1)

    pages = []
    for p in range(page_count):
        if end > len(stats):
            end = len(stats)

        rows = []
        for i in range(start, end):
            method_key = list(stats.keys())[i]
            max_runtime, min_runtime, avg_runtime, calls_per_minute, total_calls, error_count, impact_score = stats[
                method_key
            ]
            rows.append(
                [
                    method_key,
                    f"{_format(min_runtime)}/{_format(max_runtime)}/{_format(avg_runtime)}",
                    _format_cpm(calls_per_minute),
                    total_calls,
                    error_count,
                    round(impact_score),
                ]
            )

        page = f"{tabulate(rows, headers=cols)}\n\n"
        page += "+ Tracking\n- Has Errors\n"
        page = box(page, lang="diff")

        if db.track_commands:
            page += "(C) = `Command`, (S) = `Slash Command`, (H) = `Hybrid Command`"
        if db.track_tasks:
            page += ", (T) = `Task Loop`"
        if db.track_listeners:
            page += ", (L) = `Listener`"

        page += "\n"
        page += f"**Page** `{p + 1}/{page_count}`"

        if query:
            page += f"\nCurrent Filter: `{query}`"

        pages.append(page)
        start += per_page
        end += per_page

    if not pages:
        pages.append("No data to display. Come back later.")
    return pages


def format_runtimes(stats: t.Dict[str, t.List[StatsProfile]]):
    rows = []
    for method_key, profiles in stats.items():
        for profile in profiles:
            if profile.total_tt < 1:
                exe_time = f"{profile.total_tt * 1000:.2f}ms"
            else:
                exe_time = f"{profile.total_tt:.4f}s"

            rows.append([method_key, exe_time, profile.is_command, profile.is_coro])
    cols = ["Method", "Time", "Command", "Coro"]
    return tabulate(rows, headers=cols)


def timedelta_format(delta: t.Optional[timedelta] = None, seconds: t.Optional[int] = None) -> str:
    try:
        obj = seconds if seconds is not None else delta.total_seconds()
    except AttributeError:
        raise ValueError("You must provide either a timedelta or a number of seconds")

    seconds = int(obj)
    periods = [
        ("Yr", 60 * 60 * 24 * 365),
        ("M", 60 * 60 * 24 * 30),
        ("d", 60 * 60 * 24),
        ("h", 60 * 60),
        ("m", 60),
        ("s", 1),
    ]

    strings = []
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            if period_value == 0:
                continue
            strings.append(f"{period_value}{period_name}")

    return ", ".join(strings)


def humanize_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if abs(num) < 1024.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1024.0
    return "{0:.1f}{1}".format(num, "YB")
