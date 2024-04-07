import asyncio
import logging
import typing as t
from contextlib import suppress
from io import StringIO

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number, text_to_file

from ..abc import MixinMeta
from ..common.models import Profile

log = logging.getLogger("red.vrt.ideaboard.commands.admin")
_ = Translator("IdeaBoard", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(name="ideaset", aliases=["ideaboard"])
    @commands.admin_or_permissions(manage_guild=True)
    async def ideaset(self, ctx: commands.Context):
        """Manage IdeaBoard settings"""
        pass

    @ideaset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """View IdeaBoard settings"""
        conf = self.db.get_conf(ctx.guild)
        vote_role_mentions = [ctx.guild.get_role(r).mention for r in conf.vote_roles if ctx.guild.get_role(r)]
        suggest_role_mentions = [ctx.guild.get_role(r).mention for r in conf.suggest_roles if ctx.guild.get_role(r)]
        approver_mentions = [ctx.guild.get_role(r).mention for r in conf.approvers if ctx.guild.get_role(r)]
        cooldown_roles = {
            ctx.guild.get_role(k).mention: v for k, v in conf.role_cooldowns.items() if ctx.guild.get_role(k)
        }
        up, down = conf.get_emojis(self.bot)
        main = _(
            "`Approved Channel:   `{}\n"
            "`Rejected Channel:   `{}\n"
            "`Pending Channel:    `{}\n"
            "`Anonymous:          `{}\n"
            "`Reveal Complete:    `{}\n"
            "`DM Result:          `{}\n"
            "`Discussion Threads: `{}\n"
            "`Upvote Emoji:       `{}\n"
            "`Downvote Emoji:     `{}\n"
            "`Show Vote Counts:   `{}\n"
            "`Suggestions:        `{}\n"
            "`Suggestion #:       `{}\n"
        ).format(
            f"<#{conf.approved}>" if conf.approved else _("Not set"),
            f"<#{conf.rejected}>" if conf.rejected else _("Not set"),
            f"<#{conf.pending}>" if conf.pending else _("Not set"),
            conf.anonymous,
            conf.reveal,
            conf.dm,
            conf.discussion_threads,
            up,
            down,
            conf.show_vote_counts,
            len(conf.suggestions),
            conf.counter,
        )
        embed = discord.Embed(
            description=main,
            color=ctx.author.color,
        )
        embed.set_author(name=_("Ideaboard Settings"), icon_url=ctx.guild.icon)

        name = _("Cooldowns")
        value = _("Base: {0.base_cooldown} seconds\nRole Cooldowns: {1}").format(
            conf, "\n".join(f"{r}: {c}s" for r, c in cooldown_roles.items()) if cooldown_roles else _("None Set")
        )
        embed.add_field(name=name, value=value, inline=False)

        name = _("Account Age")
        value = _(
            "Minimum age of account to vote or suggest\n"
            "Vote: {0.min_account_age_to_vote} hours\n"
            "Suggest: {0.min_account_age_to_suggest} hours"
        ).format(conf)
        embed.add_field(name=name, value=value, inline=False)

        name = _("Join Time")
        value = _(
            "Minimum time in server to vote or suggest\n"
            "Vote: {0.min_join_time_to_vote} hours\n"
            "Suggest: {0.min_join_time_to_suggest} hours"
        ).format(conf)
        embed.add_field(name=name, value=value, inline=False)

        name = _("Vote Roles")
        value = (
            _("Roles required to vote\nIf no roles are set, anyone can vote.\n") + "\n".join(vote_role_mentions)
            if vote_role_mentions
            else _("None Set")
        )
        embed.add_field(name=name, value=value, inline=False)

        name = _("Suggest Roles")
        value = (
            _("Roles required to suggest\nIf no roles are set, anyone can make suggestions.\n")
            + "\n".join(suggest_role_mentions)
            if suggest_role_mentions
            else _("None Set")
        )
        embed.add_field(name=name, value=value, inline=False)

        name = _("Approvers")
        value = (
            _("Roles required to approve suggestions\n") + "\n".join(approver_mentions)
            if approver_mentions
            else _("None Set")
        )
        embed.add_field(name=name, value=value, inline=False)

        name = _("LevelUp Integration")
        value = _(
            "Minimum level required to vote or make suggestions.\n"
            "Vote: {0.min_level_to_vote}\n"
            "Suggest: {0.min_level_to_suggest}"
        ).format(conf)
        embed.add_field(name=name, value=value, inline=False)
        if self.bot.get_cog("ArkTools"):
            name = _("Ark Playtime Integration")
            value = _(
                "Minimum playtime to vote or make suggestions\n"
                "Vote: {0.min_playtime_to_vote} hours\n"
                "Suggest: {0.min_playtime_to_suggest} hours"
            ).format(conf)
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @ideaset.command(name="channel")
    async def ideaset_channel(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        channel_type: t.Literal["approved", "rejected", "pending"],
    ):
        """Set the approved, rejected, or pending channels for IdeaBoard"""
        conf = self.db.get_conf(ctx.guild)
        if channel_type == "approved":
            conf.approved = channel.id
        elif channel_type == "rejected":
            conf.rejected = channel.id
        else:
            conf.pending = channel.id
        txt = _("Set {} channel to {}").format(channel_type, channel.mention)
        await ctx.send(txt)
        await self.save()

    @ideaset.command(name="toggleanonymous", aliases=["toggleanon", "anonymous", "anon"])
    async def toggle_anonymous(self, ctx: commands.Context):
        """Toggle allowing anonymous suggestions"""
        conf = self.db.get_conf(ctx.guild)
        conf.anonymous = not conf.anonymous
        state = "enabled" if conf.anonymous else "disabled"
        await ctx.send(_("Anonymous suggestions are now {}.").format(state))
        await self.save()

    @ideaset.command(name="togglereveal", aliases=["reveal"])
    async def toggle_reveal(self, ctx: commands.Context):
        """
        Toggle reveal suggestion author on approval

        Approved suggestions are ALWAYS revealed regardless of this setting.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.reveal = not conf.reveal
        state = "enabled" if conf.reveal else "disabled"
        await ctx.send(_("Revealing of authors on rejection is now {}.").format(state))
        await self.save()

    @ideaset.command(name="togglevotecount", aliases=["votecount"])
    async def toggle_vote_count(self, ctx: commands.Context):
        """Toggle showing vote counts on suggestions"""
        conf = self.db.get_conf(ctx.guild)
        conf.show_vote_counts = not conf.show_vote_counts
        state = "enabled" if conf.show_vote_counts else "disabled"
        await ctx.send(_("Showing vote counts on suggestions is now {}.").format(state))
        await self.save()

    @ideaset.command(name="toggledm", aliases=["dm"])
    async def toggle_dm(self, ctx: commands.Context):
        """Toggle DMing users the results of suggestions they made"""
        conf = self.db.get_conf(ctx.guild)
        conf.dm = not conf.dm
        state = "enabled" if conf.dm else "disabled"
        await ctx.send(_("DMing users about suggestion results is now {}.").format(state))
        await self.save()

    @ideaset.command(name="discussions", aliases=["threads", "discussion"])
    async def toggle_discussions(self, ctx: commands.Context):
        """Toggle opening a discussion thread for each suggestion"""
        conf = self.db.get_conf(ctx.guild)
        conf.discussion_threads = not conf.discussion_threads
        state = "enabled" if conf.discussion_threads else "disabled"
        await ctx.send(_("Discussion threads are now {}.").format(state))
        await self.save()

    @ideaset.command(name="upvoteemoji", aliases=["upvote", "up"])
    async def upvote_emoji(self, ctx: commands.Context, emoji: t.Union[discord.Emoji, str]):
        """Set the upvote emoji"""
        conf = self.db.get_conf(ctx.guild)
        conf.upvote = emoji if isinstance(emoji, str) else emoji.id
        await ctx.send(_("Upvote emoji set to {}").format(emoji))
        await self.save()

    @ideaset.command(name="downvoteemoji", aliases=["downvote", "down"])
    async def downvote_emoji(self, ctx: commands.Context, emoji: t.Union[discord.Emoji, str]):
        """Set the downvote emoji"""
        conf = self.db.get_conf(ctx.guild)
        conf.downvote = emoji if isinstance(emoji, str) else emoji.id
        await ctx.send(_("Downvote emoji set to {}").format(emoji))
        await self.save()

    @ideaset.command(name="cooldown", aliases=["cd"])
    async def set_cooldown(self, ctx: commands.Context, cooldown: int):
        """Set the base cooldown for making suggestions"""
        conf = self.db.get_conf(ctx.guild)
        conf.base_cooldown = cooldown
        if cooldown:
            await ctx.send(_("Base cooldown set to {} seconds.").format(cooldown))
        else:
            await ctx.send(_("Base cooldown disabled."))
        await self.save()

    @ideaset.command(name="rolecooldown", aliases=["rolecd"])
    async def set_role_cooldown(self, ctx: commands.Context, role: discord.Role, cooldown: int):
        """Set the suggestion cooldown for a specific role

        To remove a role cooldown, specify 0 as the cooldown.
        """
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.role_cooldowns:
            if cooldown:
                conf.role_cooldowns[role.id] = cooldown
                await ctx.send(_("Cooldown for role {} updated to {} seconds.").format(role.mention, cooldown))
            else:
                del conf.role_cooldowns[role.id]
                await ctx.send(_("Cooldown for role {} removed.").format(role.mention))
        else:
            if cooldown:
                conf.role_cooldowns[role.id] = cooldown
                await ctx.send(_("Cooldown for role {} set to {} seconds.").format(role.mention, cooldown))
            else:
                await ctx.send(_("Cooldown for role {} already disabled.").format(role.mention))
        await self.save()

    @ideaset.command(name="voterole")
    async def vote_role(self, ctx: commands.Context, role: discord.Role):
        """Add/remove a role to the voting role whitelist"""
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.vote_roles:
            conf.vote_roles.remove(role.id)
            state = "removed from"
        else:
            conf.vote_roles.append(role.id)
            state = "added to"
        await ctx.send(_("Role {} `{}` voting whitelist.").format(role.name, state))
        await self.save()

    @ideaset.command(name="suggestrole")
    async def suggest_role(self, ctx: commands.Context, role: discord.Role):
        """Add/remove a role to the suggest role whitelist"""
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.suggest_roles:
            conf.suggest_roles.remove(role.id)
            state = "removed from"
        else:
            conf.suggest_roles.append(role.id)
            state = "added to"
        await ctx.send(_("Role {} `{}` suggest whitelist.").format(role.name, state))
        await self.save()

    @ideaset.command(name="approverole")
    async def approver_role(self, ctx: commands.Context, role: discord.Role):
        """Add/remove a role to the approver role list"""
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.approvers:
            conf.approvers.remove(role.id)
            state = "removed from"
        else:
            conf.approvers.append(role.id)
            state = "added to"
        await ctx.send(_("Role {} `{}` approvers list.").format(role.name, state))
        await self.save()

    @ideaset.command(name="roleblacklist", aliases=["blacklistrole", "rolebl"])
    async def role_blacklist(self, ctx: commands.Context, role: discord.Role):
        """Add/remove a role to/from the role blacklist"""
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.role_blacklist:
            conf.role_blacklist.remove(role.id)
            await ctx.send(_("Role `{}` removed from blacklist.").format(role.name))
        else:
            conf.role_blacklist.append(role.id)
            await ctx.send(_("Role `{}` added to blacklist.").format(role.name))
        await self.save()

    @ideaset.command(name="userblacklist", aliases=["blacklistuser", "userbl"])
    async def user_blacklist(self, ctx: commands.Context, member: discord.Member):
        """Add/remove a user to/from the user blacklist"""
        conf = self.db.get_conf(ctx.guild)
        if member.id in conf.user_blacklist:
            conf.user_blacklist.remove(member.id)
            await ctx.send(_("User `{}` removed from blacklist.").format(member.display_name))
        else:
            conf.user_blacklist.append(member.id)
            await ctx.send(_("User `{}` added to blacklist.").format(member.display_name))
        await self.save()

    @ideaset.command(name="accountage")
    async def set_account_age(self, ctx: commands.Context, to_vote: int, to_suggest: int):
        """
        Set the minimum account age required to vote and suggest.

        Args:
            to_vote: Minimum age in hours required to vote.
            to_suggest: Minimum age in hours required to suggest.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.min_account_age_to_vote = to_vote
        conf.min_account_age_to_suggest = to_suggest
        await ctx.send(
            _("Minimum account age to vote is set to {0} hours and to suggest is set to {1} hours.").format(
                to_vote, to_suggest
            )
        )
        await self.save()

    @ideaset.command(name="jointime")
    async def set_join_time(self, ctx: commands.Context, to_vote: int, to_suggest: int):
        """
        Set the minimum time a user must be in the server to vote and suggest.

        Args:
            to_vote: Minimum time in hours required to vote.
            to_suggest: Minimum time in hours required to suggest.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.min_join_time_to_vote = to_vote
        conf.min_join_time_to_suggest = to_suggest
        await ctx.send(
            _("Minimum join time to vote is set to {0} hours and to suggest is set to {1} hours.").format(
                to_vote, to_suggest
            )
        )
        await self.save()

    @ideaset.command(name="minlevel")
    async def set_min_level(self, ctx: commands.Context, to_vote: int, to_suggest: int):
        """
        Set the LevelUp integration minimum level required to vote and suggest.

        Args:
            to_vote: Minimum level required to vote.
            to_suggest: Minimum level required to suggest.
        """
        if not self.bot.get_cog("LevelUp"):
            txt = _("LevelUp is not loaded. Please load it and try again.")
            return await ctx.send(txt)

        conf = self.db.get_conf(ctx.guild)
        conf.min_level_to_vote = to_vote
        conf.min_level_to_suggest = to_suggest
        await ctx.send(
            _("Minimum level to vote is set to {0} and to suggest is set to {1}.").format(to_vote, to_suggest)
        )
        await self.save()

    @ideaset.command(name="minplaytime")
    async def set_min_playtime(self, ctx: commands.Context, to_vote: int, to_suggest: int):
        """
        Set the ArkTools integration minimum playtime required to vote and suggest.

        Args:
            to_vote: Minimum playtime in hours required to vote.
            to_suggest: Minimum playtime in hours required to suggest.
        """
        if self.bot.user.id not in [
            770755544448499744,  # Autto
            859930241119289345,  # VrtDev
            857070505294430218,  # Arkon
        ]:
            txt = _("This command is only available to Vertyco and Arkon.")
            return await ctx.send(txt)
        if not self.bot.get_cog("ArkTools"):
            txt = _("ArkTools is not loaded. Please load it and try again.")
            return await ctx.send(txt)

        conf = self.db.get_conf(ctx.guild)
        conf.min_playtime_to_vote = to_vote
        conf.min_playtime_to_suggest = to_suggest
        await ctx.send(
            _("Minimum playtime to vote is set to {0} hours and to suggest is set to {1} hours.").format(
                to_vote, to_suggest
            )
        )
        await self.save()

    @commands.hybrid_command(name="approve", description=_("Approve a suggestion."))
    @app_commands.describe(number=_("Suggestion number"))
    @commands.guild_only()
    async def approve_suggestion(self, ctx: commands.Context, number: int, *, reason: str = None):
        """Approve an idea/suggestion."""
        conf = self.db.get_conf(ctx.guild)
        if not conf.approvers:
            txt = _("No approvers have been set! Use the {} command to add one.").format(
                f"`{ctx.clean_prefix}ideaset approverole @role`"
            )
            return await ctx.send(txt)
        if not any(role in [role.id for role in ctx.author.roles] for role in conf.approvers):
            txt = _("You do not have the required roles to approve suggestions.")
            return await ctx.send(txt)

        if not conf.pending:
            txt = _("The pending suggestions channel has not been set!")
            return await ctx.send(txt)
        if not conf.approved:
            txt = _("The approved suggestions channel has not been set!")
            return await ctx.send(txt)

        pending_channel = ctx.guild.get_channel(conf.pending)
        if not pending_channel:
            txt = _("The pending suggestions channel no longer exists!")
            return await ctx.send(txt)
        approved_channel = ctx.guild.get_channel(conf.approved)
        if not approved_channel:
            txt = _("The approved suggestions channel no longer exists!")
            return await ctx.send(txt)

        perms = [
            pending_channel.permissions_for(ctx.me).send_messages,
            pending_channel.permissions_for(ctx.me).embed_links,
            approved_channel.permissions_for(ctx.me).send_messages,
            approved_channel.permissions_for(ctx.me).embed_links,
        ]
        if not all(perms):
            txt = _("I do not have the required permissions to send messages in the suggestion channels.")
            return await ctx.send(txt)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            txt = _("That suggestion does not exist!")
            return await ctx.send(txt)

        message = await pending_channel.fetch_message(suggestion.message_id)
        if not message:
            txt = _("Cannot find the message associated with this suggestion! Cleaning from config...")
            del conf.suggestions[number]
            await ctx.send(txt)
            await self.save()
            return

        if suggestion.thread_id:
            thread = await ctx.guild.fetch_channel(suggestion.thread_id)
            if thread:
                with suppress(discord.NotFound):
                    await thread.delete()

        content = message.embeds[0].description
        embed = discord.Embed(color=discord.Color.green(), description=content, title=_("Approved Suggestion"))
        if author := ctx.guild.get_member(suggestion.author_id):
            foot = _("Suggested by {}").format(f"{author.name} ({author.id})")
            embed.set_footer(text=foot, icon_url=author.display_avatar)
        else:
            embed.set_footer(text=_("Suggested by a user who is no longer in the server."))

        if reason:
            embed.add_field(name=_("Reason"), value=reason)

        up, down = conf.get_emojis(self.bot)
        embed.add_field(
            name=_("Results"),
            value=f"{len(suggestion.upvotes)}x {up}\n{len(suggestion.downvotes)}x {down}",
            inline=False,
        )

        with suppress(discord.NotFound):
            await message.delete()

        try:
            txt = _("Suggestion #{}").format(number)
            message = await approved_channel.send(txt, embed=embed)
        except discord.Forbidden:
            txt = _("I do not have the required permissions to send messages in the approved suggestions channel.")
            return await ctx.send(txt)
        except discord.NotFound:
            txt = _("The approved suggestions channel no longer exists!")
            return await ctx.send(txt)

        # Add stats to users before deleting the suggestion from config
        profile = conf.get_profile(suggestion.author_id)
        profile.suggestions_approved += 1

        for uid in suggestion.upvotes:
            profile = conf.get_profile(uid)
            profile.wins += 1

        for uid in suggestion.downvotes:
            profile = conf.get_profile(uid)
            profile.losses += 1

        member = ctx.guild.get_member(suggestion.author_id)
        if member and conf.dm:
            txt = _("Your [suggestion]({}) has been approved!").format(message.jump_url)
            try:
                await member.send(txt)
            except discord.Forbidden:
                pass

        del conf.suggestions[number]

        await ctx.send(_("Suggestion #{} has been approved.").format(number))

        await self.save()

    @commands.hybrid_command(name="reject", description=_("Reject a suggestion."))
    @app_commands.describe(number=_("Suggestion number"))
    @commands.guild_only()
    async def reject_suggestion(self, ctx: commands.Context, number: int, *, reason: str = None):
        """Reject an idea/suggestion."""
        conf = self.db.get_conf(ctx.guild)
        if not conf.approvers:
            txt = _("No approvers have been set! Use the {} command to add one.").format(
                f"`{ctx.clean_prefix}ideaset approverole @role`"
            )
            return await ctx.send(txt)
        if not any(role in [role.id for role in ctx.author.roles] for role in conf.approvers):
            txt = _("You do not have the required roles to reject suggestions.")
            return await ctx.send(txt)

        if not conf.pending:
            txt = _("The pending suggestions channel has not been set!")
            return await ctx.send(txt)
        if not conf.rejected:
            txt = _("The rejected suggestions channel has not been set!")
            return await ctx.send(txt)

        pending_channel = ctx.guild.get_channel(conf.pending)
        if not pending_channel:
            txt = _("The pending suggestions channel no longer exists!")
            return await ctx.send(txt)
        rejected_channel = ctx.guild.get_channel(conf.rejected)
        if not rejected_channel:
            txt = _("The rejected suggestions channel no longer exists!")
            return await ctx.send(txt)

        perms = [
            pending_channel.permissions_for(ctx.me).send_messages,
            pending_channel.permissions_for(ctx.me).embed_links,
            rejected_channel.permissions_for(ctx.me).send_messages,
            rejected_channel.permissions_for(ctx.me).embed_links,
        ]
        if not all(perms):
            txt = _("I do not have the required permissions to send messages in the suggestion channels.")
            return await ctx.send(txt)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            txt = _("That suggestion does not exist!")
            return await ctx.send(txt)

        message = await pending_channel.fetch_message(suggestion.message_id)
        if not message:
            txt = _("Cannot find the message associated with this suggestion! Cleaning from config...")
            del conf.suggestions[number]
            await ctx.send(txt)
            await self.save()
            return

        if suggestion.thread_id:
            thread = await ctx.guild.fetch_channel(suggestion.thread_id)
            if thread:
                with suppress(discord.NotFound):
                    await thread.delete()

        content = message.embeds[0].description
        embed = discord.Embed(color=discord.Color.red(), description=content, title=_("Rejected Suggestion"))
        if conf.anonymous and not conf.reveal:
            embed.set_footer(text=_("Suggested anonymously"))
        elif author := ctx.guild.get_member(suggestion.author_id):
            foot = _("Suggested by {}").format(f"{author.name} ({author.id})")
            embed.set_footer(text=foot, icon_url=author.display_avatar)

        if reason:
            embed.add_field(name=_("Reason for Rejection"), value=reason)

        up, down = conf.get_emojis(self.bot)
        embed.add_field(
            name=_("Results"),
            value=f"{len(suggestion.upvotes)}x {up}\n{len(suggestion.downvotes)}x {down}",
            inline=False,
        )

        with suppress(discord.NotFound):
            await message.delete()

        try:
            txt = _("Suggestion #{}").format(number)
            message = await rejected_channel.send(txt, embed=embed)
        except discord.Forbidden:
            txt = _("I do not have the required permissions to send messages in the denied suggestions channel.")
            return await ctx.send(txt)
        except discord.NotFound:
            txt = _("The denied suggestions channel no longer exists!")
            return await ctx.send(txt)

        # Add stats to users before deleting the suggestion from config
        profile = conf.get_profile(suggestion.author_id)
        profile.suggestions_denied += 1

        for uid in suggestion.upvotes:
            profile = conf.get_profile(uid)
            profile.losses += 1

        for uid in suggestion.downvotes:
            profile = conf.get_profile(uid)
            profile.wins += 1

        member = ctx.guild.get_member(suggestion.author_id)
        if member and conf.dm:
            txt = _("Your [suggestion]({}) has been rejected!").format(message.jump_url)
            try:
                await member.send(txt)
            except discord.Forbidden:
                pass

        del conf.suggestions[number]

        await ctx.send(_("Suggestion #{} has been rejected.").format(number))

        await self.save()

    @commands.hybrid_command(
        name="viewvotes",
        description=_("View the current upvoters and downvoters of a suggestion."),
    )
    @app_commands.describe(number=_("Suggestion number to view votes for"))
    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def view_votes(self, ctx: commands.Context, number: int):
        """View the list of who has upvoted and who has downvoted a suggestion."""
        conf = self.db.get_conf(ctx.guild)

        if not conf.approvers:
            txt = _("No approvers have been set! Use the {} command to add one.").format(
                f"`{ctx.clean_prefix}ideaset approverole @role`"
            )
            return await ctx.send(txt)

        if not any(role in [role.id for role in ctx.author.roles] for role in conf.approvers):
            txt = _("You do not have the required roles to inspect suggestions.")
            return await ctx.send(txt)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            await ctx.send(_("That suggestion does not exist!"))
            return

        description = _("Suggestion could not be found in pending channel!")

        if pending_channel := ctx.guild.get_channel(conf.pending):
            try:
                message = await pending_channel.fetch_message(suggestion.message_id)
                description = message.embeds[0].description
            except discord.NotFound:
                pass

        embed = discord.Embed(
            color=discord.Color.blue(),
            title=_("Votes for Suggestion #{}").format(number),
            description=description,
        )

        upvoter_ids = suggestion.upvotes
        downvoter_ids = suggestion.downvotes

        upvoter_mentions = ", ".join(f"<@{uid}>" for uid in upvoter_ids)
        downvoter_mentions = ", ".join(f"<@{uid}>" for uid in downvoter_ids)

        upvoters_label = _("Upvoters ({})").format(len(upvoter_ids)) if upvoter_ids else _("No upvotes yet")
        downvoters_label = _("Downvoters ({})").format(len(downvoter_ids)) if downvoter_ids else _("No downvotes yet")

        file = None
        if len(upvoter_mentions) > 1024 or len(downvoter_mentions) > 1024:
            embed.add_field(name=upvoters_label, value=humanize_number(len(upvoter_ids) or _("N/A")), inline=False)
            embed.add_field(name=downvoters_label, value=humanize_number(len(upvoter_ids) or _("N/A")), inline=False)

            raw = StringIO()
            raw.write(_("Upvoters ({}):\n").format(len(upvoter_ids)))
            for uid in upvoter_ids:
                member = ctx.guild.get_member(uid)
                if member:
                    raw.write(f"{member.name} ({member.id})\n")
                else:
                    raw.write(f"LEFT SERVER ({uid})\n")

            raw.write(_("\nDownvoters ({}):\n").format(len(downvoter_ids)))
            for uid in downvoter_ids:
                member = ctx.guild.get_member(uid)
                if member:
                    raw.write(f"{member.name} ({member.id})\n")
                else:
                    raw.write(f"LEFT SERVER ({uid})\n")

            file = text_to_file(raw.getvalue(), filename="votes.txt")

        else:
            embed.add_field(name=upvoters_label, value=upvoter_mentions or _("N/A"), inline=False)
            embed.add_field(name=downvoters_label, value=downvoter_mentions or _("N/A"), inline=False)

        author = ctx.guild.get_member(suggestion.author_id)
        if author:
            embed.set_footer(
                text=_("Suggested by {}").format(f"{author.name} ({author.id})"), icon_url=author.display_avatar
            )
        else:
            user = await self.bot.fetch_user(suggestion.author_id)
            embed.set_footer(text=_("Suggested by {} [No longer in server]").format(f"{user.name} ({user.id})"))

        await ctx.send(embed=embed, file=file)

    @ideaset.command(name="insights")
    async def view_insights(self, ctx: commands.Context, amount: int = 3):
        """View insights about the server's suggestions.

        **Arguments**
        - `amount` The number of top users to display for each section.
        """
        amount = max(1, min(amount, 10))
        conf = self.db.get_conf(ctx.guild)
        if not conf.profiles:
            return await ctx.send(_("No suggestions have been made yet."))
        p: t.Dict[discord.Member, Profile] = {
            ctx.guild.get_member(k): v for k, v in conf.profiles.items() if ctx.guild.get_member(k)
        }

        def winloss_ratio(x: t.Tuple[discord.Member, Profile]) -> float:
            return round(x[1].suggestions_approved / (x[1].suggestions_denied or 1), 2)

        def upvote_ratio(x: t.Tuple[discord.Member, Profile]) -> float:
            return round(x[1].upvotes / (x[1].downvotes or 1), 2)

        def downvote_ratio(x: t.Tuple[discord.Member, Profile]) -> float:
            return round(x[1].downvotes / (x[1].upvotes or 1), 2)

        def fmt_results(res: t.List[t.Tuple[discord.Member, Profile]], attr: str) -> str:
            # Return a numbered list of the top users
            place_emojis = ["🥇", "🥈", "🥉"]
            buffer = StringIO()
            for i, (member, profile) in enumerate(res):
                place = place_emojis[i] if i < 3 else f"{i+1}."
                buffer.write(f"{place} {member.mention} ({humanize_number(getattr(profile, attr))})\n")
            return buffer.getvalue()

        def fmt_ratio(res: t.List[t.Tuple[discord.Member, Profile]], func: t.Callable) -> str:
            place_emojis = ["🥇", "🥈", "🥉"]
            buffer = StringIO()
            for i, (member, profile) in enumerate(res):
                place = place_emojis[i] if i < 3 else f"{i+1}."
                buffer.write(f"{place} {member.mention} ({humanize_number(func((member, profile)))})\n")
            return buffer.getvalue()

        def _embed() -> discord.Embed:
            avg_suggestions = sum(i.suggestions_made for i in p.values()) / len(p)
            # Top X users based on suggestions made
            top_suggesters = sorted(p.items(), key=lambda x: x[1].suggestions_made, reverse=True)[:amount]
            # Top X users with most approved suggestions
            most_successful = sorted(p.items(), key=lambda x: x[1].suggestions_approved, reverse=True)[:amount]
            # Top X users with most denied suggestions
            most_denied = sorted(p.items(), key=lambda x: x[1].suggestions_denied, reverse=True)[:amount]
            # Top X users with highest approval ratio
            highest_ratio = sorted(p.items(), key=winloss_ratio, reverse=True)[:amount]
            # Top X users with most wins
            most_wins = sorted(p.items(), key=lambda x: x[1].wins, reverse=True)[:amount]
            # Top X users with most losses
            most_losses = sorted(p.items(), key=lambda x: x[1].losses, reverse=True)[:amount]
            # Top X users with highest upvote to downvote ratio
            highest_vote_ratio = sorted(p.items(), key=upvote_ratio, reverse=True)[:amount]
            # Top X most negative users by downvote/upvote ratio
            highest_downvote_ratio = sorted(p.items(), key=downvote_ratio, reverse=True)[:amount]

            embed = discord.Embed(title=_("Server Insights"), color=discord.Color.gold())
            embed.add_field(
                name=_("Average Suggestions Made Per User"),
                value=humanize_number(avg_suggestions),
                inline=False,
            )
            embed.add_field(
                name=_("Most Suggestions Made"),
                value=fmt_results(top_suggesters, "suggestions_made"),
                inline=False,
            )
            embed.add_field(
                name=_("Most Successful Users"),
                value=(
                    _("These users have the most suggestions approved.\n")
                    + fmt_results(most_successful, "suggestions_approved")
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Least Successful Users"),
                value=(
                    _("These users have the most suggestions denied.\n")
                    + fmt_results(most_denied, "suggestions_denied")
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Highest Approval Ratio"),
                value=(
                    _("These users have the highest approval to rejection ratio.\n")
                    + fmt_ratio(highest_ratio, winloss_ratio)
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Most Wins"),
                value=(
                    _("These users have the most votes that ended in their favor.\n") + fmt_results(most_wins, "wins")
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Most Losses"),
                value=(
                    _("These users have the most votes that ended against their favor.\n")
                    + fmt_results(most_losses, "losses")
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Most Optimistic Users"),
                value=(
                    _("These users have the highest upvote to downvote ratio.\n")
                    + fmt_ratio(highest_vote_ratio, upvote_ratio)
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Most Negative Users"),
                value=(
                    _("These users have the highest downvote to upvote ratio.\n")
                    + fmt_ratio(highest_downvote_ratio, downvote_ratio)
                ),
                inline=False,
            )
            return embed

        async with ctx.typing():
            embed = await asyncio.to_thread(_embed)
            await ctx.send(embed=embed)
