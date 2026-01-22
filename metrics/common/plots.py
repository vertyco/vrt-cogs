import pandas as pd
from plotly import graph_objects as go
from plotly.subplots import make_subplots


def render_bank_plot(
    plot_df: pd.DataFrame,
    main_column: str,
    rolling_column: str,
    rolling_color: str = "#15FF00",
) -> bytes:
    times = plot_df["Date"]
    x_values = times.to_numpy(copy=False)

    fig = go.Figure()
    for name, color, width, dash, opacity in (
        (main_column, "#5865F2", 1.8, "dot", 0.55),
        (rolling_column, rolling_color, 3.0, "solid", 1.0),
    ):
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=plot_df[name].to_numpy(copy=False),
                mode="lines",
                name=name,
                line=dict(color=color, width=width, dash=dash),
                opacity=opacity,
            )
        )

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=50, r=50, t=80, b=60),
        legend=dict(orientation="h", y=1.1, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=14)),
    )
    fig.update_xaxes(showgrid=False, tickformat="%b %d\n%Y")
    fig.update_yaxes(title=main_column)

    return fig.to_image(format="png", width=1280, height=720, scale=2)


def render_member_plot(
    plot_df: pd.DataFrame,
    dataset_label: str,
    rolling_column: str,
    rolling_color: str,
) -> bytes:
    return render_bank_plot(plot_df, dataset_label, rolling_column, rolling_color)


def render_performance_plot(
    plot_df: pd.DataFrame,
    dataset_label: str,
    rolling_column: str,
) -> bytes:
    return render_bank_plot(plot_df, dataset_label, rolling_column)


def render_multi_metric_plot(
    df: pd.DataFrame,
    metric_keys: list[str],
    metric_map: dict[str, tuple[str, str]],
    rolling_window: int,
) -> bytes:
    """
    Render a multi-series plot with multiple metrics on the same graph.
    Uses dual y-axes when metric scales differ significantly.

    Args:
        df: DataFrame with datetime index and metric columns.
        metric_keys: List of column names to plot.
        metric_map: Dict mapping column names to (label, color) tuples.
        rolling_window: Window size for rolling average.

    Returns:
        PNG image bytes of the rendered graph.
    """

    x_values = df.index.to_numpy(copy=False)

    # Calculate ranges to determine if we need dual y-axes
    metric_ranges: dict[str, tuple[float, float]] = {}
    for metric_key in metric_keys:
        if metric_key in df.columns:
            col = df[metric_key].dropna()
            if len(col) > 0:
                metric_ranges[metric_key] = (col.min(), col.max())

    # Determine if we need dual y-axes (>10x difference in max values)
    use_secondary = False
    secondary_metrics: set[str] = set()
    if len(metric_ranges) >= 2:
        max_values = [(k, v[1]) for k, v in metric_ranges.items()]
        max_values.sort(key=lambda x: x[1], reverse=True)
        largest_max = max_values[0][1] if max_values[0][1] > 0 else 1
        for k, max_val in max_values[1:]:
            if largest_max / (max_val if max_val > 0 else 1) > 10:
                secondary_metrics.add(k)
                use_secondary = True

    if use_secondary:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
    else:
        fig = go.Figure()

    for metric_key in metric_keys:
        if metric_key not in df.columns:
            continue

        label, color = metric_map.get(metric_key, (metric_key, "#5865F2"))
        raw_values = df[metric_key].to_numpy(copy=False)
        is_secondary = metric_key in secondary_metrics

        # Add raw data trace (faint dotted line)
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=raw_values,
                mode="lines",
                name=f"{label} (raw)",
                line=dict(color=color, width=1.2, dash="dot"),
                opacity=0.4,
                showlegend=False,
            ),
            secondary_y=is_secondary if use_secondary else None,
        )

        # Add rolling average trace (solid line)
        if rolling_window > 1 and len(df) >= rolling_window:
            rolling_values = df[metric_key].rolling(window=rolling_window, min_periods=1).mean()
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=rolling_values.to_numpy(copy=False),
                    mode="lines",
                    name=label + (" (right)" if is_secondary else ""),
                    line=dict(color=color, width=2.5),
                    opacity=1.0,
                ),
                secondary_y=is_secondary if use_secondary else None,
            )
        else:
            # If not enough data for rolling, just show raw as main
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=raw_values,
                    mode="lines",
                    name=label + (" (right)" if is_secondary else ""),
                    line=dict(color=color, width=2.5),
                    opacity=1.0,
                ),
                secondary_y=is_secondary if use_secondary else None,
            )

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=50, r=50, t=80, b=60),
        legend=dict(
            orientation="h",
            y=1.15,
            x=0.5,
            xanchor="center",
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        ),
    )
    fig.update_xaxes(showgrid=False, tickformat="%b %d\n%Y")
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.1)")
    if use_secondary:
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.1)", secondary_y=True)

    return fig.to_image(format="png", width=1280, height=720, scale=2)
