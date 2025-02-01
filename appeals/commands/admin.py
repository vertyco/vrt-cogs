import logging
import typing as t
from copy import deepcopy

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.checks import ensure_db_connection
from ..db.tables import AppealGuild, AppealQuestion, AppealSubmission
from ..views.appeal import AppealView
from ..views.dynamic_menu import DynamicMenu

log = logging.getLogger("red.vrt.appeals.commands.admin")


class MessageParser:
    def __init__(self, argument):
        if "-" not in argument:
            raise commands.BadArgument("Invalid format, must be `channelID-messageID`")
        try:
            cid, mid = [i.strip() for i in argument.split("-")]
        except ValueError:
            raise commands.BadArgument("Invalid format, must be `channelID-messageID`")
        try:
            self.channel_id = int(cid)
        except ValueError:
            raise commands.BadArgument("Channel ID must be an integer")
        try:
            self.message_id = int(mid)
        except ValueError:
            raise commands.BadArgument("Message ID must be an integer")


class Admin(MixinMeta):
    async def no_appealguild(self, ctx: commands.Context):
        txt = (
            "This server hasn't been set up for the appeal system yet!\n"
            f"Type `{ctx.clean_prefix}appeal help` to get started."
        )
        return await ctx.send(txt)

    async def appeal_guild_check(self, ctx: commands.Context):
        if not await AppealGuild.exists().where(AppealGuild.id == ctx.guild.id):
            txt = (
                "This server hasn't been set up for the appeal system yet!\n"
                f"Type `{ctx.clean_prefix}appeal help` to get started."
            )
            await ctx.send(txt)
            return False
        return True

    @ensure_db_connection()
    @commands.command(name="appealsfor")
    @commands.bot_has_permissions(embed_links=True)
    async def get_appeal_submissions(self, ctx: commands.Context, user: discord.User | discord.Member | int):
        """Get all appeal submissions for a specific user"""
        if not await self.appeal_guild_check(ctx):
            return
        if isinstance(user, int):
            user = self.bot.get_user(user)
        user_id = user.id if isinstance(user, discord.User) else user
        submission = await AppealSubmission.objects().get(
            (AppealSubmission.user_id == user_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        if not submission:
            return await ctx.send("No submissions found for that user.")
        embed = submission.embed(user)
        await ctx.send(embed=embed)

    @ensure_db_connection()
    @commands.command(name="viewappeal")
    @commands.bot_has_permissions(embed_links=True)
    async def view_appeal_submission(self, ctx: commands.Context, submission_id: int):
        """View an appeal submission by ID"""
        if not await self.appeal_guild_check(ctx):
            return
        submission = await AppealSubmission.objects().get(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        if not submission:
            return await ctx.send("No submission found with that ID.")
        member = ctx.guild.get_member(submission.user_id) or self.bot.get_user(submission.user_id)
        embed = submission.embed(member)
        await ctx.send(embed=embed)

    @ensure_db_connection()
    @commands.command(name="viewappeals")
    @commands.bot_has_permissions(embed_links=True)
    async def view_appeal_submissions(self, ctx: commands.Context):
        """View all appeal submissions in the server"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        submissions = await AppealSubmission.objects().where(AppealSubmission.guild == ctx.guild.id)
        if not submissions:
            return await ctx.send("No submissions found in this server.")
        pages = []
        page_count = len(submissions)
        for idx, submission in enumerate(submissions):
            member = ctx.guild.get_member(submission.user_id) or self.bot.get_user(submission.user_id)
            embed = submission.embed(member)
            page = f"Page {idx + 1}/{page_count}"
            foot = embed.footer.text + f"\n{page}"  # type: ignore
            embed.set_footer(text=foot)
            current_channel = getattr(appealguild, f"{submission.status}_channel")
            jump_url = f"https://discord.com/channels/{ctx.guild.id}/{current_channel}/{submission.message_id}"
            embed.add_field(name="Message", value=jump_url)
            pages.append(embed)
        await DynamicMenu(ctx, pages).refresh()

    @commands.group(name="appeal", aliases=["appeals", "appealset"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def appealset(self, ctx: commands.Context):
        """Configure appeal server settings"""

    @ensure_db_connection()
    @appealset.command(name="gethelp", aliases=["info", "setup"])
    @commands.bot_has_permissions(embed_links=True)
    async def appeal_help(self, ctx: commands.Context):
        """How to set up the appeal system"""
        p = ctx.clean_prefix
        desc = (
            f"**Step 1**: Set the target server to unban users from using `{p}appeal server <server_id>`\n"
            f"**Step 2**: Set the channels for appeals using `{p}appeal channel <pending/approved/denied> <channel>`\n"
            f"**Step 3**: Create a question for the appeal form using `{p}appeal addquestion <question>`\n"
            f"**Step 4**: Quickly create an appeal message button for users using `{p}appeal createappealmessage <channel>`\n"
            "This is the bare minimum to get the appeal system working.\n"
            "### Additional Commands\n"
            f"• Add/Remove alert roles using `{p}appeal alertroles <role>`\n"
            f"• Set an alert channel using `{p}appeal alertchannel <channel>`, this can be in either the appeal or target server.\n"
            f"• You can set an existing appeal message manually using `{p}appeal appealmessage <channelID-messageID>`\n"
        )
        embed = discord.Embed(
            title="Appeal System Setup",
            description=desc,
            color=await self.bot.get_embed_color(ctx),
        )
        await ctx.send(embed=embed)

    @ensure_db_connection()
    @appealset.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_appeal_settings(self, ctx: commands.Context):
        """View the current appeal server settings"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)

        if target := appealguild.target_guild_id:
            target_guild = self.bot.get_guild(target)
            if target_guild:
                target_guild_name = target_guild.name
            else:
                target_guild_name = f"Not Found - `{target}`"
        else:
            target_guild_name = "Not Set"

        def cname(cid: int):
            if cid:
                channel = self.bot.get_channel(cid)
                if channel:
                    return channel.mention
                else:
                    return f"Not Found - `{cid}`"
            return "Not Set"

        roles = [f"<@&{r}>" for r in appealguild.alert_roles]

        if appealguild.appeal_channel and appealguild.appeal_message:
            appeal_msg = (
                f"https://discord.com/channels/{ctx.guild.id}/{appealguild.appeal_channel}/{appealguild.appeal_message}"
            )
        else:
            appeal_msg = "Not set"

        desc = (
            f"**Target Server**: {target_guild_name}\n"
            f"**Pending Channel**: {cname(appealguild.pending_channel)}\n"
            f"**Approved Channel**: {cname(appealguild.approved_channel)}\n"
            f"**Denied Channel**: {cname(appealguild.denied_channel)}\n"
            f"**Appeal Message**: {appeal_msg}\n"
            f"**Alert Channel**: {cname(appealguild.alert_channel)}\n"
            f"**Alert Roles**: {', '.join([r.mention for r in roles]) if roles else 'None set'}\n"
            f"**Questions**: {await AppealQuestion.count().where(AppealQuestion.guild == ctx.guild.id)}"
        )
        embed = discord.Embed(
            title="Appeal Server Settings",
            description=desc,
            color=await self.bot.get_embed_color(ctx),
        )
        await ctx.send(embed=embed)

    @ensure_db_connection()
    @appealset.command(name="nukedb")
    @commands.is_owner()
    async def nuke_appeal_db(self, ctx: commands.Context, confirm: bool):
        """Nuke the entire appeal database"""
        if not confirm:
            return await ctx.send("You must confirm this action by passing `True` as an argument.")
        await AppealQuestion.delete(force=True)
        await AppealSubmission.delete(force=True)
        await AppealGuild.delete(force=True)
        await ctx.send("Successfully nuked the appeal database.")

    @ensure_db_connection()
    @appealset.command(name="wipeappeals")
    async def wipe_appeals(self, ctx: commands.Context, confirm: bool):
        """Wipe all appeal submissions"""
        if not confirm:
            return await ctx.send("You must confirm this action by passing `True` as an argument.")
        await AppealSubmission.delete().where(AppealSubmission.guild == ctx.guild.id)
        await ctx.send("Successfully wiped all appeal submissions.")

    @ensure_db_connection()
    @appealset.command(name="approve")
    async def approve_appeal(self, ctx: commands.Context, submission_id: int, *, reason: str = None):
        """Approve an appeal submission by ID"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        submission = await AppealSubmission.objects().get(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        if not submission:
            return await ctx.send("No submission found with that ID.")
        if submission.status == "approved":
            return await ctx.send("This submission has already been approved.")
        elif submission.status == "denied":
            return await ctx.send("This submission has already been denied.")
        update_kwargs = {AppealSubmission.status: "approved"}
        if reason:
            update_kwargs[AppealSubmission.reason] = reason
        await AppealSubmission.update(update_kwargs).where(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        submission.status = "approved"
        submission.reason = reason or ""
        await ctx.send(f"Successfully approved submission ID: {submission_id}")
        member = ctx.guild.get_member(submission.user_id)
        if not member:
            member = await self.bot.get_or_fetch_user(submission.user_id)
        # Send the submission to the approved channel and then delete from the pending channel
        approved_channel = ctx.guild.get_channel(appealguild.approved_channel)
        if approved_channel:
            new_message = await approved_channel.send(embed=submission.embed(member))
            await AppealSubmission.update({AppealSubmission.message_id: new_message.id}).where(
                (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
            )
        pending_channel = ctx.guild.get_channel(appealguild.pending_channel)
        if pending_channel:
            if not pending_channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.send(f"I do not have permissions to delete messages from {pending_channel.mention}")
            else:
                try:
                    message = await pending_channel.fetch_message(submission.message_id)
                    await message.delete()
                except discord.NotFound:
                    await ctx.send(f"Submission message not found in {pending_channel.mention}")
        else:
            await ctx.send("Pending channel not found, could not delete the message.")
        # Now unban them from the target guild
        target_guild = self.bot.get_guild(appealguild.target_guild_id)
        if not target_guild:
            return await ctx.send("Target guild not found! I can't unban the user.")
        if member.id in [m.id for m in target_guild.members]:
            return await ctx.send("User is already in the target guild!")

        try:
            await target_guild.fetch_ban(member)
            try:
                await target_guild.unban(member, reason=reason or "Appeal approved")
                await ctx.send(f"Unbanned **{member}** (`{member.id}`) from {target_guild.name}")
            except discord.Forbidden:
                return await ctx.send("I don't have permission to unban the user from the target guild!")
        except discord.NotFound:
            await ctx.send("User is not banned from the target guild!")
            try:
                await member.send(
                    f"Your appeal was approved in **{ctx.guild.name}** but you weren't banned from **{target_guild.name}**."
                )
            except discord.Forbidden:
                await ctx.send("I couldn't send a DM to the user to notify them that they weren't banned.")
            return

        if cog := ctx.bot.get_cog("ArkTools"):
            try:
                player = await cog.db_utils.get_player_discord(appealguild.id, member.id)
                if player:
                    fake_ctx = deepcopy(ctx)
                    setattr(fake_ctx, "guild", target_guild)
                    await cog.ban_unban_player(
                        ctx=fake_ctx,
                        player_id=player.gameid,
                        ban=False,
                        reason=reason or "",
                        prompt=True,
                    )
            except Exception as e:
                log.error("Error unbanning player", exc_info=e)
                await ctx.send(f"Error unbanning player from the Ark servers: {e}")

        # Alert the user that their appeal has been approved
        try:
            await member.send(
                f"Your appeal has been approved in **{ctx.guild.name}**. You have been unbanned from **{target_guild.name}**."
            )
            await ctx.send("User has been notified of the approval.")
        except discord.Forbidden:
            await ctx.send("I couldn't send a DM to the user to notify them of the approval.")

    @ensure_db_connection()
    @appealset.command(name="deny")
    async def deny_appeal(self, ctx: commands.Context, submission_id: int, *, reason: str = None):
        """Deny an appeal submission by ID"""
        appealguild: AppealGuild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        submission = await AppealSubmission.objects().get(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        if not submission:
            return await ctx.send("No submission found with that ID.")
        if submission.status == "denied":
            return await ctx.send("This submission has already been denied.")
        elif submission.status == "approved":
            return await ctx.send("This submission has already been approved.")
        update_kwargs = {AppealSubmission.status: "denied"}
        if reason:
            update_kwargs[AppealSubmission.reason] = reason
        await AppealSubmission.update(update_kwargs).where(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        submission.status = "denied"
        submission.reason = reason or ""
        await ctx.send(f"Successfully denied submission ID: {submission_id}")
        member = ctx.guild.get_member(submission.user_id) or self.bot.get_user(submission.user_id)
        # Send the submission to the denied channel and then delete from the pending channel
        denied_channel = ctx.guild.get_channel(appealguild.denied_channel)
        if denied_channel:
            new_embed = submission.embed(member)
            new_message = await denied_channel.send(embed=new_embed)
            await AppealSubmission.update({AppealSubmission.message_id: new_message.id}).where(
                (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
            )
        pending_channel = ctx.guild.get_channel(appealguild.pending_channel)
        if pending_channel:
            if not pending_channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.send(f"I do not have permissions to delete messages from {pending_channel.mention}")
            else:
                try:
                    message = await pending_channel.fetch_message(submission.message_id)
                    await message.delete()
                except discord.NotFound:
                    await ctx.send(f"Submission message not found in {pending_channel.mention}")
        else:
            await ctx.send("Pending channel not found, could not delete the message.")
        # Alert the user that their appeal has been denied
        target_guild = self.bot.get_guild(appealguild.target_guild_id)
        targetname = f"**{target_guild.name}**" if target_guild else "the target server"
        try:
            txt = f"Your appeal has been denied in **{ctx.guild.name}**. You are still banned from {targetname}"
            if reason:
                txt += f"\n\n**Reason**: {reason}"
            await member.send(txt)
            await ctx.send("User has been notified of the denial.")
        except discord.Forbidden:
            await ctx.send("I couldn't send a DM to the user to notify them of the denial.")

    @ensure_db_connection()
    @appealset.command(name="delete")
    async def delete_appeal(self, ctx: commands.Context, submission_id: int):
        """Delete an appeal submission by ID"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        submission = await AppealSubmission.objects().get(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        if not submission:
            return await ctx.send("No submission found with that ID.")
        channel = ctx.guild.get_channel(getattr(appealguild, f"{submission.status}_channel"))
        if channel:
            if not channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.send(f"I do not have permissions to delete messages from {channel.mention}")
            else:
                try:
                    message = await channel.fetch_message(submission.message_id)
                    await message.delete()
                except discord.NotFound:
                    await ctx.send(f"Submission message not found in {channel.mention}")
        await submission.delete().where(
            (AppealSubmission.id == submission_id) & (AppealSubmission.guild == ctx.guild.id)
        )
        await ctx.send(f"Successfully deleted submission ID: {submission_id}")

    @commands.guildowner()
    @ensure_db_connection()
    @appealset.command(name="server")
    async def set_target_server(self, ctx: commands.Context, server_id: int):
        """
        Set the server ID where users will be unbanned from

        **NOTES**
        - This is the first step to setting up the appeal system
        - This server will be the appeal server
        - You must be the owner of the target server
        """
        target_guild = self.bot.get_guild(server_id)
        if not target_guild:
            return await ctx.send("The server ID provided is invalid.")
        if target_guild.id == ctx.guild.id:
            return await ctx.send(
                "You can't use the same server as the appeal server. (This server is the appeal server)"
            )
        if target_guild.owner_id != ctx.author.id:
            return await ctx.send("You are not the owner of that server!")

        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            appealguild = AppealGuild(id=ctx.guild.id, target_guild_id=server_id)
            await appealguild.save()
            txt = f"Successfully set the target server to **{target_guild.name}**\nUsers will come to **this** server to appeal for unbans."
            return await ctx.send(txt)
        if appealguild.target_guild_id == server_id:
            return await ctx.send(f"This server is already set to unban users from **{target_guild.name}**")
        await AppealGuild.update({AppealGuild.target_guild_id: server_id}).where(AppealGuild.id == ctx.guild.id)
        await ctx.send(f"Updated the target server to **{target_guild.name}**")

    @ensure_db_connection()
    @appealset.command(name="channel")
    async def set_channels(
        self,
        ctx: commands.Context,
        channel_type: t.Literal["pending", "approved", "denied"],
        channel: discord.TextChannel,
    ):
        """
        Set the channel where submitted appeals will go

        `channel_type` must be one of: pending, approved, denied

        **NOTE**: All 3 channel types must be set for the appeal system to work properly.
        """
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)

        if channel_type == "pending":
            if channel.id == appealguild.pending_channel:
                return await ctx.send("That channel is already set as the pending appeals channel.")
            update_col = AppealGuild.pending_channel
            await ctx.send(f"Successfully set the pending appeals channel to {channel.mention}")
        elif channel_type == "approved":
            if channel.id == appealguild.approved_channel:
                return await ctx.send("That channel is already set as the approved appeals channel.")
            update_col = AppealGuild.approved_channel
            await ctx.send(f"Successfully set the approved appeals channel to {channel.mention}")
        elif channel_type == "denied":
            if channel.id == appealguild.denied_channel:
                return await ctx.send("That channel is already set as the denied appeals channel.")
            update_col = AppealGuild.denied_channel
            await ctx.send(f"Successfully set the denied appeals channel to {channel.mention}")
        else:
            return await ctx.send("Invalid channel type provided.")
        await AppealGuild.update({update_col: channel.id}).where(AppealGuild.id == ctx.guild.id)
        await self.refresh(ctx)

    @ensure_db_connection()
    @appealset.command(name="createappealmessage", aliases=["create"])
    async def create_appeal_message(self, ctx: commands.Context, channel: discord.TextChannel):
        """Quickly create and set a pre-baked appeal message in the specified channel"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        if not channel.permissions_for(ctx.guild.me).send_messages:
            return await ctx.send("I don't have permission to send messages in that channel.")
        embed = discord.Embed(
            title="Submit an Appeal",
            description="Click the button below to submit an appeal.",
            color=await self.bot.get_embed_color(ctx),
        )
        message = await channel.send(embed=embed, view=AppealView(custom_id=f"{ctx.guild.id}"))
        await AppealGuild.update(
            {
                AppealGuild.appeal_channel: channel.id,
                AppealGuild.appeal_message: message.id,
            }
        ).where(AppealGuild.id == ctx.guild.id)
        await ctx.send(f"Successfully created and set the appeal message in {channel.mention}")

    @ensure_db_connection()
    @appealset.command(name="appealmessage")
    async def set_appeal_message(self, ctx: commands.Context, message: MessageParser):
        """
        Set the message where users will appeal from
        Message format: `channelID-messageID`
        """
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        channel = ctx.guild.get_channel(message.channel_id)
        if not channel:
            return await ctx.send("Invalid channel ID provided.")
        try:
            msg = await channel.fetch_message(message.message_id)
        except discord.NotFound:
            return await ctx.send("Invalid message ID provided.")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to read messages in that channel.")
        except discord.HTTPException:
            return await ctx.send("An error occurred while fetching the message.")
        await AppealGuild.update(
            {
                AppealGuild.appeal_channel: channel.id,
                AppealGuild.appeal_message: message.id,
            }
        ).where(AppealGuild.id == ctx.guild.id)
        await ctx.send(f"Successfully set the appeal message to {msg.jump_url}")
        await self.refresh(ctx)

    @ensure_db_connection()
    @appealset.command(name="addquestion")
    async def add_appeal_question(self, ctx: commands.Context, *, question: str):
        """Add a question to the appeal form"""  # TODO: menu system for extra options
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        count = await AppealQuestion.count().where(AppealQuestion.guild == appealguild)
        if count >= 24:
            return await ctx.send("You can only have up to 24 questions in the appeal form.")
        question = AppealQuestion(
            guild=ctx.guild.id,
            question=question,
        )
        await question.save()
        await ctx.send("Successfully added the question to the appeal form.")
        await self.refresh(ctx)

    @ensure_db_connection()
    @appealset.command(name="removequestion")
    async def remove_appeal_question(self, ctx: commands.Context, question_id: int):
        """Remove a question from the appeal form"""  # TODO: menu system for extra options
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        count = await AppealQuestion.count().where(AppealQuestion.guild == appealguild)
        if count < 1:
            return await ctx.send("No questions have been created yet.")
        if count == 1:
            return await ctx.send("You can't remove the only question from the appeal system!")
        questions = (
            await AppealQuestion.delete()
            .where((AppealQuestion.id == question_id) & (AppealQuestion.guild == appealguild))
            .returning(AppealQuestion.question)
        )
        if not questions:
            return await ctx.send("No question found with that ID.")
        await ctx.send(f"Successfully removed the following question: {questions[0]['question']}")

    @ensure_db_connection()
    @appealset.command(name="questions")
    async def appeal_question_menu(self, ctx: commands.Context):
        """Menu to view questions in the appeal form"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        questions = await self.db_utils.get_sorted_questions(ctx.guild.id)
        if not questions:
            return await ctx.send("No questions found have been created yet.")
        pages: list[discord.Embed] = []
        color = await self.bot.get_embed_color(ctx)
        for idx, question in enumerate(questions):
            embed = question.embed(color)
            foot = (
                f"Page {idx + 1}/{len(questions)}\n"
                "The order of the pages is how the sort order will look in the appeal form."
            )
            embed.set_footer(text=foot)
            pages.append(embed)

        await DynamicMenu(ctx, pages).refresh()

    @ensure_db_connection()
    @appealset.command(name="listquestions")
    async def list_appeal_questions(self, ctx: commands.Context):
        """
        List all questions in the appeal form

        Questions will be sorted by their sort order and then by creation date.
        """
        if not await self.appeal_guild_check(ctx):
            return
        questions = await self.db_utils.get_sorted_questions(ctx.guild.id)
        if not questions:
            return await ctx.send("No questions found have been created yet.")
        msg = "\n".join([f"{q.id}. [{q.sort_order}] {q.question}" for q in questions])
        for page in pagify(msg, page_length=1800):
            await ctx.send(f"**ID. [Sort Order] Question**\n{box(page)}")

    @ensure_db_connection()
    @appealset.command(name="viewquestion")
    @commands.bot_has_permissions(embed_links=True)
    async def view_appeal_question(self, ctx: commands.Context, question_id: int):
        """View a question in the appeal form"""
        if not await self.appeal_guild_check(ctx):
            return
        question = await AppealQuestion.objects().get(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        if not question:
            return await ctx.send("No question found with that ID.")
        embed = discord.Embed(
            title=f"Question ID: {question.id}",
            description=question.question,
            color=await self.bot.get_embed_color(ctx),
        )
        embed.add_field(
            name="Created At",
            value=f"{question.created('F')} ({question.created('R')})",
        )
        embed.add_field(
            name="Last Modified",
            value=f"{question.modified('F')} ({question.modified('R')})",
        )
        embed.add_field(name="Sort Order", value=question.sort_order)
        embed.add_field(name="Required", value="Yes" if question.required else "No")
        embed.add_field(name="Style", value=question.style)
        embed.add_field(name="Button Style", value=question.button_style)
        embed.add_field(name="Placeholder", value=question.placeholder or "Not set")
        embed.add_field(name="Default Value", value=question.default or "Not set")
        embed.add_field(name="Max Length", value=question.max_length or "Not set")
        embed.add_field(name="Min Length", value=question.min_length or "Not set")
        await ctx.send(embed=embed)

    @ensure_db_connection()
    @appealset.command(name="editquestion")
    async def edit_appeal_question(self, ctx: commands.Context, question_id: int, *, question: str):
        """Edit a question in the appeal form"""
        if not await self.appeal_guild_check(ctx):
            return
        original = await AppealQuestion.objects().get(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        if not original:
            return await ctx.send("No question found with that ID.")
        await (
            AppealQuestion.update({AppealQuestion.question: question})
            .where((AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id))
            .returning(AppealQuestion.question)
        )
        await ctx.send(f"Question has been edited! Original content: {original.question}")

    @ensure_db_connection()
    @appealset.command(name="sortorder")
    async def set_appeal_question_order(self, ctx: commands.Context, question_id: int, sort_order: int):
        """Set the sort order for a question in the appeal form"""
        if not await self.appeal_guild_check(ctx):
            return
        question = await AppealQuestion.objects().get(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        if not question:
            return await ctx.send("No question found with that ID.")
        await AppealQuestion.update({AppealQuestion.sort_order: sort_order}).where(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        await ctx.send(f"Successfully updated the sort order for question ID: {question_id}")

    @ensure_db_connection()
    @appealset.command(
        name="questiondetails",
        aliases=["questiondata", "setquestiondata", "qd", "details"],
    )
    async def set_appeal_question_data(
        self,
        ctx: commands.Context,
        question_id: int,
        required: bool,
        modal_style: str = None,
        button_style: str = None,
        placeholder: str = None,
        default: str = None,
        min_length: int = None,
        max_length: int = None,
    ):
        """Set specific data for a question in the appeal form

        **Arguments**
        - `required`: Whether the question is required or not
        - `modal_style`: The style of the modal for the question
          - `long`: The modal will be a long text input
          - `short`: The modal will be a short text input
        - `button_style`: The color of the button for the question
          - `primary🔵`, `secondary⚫`, `success🟢`, `danger🔴`
        - `placeholder`: The placeholder text for the input
        - `default`: The default value for the input
        - `min_length`: The minimum length for the input
        - `max_length`: The maximum length for the input
        """
        if not await self.appeal_guild_check(ctx):
            return
        if isinstance(placeholder, str) and "none" in placeholder.casefold():
            placeholder = None
        if isinstance(default, str) and "none" in default.casefold():
            default = None
        if max_length == 0:
            max_length = None
        if min_length == 0:
            min_length = None

        if isinstance(max_length, int) and max_length > 1024:
            return await ctx.send("Max length must be 1024 characters or less.")
        if isinstance(min_length, int) and min_length > 1023:
            return await ctx.send("Min length must be 1023 characters or less.")
        if isinstance(max_length, int) and isinstance(min_length, int) and max_length < min_length:
            return await ctx.send("Max length must be greater than or equal to min length.")
        if modal_style not in ("long", "short", None):
            return await ctx.send("Modal style must be either `long` or `short`.")
        if button_style not in ("primary", "secondary", "success", "danger", None):
            return await ctx.send("Button style must be one of: primary, secondary, success, danger.")

        question = await AppealQuestion.objects().get(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        if not question:
            return await ctx.send("No question found with that ID.")

        update_kwargs = {AppealQuestion.required: required}
        if modal_style is not None:
            update_kwargs[AppealQuestion.style] = modal_style
        if button_style is not None:
            update_kwargs[AppealQuestion.button_style] = button_style
        if placeholder is not None:
            update_kwargs[AppealQuestion.placeholder] = placeholder
        if default is not None:
            update_kwargs[AppealQuestion.default] = default
        if min_length is not None:
            update_kwargs[AppealQuestion.min_length] = min_length
        if max_length is not None:
            update_kwargs[AppealQuestion.max_length] = max_length

        await AppealQuestion.update(update_kwargs).where(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        question = await AppealQuestion.objects().get(
            (AppealQuestion.id == question_id) & (AppealQuestion.guild == ctx.guild.id)
        )
        embed = question.embed(await self.bot.get_embed_color(ctx))

        await ctx.send(
            f"Successfully updated the question data for question ID: {question_id}",
            embed=embed,
        )

    @ensure_db_connection()
    @appealset.command(name="alertrole")
    async def set_alert_roles(self, ctx: commands.Context, *, role: discord.Role | int):
        """
        Add/Remove roles to be pinged when a new appeal is submitted
        These roles will be pinged in the appeal server, NOT the target server.
        """
        rid = role.id if isinstance(role, discord.Role) else role
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        if rid in appealguild.alert_roles:
            appealguild.alert_roles.remove(rid)
            await ctx.send(f"Removed {role.name} from the alert roles.")
        else:
            appealguild.alert_roles.append(rid)
            await ctx.send(f"Added {role.name} to the alert roles.")
        await AppealGuild.update({AppealGuild.alert_roles: appealguild.alert_roles}).where(
            AppealGuild.id == ctx.guild.id
        )

    @ensure_db_connection()
    @appealset.command(name="alertchannel")
    async def set_alert_channel(self, ctx: commands.Context, *, channel: discord.TextChannel | int = None):
        """
        Set the channel ID where alerts for new appeals will be sent

        This can be in either the appeal server or the target server.
        Alert roles will not be pinged in this message.
        """
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        if isinstance(channel, int):
            channel = self.bot.get_channel(channel)
            if not channel:
                return await ctx.send("Invalid channel ID provided.")
        if channel:
            await AppealGuild.update({AppealGuild.alert_channel: channel.id}).where(AppealGuild.id == ctx.guild.id)
            return await ctx.send(f"Successfully set the alert channel to {channel.mention}")
        await AppealGuild.update({AppealGuild.alert_channel: 0}).where(AppealGuild.id == ctx.guild.id)
        await ctx.send("Successfully removed the alert channel.")

    @ensure_db_connection()
    @appealset.command(name="refresh")
    async def refresh_appeal(self, ctx: commands.Context):
        """Refresh the appeal message with the current appeal form"""
        await self.refresh(ctx)

    async def refresh(self, ctx: discord.Guild | commands.Context) -> str | None:
        guild = ctx.guild if isinstance(ctx, commands.Context) else ctx
        ready, reason = await self.conditions_met(guild)
        if not ready:
            if isinstance(ctx, commands.Context):
                await ctx.send(f"Appeal system not ready yet: {reason}")
            return reason
        appealguild = await AppealGuild.objects().get(AppealGuild.id == guild.id)
        channel = guild.get_channel(appealguild.appeal_channel)
        message = await channel.fetch_message(appealguild.appeal_message)
        view = AppealView(custom_id=f"{appealguild.id}")
        await message.edit(view=view)

    @ensure_db_connection()
    @appealset.command(name="buttonstyle")
    async def set_button_style(
        self,
        ctx: commands.Context,
        style: t.Literal["primary", "secondary", "success", "danger"],
    ):
        """Set the style of the appeal button"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        await AppealGuild.update({AppealGuild.button_style: style}).where(AppealGuild.id == ctx.guild.id)
        view = discord.ui.View().add_item(
            discord.ui.Button(
                style=getattr(discord.ButtonStyle, style),
                label=appealguild.button_label,
                disabled=True,
                emoji=appealguild.get_emoji(ctx.bot),
            )
        )
        await ctx.send(f"Successfully set the button style to {style}", view=view)
        await self.refresh(ctx)

    @ensure_db_connection()
    @appealset.command(name="buttonlabel")
    async def set_button_label(self, ctx: commands.Context, *, label: str):
        """Set the label of the appeal button"""
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        if len(label) > 45:
            return await ctx.send("Button label must be 45 characters or less.")
        await AppealGuild.update({AppealGuild.button_label: label}).where(AppealGuild.id == ctx.guild.id)
        view = discord.ui.View().add_item(
            discord.ui.Button(
                style=getattr(discord.ButtonStyle, appealguild.button_style),
                label=label,
                disabled=True,
                emoji=appealguild.get_emoji(ctx.bot),
            )
        )
        await ctx.send(f"Successfully set the button label to {label}", view=view)
        await self.refresh(ctx)

    @ensure_db_connection()
    @appealset.command(name="buttonemoji")
    async def set_button_emoji(
        self,
        ctx: commands.Context,
        emoji: discord.Emoji | discord.PartialEmoji | str = None,
    ):
        """Set the emoji of the appeal button"""
        if isinstance(emoji, discord.Emoji) and not emoji.is_usable():
            return await ctx.send("That emoji is not a usable emoji.")
        elif isinstance(emoji, discord.PartialEmoji):
            emoji = self.bot.get_emoji(emoji.id)
            if not emoji:
                return await ctx.send("That emoji is not found in this server.")
        appealguild = await AppealGuild.objects().get(AppealGuild.id == ctx.guild.id)
        if not appealguild:
            return await self.no_appealguild(ctx)
        if emoji:
            tosave = str(emoji if isinstance(emoji, str) else emoji.id)
            await AppealGuild.update({AppealGuild.button_emoji: tosave}).where(AppealGuild.id == ctx.guild.id)
            view = discord.ui.View().add_item(
                discord.ui.Button(
                    style=getattr(discord.ButtonStyle, appealguild.button_style),
                    label=appealguild.button_label,
                    disabled=True,
                    emoji=emoji,
                )
            )
            return await ctx.send(f"Successfully set the button emoji to {emoji}", view=view)
        await AppealGuild.update({AppealGuild.button_emoji: None}).where(AppealGuild.id == ctx.guild.id)
        view = discord.ui.View().add_item(
            discord.ui.Button(
                style=getattr(discord.ButtonStyle, appealguild.button_style),
                label=appealguild.button_label,
                disabled=True,
            )
        )
        await ctx.send("Successfully removed the button emoji", view=view)
        await self.refresh(ctx)
