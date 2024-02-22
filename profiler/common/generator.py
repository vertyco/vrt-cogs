import typing as t
from datetime import datetime

import plotly.graph_objects as go
import plotly.io as pio
from redbot.core.utils.chat_formatting import humanize_timedelta

from .models import StatsProfile


def generate_line_graph(profile_data: t.List[StatsProfile]) -> bytes:
    sorted_data = sorted(profile_data, key=lambda x: x.timestamp)
    # Extracting the total_tt and timestamp from each profile
    execution_times: t.List[float] = [profile.total_tt * 1000 for profile in sorted_data]
    timestamps: t.List[datetime] = [profile.timestamp for profile in sorted_data]

    delta = timestamps[-1] - timestamps[0]
    humanized_delta = humanize_timedelta(timedelta=delta)

    # Creating the plot
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=timestamps, y=execution_times, mode="lines+markers", name="Total Execution Time"))

    # Customizing the plot
    fig.update_layout(
        title=f"Execution Times Over {humanized_delta}",
        xaxis_title="Time",
        yaxis_title="Execution Time (milliseconds)",
        xaxis=dict(tickformat="%Y-%m-%d\n%I:%M:%S %p"),
        template="plotly_dark",
    )
    # Write the plot to bytes
    plot_bytes = pio.to_image(fig, format="png")
    return plot_bytes
