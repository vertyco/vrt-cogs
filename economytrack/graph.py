import asyncio
from io import BytesIO

import discord
import pandas as pd
from plotly import express as px
from redbot.core.i18n import Translator, cog_i18n

from economytrack.abc import MixinMeta

_ = Translator("EconomyTrackCommands", __file__)


@cog_i18n(_)
class PlotGraph(MixinMeta):
    async def get_plot(self, df: pd.DataFrame, y_label: str) -> discord.File:
        return await asyncio.to_thread(self.make_plot, df, y_label)

    @staticmethod
    def make_plot(df: pd.DataFrame, y_label: str) -> discord.File:
        fig = px.line(
            df,
            template="plotly_dark",
            labels={"ts": _("Date"), "value": y_label},
        )
        fig.update_xaxes(tickformat="%I:%M %p\n%b %d %Y")
        fig.update_layout(
            showlegend=False,
        )
        bytefile = fig.to_image(format="png", width=800, height=500, scale=1)
        buffer = BytesIO(bytefile)
        buffer.seek(0)
        file = discord.File(buffer, filename="plot.png")
        buffer.close()
        return file
