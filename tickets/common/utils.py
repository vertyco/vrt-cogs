import asyncio
import logging
import zipfile
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, time
from io import BytesIO, StringIO
from pathlib import Path
from typing import List, Optional, Tuple, Union

import chat_exporter
import discord
import pytz
from discord.utils import escape_markdown
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, text_to_file
from redbot.core.utils.mod import is_admin_or_superior

from .transcript import process_transcript_html

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", __file__)


class _MessageProxy:
    """Proxy wrapper for discord.Message that allows setting the 'interaction' property.

    The chat-exporter library tries to set message.interaction = "" which fails in newer
    discord.py versions where 'interaction' is a read-only property. This proxy intercepts
    that assignment while delegating all other attribute access to the wrapped message.
    """

    __slots__ = ("_message", "_interaction")

    def __init__(self, message: discord.Message):
        object.__setattr__(self, "_message", message)
        # Access interaction_metadata instead of deprecated interaction property
        # This avoids the deprecation warning entirely
        interaction = getattr(message, "interaction_metadata", None) or getattr(message, "_interaction", None)
        object.__setattr__(self, "_interaction", interaction)

    @property
    def interaction(self):
        return object.__getattribute__(self, "_interaction")

    @interaction.setter
    def interaction(self, value):
        object.__setattr__(self, "_interaction", value)

    def __getattr__(self, name: str):
        return getattr(object.__getattribute__(self, "_message"), name)

    def __setattr__(self, name: str, value):
        if name in ("_message", "_interaction", "interaction"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_message"), name, value)


def _patch_messages_for_export(messages: list[discord.Message]) -> list[_MessageProxy]:
    """Wrap messages in proxy objects that allow chat-exporter to set 'interaction'.

    Args:
        messages: List of discord.Message objects

    Returns:
        List of _MessageProxy objects wrapping the original messages
    """
    return [_MessageProxy(msg) for msg in messages]


# Day name mapping for working hours
DAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


def is_within_working_hours(panel: dict) -> Tuple[bool, Optional[int], Optional[int]]:
    """Check if the current time is within working hours for a panel.

    Args:
        panel: The panel configuration dict

    Returns:
        Tuple of (is_within_hours, today_start_timestamp, today_end_timestamp)
        - is_within_hours: True if within working hours or no hours set, False otherwise
        - today_start_timestamp: Unix timestamp for today's start time or None
        - today_end_timestamp: Unix timestamp for today's end time or None
    """
    working_hours = panel.get("working_hours", {})
    if not working_hours:
        return (True, None, None)

    timezone_str = panel.get("timezone", "UTC")
    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    now = datetime.now(tz)
    day_name = DAY_NAMES[now.weekday()]

    day_hours = working_hours.get(day_name)
    if not day_hours:
        # No hours set for today - not within working hours
        return (False, None, None)

    start_str = day_hours.get("start")
    end_str = day_hours.get("end")
    if not start_str or not end_str:
        return (True, None, None)

    try:
        start_hour, start_min = map(int, start_str.split(":"))
        end_hour, end_min = map(int, end_str.split(":"))

        start_time = time(start_hour, start_min)
        end_time = time(end_hour, end_min)
        current_time = now.time()

        # Create datetime objects for today with start/end times for Discord timestamps
        start_dt = tz.localize(datetime(now.year, now.month, now.day, start_hour, start_min))
        end_dt = tz.localize(datetime(now.year, now.month, now.day, end_hour, end_min))
        start_timestamp = int(start_dt.timestamp())
        end_timestamp = int(end_dt.timestamp())

        is_within = start_time <= current_time <= end_time
        return (is_within, start_timestamp, end_timestamp)
    except (ValueError, AttributeError):
        return (True, None, None)


def format_working_hours_embed(panel: dict, user: discord.Member) -> Optional[discord.Embed]:
    """Generate an embed for the outside working hours message.

    Args:
        panel: The panel configuration dict
        user: The user who opened the ticket

    Returns:
        Discord embed if there's a custom message, None otherwise
    """
    custom_message = panel.get("outside_hours_message", "")
    working_hours = panel.get("working_hours", {})
    timezone_str = panel.get("timezone", "UTC")

    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    now = datetime.now(tz)
    day_name = DAY_NAMES[now.weekday()]
    day_hours = working_hours.get(day_name, {})
    start_str = day_hours.get("start", "")
    end_str = day_hours.get("end", "")

    if not custom_message:
        # Default message
        desc = _("You've created a ticket outside of our working hours, so please be aware that our ")
        desc += _("response time may be slightly delayed.")
        if start_str and end_str:
            # Create Discord timestamps for today's working hours
            try:
                start_hour, start_min = map(int, start_str.split(":"))
                end_hour, end_min = map(int, end_str.split(":"))
                start_dt = tz.localize(datetime(now.year, now.month, now.day, start_hour, start_min))
                end_dt = tz.localize(datetime(now.year, now.month, now.day, end_hour, end_min))
                start_ts = int(start_dt.timestamp())
                end_ts = int(end_dt.timestamp())
                desc += _(" Our working hours today are <t:{}:t> to <t:{}:t>.").format(start_ts, end_ts)
            except (ValueError, AttributeError):
                pass
    else:
        desc = custom_message

    embed = discord.Embed(
        title=_("Outside Working Hours"),
        description=desc,
        color=discord.Color.orange(),
    )
    embed.set_footer(text=user.name, icon_url=user.display_avatar.url)
    return embed


async def can_close(
    bot: Red,
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    author: discord.Member,
    owner_id: int,
    conf: dict,
):
    if str(owner_id) not in conf["opened"]:
        return False
    if str(channel.id) not in conf["opened"][str(owner_id)]:
        return False

    panel_name = conf["opened"][str(owner_id)][str(channel.id)]["panel"]
    panel_roles = conf["panels"][panel_name]["roles"]
    user_roles = [r.id for r in author.roles]

    support_roles = [i[0] for i in conf["support_roles"]]
    support_roles.extend([i[0] for i in panel_roles])

    can_close = False
    if any(i in support_roles for i in user_roles):
        can_close = True
    elif author.id == guild.owner_id:
        can_close = True
    elif await is_admin_or_superior(bot, author):
        can_close = True
    elif str(owner_id) == str(author.id) and conf["user_can_close"]:
        can_close = True
    return can_close


async def fetch_channel_history(channel: discord.TextChannel, limit: int | None = None) -> List[discord.Message]:
    history = []
    async for msg in channel.history(oldest_first=True, limit=limit):
        history.append(msg)
    return history


async def ticket_owner_hastyped(channel: discord.TextChannel, user: discord.Member) -> bool:
    async for msg in channel.history(limit=50, oldest_first=True):
        if msg.author.id == user.id:
            return True
    return False


def get_ticket_owner(opened: dict, channel_id: str) -> Optional[str]:
    for uid, tickets in opened.items():
        if channel_id in tickets:
            return uid


async def close_ticket(
    bot: Red,
    member: Union[discord.Member, discord.User],
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    conf: dict,
    reason: str | None,
    closedby: str,
    config: Config,
) -> None:
    opened = conf["opened"]
    if not opened:
        return
    uid = str(member.id)
    cid = str(channel.id)
    if uid not in opened:
        return
    if cid not in opened[uid]:
        return

    ticket = opened[uid][cid]
    pfp = ticket["pfp"]
    panel_name = ticket["panel"]
    panel = conf["panels"][panel_name]
    panel.get("threads")

    if not channel.permissions_for(guild.me).manage_channels and isinstance(channel, discord.TextChannel):
        await channel.send(_("I am missing the `Manage Channels` permission to close this ticket!"))
        return
    if not channel.permissions_for(guild.me).manage_threads and isinstance(channel, discord.Thread):
        await channel.send(_("I am missing the `Manage Threads` permission to close this ticket!"))
        return

    opened = int(datetime.fromisoformat(ticket["opened"]).timestamp())
    closed = int(datetime.now().timestamp())
    closer_name = escape_markdown(closedby)

    desc = _(
        "Ticket created by **{}-{}** has been closed.\n"
        "`PanelType: `{}\n"
        "`Opened on: `<t:{}:F>\n"
        "`Closed on: `<t:{}:F>\n"
        "`Closed by: `{}\n"
        "`Reason:    `{}\n"
    ).format(
        member.name,
        member.id,
        panel_name,
        opened,
        closed,
        closer_name,
        str(reason),
    )
    if isinstance(channel, discord.Thread) and conf["thread_close"]:
        desc += _("`Thread:    `{}\n").format(channel.mention)

    backup_text = _("Ticket Closed\n{}\nCurrently missing permissions to send embeds to this channel!").format(desc)
    embed_title = _("Ticket Closed")
    embed = discord.Embed(
        title=embed_title,
        description=desc,
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=pfp)
    log_chan: discord.TextChannel = guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None

    buffer = StringIO()
    files: List[dict] = []
    filename = (
        f"{member.name}-{member.id}.html" if conf.get("detailed_transcript") else f"{member.name}-{member.id}.txt"
    )
    filename = filename.replace("/", "")

    # Prep embed in case we're exporting a transcript
    em = discord.Embed(color=member.color)
    em.set_author(name=_("Archiving Ticket..."), icon_url=LOADING)

    use_exporter = conf.get("detailed_transcript", False)
    is_thread = isinstance(channel, discord.Thread)
    exporter_success = False

    if conf["transcript"]:
        temp_message = await channel.send(embed=em)

        # Fetch history first - we need it for both export methods and attachment collection
        history = await fetch_channel_history(channel)

        if use_exporter and history:
            try:
                # Wrap messages in proxy objects that allow chat-exporter to set 'interaction'
                patched_messages = _patch_messages_for_export(history)
                patched_messages.reverse()
                res = await chat_exporter.raw_export(
                    channel=channel,
                    messages=patched_messages,
                    tz_info="UTC",
                    guild=guild,
                    bot=bot,
                    military_time=True,
                    fancy_times=True,
                    support_dev=False,
                )
                if res:
                    buffer.write(res)
                    exporter_success = True
            except Exception as e:
                # chat-exporter may fail due to Discord.py API changes
                # Fall back to simple text transcript
                log.error(f"HTML transcript export failed, falling back to text: {e}", exc_info=e)
                exporter_success = False

        # If exporter failed or wasn't used, build simple text transcript
        if not exporter_success:
            # Update filename to .txt since we're not using HTML
            filename = f"{member.name}-{member.id}.txt".replace("/", "")

        answers = ticket.get("answers")
        if answers and not exporter_success:
            for q, a in answers.items():
                buffer.write(_("Question: {}\nResponse: {}\n").format(q, a))

        filenames = defaultdict(int)
        for msg in history:
            if msg.author.bot:
                continue
            if not msg:
                continue

            att: list[discord.Attachment] = []
            for i in msg.attachments:
                att.append(i)
                if i.size < guild.filesize_limit and (not is_thread or conf["thread_close"]):
                    filenames[i.filename] += 1
                    if filenames[i.filename] > 1:
                        # Increment filename count to avoid overwriting
                        p = Path(i.filename)
                        i.filename = f"{p.stem}_{filenames[i.filename]}{p.suffix}"

                    files.append({"filename": i.filename, "content": await i.read(), "url": i.url})

            if not exporter_success:
                if msg.content:
                    buffer.write(
                        f"{msg.created_at.strftime('%m-%d-%Y %I:%M:%S %p')} - {msg.author.name}: {msg.content}\n"
                    )
                if att:
                    buffer.write(_("Files Uploaded:\n"))
                    for i in att:
                        buffer.write(f"[{i.filename}]({i.url})\n")

        with suppress(discord.HTTPException):
            await temp_message.delete()

    else:
        history = await fetch_channel_history(channel, limit=1)

    # Process HTML transcript: embed images as base64, compress to WebP
    files_for_zip = files
    if exporter_success and buffer.getvalue():
        try:
            processed_html, files_for_zip, embedded = await process_transcript_html(
                html=buffer.getvalue(),
                downloaded_files=files,
                guild_filesize_limit=guild.filesize_limit,
            )
            # Replace buffer content with processed HTML
            buffer = StringIO()
            buffer.write(processed_html)
            if embedded:
                log.debug(f"Embedded {len(embedded)} files into transcript HTML")
        except Exception as e:
            log.error(f"Failed to process transcript HTML: {e}", exc_info=True)
            # Fall back to original HTML and all files in zip
            files_for_zip = files

    def zip_files():
        if files_for_zip:
            # Create a zip archive in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
                for file_dict in files_for_zip:
                    zip_file.writestr(
                        file_dict["filename"],
                        file_dict["content"],
                        compress_type=zipfile.ZIP_DEFLATED,
                        compresslevel=9,
                    )
            zip_buffer.seek(0)
            return zip_buffer.getvalue()

    zip_bytes = await asyncio.to_thread(zip_files)

    # Send off new messages
    view = None
    if history and is_thread and conf["thread_close"]:
        jump_url = history[0].jump_url
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Thread",
                style=discord.ButtonStyle.link,
                url=jump_url,
            )
        )

    text = buffer.getvalue()

    if log_chan and ticket["logmsg"]:
        text_file = text_to_file(text, filename) if text else None
        zip_file = discord.File(BytesIO(zip_bytes), filename="attachments.zip") if zip_bytes else None

        perms = [
            log_chan.permissions_for(guild.me).embed_links,
            log_chan.permissions_for(guild.me).attach_files,
        ]

        attachments = []
        text_file_size = 0
        if text_file:
            text_file_size = text_file.__sizeof__()
            attachments.append(text_file)
        if zip_file and ((zip_file.__sizeof__() + text_file_size) < guild.filesize_limit):
            attachments.append(zip_file)

        log_msg: discord.Message = None
        # attachment://image.webp
        try:
            if all(perms):
                log_msg = await log_chan.send(embed=embed, files=attachments or None, view=view)
            elif perms[0]:
                log_msg = await log_chan.send(embed=embed, view=view)
            elif perms[1]:
                log_msg = await log_chan.send(backup_text, files=attachments or None, view=view)
        except discord.HTTPException as e:
            if "Payload Too Large" in str(e) or "Request entity too large" in str(e):
                text_file = text_to_file(text, filename) if text else None
                zip_file = discord.File(BytesIO(zip_bytes), filename="attachments.zip") if zip_bytes else None
                attachments = []
                text_file_size = 0
                if text_file:
                    text_file_size = text_file.__sizeof__()
                    attachments.append(text_file)
                if zip_file and ((zip_file.__sizeof__() + text_file_size) < guild.filesize_limit):
                    attachments.append(zip_file)

                # Pop last element and try again
                if text_file:
                    attachments.pop(-1)
                else:
                    attachments = None
                if all(perms):
                    log_msg = await log_chan.send(embed=embed, files=attachments or None, view=view)
                elif perms[0]:
                    log_msg = await log_chan.send(embed=embed, view=view)
                elif perms[1]:
                    log_msg = await log_chan.send(backup_text, files=attachments or None, view=view)
            else:
                raise

        # Delete old log msg
        log_msg_id = ticket["logmsg"]
        try:
            log_msg = await log_chan.fetch_message(log_msg_id)
        except discord.HTTPException:
            log.warning("Failed to get log channel message")
            log_msg = None
        if log_msg:
            try:
                await log_msg.delete()
            except Exception as e:
                log.warning(f"Failed to auto-delete log message: {e}")

    if conf["dm"]:
        try:
            if text:
                text_file = text_to_file(text, filename) if text else None
                await member.send(embed=embed, file=text_file)
            else:
                await member.send(embed=embed)

        except discord.Forbidden:
            pass

    # Delete/close ticket channel
    if is_thread and conf["thread_close"]:
        try:
            await channel.edit(archived=True, locked=True)
        except Exception as e:
            log.error("Failed to archive thread ticket", exc_info=e)
    else:
        try:
            await channel.delete()
        except discord.DiscordServerError:
            await asyncio.sleep(3)
            try:
                await channel.delete()
            except Exception as e:
                log.error("Failed to delete ticket channel", exc_info=e)

    async with config.guild(guild).all() as conf:
        tickets = conf["opened"]
        if uid not in tickets:
            return
        if cid not in tickets[uid]:
            return
        del tickets[uid][cid]
        # If user has no more tickets, clean up their key from the config
        if not tickets[uid]:
            del tickets[uid]

        new_id = await update_active_overview(guild, conf)
        if new_id:
            conf["overview_msg"] = new_id


