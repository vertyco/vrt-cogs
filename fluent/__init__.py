import json
from pathlib import Path

import discord

from .fluent import Fluent

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]

___red_end_user_data_statement__ = (
    "This cog does not persistently store data about users. This cog uses google's free translator api"
)


async def setup(bot):
    cog = Fluent(bot)
    if discord.__version__ > "1.7.3":
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
