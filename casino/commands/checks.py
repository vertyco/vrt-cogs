import asyncio
import logging

from redbot.core import commands
from redbot.core.i18n import Translator

from ..common.perms import can_manage

log = logging.getLogger("red.vrt.casino")
_ = Translator("Casino", __file__)


async def ready(ctx) -> bool:
    """Commands wait for the database, which opens a moment after the bot starts"""
    try:
        await asyncio.wait_for(ctx.cog.ready.wait(), 30)
    except asyncio.TimeoutError as e:
        log.debug("A command waited 30 seconds for the casino database", exc_info=e)
        raise commands.UserFeedbackCheckFailure(_("The casino is still opening. Try again in a moment.")) from e
    return True


def manager():
    """Server admins in server mode; only the bot owner in global mode"""

    async def predicate(ctx) -> bool:
        await ready(ctx)
        global_mode = await ctx.cog.store.global_mode()
        if await can_manage(ctx.bot, ctx.author, global_mode):
            return True
        # A server admin who would pass in server mode is told why they can't here
        if global_mode and await can_manage(ctx.bot, ctx.author, False):
            raise commands.UserFeedbackCheckFailure(_("Only the bot owner can do that."))
        return False

    return commands.check(predicate)
