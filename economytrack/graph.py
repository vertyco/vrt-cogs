import os
from concurrent.futures.thread import ThreadPoolExecutor
from io import BytesIO

import discord
import pandas as pd
from plotly import express as px
from redbot.core.i18n import Translator, cog_i18n

from economytrack.abc import MixinMeta

_ = Translator("EconomyTrackCommands", __file__)


@cog_i18n(_)
class PlotGraph(MixinMeta):
    def __init__(self):
        self.executor = ThreadPoolExecutor(
            max_workers=os.cpu_count() if os.cpu_count() else 4,
            thread_name_prefix="economytrack_plot"
        )

    async def get_plot(self, df: pd.DataFrame) -> discord.File:
        return await self.bot.loop.run_in_executor(
            self.executor,
            lambda: self.make_plot(df)
        )

    @staticmethod
    def make_plot(df: pd.DataFrame) -> discord.File:
        fig = px.line(
            df,
            template="plotly_dark",
            labels={"ts": _("Date"), "value": _("Total Economy Credits")}
        )
        fig.update_xaxes(
            tickformat="%I:%M %p\n%b %d %Y"
        )
        fig.update_layout(
            showlegend=False,

        )
        bytefile = fig.to_image(format="png", width=800, height=500, scale=1)
        buffer = BytesIO(bytefile)
        buffer.seek(0)
        file = discord.File(buffer, filename="plot.png")
        buffer.close()
        return file
