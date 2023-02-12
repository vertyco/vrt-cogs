import json
from pathlib import Path

import discord

from .hunting import Hunting

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    if discord.__version__ > "1.7.3":
        await bot.add_cog(Hunting(bot))
    else:
        bot.add_cog(Hunting(bot))
