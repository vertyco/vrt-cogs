from io import BytesIO

import discord
import plotly.express as px


def generate_pie_chart(labels: list, sizes: list, title: str) -> discord.File:
    fig = px.pie(
        names=labels,
        values=sizes,
        title=title,
        hole=0.3,
    )

    marker = dict(line=dict(color="#ffffff", width=2))
    fig.update_traces(textposition="inside", textinfo="percent+label", marker=marker)
    fig.update_layout(
        font_color="rgb(255,255,255)",
        font_size=20,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    buffer = BytesIO()
    fig.write_image(buffer, format="webp", scale=2)
    buffer.seek(0)
    return discord.File(buffer, filename="pie.webp")
