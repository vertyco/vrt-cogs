import logging
import typing as t
from contextlib import suppress
from datetime import datetime
from uuid import uuid4

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_timedelta

from ..abc import MixinMeta
from ..common.models import Suggestion
from ..views.voteview import VoteView

log = logging.getLogger("red.vrt.ideaboard.commands.user")
_ = Translator("IdeaBoard", __file__)


@cog_i18n(_)
class User(MixinMeta):
    @commands.hybrid_command(name="idea", aliases=["suggest"], description=_("Share an idea/make a suggestion."))
    @app_commands.describe(content="Your idea or suggestion")
    @commands.guild_only()
    @commands.bot_has_guild_permissions(send_messages=True, embed_links=True, create_public_threads=True)
    async def idea(self, ctx: commands.Context, *, content: str):
        """Share an idea/make a suggestion."""

        async def resp(txt: str):
            """Return a response to the user, and delete their message if possible."""
            if ctx.interaction:
                try:
                    await ctx.interaction.response.send_message(txt, ephemeral=True)
                except discord.NotFound:
                    await ctx.interaction.followup.send(txt, ephemeral=True)
            else:
                await ctx.send(txt)

            if ctx.channel.permissions_for(ctx.me).manage_messages:
                with suppress(discord.NotFound, discord.Forbidden):
                    await ctx.message.delete()

        conf = self.db.get_conf(ctx.guild)
        if not conf.pending:
            txt = _("The pending suggestions channel has not been set!")
            return await resp(txt)

        channel = ctx.guild.get_channel(conf.pending)
        if not channel:
            txt = _("The pending suggestions channel no longer exists!")
            return await resp(txt)

        perms = [
            channel.permissions_for(ctx.me).send_messages,
            channel.permissions_for(ctx.me).embed_links,
        ]
        if not all(perms):
            txt = _("I do not have the required permissions to send messages in the pending suggestions channel.")
            return await resp(txt)

        # Check user's permission to suggest
        if conf.suggest_roles and not any(
            role in [role.id for role in ctx.author.roles] for role in conf.suggest_roles
        ):
            return await resp(_("You do not have the required roles to make suggestions."))

        # Check account age
        if conf.min_account_age_to_suggest:
            account_age = (datetime.now().astimezone() - ctx.author.created_at).total_seconds() / 3600
            if account_age < conf.min_account_age_to_suggest:
                return await resp(_("Your account is too young to make suggestions."))

        # Check join time
        if conf.min_join_time_to_suggest:
            join_age = (datetime.now().astimezone() - ctx.author.joined_at).total_seconds() / 3600
            if join_age < conf.min_join_time_to_suggest:
                return await resp(_("You haven't been in the server long enough to make suggestions."))

        # Check role blacklist
        if conf.role_blacklist and any(role in [role.id for role in ctx.author.roles] for role in conf.role_blacklist):
            return await resp(_("You are not allowed to make suggestions due to a blacklisted role."))

        # Check user blacklist
        if conf.user_blacklist and ctx.author.id in conf.user_blacklist:
            return await resp(_("You are blacklisted from making suggestions."))

        if not conf.approvers:
            txt = _("No approvers have been set! Admins needs to use the {} command to add one.").format(
                f"`{ctx.clean_prefix}ideaset approverole @role`"
            )
            return await resp(txt)

        # Check LevelUp requirement
        try:
            txt = _("You must be level {} or higher to make suggestions.\nUse the {} command to check your level.")
            if conf.min_level_to_suggest and self.bot.get_cog("LevelUp"):
                levelup = self.bot.get_cog("LevelUp")
                if ctx.guild.id in levelup.data:
                    levelup.init_user(ctx.guild.id, str(ctx.author.id))
                    level = levelup.data[ctx.guild.id]["users"][str(ctx.author.id)]["level"]
                    if level < conf.min_level_to_suggest:
                        return await resp(txt.format(conf.min_level_to_suggest, f"`{ctx.clean_prefix}pf`"))
        except Exception as e:
            log.exception(f"Failed to check LevelUp requirement in {ctx.guild.name}", exc_info=e)

        # Check ArkTools requirement
        try:
            if conf.min_playtime_to_suggest and self.bot.get_cog("ArkTools"):
                arktools = self.bot.get_cog("ArkTools")
                players = await arktools.db_utils.search_players(ctx.guild, ctx.author)
                if not players:
                    txt = _("You must be registered in the ArkTools database to make suggestions.")
                    return await resp(txt)
                player = players[0]
                playtime_hours = player.total_playtime / 3600
                if playtime_hours < conf.min_playtime_to_suggest:
                    return await resp(
                        _("You must have at least {} hours of playtime to make suggestions.").format(
                            conf.min_playtime_to_suggest
                        )
                    )
        except Exception as e:
            log.exception(f"Failed to check ArkTools requirement in {ctx.guild.name}", exc_info=e)

        # Check if user has an approver role
        is_approver = False
        if any(role in [role.id for role in ctx.author.roles] for role in conf.approvers):
            is_approver = True

        # Check cooldowns
        profile = conf.get_profile(ctx.author)
        if profile.last_suggestion and not is_approver:
            # Cooldown only applies to non approvers
            delta = datetime.now() - profile.last_suggestion
            cooldown = conf.base_cooldown
            # Check role cooldowns, use the lowest cooldown of all roles the user has
            if conf.role_cooldowns:
                # Fetch all cooldowns of roles the user has
                user_roles = [r.id for r in ctx.author.roles]
                cooldowns = {k: v for k, v in conf.role_cooldowns.items() if k in user_roles}
                # If user has roles with cooldowns, use that instead of the base cooldown
                if cooldowns:
                    cooldown = min(cooldowns.values())

            if delta.total_seconds() < cooldown:
                return await resp(
                    _("You must wait `{}` before making another suggestion.").format(
                        humanize_timedelta(seconds=cooldown - delta.total_seconds())
                    )
                )

        if ctx.channel.permissions_for(ctx.me).manage_messages:
            with suppress(discord.NotFound, discord.Forbidden):
                await ctx.message.delete()

        suggestion_number = conf.counter + 1
        profile.last_suggestion = datetime.now()

        count = _("Suggestion #{}").format(suggestion_number)
        # Create the suggestion embed
        embed = discord.Embed(color=discord.Color.blurple(), description=content)
        if conf.anonymous:
            embed.set_footer(text=_("Posted anonymously"))
        else:
            text = _("Posted by {}").format(f"{ctx.author.name} ({ctx.author.id})")
            embed.set_footer(text=text, icon_url=ctx.author.display_avatar)

        suggestion_id = str(uuid4())
        view = VoteView(self, ctx.guild, suggestion_number, suggestion_id)
        message = await channel.send(count, embed=embed, view=view)

        suggestion = Suggestion(
            id=suggestion_id,
            message_id=message.id,
            author_id=ctx.author.id,
            content=content,
        )
        if conf.discussion_threads:
            try:
                name = _("Suggestion #{} Discussion").format(suggestion_number)
                reason = _("Discussion thread for suggestion #{}").format(suggestion_number)
                thread = await message.create_thread(name=name, reason=reason)
                suggestion.thread_id = thread.id
            except discord.Forbidden:
                log.warning(f"Missing permissions to create a discussion thread in {ctx.guild}")

        conf.suggestions[suggestion_number] = suggestion
        conf.counter = suggestion_number
        profile.suggestions_made += 1

        if ctx.invoked_with == "idea":
            word = "idea"
        else:
            word = "suggestion"
        if channel.permissions_for(ctx.author).view_channel:
            txt = _("Your [{}]({}) has been posted!").format(f"{word} #{suggestion_number}", message.jump_url)
        else:
            txt = _("Your {} has been posted!").format(f"{word} #{suggestion_number}")

        if ctx.interaction:
            try:
                await ctx.interaction.response.send_message(txt, embed=embed, ephemeral=True)
            except discord.NotFound:
                try:
                    await ctx.interaction.followup.send(txt, embed=embed, ephemeral=True)
                except discord.NotFound:
                    try:
                        await ctx.author.send(txt, embed=embed)
                    except discord.Forbidden:
                        await ctx.channel.send(txt, embed=embed)
        else:
            try:
                await ctx.author.send(txt, embed=embed)
            except discord.Forbidden:
                await ctx.channel.send(txt, embed=embed, delete_after=10)

        await self.save()

    @commands.hybrid_command(
        name="ideastats",
        description=_("View your profile stats regarding suggestions and votes."),
    )
    @commands.guild_only()
    async def view_profile(self, ctx: commands.Context, *, member: t.Optional[discord.Member] = None):
        """Display your current profile stats for suggestions and votes."""
        embed = await self.fetch_profile(member or ctx.author)
        await ctx.send(embed=embed)

    async def fetch_profile(self, user: discord.Member) -> discord.Embed:
        conf = self.db.get_conf(user.guild)
        profile = conf.get_profile(user)

        embed = discord.Embed(color=discord.Color.gold(), title=_("Stats for {}").format(user.display_name))
        embed.set_thumbnail(url=user.display_avatar)

        embed.add_field(
            name=_("Suggestion Summary"),
            value=_(
                "Suggestions Made: {}\n" "Suggestions Approved: {}\n" "Suggestions Denied: {}\n" "Karma: {}"
            ).format(
                profile.suggestions_made, profile.suggestions_approved, profile.suggestions_denied, profile.karma_str
            ),
            inline=False,
        )

        embed.add_field(
            name=_("Voting Summary"),
            value=_(
                "Total Upvotes: {}\n"
                "Total Downvotes: {}\n"
                "Successful Votes (Wins): {}\n"
                "Unsuccessful Votes (Losses): {}"
            ).format(profile.upvotes, profile.downvotes, profile.wins, profile.losses),
            inline=False,
        )

        return embed
