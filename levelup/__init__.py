# redgettext base.py generator.py levelup.py utils/formatter.py --command-docstring
import asyncio
import logging

from redbot.core import VersionInfo, version_info
from redbot.core.bot import Red
from redbot.core.utils import get_end_user_data_statement

from .levelup import LevelUp

__red_end_user_data_statement__ = get_end_user_data_statement(__file__)
log = logging.getLogger("red.vrt.levelup")


async def setup(bot: Red):
    asyncio.create_task(setup_after_ready(bot))


async def setup_after_ready(bot: Red):
    await bot.wait_until_red_ready()
    cog = LevelUp(bot)
    if version_info >= VersionInfo.from_str("3.5.0"):
        await bot.add_cog(cog)
    else:
        bot.add_cog(cog)
    await cog.initialize()
