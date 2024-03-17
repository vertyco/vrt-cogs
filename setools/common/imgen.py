from io import StringIO

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
        asteroid_x, asteroid_y, asteroid_z = zip(
            *[(ast.Position.X, ast.Position.Y, ast.Position.Z) for ast in asteroids]
        )
        traces.append(
            go.Scatter3d(
                x=asteroid_x,
                y=asteroid_y,
                z=asteroid_z,
                mode="markers",
                name="Asteroids",
                marker=dict(color="gray", size=5),
            )
        )

    if objects:
        for obj in objects:
            color = "red" if obj.Kind == "FloatingObject" else "yellow"
            traces.append(
                go.Scatter3d(
                    x=[obj.Position.X],
                    y=[obj.Position.Y],
                    z=[obj.Position.Z],
                    mode="markers",
                    name=obj.DisplayName,
                    marker=dict(color=color, size=3),
                )
            )

    if grids:
        for grid in grids:
            color = "green" if grid.IsPowered else "orange"
            traces.append(
                go.Scatter3d(
                    x=[grid.Position.X],
                    y=[grid.Position.Y],
                    z=[grid.Position.Z],
                    mode="markers",
                    name=f"{grid.DisplayName} {grid.BlocksCount} ({grid.GridSize.value})",
                    marker=dict(color=color, size=6),
                )
            )

    if planets:
        for planet in planets:
            traces.append(
                go.Scatter3d(
                    x=[planet.Position.X],
                    y=[planet.Position.Y],
                    z=[planet.Position.Z],
                    mode="markers",
                    name=planet.DisplayName,
                    marker=dict(color="blue", size=10),
                )
            )

    fig = go.Figure(data=traces)
    fig.update_layout(
        margin=dict(l=0, r=0, b=0, t=0),
        title="World Visualization",
        scene=dict(xaxis_title="X Axis", yaxis_title="Y Axis", zaxis_title="Z Axis"),
    )

    buffer = StringIO()
    fig.write_html(file=buffer)
    return buffer.getvalue()
