import asyncio
import json
import typing as t

import discord
from aiocache import cached
from redbot.core import bank, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number, humanize_timedelta
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import MessagePredicate, ReactionPredicate

from ..common.models import DB, CommandCost, GuildSettings

_ = Translator("ExtendedEconomy", __file__)
CTYPES = commands.Context | discord.app_commands.ContextMenu | discord.app_commands.Command


async def edit_delete_delay(message: discord.Message, new_content: str, delay: int = None):
    await message.edit(content=new_content, view=None)
    if delay:
        await message.delete(delay=delay)


def ctx_to_id(ctx: commands.Context):
    """Generate a unique ID for a context command"""
    parts = [
        str(ctx.author.id),
        str(ctx.guild.id if ctx.guild else 0),
        str(ctx.channel.id if ctx.guild else 0),
        str(int(ctx.message.created_at.timestamp())),
        ctx.command.qualified_name,
    ]
    return "-".join(parts)


def ctx_to_dict(c: t.Union[commands.Context, discord.Interaction]):
    if isinstance(c, discord.Interaction):
        info = {
            "type": "Interaction",
            "id": c.id,
            "user": c.user.id,
            "guild": c.guild.id if c.guild else None,
            "channel": c.channel.id,
        }
    else:
        info = {
            "type": "Context",
            "id": c.message.id,
            "user": c.author.id,
            "guild": c.guild.id if c.guild else None,
            "channel": c.channel.id,
        }
    return json.dumps(info, indent=2)


@cached(ttl=600)
async def get_cached_credits_name(guild: discord.Guild) -> str:
    return await bank.get_currency_name(guild)


def has_cost_check(command: CTYPES):
    """Check if a command already has the cost check attached to it"""
    for check in command.checks:
        if check.__qualname__ == "Checks.cost_check":
            return True
    return False


async def confirm_msg(ctx: t.Union[commands.Context, discord.Interaction]) -> t.Union[bool, None]:
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
    del_after = _("`Delete After:        `{}\n").format(humanize_timedelta(seconds=delay) if delay else _("Disabled"))
    txt = _(
        "# Extended Economy Settings\n"
        "`Transfer Tax:        `{}\n"
        "`Command Costs:       `{}\n"
        "`Global Bank:         `{}\n"
        "{}"
        "## Event Log Channels\n"
        "`Default Log Channel: `{}\n"
        "`Set Balance:         `{}\n"
        "`Transfer Credits:    `{}\n"
        "`Bank Wipe:           `{}\n"
        "`Prune Accounts:      `{}\n"
        "`Payday Claim:        `{}\n"
    ).format(
        f"{round(conf.transfer_tax * 100, 2)}%" if conf.transfer_tax else _("None"),
        len(conf.command_costs) or _("None"),
        is_global,
        del_after if owner else "",
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
        txt += _("`Auto Paydays:        `{}\n").format(conf.auto_payday_claim)
        txt += _("`Disable AutoPayday:  `{}\n").format(conf.auto_payday_disabled)
    else:
        txt += _("`Stack Paydays:       `{}\n").format(conf.stack_paydays)
        autoclaim = [f"<@&{r}>" for r in conf.auto_claim_roles]
        txt += _("`Auto Claim Roles:    `{}\n").format(", ".join(autoclaim) or not_set)
    txt += _("`Auto Claim Channel:  `{}\n").format(f"<#{conf.logs.auto_claim}>" if conf.logs.auto_claim else not_set)
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
