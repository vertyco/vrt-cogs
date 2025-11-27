import pandas as pd
from plotly import graph_objects as go


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
