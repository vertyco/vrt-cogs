"""Player count graph for the live status panel. Pure rendering, the rows come from db/utils."""

import logging
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import matplotlib.dates as mdates
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from redbot.core.i18n import Translator

log = logging.getLogger("red.vrt.paltools.graph")
_ = Translator("PalTools", __file__)

# Discord renders the panel on a dark backdrop, so the figure is transparent with light ink
INK = "#dbdee1"
GRID_ALPHA = 0.12


def resolve_zone(name: str) -> tuple[ZoneInfo, str]:
    """The configured zone plus the abbreviation to label the axis with, falling back to UTC.

    A bad name only reaches here if the zone was dropped from the tz database since it was set,
    and a graph in the wrong hours beats no panel at all.
    """
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        log.warning("Unknown timezone %r, drawing the graph in UTC: %s", name, e)
        zone = ZoneInfo("UTC")
    # From the current moment, so the label follows daylight saving rather than naming the
    # standard-time abbreviation all year
    return zone, datetime.now(zone).tzname() or name


def render_player_graph(rows: list[dict], hours: int, tz: str = "UTC") -> bytes:
    """PNG of player count per server over time. Blocking, call it in a thread."""
    zone, zone_label = resolve_zone(tz)
    series: dict[str, dict[datetime, int]] = defaultdict(dict)
    totals: dict[datetime, int] = defaultdict(int)
    for row in rows:
        series[row["server_name"]][row["bucket"]] = row["players"]
        totals[row["bucket"]] += row["players"]

    fig = Figure(figsize=(8, 4), dpi=150)
    fig.patch.set_alpha(0)
    ax = fig.add_subplot()
    ax.patch.set_alpha(0)

    for name in sorted(series):
        points = sorted(series[name].items())
        ax.plot([b for b, _c in points], [c for _b, c in points], linewidth=2, label=name)
    if len(series) > 1:
        points = sorted(totals.items())
        ax.plot(
            [b for b, _c in points],
            [c for _b, c in points],
            linewidth=2.5,
            linestyle=":",
            color=INK,
            label=_("Total"),
        )

    peak = max(totals.values(), default=0)
    ax.set_title(_("Players over the last {} hours ({})").format(hours, zone_label), color=INK)
    ax.set_ylabel(_("Player Count (Peak {})").format(peak), color=INK)
    ax.set_ylim(bottom=0, top=max(peak, 1) * 1.15)
    ax.tick_params(colors=INK)
    ax.grid(True, color=INK, alpha=GRID_ALPHA)
    for spine in ax.spines.values():
        spine.set_visible(False)
    # The buckets stay UTC-aware and matplotlib converts them: passing the zone to the formatter
    # is what moves the tick labels, rather than shifting the plotted values themselves
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%I:%M %p", tz=zone))

    legend = ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=min(len(series) + 1, 5),
        frameon=False,
    )
    for text in legend.get_texts():
        text.set_color(INK)

    fig.tight_layout()
    buffer = BytesIO()
    FigureCanvasAgg(fig).print_png(buffer)
    return buffer.getvalue()
