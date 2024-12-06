import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..db.tables import AppealGuild, AppealSubmission

log = logging.getLogger("red.vrt.appeals.listeners.messages")


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.id != self.bot.user.id:
            return
        if not message.embeds:
            return
        if not message.embeds[0].footer:
            return
        if not message.embeds[0].footer.text:
            return
        footer = message.embeds[0].footer.text
        parts = footer.split("Submission ID: ")
        if len(parts) != 2:
            return
        try:
            submission_id = int(parts[1])
        except ValueError:
            return

        submission: dict = (
            await AppealSubmission.select(AppealSubmission.all_columns())
            .where(AppealSubmission.id == submission_id)
            .output(load_json=True)
            .first()
        )
        if not submission:
            return
        await AppealSubmission.delete().where(AppealSubmission.id == submission_id)
        log.info(f"Deleted submission {submission_id} due to message deletion")
        appealguild = await AppealGuild.objects().get(AppealGuild.id == message.guild.id)
        if not appealguild:
            return
        channel = self.bot.get_channel(appealguild.alert_channel)
        if not channel:
            return
        perms = [
            channel.permissions_for(message.guild.me).view_channel,
            channel.permissions_for(message.guild.me).send_messages,
            channel.permissions_for(message.guild.me).embed_links,
        ]
        if not all(perms):
            return
        desc = f"Deleted submission `{submission_id}` due to message deletion"
        embed = discord.Embed(description=desc, color=await self.bot.get_embed_color(channel))
        try:
            user = await self.bot.get_or_fetch_user(submission["user_id"])
            username = f"{user.name} ({user.id})" if user else f"Unknown User ({submission['user_id']})"
        except discord.HTTPException:
            username = f"Unknown User ({submission['user_id']})"
        embed.add_field(name="Appeal Created By", value=username)
        embed.add_field(name="Status", value=submission["status"].capitalize())
        embed.set_footer(text=f"Submission ID: {submission_id}")
        if user:
            embed.set_thumbnail(url=user.display_avatar)

        for question, answer in submission["answers"].items():
            embed.add_field(name=question, value=answer, inline=False)

        await channel.send(embed=embed)
