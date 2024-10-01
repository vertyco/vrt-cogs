import asyncio
import logging
import typing as t
from contextlib import suppress
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number
from redbot.core.utils.predicates import MessagePredicate

from ..abc import MixinMeta
from ..common.models import Profile, Suggestion
from ..views.voteview import VoteView

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
            "`Delete Threads:     `{}\n"
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
            conf.delete_threads,
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
        value = _("Base: {} seconds\nRole Cooldowns: {}").format(
            conf.base_cooldown,
            "\n".join(f"{r}: {c}s" for r, c in cooldown_roles.items()) if cooldown_roles else _("None Set"),
        )
        embed.add_field(name=name, value=value, inline=False)

        name = _("Account Age")
        value = _("Minimum age of account to vote or suggest\nVote: {} hours\nSuggest: {} hours").format(
            conf.min_account_age_to_vote, conf.min_account_age_to_suggest
        )
        embed.add_field(name=name, value=value, inline=False)

        name = _("Join Time")
        value = _("Minimum time in server to vote or suggest\nVote: {} hours\nSuggest: {} hours").format(
            conf.min_join_time_to_vote, conf.min_join_time_to_suggest
        )
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

        if self.bot.get_cog("LevelUp"):
            name = _("LevelUp Integration")
            value = _("Minimum level required to vote or make suggestions.\nVote: {}\nSuggest: {}").format(
                conf.min_level_to_vote, conf.min_level_to_suggest
            )
            embed.add_field(name=name, value=value, inline=False)
        if self.bot.get_cog("ArkTools"):
            name = _("Ark Playtime Integration")
            value = _("Minimum playtime to vote or make suggestions\nVote: {} hours\nSuggest: {} hours").format(
                conf.min_playtime_to_vote, conf.min_playtime_to_suggest
            )
            embed.add_field(name=name, value=value, inline=False)

        if conf.role_blacklist:
            name = _("Role Blacklist")
            value = "\n".join(ctx.guild.get_role(r).mention for r in conf.role_blacklist if ctx.guild.get_role(r))
            embed.add_field(name=name, value=value, inline=False)
        if conf.user_blacklist:
            name = _("User Blacklist")
            value = "\n".join(ctx.guild.get_member(r).mention for r in conf.user_blacklist if ctx.guild.get_member(r))
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
        current = getattr(conf, channel_type)
        if current == channel.id:
            return await ctx.send(_("This channel is already set as the {} channel!").format(channel_type))
        if not channel.permissions_for(ctx.me).send_messages:
            return await ctx.send(_("I don't have permission to send messages in {}!").format(channel.mention))
        if not channel.permissions_for(ctx.me).embed_links:
            return await ctx.send(_("I don't have permission to send embeds in {}!").format(channel.mention))

        if channel_type == "pending" and conf.suggestions:
            # Prompt user if they want to move pending suggestions to the new channel
            txt = _("Changing the pending channel will move all pending suggestions to the new channel.\n")
            txt += _("Are you sure you want to continue? (y/n)")
            msg = await ctx.send(txt)
            pred = MessagePredicate.yes_or_no(ctx)
            await self.bot.wait_for("message", check=pred)
            if not pred.result:
                return await msg.edit(content=_("Change cancelled."))
            with suppress(discord.HTTPException):
                await msg.delete()

            async with ctx.channel.typing():
                # Move pending suggestions to the new channel
                pending = ctx.guild.get_channel(current)
                sorted_suggestions = sorted(conf.suggestions.items(), key=lambda x: x[0])
                for num, suggestion in sorted_suggestions:
                    original_thread = (
                        await ctx.guild.fetch_channel(suggestion.thread_id) if suggestion.thread_id else None
                    )
                    original_message = None
                    if pending:
                        with suppress(discord.HTTPException):
                            original_message = await pending.fetch_message(suggestion.message_id)
                    # Send the suggestion to the new channel
                    content = _("Suggestion #{}").format(num)
                    embed = discord.Embed(color=discord.Color.blurple(), description=suggestion.content)
                    if conf.anonymous:
                        embed.set_footer(text=_("Posted anonymously"))
                    else:
                        user = ctx.guild.get_member(suggestion.author_id) or await self.bot.get_or_fetch_user(
                            suggestion.author_id
                        )
                        text = _("Posted by {}").format(f"{user.name} ({user.id})")
                        embed.set_footer(text=text, icon_url=user.display_avatar)
                    view = VoteView(self, ctx.guild, num, suggestion.id)
                    message = await channel.send(content=content, embed=embed, view=view)
                    conf.suggestions[num].message_id = message.id
                    if conf.discussion_threads:
                        name = _("Suggestion #{} Discussion").format(num)
                        reason = _("Discussion thread for suggestion #{}").format(num)
                        try:
                            thread = await channel.create_thread(name=name, reason=reason)
                            conf.suggestions[num].thread_id = thread.id
                        except discord.HTTPException as e:
                            txt = _("Faile to create discussion thread in {} for suggestion #{}: {}").format(
                                channel.mention, num, str(e.text)
                            )
                            await ctx.send(txt)

                    # Delete from old channel if it exists
                    if original_message:
                        with suppress(discord.HTTPException):
                            await original_message.delete()
                    # Delete the thread if it exists
                    if original_thread:
                        with suppress(discord.HTTPException):
                            await original_thread.delete()

        if current:
            txt = _("The {} channel has been changed from {} to {}").format(
                channel_type, f"<#{current}>", channel.mention
            )
        else:
            txt = _("Set {} channel to {}").format(channel_type, channel.mention)
        setattr(conf, channel_type, channel.id)
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

    @ideaset.command(name="deletethreads", aliases=["delete", "delthreads"])
    async def toggle_delete_threads(self, ctx: commands.Context):
        """Toggle deleting discussion threads when a suggestion is approved/denied"""
        conf = self.db.get_conf(ctx.guild)
        if conf.delete_threads:
            txt = _("Threads will now be locked/archived when a suggestion is approved/denied.")
        else:
            txt = _("Threads will now be deleted when a suggestion is approved/denied.")
        conf.delete_threads = not conf.delete_threads
        await ctx.send(txt)
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
    async def role_blacklist(self, ctx: commands.Context, role: discord.Role | int):
        """Add/remove a role to/from the role blacklist"""
        conf = self.db.get_conf(ctx.guild)
        if isinstance(role, discord.Role):
            if role.id in conf.role_blacklist:
                conf.role_blacklist.remove(role.id)
                await ctx.send(_("Role `{}` removed from blacklist.").format(role.name))
            else:
                conf.role_blacklist.append(role.id)
                await ctx.send(_("Role `{}` added to blacklist.").format(role.name))
        else:
            if role in conf.role_blacklist:
                conf.role_blacklist.remove(role)
                await ctx.send(_("Role with ID `{}` removed from blacklist.").format(role))
            else:
                return await ctx.send(_("Role with ID `{}` not found in blacklist.").format(role))
        await self.save()

    @ideaset.command(name="userblacklist", aliases=["blacklistuser", "userbl"])
    async def user_blacklist(self, ctx: commands.Context, member: discord.Member | int):
        """Add/remove a user to/from the user blacklist"""
        conf = self.db.get_conf(ctx.guild)
        if isinstance(member, discord.Member):
            if member.id in conf.user_blacklist:
                conf.user_blacklist.remove(member.id)
                await ctx.send(_("User `{}` removed from blacklist.").format(member.display_name))
            else:
                conf.user_blacklist.append(member.id)
                await ctx.send(_("User `{}` added to blacklist.").format(member.display_name))
        else:
            if member in conf.user_blacklist:
                conf.user_blacklist.remove(member)
                await ctx.send(_("User with ID `{}` removed from blacklist.").format(member))
            else:
                return await ctx.send(_("User with ID `{}` not found in blacklist.").format(member))
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

    @ideaset.command(name="resetuser")
    async def reset_user_stats(self, ctx: commands.Context, *, member: discord.Member):
        """Reset a user's stats"""
        conf = self.db.get_conf(ctx.guild)
        if member.id not in conf.profiles:
            return await ctx.send(_("This user has no stats to reset."))
        del conf.profiles[member.id]
        await ctx.send(_("Stats for {} have been reset.").format(member.display_name))
        await self.save()

    @ideaset.command(name="resetall")
    async def reset_all_stats(self, ctx: commands.Context):
        """Reset all user stats"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.profiles:
            return await ctx.send(_("No user stats to reset."))
        msg = await ctx.send(_("Are you sure you want to reset all user stats?"))
        pred = MessagePredicate.yes_or_no(ctx)
        await self.bot.wait_for("message", check=pred)
        if not pred.result:
            return await msg.edit(content=_("Reset cancelled."))
        conf.profiles = {}
        await msg.edit(content=_("All user stats have been reset."))
        await self.save()

    @ideaset.command(name="showstale")
    async def show_stale_suggestions(self, ctx: commands.Context):
        """View the numbers of suggestions who's message no longer exists."""
        conf = self.db.get_conf(ctx.guild)
        if not conf.suggestions:
            return await ctx.send(_("No suggestions have been made yet."))
        pending = ctx.guild.get_channel(conf.pending)
        if not pending:
            return await ctx.send(_("The pending channel is not set."))
        dont_exist = []
        for num, suggestion in conf.suggestions.items():
            try:
                await pending.fetch_message(suggestion.message_id)
            except discord.NotFound:
                dont_exist.append(num)
        if not dont_exist:
            return await ctx.send(_("All suggestions are accounted for."))
        txt = _("The following suggestions are missing their message:\n")
        txt += ", ".join(f"`{num}`" for num in dont_exist)
        txt += _("\n- To prune these suggestions, use {}").format(f"`{ctx.clean_prefix}ideaset cleanup`")
        txt += _("\n- To view the content of a suggestion, use {}").format(f"`{ctx.clean_prefix}viewvotes <number>`")
        await ctx.send(txt)

    @ideaset.command(name="cleanup")
    async def cleanup_config(self, ctx: commands.Context):
        """
        Cleanup the config.
        - Remove suggestions who's message no longer exists.
        - Remove profiles of users who have left the server.
        - Remove votes from users who have left the server.
        """
        async with ctx.typing():
            conf = self.db.get_conf(ctx.guild)
            users_to_remove = [uid for uid in conf.profiles if not ctx.guild.get_member(uid)]
            for uid in users_to_remove:
                del conf.profiles[uid]
            results = StringIO()
            if users_to_remove:
                results.write(
                    _("- Removed {} profiles of users who have left the server.\n").format(len(users_to_remove))
                )
            else:
                results.write(_("- No profiles were removed.\n"))

            to_remove: t.Dict[int, Suggestion] = {}
            if pending := ctx.guild.get_channel(conf.pending):
                for num, suggestion in conf.suggestions.items():
                    try:
                        await pending.fetch_message(suggestion.message_id)
                        # Check if any uid in users_to_remove is in the upvotes/downvotes
                        for uid in users_to_remove:
                            if uid in suggestion.upvotes:
                                suggestion.upvotes.remove(uid)
                                results.write(_("- Removed upvote from user {} on suggestion #{}.\n").format(uid, num))
                            if uid in suggestion.downvotes:
                                suggestion.downvotes.remove(uid)
                                results.write(
                                    _("- Removed downvote from user {} on suggestion #{}.\n").format(uid, num)
                                )
                    except discord.NotFound:
                        to_remove[num] = suggestion
                        profile = conf.get_profile(suggestion.author_id)
                        profile.suggestions_made -= 1
                        for uid in suggestion.upvotes:
                            if uid in users_to_remove:
                                continue
                            profile = conf.get_profile(uid)
                            profile.upvotes -= 1
                        for uid in suggestion.downvotes:
                            if uid in users_to_remove:
                                continue
                            profile = conf.get_profile(uid)
                            profile.downvotes -= 1

            for num, suggestion in to_remove.items():
                results.write(_("- Removed suggestion #{} as the message no longer exists.\n").format(num))
                if thread := ctx.guild.get_channel(suggestion.thread_id):
                    try:
                        await thread.delete()
                    except discord.HTTPException as e:
                        results.write(
                            _("- Failed to delete discussion thread for suggestion #{}: {}.\n").format(num, str(e))
                        )
                del conf.suggestions[num]

            await ctx.send(results.getvalue())
            await self.save()

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
                num = profile.karma_str if attr == "karma_str" else f"({humanize_number(getattr(profile, attr))})"
                buffer.write(f"{place} {member.mention} {num}\n")
            return buffer.getvalue()

        def fmt_ratio(res: t.List[t.Tuple[discord.Member, Profile]], func: t.Callable) -> str:
            place_emojis = ["🥇", "🥈", "🥉"]
            buffer = StringIO()
            for i, (member, profile) in enumerate(res):
                place = place_emojis[i] if i < 3 else f"{i+1}."
                buffer.write(f"{place} {member.mention} ({humanize_number(func((member, profile)))})\n")
            return buffer.getvalue()

        def _embed() -> discord.Embed:
            made_suggestions = [i for i in p.values() if i.suggestions_made > 0]
            avg_suggestions = sum(i.suggestions_made for i in made_suggestions) / (len(made_suggestions) or 1)
            # Top X users based on suggestions made
            top_suggesters = sorted(p.items(), key=lambda x: x[1].suggestions_made, reverse=True)[:amount]
            # Top X users with most approved suggestions
            most_successful = sorted(p.items(), key=lambda x: x[1].suggestions_approved, reverse=True)[:amount]
            # Top X users with most denied suggestions
            most_denied = sorted(p.items(), key=lambda x: x[1].suggestions_denied, reverse=True)[:amount]
            # Top X users with highest approval ratio
            highest_ratio = sorted(p.items(), key=winloss_ratio, reverse=True)[:amount]
            # Top X users with the lowest approval ratio
            lowest_ratio = sorted(
                [i for i in p.items() if i[1].suggestions_made > 0] or p.items(), key=winloss_ratio, reverse=False
            )[:amount]
            # Top X users with most wins
            most_wins = sorted(p.items(), key=lambda x: x[1].wins, reverse=True)[:amount]
            # Top X users with most losses
            most_losses = sorted(p.items(), key=lambda x: x[1].losses, reverse=True)[:amount]
            # Top X users with highest upvote to downvote ratio
            highest_vote_ratio = sorted(p.items(), key=upvote_ratio, reverse=True)[:amount]
            # Top X most negative users by downvote/upvote ratio
            highest_downvote_ratio = sorted(p.items(), key=downvote_ratio, reverse=True)[:amount]
            # Top X users with the highest karma
            highest_karma = sorted(p.items(), key=lambda x: x[1].karma, reverse=True)[:amount]
            # Top X users with the lowest karma
            lowest_karma = sorted(p.items(), key=lambda x: x[1].karma, reverse=False)[:amount]

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
                name=_("Lowest Approval Ratio"),
                value=(
                    _("These users have the lowest approval to rejection ratio.\n")
                    + fmt_ratio(lowest_ratio, winloss_ratio)
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
            embed.add_field(
                name=_("Highest Karma"),
                value=(
                    _("These users have the highest received upvote to downvote ratio.\n")
                    + fmt_results(highest_karma, "karma_str")
                ),
                inline=False,
            )
            embed.add_field(
                name=_("Lowest Karma"),
                value=(
                    _("These users have the lowest received upvote to downvote ratio.\n")
                    + fmt_results(lowest_karma, "karma_str")
                ),
                inline=False,
            )
            return embed

        async with ctx.typing():
            embed = await asyncio.to_thread(_embed)
            await ctx.send(embed=embed)
