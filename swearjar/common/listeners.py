import logging

import discord
from redbot.core import bank, commands
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from .utils import calculate_fine, find_matches

log = logging.getLogger("red.vrt.swearjar")


class Listeners(MixinMeta):
    @commands.Cog.listener("on_message_without_command")
    async def check_for_swears(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not message.content:
            return
        member = message.author
        if not isinstance(member, discord.Member):
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        conf = await self.config.guild(message.guild).all()
        if not conf["enabled"] or not conf["words"]:
            return
        parent_id = getattr(message.channel, "parent_id", None)
        if message.channel.id in conf["ignored_channels"] or parent_id in conf["ignored_channels"]:
            return
        if any(role.id in conf["ignored_roles"] for role in member.roles):
            return
        matched = find_matches(message.content, conf["words"])
        if not matched:
            return
        fine = calculate_fine(matched, conf["words"], conf["default_fine"], conf["stack_fines"])
        if fine <= 0:
            return
        try:
            balance = await bank.get_balance(member)
            taken = min(fine, balance)
            if taken <= 0:
                return
            await bank.withdraw_credits(member, taken)
        except Exception as e:
            log.error("Failed to fine %s in %s", member.id, message.guild.id, exc_info=e)
            return
        try:
            jar_total = await self.config.guild(message.guild).jar_total()
            await self.config.guild(message.guild).jar_total.set(jar_total + taken)
            paid = await self.config.member(member).paid()
            await self.config.member(member).paid.set(paid + taken)
        except Exception as e:
            log.error(
                "Withdrew %s from %s in %s but failed to record it",
                taken,
                member.id,
                message.guild.id,
                exc_info=e,
            )
        if conf["respond"]:
            currency = await bank.get_currency_name(message.guild)
            try:
                await message.channel.send(
                    f"💰 {member.display_name} dropped {humanize_number(taken)} {currency} in the swear jar."
                )
            except discord.HTTPException as e:
                log.warning("Failed to send swear jar response in %s", message.channel.id, exc_info=e)
