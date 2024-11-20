import logging
from contextlib import suppress
from io import StringIO

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number, text_to_file
from redbot.core.utils.predicates import MessagePredicate

from ..abc import MixinMeta
from ..views.voteview import VoteView

log = logging.getLogger("red.vrt.ideaboard.commands.adminbase")
_ = Translator("IdeaBoard", __file__)


@cog_i18n(_)
class AdminBase(MixinMeta):
    @commands.hybrid_command(name="approve", description=_("Approve a suggestion."))
    @app_commands.describe(number=_("Suggestion number"))
    @app_commands.checks.has_permissions(manage_messages=True)
    @commands.mod_or_permissions(manage_messages=True)
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
            approved_channel.permissions_for(ctx.me).manage_channels,
            approved_channel.permissions_for(ctx.me).embed_links,
        ]
        if not all(perms):
            txt = _("I do not have the required permissions to send messages in the suggestion channels.")
            return await ctx.send(txt)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            txt = _("That suggestion does not exist!")
            return await ctx.send(txt)

        try:
            message = await pending_channel.fetch_message(suggestion.message_id)
            await message.delete()
        except discord.HTTPException as e:
            txt = _("I couldn't delete the pending message: {}").format(e.text)
            await ctx.send(txt)

        if suggestion.thread_id:
            with suppress(discord.NotFound):
                thread: discord.Thread = await ctx.guild.fetch_channel(suggestion.thread_id)
                if thread:
                    if conf.delete_threads:
                        with suppress(discord.HTTPException):
                            await thread.delete()
                    else:
                        # Close and lock the thread
                        newname = thread.name + _(" [Approved]")
                        embed = discord.Embed(
                            color=discord.Color.green(),
                            description=suggestion.content,
                            title=_("Approved Suggestion"),
                        )
                        with suppress(discord.HTTPException):
                            await thread.send(embed=embed)
                            await thread.edit(archived=True, locked=True, name=newname)

        embed = discord.Embed(
            color=discord.Color.green(),
            description=suggestion.content,
            title=_("Approved Suggestion"),
        )
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
            txt = _("Your [suggestion #{}]({}) has been approved!").format(number, message.jump_url)
            if reason:
                txt += _("\nReason: {}").format(reason)
            try:
                await member.send(txt)
            except discord.Forbidden:
                pass

        if number in conf.suggestions:
            del conf.suggestions[number]

        await ctx.send(_("Suggestion #{} has been approved.").format(number))

        await self.save()

    @commands.hybrid_command(name="reject", description=_("Reject a suggestion."))
    @app_commands.describe(number=_("Suggestion number"))
    @app_commands.checks.has_permissions(manage_messages=True)
    @commands.mod_or_permissions(manage_messages=True)
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
            rejected_channel.permissions_for(ctx.me).manage_channels,
            rejected_channel.permissions_for(ctx.me).embed_links,
        ]
        if not all(perms):
            txt = _("I do not have the required permissions to send messages in the suggestion channels.")
            return await ctx.send(txt)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            txt = _("That suggestion does not exist!")
            return await ctx.send(txt)

        try:
            message = await pending_channel.fetch_message(suggestion.message_id)
            await message.delete()
        except discord.HTTPException as e:
            txt = _("I couldn't delete the pending message: {}").format(e.text)
            await ctx.send(txt)

        if suggestion.thread_id:
            with suppress(discord.NotFound):
                thread: discord.Thread = await ctx.guild.fetch_channel(suggestion.thread_id)
                if thread:
                    with suppress(discord.HTTPException):
                        if conf.delete_threads:
                            await thread.delete()
                        else:
                            # Close and lock the thread
                            newname = thread.name + _(" [Rejected]")
                            embed = discord.Embed(
                                color=discord.Color.red(),
                                description=suggestion.content,
                                title=_("Rejected Suggestion"),
                            )
                            await thread.send(embed=embed)
                            await thread.edit(archived=True, locked=True, name=newname)

        embed = discord.Embed(
            color=discord.Color.red(),
            description=suggestion.content,
            title=_("Rejected Suggestion"),
        )
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
            txt = _("Your [suggestion #{}]({}) has been rejected!").format(number, message.jump_url)
            if reason:
                txt += _("\nReason: {}").format(reason)
            try:
                await member.send(txt)
            except discord.Forbidden:
                pass

        if number in conf.suggestions:
            del conf.suggestions[number]

        await ctx.send(_("Suggestion #{} has been rejected.").format(number))

        await self.save()

    @commands.hybrid_command(
        name="viewvotes",
        description=_("View the current upvoters and downvoters of a suggestion."),
    )
    @app_commands.describe(number=_("Suggestion number to view votes for"))
    @commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(attach_files=True, embed_links=True)
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    @commands.mod_or_permissions(manage_messages=True)
    async def view_votes(self, ctx: commands.Context, number: int):
        """View the list of who has upvoted and who has downvoted a suggestion."""
        conf = self.db.get_conf(ctx.guild)

        if not conf.approvers:
            txt = _("No approvers have been set! Use the {} command to add one.").format(
                f"`{ctx.clean_prefix}ideaset approverole @role`"
            )
            return await ctx.send(txt, ephemeral=True)

        if not any(role in [role.id for role in ctx.author.roles] for role in conf.approvers):
            txt = _("You do not have the required roles to inspect suggestions.")
            return await ctx.send(txt, ephemeral=True)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            await ctx.send(_("That suggestion does not exist!"), ephemeral=True)
            return

        pending = ctx.guild.get_channel(conf.pending)
        if pending:
            try:
                await pending.fetch_message(suggestion.message_id)
            except discord.HTTPException:
                txt = _(
                    "I cannot find the message associated with this suggestion, would you like me to repost it? (y/n)"
                )
                msg = await ctx.send(txt)
                pred = MessagePredicate.yes_or_no(ctx)
                await self.bot.wait_for("message", check=pred)
                if pred.result:
                    content = _("Suggestion #{}").format(number)
                    embed = discord.Embed(color=discord.Color.blurple(), description=suggestion.content)
                    if conf.anonymous:
                        embed.set_footer(text=_("Posted anonymously"))
                    else:
                        user = ctx.guild.get_member(suggestion.author_id) or await self.bot.get_or_fetch_user(
                            suggestion.author_id
                        )
                        text = _("Posted by {}").format(f"{user.name} ({user.id})")
                        embed.set_footer(text=text, icon_url=user.display_avatar)
                    view = VoteView(self, ctx.guild, number, suggestion.id)
                    message = await pending.send(content=content, embed=embed, view=view)
                    conf.suggestions[number].message_id = message.id
                    await self.save()
                    await msg.edit(content=_("Suggestion #{} has been reposted.").format(number))
                else:
                    txt = _("Not reposting Suggestion #{}.\n").format(number)
                    txt += _("You can remove it from the config by typing {}").format(
                        f"`{ctx.clean_prefix}ideaset cleanup`"
                    )
                    await msg.edit(content=txt)

        embed = discord.Embed(
            color=discord.Color.blue(),
            title=_("Votes for Suggestion #{}").format(number),
            description=suggestion.content,
            timestamp=suggestion.created,
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

        await ctx.send(embed=embed, file=file, ephemeral=True)

    @commands.hybrid_command(
        name="refresh",
        description=_("Refresh the buttons on a suggestion if it gets stuck."),
    )
    @app_commands.describe(number=_("Suggestion number to view votes for"))
    @commands.guild_only()
    @app_commands.checks.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def refresh_suggestion(self, ctx: commands.Context, number: int):
        """Refresh the buttons on a suggestion if it gets stuck."""
        conf = self.db.get_conf(ctx.guild)

        if not conf.approvers:
            txt = _("No approvers have been set! Use the {} command to add one.").format(
                f"`{ctx.clean_prefix}ideaset approverole @role`"
            )
            return await ctx.send(txt, ephemeral=True)

        if not any(role in [role.id for role in ctx.author.roles] for role in conf.approvers):
            txt = _("You do not have the required roles to refresh suggestions.")
            return await ctx.send(txt, ephemeral=True)

        suggestion = conf.suggestions.get(number)
        if not suggestion:
            await ctx.send(_("That suggestion does not exist!"), ephemeral=True)
            return

        pending = ctx.guild.get_channel(conf.pending)
        if not pending:
            txt = _("The pending suggestions channel no longer exists!")
            return await ctx.send(txt, ephemeral=True)

        try:
            message = await pending.fetch_message(suggestion.message_id)
        except discord.HTTPException:
            txt = _("I cannot find the message associated with this suggestion.")
            return await ctx.send(txt, ephemeral=True)

        view = VoteView(self, ctx.guild, number, suggestion.id)
        await message.edit(view=view)
        await ctx.send(_("Suggestion #{} has been refreshed.").format(number), ephemeral=True)

    @reject_suggestion.autocomplete("number")
    @approve_suggestion.autocomplete("number")
    @refresh_suggestion.autocomplete("number")
    @view_votes.autocomplete("number")
    async def suggest_autocomplete(self, interaction: discord.Interaction, current: str):
        conf = self.db.get_conf(interaction.guild)
        opened = [str(i) for i in conf.suggestions]
        if current:
            return [app_commands.Choice(name=i, value=i) for i in opened if i.startswith(current)][:25]
        return [app_commands.Choice(name=i, value=i) for i in opened][:25]
