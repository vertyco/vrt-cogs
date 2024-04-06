import logging
import typing as t
from contextlib import suppress
from datetime import datetime

import discord
from redbot.core import bank, commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.extendedeconomy.listeners")
_ = Translator("ExtendedEconomy", __file__)


class Listeners(MixinMeta):
    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog):
        if cog.qualified_name in self.checks:
            return
        for cmd in cog.walk_commands():
            cmd.add_check(self.cost_check)
        for cmd in cog.walk_app_commands():
            cmd.add_check(self.cost_check)
        self.checks.add(cog.qualified_name)

    async def log_event(self, event: str, payload: t.NamedTuple):
        is_global = await bank.is_global()
        if event == "payday_claim":
            guild = payload.member.guild
        else:
            guild = getattr(payload, "guild", None)

        if not is_global and not guild:
            log.error(f"Guild is None for non-global bank event: {event}\n{payload}")
            return

        if is_global:
            logs = self.db.logs
        else:
            logs = self.db.get_conf(guild).logs

        channel_id = getattr(logs, event, 0) or logs.default_log_channel
        if not channel_id:
            return
        channel: discord.TextChannel = self.bot.get_channel(channel_id)
        if not channel:
            return
        event_map = {
            "set_balance": _("Set Balance"),
            "transfer_credits": _("Transfer Credits"),
            "bank_wipe": _("Bank Wipe"),
            "prune": _("Prune Accounts"),
            "set_global": _("Set Global"),
            "payday_claim": _("Payday Claim"),
        }
        currency = await bank.get_currency_name(guild)

        title = _("Bank Event: {}").format(event_map[event])
        color = await self.bot.get_embed_color(channel)
        embed = discord.Embed(title=title, color=color, timestamp=datetime.now())
        if event == "set_balance":
            embed.add_field(name=_("Recipient"), value=f"{payload.recipient.mention}\n`{payload.recipient.id}`")
            embed.add_field(name=_("Old Balance"), value=humanize_number(payload.recipient_old_balance))
            embed.add_field(name=_("New Balance"), value=humanize_number(payload.recipient_new_balance))
            if guild and is_global:
                embed.add_field(name=_("Guild"), value=guild.name)
        elif event == "transfer_credits":
            embed.add_field(name=_("Sender"), value=f"{payload.sender.mention}\n`{payload.sender.id}`")
            embed.add_field(name=_("Recipient"), value=f"{payload.recipient.mention}\n`{payload.recipient.id}`")
            embed.add_field(name=_("Transfer Amount"), value=f"{humanize_number(payload.transfer_amount)} {currency}")
            if guild and is_global:
                embed.add_field(name=_("Guild"), value=guild.name)
        elif event == "prune":
            if payload.user_id:
                embed.add_field(name=_("User ID"), value=payload.user_id)
            else:
                embed.add_field(name=_("Pruned Users"), value=humanize_number(len(payload.pruned_users)))
            if guild and is_global:
                embed.add_field(name=_("Guild"), value=guild.name)
        elif event == "payday_claim":
            embed.add_field(name=_("Recipient"), value=f"{payload.member.mention}\n`{payload.member.id}`")
            embed.add_field(name=_("Amount"), value=f"{humanize_number(payload.amount)} {currency}")
            embed.add_field(name=_("Old Balance"), value=humanize_number(payload.old_balance))
            embed.add_field(name=_("New Balance"), value=humanize_number(payload.new_balance))

            if is_global:
                embed.add_field(name=_("Guild"), value=payload.member.guild.name)
            else:
                embed.add_field(name=_("Channel"), value=payload.channel.mention)
        else:
            log.error(f"Unknown event type: {event}")
            return
        with suppress(discord.HTTPException, discord.Forbidden):
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_red_bank_set_balance(self, payload: t.NamedTuple):
        """Payload attributes:
        - recipient: Union[discord.Member, discord.User]
        - guild: Union[discord.Guild, None]
        - recipient_old_balance: int
        - recipient_new_balance: int
        """
        await self.log_event("set_balance", payload)

    @commands.Cog.listener()
    async def on_red_bank_transfer_credits(self, payload: t.NamedTuple):
        """Payload attributes:
        - sender: Union[discord.Member, discord.User]
        - recipient: Union[discord.Member, discord.User]
        - guild: Union[discord.Guild, None]
        - transfer_amount: int
        - sender_new_balance: int
        - recipient_new_balance: int
        """
        await self.log_event("transfer_credits", payload)

    @commands.Cog.listener()
    async def on_red_bank_wipe(self, scope: t.Optional[int] = None):
        """scope: int (-1 for global, None for all members, guild_id for server bank)"""
        if scope == -1 or scope is None:
            log_channel_id = self.db.logs.bank_wipe or self.db.logs.default_log_channel
            txt = _("Global bank has been wiped!")
        elif scope is None:
            log_channel_id = self.db.logs.bank_wipe or self.db.logs.default_log_channel
            txt = _("All bank accounts for all guilds have been wiped!")
        else:
            # Scope is a guild ID
            guild: discord.Guild = self.bot.get_guild(scope)
            if not guild:
                return
            conf = self.db.get_conf(guild)
            log_channel_id = conf.logs.bank_wipe or conf.logs.default_log_channel
            txt = _("Bank accounts have been wiped!")

        if not log_channel_id:
            return
        log_channel: discord.TextChannel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(
            title=_("Bank Wipe"),
            description=txt,
            color=await self.bot.get_embed_color(log_channel),
        )
        with suppress(discord.HTTPException, discord.Forbidden):
            await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_red_bank_prune(self, payload: t.NamedTuple):
        """Payload attributes:
        - guild: Union[discord.Guild, None]
        - user_id: Union[int, None]
        - scope: int (1 for global, 2 for server, 3 for user)
        - pruned_users: list[int(user_id)] or dict[int(guild_id), list[int(user_id)]]
        """
        await self.log_event("prune", payload)

    @commands.Cog.listener()
    async def on_red_bank_set_global(self, is_global: bool):
        """is_global: True if global bank, False if server bank"""
        txt = _("Bank has been set to Global!") if is_global else _("Bank has been set to per-server!")
        log_channel_id = self.db.logs.set_global or self.db.logs.default_log_channel
        if not log_channel_id:
            return
        log_channel: discord.TextChannel = self.bot.get_channel(log_channel_id)
        if not log_channel:
            return
        embed = discord.Embed(
            title=_("Set Global Bank"),
            description=txt,
            color=await self.bot.get_embed_color(log_channel),
        )
        # with suppress(discord.HTTPException, discord.Forbidden):
        await log_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_red_economy_payday_claim(self, payload: t.NamedTuple):
        """Payload attributes:
        - member: discord.Member
        - channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel]
        - amount: int
        - old_balance: int
        - new_balance: int
        """
        await self.log_event("payday_claim", payload)
