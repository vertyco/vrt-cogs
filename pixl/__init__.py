import json
from pathlib import Path

import discord
from redbot.core.bot import Red

from .pixl import Pixl

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot: Red):
    cog = Pixl(bot)
    if discord.version_info.major >= 2:
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
