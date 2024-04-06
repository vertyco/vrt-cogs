import asyncio
import typing as t

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number, humanize_timedelta
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

from ..common.models import DB, CommandCost, GuildSettings

_ = Translator("ExtendedEconomy", __file__)


async def confirm_msg(ctx: t.Union[commands.Context, discord.Interaction]):
    """Wait for user to respond yes or no"""
    if isinstance(ctx, discord.Interaction):
        pred = MessagePredicate.yes_or_no(channel=ctx.channel, user=ctx.user)
        bot = ctx.client
    else:
        pred = MessagePredicate.yes_or_no(ctx)
        bot = ctx.bot
    try:
        await bot.wait_for("message", check=pred, timeout=30)
    except asyncio.TimeoutError:
        return None
    else:
        return pred.result


async def confirm_msg_reaction(message: discord.Message, author: t.Union[discord.Member, discord.User], bot: Red):
    """Wait for user to react with a checkmark or x"""
    start_adding_reactions(message, ReactionPredicate.YES_OR_NO_EMOJIS)
    pred = ReactionPredicate.yes_or_no(message, author)
    try:
        await bot.wait_for("reaction_add", check=pred, timeout=30)
    except asyncio.TimeoutError:
        return None
    else:
        return pred.result


def format_settings(
    conf: t.Union[DB, GuildSettings], is_global: bool, owner: bool, delay: t.Union[int, None]
) -> discord.Embed:
    not_set = _("Not Set")
    txt = _(
        "# Extended Economy Settings\n"
        "`Command Costs:       `{}\n"
        "`Global Bank:         `{}\n"
        "## Event Log Channels\n"
        "`Default Log Channel: `{}\n"
        "`Set Balance:         `{}\n"
        "`Transfer Credits:    `{}\n"
        "`Bank Wipe:           `{}\n"
        "`Prune Accounts:      `{}\n"
        "`Payday Claim:        `{}\n"
    ).format(
        len(conf.command_costs) or _("None"),
        is_global,
        f"<#{conf.logs.default_log_channel}>" if conf.logs.default_log_channel else not_set,
        f"<#{conf.logs.set_balance}>" if conf.logs.set_balance else not_set,
        f"<#{conf.logs.transfer_credits}>" if conf.logs.transfer_credits else not_set,
        f"<#{conf.logs.bank_wipe}>" if conf.logs.bank_wipe else not_set,
        f"<#{conf.logs.prune}>" if conf.logs.prune else not_set,
        f"<#{conf.logs.payday_claim}>" if conf.logs.payday_claim else not_set,
    )
    if is_global:
        txt += _("`Set Global:          `{}\n").format(
            f"<#{conf.logs.set_global}>" if conf.logs.set_global else not_set
        )
    if owner:
        txt += _("`Delete After:        `{}\n").format(humanize_timedelta(seconds=delay) if delay else _("Disabled"))
    if isinstance(conf, DB):
        footer = _("Showing settings for global bank")
    else:
        footer = _("Showing settings for this server")
    embed = discord.Embed(description=txt, color=discord.Color.green())
    embed.set_footer(text=footer)
    return embed


def format_command_txt(com: CommandCost):
    txt = _(
        "`Cost:        `{}\n"
        "`Duration:    `{}\n"
        "`Level:       `{}\n"
        "`Prompt:      `{}\n"
        "`Modifier:    `{}\n"
        "`Value:       `{}\n"
        "`Cached Uses: `{}\n"
    ).format(
        humanize_number(com.cost),
        humanize_timedelta(seconds=com.duration),
        com.level,
        com.prompt,
        com.modifier,
        com.value,
        humanize_number(len(com.uses)),
    )
    return txt