async def prune_invalid_tickets(
    guild: discord.Guild,
    conf: dict,
    config: Config,
    ctx: Optional[commands.Context] = None,
) -> bool:
    opened_tickets = conf["opened"]
    if not opened_tickets:
        if ctx:
            await ctx.send(_("There are no tickets stored in the database."))
        return False

    users_to_remove = []
    tickets_to_remove = []
    count = 0
    for user_id, tickets in opened_tickets.items():
        member = guild.get_member(int(user_id))
        if not member:
            count += len(list(tickets.keys()))
            users_to_remove.append(user_id)
            log.info(f"Cleaning up user {user_id}'s tickets for leaving")
            continue

        if not tickets:
            count += 1
            users_to_remove.append(user_id)
            log.info(f"Cleaning member {member} for having no tickets opened")
            continue

        for channel_id, ticket in tickets.items():
            if guild.get_channel_or_thread(int(channel_id)):
                continue

            count += 1
            log.info(f"Ticket channel {channel_id} no longer exists for {member}")
            tickets_to_remove.append((user_id, channel_id))

            panel = conf["panels"].get(ticket["panel"])
            if not panel:
                # Panel has been deleted
                continue
            log_message_id = ticket["logmsg"]
            log_channel_id = panel["log_channel"]
            if log_channel_id and log_message_id:
                log_channel = guild.get_channel(log_channel_id)
                try:
                    log_message = await log_channel.fetch_message(log_message_id)
                    await log_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

    if users_to_remove or tickets_to_remove:
        async with config.guild(guild).opened() as opened:
            for uid in users_to_remove:
                del opened[uid]
            for uid, cid in tickets_to_remove:
                if uid not in opened:
                    # User was already removed
                    continue
                if cid not in opened[uid]:
                    # Ticket was already removed
                    continue
                del opened[uid][cid]

    grammar = _("ticket") if count == 1 else _("tickets")
    if count and ctx:
        txt = _("Pruned `{}` invalid {}").format(count, grammar)
        await ctx.send(txt)
    elif not count and ctx:
        await ctx.send(_("There are no tickets to prune"))
    elif count and not ctx:
        log.info(f"{count} {grammar} pruned from {guild.name}")

    return True if count else False


