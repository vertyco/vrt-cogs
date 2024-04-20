import contextlib
import logging
import random
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

import discord
from discord.ext import tasks
from redbot.core import Config, VersionInfo, bank, commands, version_info
from redbot.core.commands import parse_timedelta
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    humanize_timedelta,
)
from redbot.core.utils.menus import DEFAULT_CONTROLS, menu

from .utils import (
    GetReply,
    get_attachments,
    get_place,
    get_size,
    guild_icon,
    profile_icon,
    select_event,
)

log = logging.getLogger("red.vrt.events")
DPY2 = True if version_info >= VersionInfo.from_str("3.5.0") else False
DEFAULT_EMOJI = "👍"


class Events(commands.Cog):
    """
    Host and manage events in your server with a variety of customization options.

    Create an event, set a channel for submissions and entry requirements/options.
    Users can enter the event and make submissions according to the parameters set.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.2.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=117)
        default_guild = {
            "events": {},
            "staff_roles": [],
            "ping_staff": False,
            "notify_roles": [],
            "notify_users": [],
            "role_blacklist": [],
            "user_blacklist": [],
            "default_emoji": None,
            "auto_delete": False,
            "result_delete": False,
        }
        self.config.register_guild(**default_guild)

        # These aren't used in the code, just helps me remember the schema
        self.event_schema = {
            "event_name": str,
            "description": str,
            "channel_id": int,
            "file_submission": bool,  # Either media/file or text submissions
            "submissions_per_user": int,  # Example 1 picture or file per user
            "winners": int,  # How many winners to select
            "rewards": dict,  # Rewards for each winner according to their place
            "submissions": dict,  # User ID keys with list of their submission entries
            "start_date": int,  # Timestamp
            "end_date": int,  # Timestamp
            "roles_required": list,  # Role IDs required to enter the event
            "need_all_roles": bool,  # Whether the user needs all the required roles to enter
            "days_in_server": int,  # Days user must be in the server to enter
            "emoji": int,  # Emoji id at the time of creation (just in case user changes default during run)
            "messages": list,  # Any non-submission messages related to the event
            "completed": bool,  # Whether the event has been completed or not
        }
        # Goes in event_schema["submissions"]
        # User ID strings with a list of message IDs corresponding to their submissions
        self.submission_schema = {str(int): list}

        self._lock = set()
        # Event check loop
        self.check_events.start()

    def cog_unload(self):
        self.check_events.cancel()

    @tasks.loop(minutes=1)
    async def check_events(self):
        now = datetime.now().timestamp()
        for guild in self.bot.guilds:
            conf = await self.config.guild(guild).all()
            if not conf["events"]:
                continue
            for event in conf["events"].values():
                if event["completed"]:
                    continue
                ends = event["end_date"]
                if now < ends:
                    continue
                await self._end_event(guild, event)

    @check_events.before_loop
    async def before_event_check(self):
        await self.bot.wait_until_red_ready()

    @commands.command(name="enotify")
    @commands.guild_only()
    async def toggle_user_notify(self, ctx: commands.Context):
        """
        Enable/Disable event notifications for yourself

        You will be notified when events start and end
        """
        users = await self.config.guild(ctx.guild).notify_users()
        user = ctx.author
        if user.id in users:
            async with self.config.guild(ctx.guild).notify_users() as notify:
                notify.remove(user.id)
            await ctx.send("I will no longer notify you when events start or end")
        else:
            async with self.config.guild(ctx.guild).notify_users() as notify:
                notify.append(user.id)
            await ctx.send("I will notify you when events start or end")

    @commands.command(name="enter")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def enter_event(self, ctx: commands.Context):
        """Enter an event if one exists"""
        if ctx.author.id in self._lock:
            return await ctx.send("You are already in the middle of entering an event!", delete_after=10)
        try:
            self._lock.add(ctx.author.id)
            await self._enter_event(ctx)
        finally:
            self._lock.discard(ctx.author.id)

    async def _enter_event(self, ctx: commands.Context):
        async def cancel(message):
            await message.edit(content="Event entry cancelled", embed=None)

        async def edit(message, content, title=None, footer=None):
            embed = discord.Embed(description=content, color=ctx.author.color)
            if title:
                embed.title = title
            if footer:
                embed.set_footer(text=footer)
            await message.edit(content=None, embed=embed)

        conf = await self.config.guild(ctx.guild).all()
        existing = conf["events"]
        if not existing:
            return await ctx.send("There are no events to enter at this time")

        rblacklist = conf["role_blacklist"]
        ublacklist = conf["user_blacklist"]
        author: discord.Member = ctx.author
        if author.id in ublacklist:
            return await ctx.send("You cannot enter events because you have been blacklisted!")
        if any([r.id in rblacklist for r in author.roles]):
            return await ctx.send("You cannot enter events because one of your roles has been blacklisted!")
        res = await select_event(ctx, existing)
        if not res:
            return

        uid = str(author.id)
        event: dict = res["event"]
        msg: discord.Message = res["msg"]
        filesub = event["file_submission"]
        per_user = event["submissions_per_user"]
        already_submitted = 0
        if uid in event["submissions"]:
            if len(event["submissions"][uid]) >= per_user:
                return await edit(
                    msg,
                    "You have already submitted the max amount of entries for this event!",
                )
            else:
                already_submitted = len(event["submissions"][uid])

        required_roles = event["roles_required"]
        if required_roles:
            need_all = event["need_all_roles"]
            mentions = [ctx.guild.get_role(rid).mention for rid in required_roles if ctx.guild.get_role(rid)]
            user_roles = [role.id for role in author.roles]
            role_matches = [rid in user_roles for rid in required_roles]
            if not need_all and not any(role_matches):
                txt = (
                    f"You do not have any of the required roles to enter.\n"
                    f"You must have at least one of these roles to enter: {humanize_list(mentions)}"
                )
                return await edit(msg, txt)
            elif need_all and not all(role_matches):
                txt = (
                    f"You do not have the required roles to enter.\n"
                    f"You must have **ALL** of these roles to enter: {humanize_list(mentions)}"
                )
                return await edit(msg, txt)

        days_required = event["days_in_server"]
        if days_required:
            now = datetime.now()
            joined_on = author.joined_at
            if (now.timestamp() - joined_on.timestamp()) / (60 * 60 * 24) < days_required:
                txt = f"You must be in the server for at least `{days_required}` day(s) in order to enter this event."
                return await edit(msg, txt)

        event_name = event["event_name"]

        grammar = "s one at a time" if per_user != 1 else ""
        if filesub:
            txt = (
                f"**Enter your file submission{grammar} below.**\n"
                f"Include some text with your upload for the entry description\n"
                f"If you don't have permission to send attachments, you can DM me instead."
            )
        else:
            txt = f"**Enter your submission{grammar} below.**"

        if per_user > 1:
            txt += (
                "\n\nWhen you are finished, type `done`.\n"
                f"This event allows up to `{per_user}` submissions per user."
            )
        txt += "\n\nType `cancel` at any time to cancel."
        await edit(msg, txt, title=event_name)

        submissions = []
        while True:
            if (len(submissions) + already_submitted) >= per_user:
                break
            async with GetReply(ctx, timeout=600) as reply:
                if reply is None:
                    return
                if reply.content.lower() == "cancel":
                    return await cancel(msg)
                if reply.content.lower() == "done":
                    break
                attachments = get_attachments(reply)
                text = str(reply.content)

            if filesub and not attachments:
                await ctx.send("**UPLOAD A FILE**", delete_after=3)
                continue

            file = None
            filename = None
            url = None
            if filesub:
                att: discord.Attachment = attachments[0]
                size_limit = ctx.guild.filesize_limit
                if size_limit < att.size:
                    guildsize = get_size(size_limit)
                    await ctx.send(
                        f"**FILE SIZE TOO LARGE!** Upload a file `{guildsize}` or smaller.",
                        delete_after=10,
                    )
                    continue
                async with ctx.typing():
                    file = await att.read()
                filename = str(att.filename)
                url = att.url
            sub = {"text": text, "file": file, "filename": filename, "url": url}
            submissions.append(sub)
            await ctx.send("Entry added!", delete_after=5)

        if not submissions:
            return await edit(msg, "No submissions send, entry cancelled")

        await edit(msg, "Are you sure you want to enter with these submissions? (y/n)")
        async with GetReply(ctx) as reply:
            if reply is None:
                return await cancel(msg)
            if reply.content.lower() == "cancel":
                return await cancel(msg)
            if "n" in reply.content.lower():
                return await cancel(msg)

        await edit(msg, "Your entries have been submitted!")

        channel = ctx.guild.get_channel(event["channel_id"])
        emoji = conf["default_emoji"]
        if emoji:
            emoji = self.bot.get_emoji(emoji)
        else:
            emoji = DEFAULT_EMOJI
        to_save = []
        for index, i in enumerate(submissions):
            text = i["text"]
            bytesfile: bytes = i["file"]
            filename = i["filename"]
            if DPY2:
                pfp = author.display_avatar.url
            else:
                pfp = author.avatar_url
            ts = int(datetime.now().timestamp())
            dtype = "Description" if filesub else "Entry"
            desc = f"`Author:    `{author}\n" f"`Submitted: `<t:{ts}:f>\n\n"
            if text.strip():
                desc += f"**{dtype}**\n{text}"

            em = discord.Embed(description=desc, color=author.color)
            em.set_footer(text="Click the emoji below to vote")

            if bytesfile:
                em.set_author(name=f"New {event_name} submission!", url=i["url"])
                em.set_image(url=f"attachment://{filename}")
            else:
                em.set_author(name=f"New {event_name} submission!")
            if pfp:
                em.set_thumbnail(url=pfp)

            if bytesfile and filename:
                buffer = BytesIO(bytesfile)
                buffer.name = filename
                buffer.seek(0)
                file = discord.File(buffer, filename=filename)
                entry_message: discord.Message = await channel.send(embed=em, file=file)
            else:
                entry_message: discord.Message = await channel.send(embed=em)
            await entry_message.add_reaction(emoji)
            to_save.append(entry_message.id)

        async with self.config.guild(ctx.guild).events() as events:
            if uid in events[event_name]["submissions"]:
                events[event_name]["submissions"][uid].extend(to_save)
            else:
                events[event_name]["submissions"][uid] = [to_save]

    @commands.group(name="events")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def events_group(self, ctx: commands.Context):
        """Create, manage and view events"""

    @events_group.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """View the current events and settings"""
        conf = await self.config.guild(ctx.guild).all()
        emoji = conf["default_emoji"]
        if emoji:
            emoji = self.bot.get_emoji(emoji)
        else:
            emoji = DEFAULT_EMOJI
        pages = []
        staff_roles = [ctx.guild.get_role(rid).mention for rid in conf["staff_roles"] if ctx.guild.get_role(rid)]
        ping_staff = conf["ping_staff"]
        notify_roles = [ctx.guild.get_role(rid).mention for rid in conf["notify_roles"] if ctx.guild.get_role(rid)]
        role_blacklist = [ctx.guild.get_role(rid).mention for rid in conf["role_blacklist"] if ctx.guild.get_role(rid)]
        user_blacklist = [str(ctx.guild.get_member(uid)) for uid in conf["user_blacklist"] if ctx.guild.get_member(uid)]
        auto_delete = "Enabled" if conf["auto_delete"] else "Disabled"
        results_delete = "Enabled" if conf["result_delete"] else "Disabled"
        em = discord.Embed(
            title="Main Settings",
            description=f"`Ping Staff:    `{ping_staff}\n"
            f"`Auto Delete:   `{auto_delete}\n"
            f"`Result Delete: `{results_delete}\n"
            f"`Default Emoji: `{emoji}",
            color=ctx.author.color,
        )
        em.add_field(
            name="Staff Roles",
            value=humanize_list(staff_roles) if staff_roles else "None",
        )
        em.add_field(
            name="Notify Roles",
            value=humanize_list(notify_roles) if notify_roles else "None",
        )
        em.add_field(
            name="Role Blacklist",
            value=humanize_list(role_blacklist) if role_blacklist else "None",
            inline=False,
        )
        em.add_field(
            name="User Blacklist",
            value=humanize_list(user_blacklist) if user_blacklist else "None",
            inline=False,
        )
        await ctx.send(embed=em)
        if not conf["events"]:
            return await ctx.send("There are no events to display")
        currency = await bank.get_currency_name(ctx.guild)
        pagecount = len(conf["events"].keys())
        for index, i in enumerate(conf["events"].values()):
            page = index + 1
            name = i["event_name"]
            channel = ctx.guild.get_channel(i["channel_id"])
            filesub = i["file_submission"]
            per_user = i["submissions_per_user"]
            winners = i["winners"]
            participants = len(i["submissions"].keys())
            submissions = sum(len(subs) for subs in i["submissions"].values()) if i["submissions"] else 0
            start = i["start_date"]
            end = i["end_date"]
            roles = i["roles_required"]
            required = [ctx.guild.get_role(rid).mention for rid in roles] if roles else []
            need_all_roles = i["need_all_roles"]
            days_in_server = i["days_in_server"]
            rewards = i["rewards"]
            status = "**COMPLETED**" if i["completed"] else "In Progress"
            desc = (
                f"`Event Name:     `{name}\n"
                f"`Status:         `{status}\n"
                f"`Channel:        `{channel.mention if channel else '#DeletedChannel'}\n"
                f"`File Uploads:   `{filesub}\n"
                f"`Per User:       `{per_user}\n"
                f"`Winners:        `{winners}\n"
                f"`Participants:   `{participants}\n"
                f"`Submissions:    `{submissions}\n"
                f"`Start Date:     `<t:{start}:f> (<t:{start}:R>)\n"
                f"`End Date:       `<t:{end}:f> (<t:{end}:R>)\n"
                f"`Days in Server: `{days_in_server}"
            )
            em = discord.Embed(title="Events", description=desc, color=ctx.author.color)
            if required:
                em.add_field(
                    name="Required Roles",
                    value=f"{humanize_list(required)}\n`All Roles Required: `{need_all_roles}",
                    inline=False,
                )
            if rewards:
                val = ""
                for place, reward in rewards.items():
                    if isinstance(reward, int):
                        val += f"`{place} place: `{humanize_number(reward)} {currency}\n"
                    else:
                        val += f"`{place} place: `{reward}\n"

                em.add_field(name="Rewards", value=val, inline=False)
            em.set_footer(text=f"Page {page}/{pagecount}")
            pages.append(em)
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @events_group.command(name="pingstaff")
    async def toggle_ping_staff(self, ctx: commands.Context):
        """(Toggle) Ping staff on event completion"""
        toggle = await self.config.guild(ctx.guild).ping_staff()
        if toggle:
            await self.config.guild(ctx.guild).ping_staff.set(False)
            await ctx.send("I will no longer ping staff on event completion")
        else:
            await self.config.guild(ctx.guild).ping_staff.set(True)
            await ctx.send("I will ping staff on event completion")

    @events_group.command(name="autodelete")
    async def toggle_auto_delete(self, ctx: commands.Context):
        """
        (Toggle) Auto delete events from config when they complete

        If auto delete is enabled, the messages in the event channel will need to be cleaned up manually
        """
        toggle = await self.config.guild(ctx.guild).auto_delete()
        if toggle:
            await self.config.guild(ctx.guild).auto_delete.set(False)
            await ctx.send("I will no longer delete events from the config when they complete")
        else:
            await self.config.guild(ctx.guild).auto_delete.set(True)
            await ctx.send("I will delete events from the config when they complete")

    @events_group.command(name="resultdelete")
    async def toggle_result_delete(self, ctx: commands.Context):
        """
        (Toggle) Include event results in the messages to delete on cleanup

        If this is on when an event is deleted and the user chooses to clean up the messages,
        the results announcement will also be deleted
        """
        toggle = await self.config.guild(ctx.guild).result_delete()
        if toggle:
            await self.config.guild(ctx.guild).result_delete.set(False)
            await ctx.send("I will no longer delete the results announcement when cleaning up")
        else:
            await self.config.guild(ctx.guild).result_delete.set(True)
            await ctx.send("I will also delete the results announcement when cleaning up")

    @events_group.command(name="staffrole")
    async def add_rem_staff_roles(self, ctx: commands.Context, *, role: discord.Role):
        """
        Add/Remove staff roles

        If ping staff is enabled, these roles will be pinged on event completion
        """
        roles = await self.config.guild(ctx.guild).staff_roles()
        if role.id in roles:
            async with self.config.guild(ctx.guild).staff_roles() as staff:
                staff.remove(role.id)
            await ctx.send(f"I have removed {role.mention} from the staff roles")
        else:
            async with self.config.guild(ctx.guild).staff_roles() as staff:
                staff.append(role.id)
            await ctx.send(f"I have added {role.mention} to the staff roles")

    @events_group.command(name="notifyrole")
    async def add_rem_notify_roles(self, ctx: commands.Context, *, role: discord.Role):
        """
        Add/Remove notify roles

        These roles will be pinged on event start and completion
        """
        roles = await self.config.guild(ctx.guild).notify_roles()
        if role.id in roles:
            async with self.config.guild(ctx.guild).notify_roles() as notify:
                notify.remove(role.id)
            await ctx.send(f"I have removed {role.mention} from the notify roles")
        else:
            async with self.config.guild(ctx.guild).notify_roles() as notify:
                notify.append(role.id)
            await ctx.send(f"I have added {role.mention} to the notify roles")

    @events_group.command(name="blacklistrole")
    async def add_rem_blacklist_role(self, ctx: commands.Context, *, role: discord.Role):
        """
        Add/Remove blacklisted roles

        These roles are not allowed to enter events, but can still vote on them
        """
        roles = await self.config.guild(ctx.guild).role_blacklist()
        if role.id in roles:
            async with self.config.guild(ctx.guild).role_blacklist() as blacklist:
                blacklist.remove(role.id)
            await ctx.send(f"I have removed {role.mention} from the role blacklist")
        else:
            async with self.config.guild(ctx.guild).role_blacklist() as blacklist:
                blacklist.append(role.id)
            await ctx.send(f"I have added {role.mention} to the role blacklist")

    @events_group.command(name="blacklistuser")
    async def add_rem_blacklist_user(self, ctx: commands.Context, *, user: discord.Member):
        """
        Add/Remove blacklisted users

        These users are not allowed to enter events, but can still vote on them
        """
        users = await self.config.guild(ctx.guild).user_blacklist()
        if user.id in users:
            async with self.config.guild(ctx.guild).user_blacklist() as blacklist:
                blacklist.remove(user.id)
            await ctx.send(f"I have removed **{user}** from the blacklist")
        else:
            async with self.config.guild(ctx.guild).user_blacklist() as blacklist:
                blacklist.append(user.id)
            await ctx.send(f"I have added **{user}** to the blacklist")

    @events_group.command(name="emoji")
    async def set_emoji(self, ctx: commands.Context, emoji: Optional[discord.Emoji]):
        """
        Set the default emoji for votes

        Changing the vote emoji only affects events created after this is changed.
        Existing events will still use the previous emoji for votes
        """
        if not emoji:
            await self.config.guild(ctx.guild).default_emoji.set(None)
            await ctx.message.add_reaction(DEFAULT_EMOJI)
            await ctx.send("Voting emoji set to default!")
        else:
            try:
                await ctx.message.add_reaction(emoji)
            except discord.HTTPException:
                return await ctx.send("Uh oh, I am unable to use that emoji")
            await self.config.guild(ctx.guild).default_emoji.set(emoji.id)
            await ctx.send("Custom voting emoji set!")

    @events_group.command(name="end")
    async def end_event(self, ctx: commands.Context):
        """
        End an event early, counting votes/announcing the winner

        This will also delete the event afterwards
        """
        existing = await self.config.guild(ctx.guild).events()
        if not existing:
            return await ctx.send("There are no events to end")
        res = await select_event(ctx, existing)
        if not res:
            return
        event: dict = res["event"]
        msg: discord.Message = res["msg"]
        if event["completed"]:
            return await msg.edit(
                content=f"This event has already completed!\n"
                f"To delete this event, use the `{ctx.clean_prefix}events delete` command",
                embed=None,
            )
        await msg.edit(
            content="Are you sure you want to end this event and tally the votes? (y/n)",
            embed=None,
        )
        async with GetReply(ctx) as reply:
            if reply is None:
                return await msg.delete()
            if "y" not in reply.content.lower():
                return await msg.edit(content=f"Not deleting **{event['event_name']}**")
        subs = event["submissions"]
        if not subs:
            return await msg.edit(
                content=f"There are no submissions for **{event['event_name']}.**\n"
                f"If you want to delete it, use the `{ctx.clean_prefix}events delete` command instead."
            )
        if not ctx.guild.get_channel(event["channel_id"]):
            return await msg.edit(
                content=f"I am unable to find the channel for **{event['event_name']}!**\n"
                f"To delete this event, use the `{ctx.clean_prefix}events delete` command."
            )
        await msg.edit(content="Ending event and tallying votes. Stand by...")
        async with ctx.typing():
            await self._end_event(ctx.guild, event)
        await msg.edit(content=f"**{event['event_name']}** has ended! Check the event channel for the results")

    @events_group.command(name="extend")
    async def extend_event(self, ctx: commands.Context, *, time_string: str):
        """
        Extend the runtime of an event

        **Examples**
        `10d` - 10 days
        `7d4h` - 7 days 4 hours
        """
        existing = await self.config.guild(ctx.guild).events()
        if not existing:
            return await ctx.send("There are no events to extend")
        res = await select_event(ctx, existing)
        if not res:
            return
        event: dict = res["event"]
        msg: discord.Message = res["msg"]
        delta = parse_timedelta(time_string, minimum=timedelta(minutes=1))
        if delta is None:
            return await msg.edit(content="That is not a valid time delta!", embed=None)
        inc = int(delta.total_seconds())
        newtime = event["end_date"] + inc
        async with ctx.typing():
            async with self.config.guild(ctx.guild).events() as events:
                events[event["event_name"]]["end_date"] += inc
        txt = (
            f"The **{event['event_name']}** event has been extended by {humanize_timedelta(timedelta=delta)}\n"
            f"New end date is <t:{newtime}:f> (<t:{newtime}:R>)"
        )
        await msg.edit(content=txt, embed=None)
        chan = ctx.guild.get_channel(event["channel_id"])
        if chan and chan.id != ctx.channel.id:
            message = await chan.send(txt)
            async with self.config.guild(ctx.guild).events() as events:
                events[event["event_name"]]["messages"].append(message.id)

    @events_group.command(name="shorten")
    async def shorten_event(self, ctx: commands.Context, *, time_string: str):
        """
        Shorten the runtime of an event

        **Examples**
        `10d` - 10 days
        `7d4h` - 7 days 4 hours
        """
        existing = await self.config.guild(ctx.guild).events()
        if not existing:
            return await ctx.send("There are no events to shorten the runtime of")
        res = await select_event(ctx, existing)
        if not res:
            return
        event: dict = res["event"]
        msg: discord.Message = res["msg"]
        delta = parse_timedelta(time_string, minimum=timedelta(minutes=1))
        if delta is None:
            return await msg.edit(content="That is not a valid time delta!", embed=None)
        inc = int(delta.total_seconds())
        newtime = event["end_date"] - inc
        async with ctx.typing():
            async with self.config.guild(ctx.guild).events() as events:
                events[event["event_name"]]["end_date"] -= inc
        txt = (
            f"The **{event['event_name']}** event has been shortened by {humanize_timedelta(timedelta=delta)}\n"
            f"New end date is <t:{newtime}:f> (<t:{newtime}:R>)"
        )
        await msg.edit(content=txt, embed=None)
        chan = ctx.guild.get_channel(event["channel_id"])
        if chan and chan.id != ctx.channel.id:
            message = await chan.send(txt)
            async with self.config.guild(ctx.guild).events() as events:
                events[event["event_name"]]["messages"].append(message.id)

    @events_group.command(name="remove")
    async def remove_user(self, ctx: commands.Context, *, user: discord.Member):
        """Remove a user from an active event"""
        existing = await self.config.guild(ctx.guild).events()
        if not existing:
            return await ctx.send("There are no events to remove users from")
        res = await select_event(ctx, existing, skip_completed=True)
        if not res:
            return
        event: dict = res["event"]
        msg: discord.Message = res["msg"]
        channel: discord.TextChannel = ctx.guild.get_channel(event["channel_id"])
        subs = event["submissions"]
        event_name = event["event_name"]

        uid = str(user.id)
        if uid not in subs:
            return await msg.edit(
                content="This user doesn't have any submissions for that event",
                embed=None,
            )

        deleted = 0
        async with ctx.typing():
            async with self.config.guild(ctx.guild).events() as events:
                for mid in events[event_name]["submissions"][uid].copy():
                    try:
                        message = await channel.fetch_message(mid)
                    except discord.NotFound:
                        continue
                    await message.delete()
                    deleted += 1
                del events[event_name]["submissions"][uid]

        await msg.edit(content=f"Removed {deleted} entries by {user.name} from the {event_name} event")

    @events_group.command(name="delete")
    async def delete_event(self, ctx: commands.Context):
        """Delete an event outright"""
        existing = await self.config.guild(ctx.guild).events()
        if not existing:
            return await ctx.send("There are no events to delete")
        res = await select_event(ctx, existing, skip_completed=False)
        if not res:
            return
        event: dict = res["event"]
        msg: discord.Message = res["msg"]
        channel: discord.TextChannel = ctx.guild.get_channel(event["channel_id"])
        messages = [event["submissions"], event["messages"]]
        if any(messages) and channel:
            await msg.edit(
                content="Would you like to cleanup the related messages for this event as well? (y/n)",
                embed=None,
            )
            async with GetReply(ctx) as reply:
                if reply is None:
                    return await msg.edit(content="Deletion cancelled, did not respond")
                if "y" in reply.content.lower():
                    with contextlib.suppress(discord.NotFound, discord.Forbidden, AttributeError):
                        for message_ids in event["submissions"].values():
                            for message_id in message_ids:
                                message = await channel.fetch_message(message_id)
                                await message.delete()
                        for message_id in event["messages"]:
                            message = await channel.fetch_message(message_id)
                            await message.delete()

        async with self.config.guild(ctx.guild).events() as events:
            del events[event["event_name"]]
        await msg.edit(content=f"The **{event['event_name']}** event has been deleted!", embed=None)

    @events_group.command(name="create")
    @commands.bot_has_permissions(embed_links=True)
    async def create_event(self, ctx: commands.Context):
        """Create a new event"""

        async def cancel(message):
            await message.edit(content="Event creation cancelled")

        conf = await self.config.guild(ctx.guild).all()
        existing = conf["events"]
        if len(existing.keys()) >= 25:
            return await ctx.send("You can only have up to 25 active events at a time")

        await ctx.send("Event creation started, you can type `cancel` at any time to stop")
        msg = await ctx.send("What would you like to call this event?")
        async with GetReply(ctx) as reply:
            if reply is None:
                return await cancel(msg)
            name = reply.content
            if name.lower() == "cancel":
                return await cancel(msg)
            if name in existing:
                await ctx.send(f"The event `{name}` already exists!", delete_after=10)
                return await cancel(msg)

        await msg.edit(content="Enter a short description of this event (1024 characters or less)")
        while True:
            async with GetReply(ctx, timeout=600) as reply:
                if reply is None:
                    return await cancel(msg)
                if reply.content.lower() == "cancel":
                    return await cancel(msg)
                if len(reply.content) > 1024:
                    await ctx.send(
                        "Keep the event description limited to 1024 characters or less",
                        delete_after=10,
                    )
                    continue
                description = reply.content
                break

        await msg.edit(
            content="What channel would you like submissions to be sent to?\n"
            "`Mention a channel`, or say `here` for this one."
        )
        channel = ctx.channel
        while True:
            async with GetReply(ctx) as reply:
                if reply is None:
                    return await cancel(msg)
                if reply.content.lower() == "cancel":
                    return await cancel(msg)
                if reply.content.lower() == "here":
                    break
                if not reply.channel_mentions:
                    await ctx.send(
                        "You must mention the channel you want submissions to be sent to!",
                        delete_after=10,
                    )
                    continue
                channel: discord.TextChannel = reply.channel_mentions[0]
                if isinstance(channel, discord.ForumChannel):
                    await ctx.send("The event needs to be in a text channel, not a forum!", delete_after=10)
                    continue
                break

        await msg.edit(content="Will submissions be file uploads, or text based?\n" "Reply with (`file` or `text`)")
        async with GetReply(ctx) as reply:
            if reply is None:
                return await cancel(msg)
            if reply.content.lower() == "cancel":
                return await cancel(msg)
            if "t" in reply.content.lower():
                filesubmission = False
            else:
                filesubmission = True

        perms = {
            channel.permissions_for(ctx.me).view_channel: "View Channel",
            channel.permissions_for(ctx.me).send_messages: "Send Messages",
            channel.permissions_for(ctx.me).embed_links: "Embed Links",
            channel.permissions_for(ctx.me).add_reactions: "Add Reactions",
        }
        if filesubmission:
            # If event is file submission, need attach files perm
            perms[channel.permissions_for(ctx.me).attach_files] = "Attach Files"
        if not all(perms.keys()):
            missing = [v for k, v in perms.items() if not k]
            return await msg.edit(
                content="I am missing the following permissions for that channel:\n" f"{box(humanize_list(missing))}"
            )

        await msg.edit(content="How many submissions per user are allowed?")
        submissions = 1
        while True:
            async with GetReply(ctx) as reply:
                if reply is None:
                    return await cancel(msg)
                if reply.content.lower() == "cancel":
                    return await cancel(msg)
                if not reply.content.isdigit():
                    await ctx.send("Your reply must be a number!", delete_after=10)
                    continue
                submissions = int(reply.content)
                break

        await msg.edit(content="How many winners will be selected? (up to 25)")
        winners = 1
        while True:
            async with GetReply(ctx) as reply:
                if reply is None:
                    return await cancel(msg)
                if reply.content.lower() == "cancel":
                    return await cancel(msg)
                if not reply.content.isdigit():
                    await ctx.send("Your reply must be a number!", delete_after=10)
                    continue
                if int(reply.content) > 25:
                    await ctx.send("You can only have up to 25 winners!", delete_after=10)
                    continue
                winners = int(reply.content)
                break

        await msg.edit(content="Would you like to include reward descriptions for the winners? (y/n)")
        rewards = {}
        do_rewards = False
        async with GetReply(ctx) as reply:
            if reply is None:
                return await cancel(msg)
            if reply.content.lower() == "cancel":
                return await cancel(msg)
            if "y" in reply.content.lower():
                do_rewards = True
        if do_rewards:
            done = False
            for i in range(winners):
                place = get_place(i + 1)
                await msg.edit(
                    content=f"Enter the reward for **{place} place**\n"
                    f"If the reward is a `number`, "
                    f"the user will be rewarded that amount of economy credits automatically.\n"
                    f"If the reward is `text`, the reward description will be included in the announcement.\n\n"
                    f"You can type `done` to skip any remaining winner reward places.\n"
                    f"*Alternatively, you can type `skip` to skip the reward for a specific place.*"
                )
                while True:
                    async with GetReply(ctx) as reply:
                        if reply is None:
                            return await cancel(msg)
                        if reply.content.lower() == "cancel":
                            return await cancel(msg)
                        if reply.content.lower() == "done":
                            done = True
                            break
                        if reply.content.lower() == "skip":
                            break
                        if reply.content.isdigit():
                            rewards[place] = int(reply.content)
                        else:
                            rewards[place] = reply.content
                        break
                if done:
                    break

        await msg.edit(content="How long will this event be running for?\n" "**Example Replies**\n10d\n7d4h\n2w3d10h")
        delta = timedelta(days=1)
        while True:
            async with GetReply(ctx) as reply:
                if reply is None:
                    return await cancel(msg)
                if reply.content.lower() == "cancel":
                    return await cancel(msg)
                rdelta = parse_timedelta(reply.content, minimum=timedelta(minutes=10))
                if rdelta is None:
                    await ctx.send(
                        "Please send a valid timedelta in the format above!",
                        delete_after=10,
                    )
                    continue
                delta = rdelta
                break

        await msg.edit(content="Does entering this event require a specific role or roles? (y/n)")
        async with GetReply(ctx) as reply:
            if reply is None:
                return await cancel(msg)
            if reply.content.lower() == "cancel":
                return await cancel(msg)
        roles = []
        mentions = []
        need_all_roles = False
        if "y" in reply.content.lower():
            await msg.edit(content="Please mention the role or roles required to enter this event")
            roles = []
            while True:
                async with GetReply(ctx) as repl:
                    if repl is None:
                        return await cancel(msg)
                    if repl.content.lower() == "cancel":
                        return await cancel(msg)
                    if not repl.role_mentions:
                        await ctx.send(
                            "Please mention the roles this event requires to enter",
                            delete_after=10,
                        )
                        continue
                    roles = [role.id for role in repl.role_mentions]
                    mentions = [role.mention for role in repl.role_mentions]
                    break
            if len(roles) > 1:
                await msg.edit(content="Do users need to have **all** of these roles in order to enter? (y/n)")
                async with GetReply(ctx) as repl:
                    if repl is None:
                        return await cancel(msg)
                    if repl.content.lower() == "cancel":
                        return await cancel(msg)
                    if "y" in repl.content.lower():
                        need_all_roles = True

        await msg.edit(content="Do users need to be in the server for a certain amount of days to enter? (y/n)")
        async with GetReply(ctx) as reply:
            if reply is None:
                return await cancel(msg)
            if reply.content.lower() == "cancel":
                return await cancel(msg)
            days_in_server = 0
            if "y" in reply.content.lower():
                await msg.edit(content="How many days do users need to be in the server to enter?")
                while True:
                    async with GetReply(ctx) as repl:
                        if repl is None:
                            return await cancel(msg)
                        if repl.content.lower() == "cancel":
                            return await cancel(msg)
                        if not repl.content.isdigit():
                            await ctx.send("Your reply must be a number!", delete_after=10)
                            continue
                        days_in_server = int(repl.content)
                        break

        now = datetime.now()
        start_date = int(now.timestamp())
        end_date = int((now + delta).timestamp())

        event = {
            "event_name": name,
            "description": description,
            "channel_id": channel.id,
            "file_submission": filesubmission,  # Either media/file or text submissions
            "submissions_per_user": submissions,  # Example 1 picture or file per user
            "winners": winners,  # How many winners to select
            "rewards": rewards,  # Rewards for each winner according to their place
            "submissions": {},  # User ID keys with list of their submission message ID's
            "start_date": start_date,  # Timestamp
            "end_date": end_date,  # Timestamp
            "roles_required": roles,  # Role IDs
            "need_all_roles": need_all_roles,  # Whether the users need all the required roles
            "days_in_server": days_in_server,  # Days user must be in server to enter
            "emoji": conf["default_emoji"],  # Default emoji at time of creation
            "messages": [],  # Any messages related to the event
            "completed": False,
        }

        await msg.edit(content="Event creation complete!")
        etype = "File submissions" if filesubmission else "Text submissions"
        embed = discord.Embed(
            title="Event Details",
            description=f"`Event Name:      `{name}\n"
            f"`Channel:         `{channel.mention}\n"
            f"`Event Type:      `{etype}\n"
            f"`Winner Count:    `{winners}\n"
            f"`Days In Server:  `{days_in_server}\n"
            f"`Start Date:      `<t:{start_date}:D> (<t:{start_date}:R>)\n"
            f"`End Date:        `<t:{end_date}:D> (<t:{end_date}:R>)",
            color=ctx.author.color,
        )
        if roles:
            embed.add_field(
                name="Required Roles",
                value=f"{humanize_list(mentions)}\n`All Roles Required: `{need_all_roles}",
                inline=False,
            )
        if ctx.channel.id != channel.id:
            await ctx.send(embed=embed)

        notify_roles = conf["notify_roles"]
        notify_roles = [ctx.guild.get_role(r).mention for r in notify_roles if ctx.guild.get_role(r)]
        notify_users = conf["notify_users"]
        notify_users = [ctx.guild.get_member(m).mention for m in notify_users if ctx.guild.get_member(m)]
        txt = f"{humanize_list(notify_users)}\n" f"{humanize_list(notify_roles)}"

        emoji_id = conf["default_emoji"]
        if emoji_id:
            emoji = self.bot.get_emoji(emoji_id)
        else:
            emoji = DEFAULT_EMOJI

        embed = discord.Embed(
            title="A new event has started!",
            description=f"`Event Name:     `**{name}**\n"
            f"`Event Type:     `{etype}\n"
            f"`Winner Count:   `{winners}\n"
            f"`Days In Server: `{days_in_server}\n"
            f"`Start Date:     `<t:{start_date}:D> (<t:{start_date}:R>)\n"
            f"`End Date:       `<t:{end_date}:D> (<t:{end_date}:R>)\n\n"
            f"Use the `{ctx.clean_prefix}enter` command to enter.\n"
            f"React with {emoji} to vote on submissions.",
            color=ctx.author.color,
        )
        icon = guild_icon(ctx.guild)
        if icon:
            embed.set_thumbnail(url=icon)
        if roles and mentions:
            if need_all_roles:
                embed.add_field(
                    name="Required Roles",
                    value=f"Must have **ALL** roles\n{humanize_list(mentions)}",
                    inline=False,
                )
            else:
                embed.add_field(
                    name="Required Roles",
                    value=f"Must have at least one role\n{humanize_list(mentions)}",
                    inline=False,
                )
        if description:
            embed.add_field(name="Event Details", value=description, inline=False)
        if rewards:
            currency = await bank.get_currency_name(ctx.guild)
            val = ""
            for place, reward in rewards.items():
                if isinstance(reward, int):
                    val += f"`{place} place: `{humanize_number(reward)} {currency}\n"
                else:
                    val += f"`{place} place: `{reward}"
            embed.add_field(name="Rewards", value=val, inline=False)

        mentions = discord.AllowedMentions(roles=True, users=True)
        announcement = await channel.send(txt, embed=embed, allowed_mentions=mentions)
        event["messages"].append(announcement.id)
        async with self.config.guild(ctx.guild).events() as events:
            events[name] = event

    async def _end_event(self, guild: discord.guild, event: dict):
        conf = await self.config.guild(guild).all()
        rblacklist = conf["role_blacklist"]
        ublacklist = conf["user_blacklist"]
        emoji_id = conf["default_emoji"]
        if emoji_id:
            emoji = self.bot.get_emoji(emoji_id)
        else:
            emoji = DEFAULT_EMOJI

        # If emoji was changed after event was created
        if event["emoji"] and event["emoji"] != emoji_id:
            emoji = self.bot.get_emoji(event["emoji"])

        channel: discord.TextChannel = guild.get_channel(int(event["channel_id"]))
        subs = event["submissions"]
        rewards = event["rewards"]
        currency = await bank.get_currency_name(guild)
        results = {}
        for uid, message_ids in subs.items():
            submitter: discord.Member = guild.get_member(int(uid))
            # Ignore users no longer in the server
            if not submitter:
                continue
            if submitter.id in ublacklist:
                continue
            if any(r.id in rblacklist for r in submitter.roles):
                continue
            for message_id in message_ids:
                if isinstance(message_id, list):
                    # IDFK
                    message_id = message_id[0]
                try:
                    message = await channel.fetch_message(message_id)
                except (discord.NotFound, discord.HTTPException):
                    log.warning(f"Failed to fetch message ID {message_id} for {submitter} in {channel.name}")
                    continue
                votes = 0
                for reaction in message.reactions:
                    if reaction.emoji != emoji:
                        continue
                    async for voter in reaction.users():
                        # Ignore votes from bots, the submitter, and users not in the guild
                        dont_want = [
                            voter.bot,
                            voter.id == submitter.id,
                            voter.guild is None,
                        ]
                        if any(dont_want):
                            continue
                        votes += 1

                attachment = message.embeds[0].image
                attachment_url = None
                filename = None
                if attachment:
                    attachment_url = attachment.url
                    filename = attachment.filename
                posted_on = message.created_at.timestamp()
                submission = {
                    "votes": votes,
                    "entry": message.jump_url,
                    "attachment_url": attachment_url,
                    "filename": filename,
                    "timestamp": posted_on,
                }

                if submitter in results:
                    if results[submitter]["votes"] == votes:
                        # Pick which one to use at random since votes are equal
                        if random.random() < 0.5:
                            results[submitter] = submission
                    elif results[submitter]["votes"] < votes:
                        results[submitter] = submission
                else:
                    results[submitter] = submission

        # Sort by timestamp first, then votes. Ties will go to the person who posted first
        pre = sorted(results.items(), key=lambda x: x[1]["timestamp"])
        final = sorted(pre, key=lambda x: x[1]["votes"], reverse=True)
        winners = event["winners"]
        title = f"The {event['event_name']} event has ended!"
        thumbnail = None
        to_mention = []
        if final:
            entries = len(final)
            if entries != 1:
                grammar = ["were a total of", "participants"]
            else:
                grammar = ["was", "participant"]
            image_url = None
            winner_color = final[0][0].color
            embed = discord.Embed(
                description=f"There {grammar[0]} {entries} {grammar[1]}!",
                color=winner_color,
            )
            places = {"1st": "🥇 ", "2nd": "🥈 ", "3rd": "🥉 "}
            for index, entry in enumerate(final[:winners]):
                place = get_place(index + 1)
                user = entry[0]
                to_mention.append(user.mention)
                medal = places[place] if place in places else ""
                i = entry[1]
                votes = i["votes"]
                grammar = "votes" if votes != 1 else "vote"
                jump_url = i["entry"]
                if index == 0:
                    image_url = i["attachment_url"]
                    if image_url:
                        embed.set_footer(text=f"1st place entry submitted by {user}")
                    pfp = profile_icon(user)
                    if pfp:
                        thumbnail = pfp
                value = f"{user} with **[{votes} {grammar}!]({jump_url})**"
                if place in rewards:
                    reward = rewards[place]
                    if isinstance(reward, int):
                        value += f"\n`Reward: `{humanize_number(reward)} {currency}"
                        try:
                            await bank.deposit_credits(user, reward)
                        except BalanceTooHigh as e:
                            await bank.set_balance(user, e.max_balance)
                    else:
                        value += f"\n`Reward: `{reward}"

                embed.add_field(name=f"{medal}{place} Place!", value=value, inline=False)
            if image_url:
                embed.set_image(url=image_url)
        else:
            embed = discord.Embed(
                title=f"The {event['event_name']} event has ended!",
                description="Sadly there were no participants 😢",
                color=discord.Color.red(),
            )

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        icon = guild_icon(guild)
        if icon:
            embed.set_author(name=title, icon_url=icon)
        else:
            embed.set_author(name=title)

        notify_roles = conf["notify_roles"]
        notify_roles = [guild.get_role(r).mention for r in notify_roles if guild.get_role(r)]
        notify_users = conf["notify_users"]
        notify_users = [guild.get_member(m).mention for m in notify_users if guild.get_member(m)]
        notify_staff = conf["ping_staff"]
        staff_roles = conf["staff_roles"]
        staff_roles = [guild.get_role(r).mention for r in staff_roles if guild.get_role(r)]
        txt = f"{humanize_list(to_mention)}\n" f"{humanize_list(notify_users)}\n" f"{humanize_list(notify_roles)}"
        if notify_staff and staff_roles:
            txt += f"\n{humanize_list(staff_roles)}"
        mentions = discord.AllowedMentions(roles=True, users=True)
        msg = await channel.send(txt, embed=embed, allowed_mentions=mentions)
        async with self.config.guild(guild).events() as events:
            if conf["auto_delete"]:
                del events[event["event_name"]]
            else:
                events[event["event_name"]]["completed"] = True
                if conf["result_delete"]:
                    events[event["event_name"]]["messages"].append(msg.id)
