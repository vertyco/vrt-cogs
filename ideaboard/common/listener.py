import logging
from contextlib import suppress

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.ideaboard.listeners")

_ = Translator("IdeaBoard", __file__)


class Listeners(MixinMeta):
    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema = {
            "name": "get_user_suggestion_stats",
            "description": (
                "Get statistics about the suggestions the user you are speaking to has made.\n"
                "This command will fetch total upvotes, downvotes, wins, losses, and more for suggestions the user may have made in the community.\n"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
        await cog.register_function(self.qualified_name, schema)

    async def get_user_suggestion_stats(self, user: discord.Member, *args, **kwargs):
        """Get the number of suggestions a user has submitted"""
        conf = self.db.get_conf(user.guild)
        profile = conf.get_profile(user)
        txt = (
            f"Suggestion Stats for {user.display_name}\n"
            f"Total suggestions that the user made: {profile.suggestions_made}\n"
            f"Suggestions user made that were approved: {profile.suggestions_approved}\n"
            f"Suggestions user made that were denied: {profile.suggestions_denied}\n"
            f"Total upvotes: {profile.upvotes}\n"
            f"Total downvotes: {profile.downvotes}\n"
            f"Suggestions user voted on that won in their favor: {profile.wins}\n"
            f"Suggestions user voted on that did not go in their favor: {profile.losses}\n"
        )
        return txt

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Check if the message deleted was a suggestions"""
        if message.guild is None:
            return
        if not message.content.startswith("Suggestion #"):
            return
        conf = self.db.get_conf(message.guild)
        for num, suggestion in conf.suggestions.copy().items():
            if suggestion.message_id != message.id:
                continue
            profile = conf.get_profile(message.author)
            profile.suggestions_made -= 1
            for uid in suggestion.upvotes:
                profile = conf.get_profile(uid)
                profile.upvotes -= 1
            for uid in suggestion.downvotes:
                profile = conf.get_profile(uid)
                profile.downvotes -= 1

            if thread_id := suggestion.thread_id:
                thread = await message.guild.fetch_channel(thread_id)
                if thread:
                    with suppress(discord.HTTPException):
                        if conf.delete_threads:
                            await thread.delete()
                        else:
                            newname = thread.name + _(" [Deleted]")
                            embed = discord.Embed(
                                color=discord.Color.dark_red(),
                                description=suggestion.content,
                                title=_("Deleted Suggestion"),
                            )
                            await thread.send(embed=embed)
                            await thread.edit(archived=True, locked=True, name=newname)

            del conf.suggestions[num]
            log.info(f"Suggestion #{num} had its message deleted in {message.guild.name} ({message.guild.id})")
            await self.save()
            break

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Remove all votes from a user when they leave the server"""
        if member.guild is None:
            return
        conf = self.db.get_conf(member.guild)
        if member.id not in conf.profiles:
            return
        purged = False
        for num, suggestion in conf.suggestions.copy().items():
            if member.id in suggestion.upvotes:
                conf.suggestions[num].upvotes.remove(member.id)
                purged = True
            if member.id in suggestion.downvotes:
                conf.suggestions[num].downvotes.remove(member.id)
                purged = True
        if purged:
            await self.save()
            log.info(
                f"Votes from {member.display_name} ({member.id}) were purged in {member.guild.name} ({member.guild.id})"
            )
