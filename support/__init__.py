import json
from pathlib import Path

from .support import Support

with open(Path(__file__).parent / "info.json") as fp:
    __red_end_user_data_statement__ = json.load(fp)["end_user_data_statement"]


async def setup(bot):
    cog = Support(bot)
    bot.add_cog(cog)
    await cog.cleanup()
    await cog.add_components()