def prep_overview_text(guild: discord.Guild, opened: dict, mention: bool = False) -> str:
    active = []
    for uid, opened_tickets in opened.items():
        member = guild.get_member(int(uid))
        if not member:
            continue
        for ticket_channel_id, ticket_info in opened_tickets.items():
            channel = guild.get_channel_or_thread(int(ticket_channel_id))
            if not channel:
                continue

            open_time_obj = datetime.fromisoformat(ticket_info["opened"])
            panel_name = ticket_info["panel"]

            entry = [
                channel.mention if mention else channel.name,
                panel_name,
                int(open_time_obj.timestamp()),
                member.name,
            ]
            active.append(entry)

    if not active:
        return _("There are no active tickets.")

    sorted_active = sorted(active, key=lambda x: x[2])

    desc = ""
    for index, i in enumerate(sorted_active):
        chan_mention, panel, ts, username = i
        desc += f"{index + 1}. {chan_mention}({panel}) <t:{ts}:R> - {username}\n"
    return desc


async def update_active_overview(guild: discord.Guild, conf: dict) -> Optional[int]:
    """Update active ticket overview

    Args:
        guild (discord.Guild): discord server
        conf (dict): settings for the guild

    Returns:
        int: Message ID of the overview panel
    """
    if not conf["overview_channel"]:
        return
    channel: discord.TextChannel = guild.get_channel(conf["overview_channel"])
    if not channel:
        return
    if not channel.permissions_for(guild.me).send_messages:
        return

    txt = prep_overview_text(guild, conf["opened"], conf.get("overview_mention", False))
    title = _("Ticket Overview")
    embeds = []
    attachments = []
    if len(txt) < 4000:
        embed = discord.Embed(
            title=title,
            description=txt,
            color=discord.Color.greyple(),
            timestamp=datetime.now(),
        )
        embeds.append(embed)
    elif len(txt) < 5500:
        for p in pagify(txt, page_length=3900):
            embed = discord.Embed(
                title=title,
                description=p,
                color=discord.Color.greyple(),
                timestamp=datetime.now(),
            )
            embeds.append(embed)
    else:
        embed = discord.Embed(
            title=title,
            description=_("Too many active tickets to include in message!"),
            color=discord.Color.red(),
            timestamp=datetime.now(),
        )
        embeds.append(embed)
        filename = _("Active Tickets") + ".txt"
        file = text_to_file(txt, filename=filename)
        attachments = [file]

    message = None
    if msg_id := conf["overview_msg"]:
        try:
            message = await channel.fetch_message(msg_id)
        except (discord.NotFound, discord.HTTPException):
            pass

    if message:
        try:
            await message.edit(content=None, embeds=embeds, attachments=attachments)
        except discord.Forbidden:
            message = await channel.send(embeds=embeds, files=attachments)
            return message.id
    else:
        try:
            message = await channel.send(embeds=embeds, files=attachments)
            return message.id
        except discord.Forbidden:
            message = await channel.send(_("Failed to send overview message due to missing permissions"))
