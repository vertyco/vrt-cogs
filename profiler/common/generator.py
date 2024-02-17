from typing import List

import plotly.graph_objects as go
import plotly.io as pio

from .models import StatsProfile


def generate_line_graph(profile_data: List[StatsProfile]) -> bytes:
    # Extracting the total_tt and timestamp from each profile
    total_tt_values = [profile.total_tt for profile in profile_data]
    timestamps = [profile.timestamp for profile in profile_data]

    # Sort the data by timestamp to ensure the line graph is chronological
    sorted_data = sorted(zip(timestamps, total_tt_values), key=lambda x: x[0])
    sorted_timestamps, sorted_total_tt = zip(*sorted_data)

    # Creating the plot
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=sorted_timestamps, y=sorted_total_tt, mode="lines+markers", name="Total Execution Time"))

    # Customizing the plot
    fig.update_layout(
        title="Total Execution Time Over Time",
        xaxis_title="Time",
        yaxis_title="Total Execution Time (seconds)",
        xaxis=dict(
            tickformat="%Y-%m-%d\n%H:%M:%S"  # Adjust the format as per your needs
        ),
    )

    # Write the plot to bytes
    plot_bytes = pio.to_image(fig, format="png")
    return plot_bytes
