import json
from pathlib import Path

import discord

from .upgradechat import UpgradeChat

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = UpgradeChat(bot)
    if discord.__version__ > "1.7.3":
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
