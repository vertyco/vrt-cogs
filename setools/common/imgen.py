import math
from io import StringIO

import numpy as np
import plotly.graph_objects as go

from ..vragepy.responses import Asteroid, FloatingObject, Grid, Planet


def generate_visualization(
    asteroids: list[Asteroid],
    planets: list[Planet],
    grids: list[Grid],
    objects: list[FloatingObject],
) -> str:
    traces = []

    if asteroids:
        asteroid_x, asteroid_y, asteroid_z, hover_text = zip(
            *[
                (
                    ast.Position.X,
                    ast.Position.Y,
                    ast.Position.Z,
                    f"{ast.DisplayName}<br>ID: {ast.EntityId}<br>Position: {ast.pos}",
                )
                for ast in asteroids
            ]
        )
        traces.append(
            go.Scatter3d(
                x=asteroid_x,
                y=asteroid_y,
                z=asteroid_z,
                mode="markers",
                name="Asteroids",
                marker=dict(color="gray", size=3),
                text=hover_text,
                hoverinfo="text",
            )
        )

    if objects:
        obj_x, obj_y, obj_z, obj_sizes, obj_hover_info = [], [], [], [], []
        for obj in objects:
            obj_x.append(obj.Position.X)
            obj_y.append(obj.Position.Y)
            obj_z.append(obj.Position.Z)
            # Scale size based on Mass
            obj_sizes.append(max(1, math.log(obj.Mass) / 2))
            hover_text = (
                f"{obj.DisplayName}<br>"
                f"EntityId: {obj.EntityId}<br>"
                f"Mass: {obj.Mass} kg<br>"
                f"Speed: {obj.LinearSpeed} m/s<br>"
                f"DistanceToPlayer: {obj.DistanceToPlayer} m<br>"
                f"Position: {obj.pos}"
            )
            obj_hover_info.append(hover_text)

        traces.append(
            go.Scatter3d(
                x=obj_x,
                y=obj_y,
                z=obj_z,
                mode="markers",
                marker=dict(color="magenta", size=obj_sizes),
                text=obj_hover_info,
                hoverinfo="text",
                name="Floating Objects",
            )
        )

    planet_size = 8
    if grids:
        grids.sort(key=lambda x: x.PCU, reverse=True)
        for grid in grids:
            color = "green" if grid.IsPowered else "red"
            size = np.sqrt(grid.BlocksCount) * (0.5 if grid.GridSize == "Large" else 0.1)
            planet_size = max(planet_size, size * 2)
            hover_text = (
                f"{grid.DisplayName}<br>"
                f"Owner ID: {grid.OwnerSteamId}<br>"
                f"EntityId: {grid.EntityId}<br>"
                f"GridSize: {grid.GridSize.value}<br>"
                f"PCU: {grid.PCU}<br>"
                f"Blocks: {grid.BlocksCount}<br>"
                f"Mass: {grid.Mass} kg<br>"
                f"Position: {grid.pos}"
            )
            name = grid.DisplayName
            if "large" not in name.lower() and "small" not in name.lower():
                name = f"{name} ({grid.GridSize.value})[PCU: {grid.PCU}]"
            else:
                name = f"{name}[PCU: {grid.PCU}]"

            traces.append(
                go.Scatter3d(
                    x=[grid.Position.X],
                    y=[grid.Position.Y],
                    z=[grid.Position.Z],
                    mode="markers",
                    marker=dict(color=color, size=size),
                    text=hover_text,
                    hoverinfo="text",
                    name=name,
                )
            )

    if planets:
        for planet in planets:
            name = planet.DisplayName
            if "-" in name:
                name = name.split("-")[0]

            hover_info = f"{planet.DisplayName}<br>EntityId: {planet.EntityId}<br>Position: {planet.pos}"
            traces.append(
                go.Scatter3d(
                    x=[planet.Position.X],
                    y=[planet.Position.Y],
                    z=[planet.Position.Z],
                    mode="markers",
                    name=name,
                    marker=dict(color="blue", size=planet_size),
                    text=hover_info,
                    hoverinfo="text",
                )
            )

    fig = go.Figure(data=traces)
    fig.update_layout(
        title="Space Objects Visualization",
        margin=dict(l=0, r=0, b=0, t=0),
        paper_bgcolor="rgba(0, 0, 0, 1)",  # Dark background for the outer padding area
        plot_bgcolor="rgba(0, 0, 0, 1)",  # Dark background inside the plot area
        scene=dict(
            xaxis_title="X Axis",
            yaxis_title="Y Axis",
            zaxis_title="Z Axis",
            xaxis=dict(
                backgroundcolor="rgb(32, 32, 32)",
                gridcolor="gray",
                showbackground=True,
                zerolinecolor="gray",
            ),
            yaxis=dict(backgroundcolor="rgb(32, 32, 32)", gridcolor="gray", showbackground=True, zerolinecolor="gray"),
            zaxis=dict(backgroundcolor="rgb(32, 32, 32)", gridcolor="gray", showbackground=True, zerolinecolor="gray"),
            bgcolor="rgb(0, 0, 0)",  # Setting the overall background color for the 3D space
        ),
        font=dict(color="white"),  # Text color for dark mode
    )

    buffer = StringIO()
    fig.write_html(file=buffer, include_mathjax="cdn")
    return buffer.getvalue()
