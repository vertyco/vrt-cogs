import calendar
import logging
import typing as t
from contextlib import suppress
from datetime import datetime, timezone

import discord
from discord.ext import tasks
from redbot.core import Config, bank
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number, text_to_file

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.extendedeconomy.tasks")
_ = Translator("ExtendedEconomy", __file__)


class Tasks(MixinMeta):
    @tasks.loop(seconds=60)
    async def auto_paydays(self):
        if not self.db.auto_payday_claim:
            return
        cog = self.bot.get_cog("Economy")
        if cog is None:
            return
        eco_conf: Config = cog.config
        is_global = await bank.is_global()
        cur_time = calendar.timegm(datetime.now(tz=timezone.utc).utctimetuple())
        if is_global:
            bankgroup = bank._config._get_base_group(bank._config.USER)
            ecogroup = eco_conf._get_base_group(eco_conf.USER)
            accounts: t.Dict[str, dict] = await bankgroup.all()
            ecousers: t.Dict[str, dict] = await ecogroup.all()
            max_bal = await bank.get_max_balance()
            payday_time = await eco_conf.PAYDAY_TIME()
            payday_credits = await eco_conf.PAYDAY_CREDITS()

            updated = []
            for user in self.bot.users:
                uid = str(user.id)
                if uid not in accounts or uid not in ecousers:
                    # Reduce unnecessary writes for users that havent used economy
                    continue
                next_payday = ecousers[uid].get("next_payday", 0) + payday_time
                if cur_time < next_payday:
                    # Not ready yet
                    continue
                accounts[uid]["balance"] = min(max_bal, accounts[uid]["balance"] + payday_credits)
                ecousers[uid]["next_payday"] = cur_time
                updated.append((f"{user.name} ({user.id}): {humanize_number(payday_credits)}\n", payday_credits))

            if updated:
                await bankgroup.set(accounts)
                await ecogroup.set(ecousers)
                if self.db.logs.auto_claim:
                    log.info(f"Claimed {len(updated)} global paydays")
                    ordered = sorted(updated, key=lambda x: x[1], reverse=True)
                    claimed = "\n".join([x[0] for x in ordered])
                    channel = self.bot.get_channel(self.db.logs.auto_claim)
                    if channel is not None:
                        with suppress(discord.HTTPException):
                            await channel.send(
                                f"Claimed {len(updated)} global paydays",
                                file=text_to_file(claimed, "paydays.txt"),
                            )
        else:
            keys = list(self.db.configs.keys())
            for guild_id in keys:
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    continue
                conf = self.db.configs[guild_id]
                if not conf.auto_claim_roles:
                    continue

                bankgroup = bank._config._get_base_group(bank._config.MEMBER, str(guild_id))
                ecogroup = eco_conf._get_base_group(eco_conf.MEMBER, str(guild_id))
                accounts: t.Dict[str, dict] = await bankgroup.all()
                ecousers: t.Dict[str, dict] = await ecogroup.all()
                max_bal = await bank.get_max_balance(guild)
                payday_time = await eco_conf.guild(guild).PAYDAY_TIME()
                payday_credits = await eco_conf.guild(guild).PAYDAY_CREDITS()
                payday_roles: t.Dict[int, dict] = await eco_conf.all_roles()

                updated = []
                for member in guild.members:
                    uid = str(member.id)
                    if uid not in accounts or uid not in ecousers:
                        # Reduce unnecessary writes for members that havent used economy
                        continue
                    next_payday = ecousers[uid].get("next_payday", 0) + payday_time
                    if cur_time < next_payday:
                        # Not ready yet
                        continue

                    to_give = payday_credits
                    can_autoclaim = False
                    for role in member.roles:
                        if role.id in payday_roles:
                            role_credits = payday_roles[role.id]["PAYDAY_CREDITS"]
                            if conf.stack_paydays:
                                to_give += role_credits
                            elif role_credits > to_give:
                                to_give = role_credits

                        if role.id in conf.auto_claim_roles:
                            can_autoclaim = True

                    if not can_autoclaim:
                        continue

                    accounts[uid]["balance"] = min(max_bal, accounts[uid]["balance"] + to_give)
                    ecousers[uid]["next_payday"] = cur_time
                    updated.append((f"{member.name} ({member.id}): {humanize_number(to_give)}\n", to_give))

                if updated:
                    await bankgroup.set(accounts)
                    await ecogroup.set(ecousers)
                    if conf.logs.auto_claim:
                        log.debug(f"Claimed {len(updated)} paydays in {guild.name}")
                        ordered = sorted(updated, key=lambda x: x[1], reverse=True)
                        claimed = "\n".join([x[0] for x in ordered])
                        channel = guild.get_channel(conf.logs.auto_claim)
                        if channel is not None:
                            with suppress(discord.HTTPException):
                                await channel.send(
                                    f"Claimed {len(updated)} paydays",
                                    file=text_to_file(claimed, "paydays.txt"),
                                )
