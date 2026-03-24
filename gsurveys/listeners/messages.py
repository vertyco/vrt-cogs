import logging
import re

import discord
from redbot.core import bank, commands

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.gsurveys")

USER_ID_PATTERN = re.compile(r"Discord User ID:\s*(\d{17,20})", re.IGNORECASE)


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if not message.webhook_id:
            return

        # Check if this webhook belongs to a configured survey
        result = self.db.find_survey_by_webhook(message.guild.id, message.webhook_id)
        if not result:
            return

        survey_id, survey = result

        # Always delete webhook messages to keep the channel clean and prevent info leakage
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        if not survey.enabled:
            return

        # Extract Discord user ID from the message content
        match = USER_ID_PATTERN.search(message.content)
        if not match:
            log.debug("Webhook message for survey '%s' but no Discord ID found", survey.name)
            return

        user_id = int(match.group(1))

        # Check if user already completed this survey
        if user_id in survey.completions:
            log.debug("User %s already completed survey '%s'", user_id, survey.name)
            return

        # Find the member
        guild = message.guild
        member = guild.get_member(user_id)
        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except (discord.NotFound, discord.HTTPException):
                log.debug("User %s not found in guild for survey '%s'", user_id, survey.name)
                return

        # Deposit credits
        try:
            await bank.deposit_credits(member, survey.reward)
        except bank.errors.BalanceTooHigh as e:
            await bank.set_balance(member, e.max_balance)

        # Track completion
        survey.completions.add(user_id)
        self.save()

        currency_name = await bank.get_currency_name(guild)
        thank_you = (
            f"Thank you for completing the **{survey.name}** survey! "
            f"You've been rewarded **{survey.reward}** {currency_name}."
        )

        # DM the user, fall back to notify channel if DMs are closed
        conf = self.db.get_conf(guild)
        dm_failed = False
        try:
            await member.send(thank_you)
        except discord.HTTPException:
            dm_failed = True

        if dm_failed and conf.notify_channel:
            notify = guild.get_channel(conf.notify_channel)
            if notify:
                try:
                    await notify.send(f"{member.mention} {thank_you}")
                except discord.HTTPException:
                    pass

        # Log to the log channel
        if conf.log_channel:
            log_ch = guild.get_channel(conf.log_channel)
            if log_ch:
                try:
                    await log_ch.send(
                        f"**{member}** (`{user_id}`) completed survey **{survey.name}** "
                        f"and was rewarded **{survey.reward}** {currency_name}."
                    )
                except discord.HTTPException:
                    pass

        log.info(
            "Rewarded %s (%s) with %s credits for survey '%s'",
            member,
            user_id,
            survey.reward,
            survey.name,
        )
