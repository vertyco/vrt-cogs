import asyncio
import logging
import re
import typing as t
import zipfile
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, time
from io import BytesIO, StringIO
from pathlib import Path

import chat_exporter
import discord
import pytz
from discord.utils import escape_markdown
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify, text_to_file
from redbot.core.utils.mod import is_admin_or_superior

from ..abc import MixinMeta
from .analytics import record_ticket_closed
from .models import GuildSettings, OpenedTicket, Panel
from .transcript import process_transcript_html

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", __file__)


DM_FILESIZE_LIMIT = 8 * 1024 * 1024


def _text_size_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _is_entity_too_large(exc: discord.HTTPException) -> bool:
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    if status == 413 or code == 40005:
        return True
    s = str(exc)
    return "Payload Too Large" in s or "Request entity too large" in s


_DATA_URI_IMG_RE = re.compile(r"<img\b[^>]*\bsrc=(['\"])data:[^'\"]+\1[^>]*>", re.IGNORECASE)
_DATA_URI_ATTR_RE = re.compile(r"\b(src|href)=(['\"])data:[^'\"]+\2", re.IGNORECASE)
_DATA_URI_CSS_RE = re.compile(r"url\((['\"]?)data:[^\)]+\1\)", re.IGNORECASE)


def _strip_data_uris_with_placeholders(html: str) -> tuple[str, bool]:
    """Remove embedded data URIs from HTML and add a banner notice.

    This reduces transcript size when chat-exporter output becomes too large.
    """

    if "data:" not in html:
        return html, False

    stripped = _DATA_URI_IMG_RE.sub("<span>[Attachment omitted]</span>", html)
    stripped = _DATA_URI_ATTR_RE.sub(r"\1=\2about:blank\2", stripped)
    stripped = _DATA_URI_CSS_RE.sub("url()", stripped)

    banner = (
        "<p><strong>Note:</strong> One or more attachments were omitted from this transcript "
        "to stay within Discord upload limits. Refer to the attached zip (if present) for files.</p>"
    )

    if "<body" in stripped.lower():
        stripped, n = re.subn(
            r"(<body[^>]*>)",
            r"\\1" + banner,
            stripped,
            count=1,
            flags=re.IGNORECASE,
        )
        if n == 0:
            stripped = banner + stripped
    else:
        stripped = banner + stripped

    return stripped, True


def _truncate_to_bytes(text: str, max_bytes: int, suffix: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text

    suffix_bytes = suffix.encode("utf-8")
    if max_bytes <= len(suffix_bytes):
        return suffix_bytes[:max_bytes].decode("utf-8", errors="ignore")

    cut = encoded[: max_bytes - len(suffix_bytes)]
    return cut.decode("utf-8", errors="ignore") + suffix


def _fit_transcript_for_upload(
    content: str,
    fallback_text: str,
    filename: str,
    max_bytes: int,
) -> tuple[str, str]:
    """Fit transcript content within an upload limit.

    Prefers keeping the existing format. For HTML, first strips embedded data URIs.
    If still too large, falls back to a truncated plain text transcript.
    """

    if not content:
        return "", filename

    effective_limit = int(max_bytes * 0.95)
    if _text_size_bytes(content) <= effective_limit:
        return content, filename

    is_html = filename.lower().endswith(".html")
    if is_html:
        stripped, _ = _strip_data_uris_with_placeholders(content)
        if _text_size_bytes(stripped) <= effective_limit:
            return stripped, filename

    txt_name = str(Path(filename).with_suffix(".txt").name)
    truncated = _truncate_to_bytes(
        fallback_text or "",
        effective_limit,
        "\n\n[Transcript truncated due to upload limits]\n",
    )
    return truncated, txt_name


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


def is_within_working_hours(panel: "Panel") -> tuple[bool, int | None, int | None]:
    """Check if the current time is within working hours for a panel.

    Args:
        panel: The panel configuration model

    Returns:
        Tuple of (is_within_hours, today_start_timestamp, today_end_timestamp)
        - is_within_hours: True if within working hours or no hours set, False otherwise
        - today_start_timestamp: Unix timestamp for today's start time or None
        - today_end_timestamp: Unix timestamp for today's end time or None
    """
    working_hours = panel.working_hours
    if not working_hours:
        return (True, None, None)

    timezone_str = panel.timezone
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

    start_str = day_hours.start
    end_str = day_hours.end
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


def format_working_hours_embed(panel: "Panel", user: discord.Member) -> discord.Embed | None:
    """Generate an embed for the outside working hours message.

    Args:
        panel: The panel configuration model
        user: The user who opened the ticket

    Returns:
        Discord embed if there's a custom message, None otherwise
    """
    custom_message = panel.outside_hours_message
    working_hours = panel.working_hours
    timezone_str = panel.timezone

    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    now = datetime.now(tz)
    day_name = DAY_NAMES[now.weekday()]
    day_hours = working_hours.get(day_name)
    start_str = day_hours.start if day_hours else ""
    end_str = day_hours.end if day_hours else ""

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
    channel: discord.TextChannel | discord.Thread,
    author: discord.Member,
    owner_id: int,
    conf: "GuildSettings",
):
    if owner_id not in conf.opened:
        return False
    if channel.id not in conf.opened[owner_id]:
        return False

    panel_name = conf.opened[owner_id][channel.id].panel
    panel_roles = conf.panels[panel_name].roles
    user_roles = [r.id for r in author.roles]

    support_roles = [i[0] for i in conf.support_roles]
    support_roles.extend([i[0] for i in panel_roles])

    can_close = False
    if any(i in support_roles for i in user_roles):
        can_close = True
    elif author.id == guild.owner_id:
        can_close = True
    elif await is_admin_or_superior(bot, author):
        can_close = True
    elif owner_id == author.id and conf.user_can_close:
        can_close = True
    return can_close


async def fetch_channel_history(channel: discord.TextChannel, limit: int | None = None) -> list[discord.Message]:
    history = []
    async for msg in channel.history(oldest_first=True, limit=limit):
        history.append(msg)
    return history


async def ticket_owner_hastyped(channel: discord.TextChannel, user: discord.Member) -> bool:
    async for msg in channel.history(limit=50, oldest_first=True):
        if msg.author.id == user.id:
            return True
    return False


def get_ticket_owner(opened: dict[int, dict[int, "OpenedTicket"]], channel_id: int) -> int | None:
    """Get the owner ID of a ticket channel.

    Args:
        opened: Dict mapping user IDs to their open tickets
        channel_id: The channel ID to look up

    Returns:
        The user ID of the ticket owner, or None if not found
    """
    for uid, tickets in opened.items():
        if channel_id in tickets:
            return uid
    return None


def get_average_response_time(response_times: list[float]) -> float | None:
    """Calculate the average response time from a list of response times.

    Args:
        response_times: List of response times in seconds

    Returns:
        Average response time in seconds, or None if no data
    """
    if not response_times:
        return None
    return sum(response_times) / len(response_times)


def format_response_time(seconds: float) -> str:
    """Format response time in a human-readable way.

    Args:
        seconds: Response time in seconds

    Returns:
        Human-readable string (e.g., "5 minutes", "2 hours", "1 day")
    """
    if seconds < 60:
        return _("less than a minute")

    minutes = seconds / 60
    if minutes < 60:
        mins = round(minutes)
        return _("{} minute").format(mins) if mins == 1 else _("{} minutes").format(mins)

    hours = minutes / 60
    if hours < 24:
        hrs = round(hours)
        return _("{} hour").format(hrs) if hrs == 1 else _("{} hours").format(hrs)

    days = hours / 24
    d = round(days)
    return _("{} day").format(d) if d == 1 else _("{} days").format(d)


async def record_response_time(
    cog: "MixinMeta",
    guild: discord.Guild,
    channel_id: int,
    ticket: "OpenedTicket",
    staff_id: int,
) -> None:
    """Record staff first response time for a ticket.

    Args:
        cog: The Tickets cog instance
        guild: Discord guild
        channel_id: Channel ID of ticket
        ticket: OpenedTicket model
        staff_id: User ID of staff member who responded
    """
    from .analytics import record_staff_first_response

    conf = cog.db.get_conf(guild)

    # Record full analytics (this also sets ticket.first_response)
    record_staff_first_response(conf, ticket, staff_id, channel_id)

    await cog.save()


async def close_ticket(
    bot: Red,
    member: discord.Member | discord.User,
    guild: discord.Guild,
    channel: discord.TextChannel | discord.Thread,
    conf: "GuildSettings",
    reason: str | None,
    closedby: int,
    cog: "MixinMeta",
) -> None:
    """Close a ticket.

    Args:
        bot: The Red bot instance
        member: The member who owns the ticket
        guild: The guild the ticket is in
        channel: The ticket channel
        conf: Guild settings model
        reason: Reason for closing
        closedby: User ID of who closed the ticket
        cog: The Tickets cog instance
    """
    opened = conf.opened
    if not opened:
        return
    uid = member.id
    cid = channel.id
    if uid not in opened:
        return
    if cid not in opened[uid]:
        return

    ticket = opened[uid][cid]
    pfp = ticket.pfp
    panel_name = ticket.panel
    panel = conf.panels[panel_name]

    if not channel.permissions_for(guild.me).manage_channels and isinstance(channel, discord.TextChannel):
        await channel.send(_("I am missing the `Manage Channels` permission to close this ticket!"))
        return
    if not channel.permissions_for(guild.me).manage_threads and isinstance(channel, discord.Thread):
        await channel.send(_("I am missing the `Manage Threads` permission to close this ticket!"))
        return

    # Get closer name
    closer = guild.get_member(closedby) or bot.get_user(closedby)
    closer_name = escape_markdown(closer.name if closer else str(closedby))

    opened_ts = int(ticket.opened.timestamp())
    closed_ts = int(datetime.now().timestamp())

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
        opened_ts,
        closed_ts,
        closer_name,
        str(reason),
    )
    if isinstance(channel, discord.Thread) and conf.thread_close:
        desc += _("`Thread:    `{}\n").format(channel.mention)

    backup_text = _("Ticket Closed\n{}\nCurrently missing permissions to send embeds to this channel!").format(desc)
    embed_title = _("Ticket Closed")
    embed = discord.Embed(
        title=embed_title,
        description=desc,
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=pfp)
    log_chan: discord.TextChannel = guild.get_channel(panel.log_channel) if panel.log_channel else None

    buffer = StringIO()
    fallback_buffer = StringIO()
    files: list[dict] = []
    filename = f"{member.name}-{member.id}.html" if conf.detailed_transcript else f"{member.name}-{member.id}.txt"
    filename = filename.replace("/", "")

    # Prep embed in case we're exporting a transcript
    em = discord.Embed(color=member.color)
    em.set_author(name=_("Archiving Ticket..."), icon_url=LOADING)

    use_exporter = conf.detailed_transcript
    is_thread = isinstance(channel, discord.Thread)
    exporter_success = False

    if conf.transcript:
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

        answers = ticket.answers
        if answers:
            for q, a in answers.items():
                fallback_buffer.write(_("Question: {}\nResponse: {}\n").format(q, a))
                if not exporter_success:
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
                if i.size < guild.filesize_limit and (not is_thread or conf.thread_close):
                    filenames[i.filename] += 1
                    if filenames[i.filename] > 1:
                        # Increment filename count to avoid overwriting
                        p = Path(i.filename)
                        i.filename = f"{p.stem}_{filenames[i.filename]}{p.suffix}"

                    files.append({"filename": i.filename, "content": await i.read(), "url": i.url})

            if msg.content:
                line = f"{msg.created_at.strftime('%m-%d-%Y %I:%M:%S %p')} - {msg.author.name}: {msg.content}\n"
                fallback_buffer.write(line)
                if not exporter_success:
                    buffer.write(line)
            if att:
                fallback_buffer.write(_("Files Uploaded:\n"))
                for i in att:
                    fallback_buffer.write(f"[{i.filename}]({i.url})\n")
                if not exporter_success:
                    buffer.write(_("Files Uploaded:\n"))
                    for i in att:
                        buffer.write(f"[{i.filename}]({i.url})\n")

        with suppress(discord.HTTPException):
            await temp_message.delete()

    else:
        history = await fetch_channel_history(channel, limit=1)

    fallback_text = fallback_buffer.getvalue()

    # Process HTML transcript: embed images as base64, compress to WebP
    files_for_zip = files
    if exporter_success and buffer.getvalue():
        try:
            # Use the guild's upload limit for transcript processing.
            # DM sends are handled separately later via _fit_transcript_for_upload.
            transcript_budget = guild.filesize_limit
            processed_html, files_for_zip, embedded = await process_transcript_html(
                html=buffer.getvalue(),
                downloaded_files=files,
                guild_filesize_limit=transcript_budget,
            )
            # Replace buffer content with processed HTML
            buffer = StringIO()
            # Only strip embedded data URIs if the transcript still exceeds the budget.
            effective_budget = int(transcript_budget * 0.95)
            if _text_size_bytes(processed_html) > effective_budget:
                processed_html, stripped = _strip_data_uris_with_placeholders(processed_html)
                if stripped:
                    # If we removed embedded attachments, include all downloaded files in the zip.
                    files_for_zip = files
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
    if history and is_thread and conf.thread_close:
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
    zip_size = len(zip_bytes) if zip_bytes else 0

    if log_chan and ticket.logmsg:
        upload_limit = guild.filesize_limit
        fitted_text, fitted_name = _fit_transcript_for_upload(text, fallback_text, filename, upload_limit)
        fitted_text_size = _text_size_bytes(fitted_text) if fitted_text else 0

        text_file = text_to_file(fitted_text, fitted_name) if fitted_text else None
        zip_file = discord.File(BytesIO(zip_bytes), filename="attachments.zip") if zip_bytes else None

        perms = [
            log_chan.permissions_for(guild.me).embed_links,
            log_chan.permissions_for(guild.me).attach_files,
        ]

        attachments = []
        used = 0
        if text_file:
            used += fitted_text_size
            attachments.append(text_file)
        if zip_file and zip_size and (used + zip_size) <= upload_limit:
            attachments.append(zip_file)

        log_msg: discord.Message = None
        try:
            if all(perms):
                log_msg = await log_chan.send(embed=embed, files=attachments or None, view=view)
            elif perms[0]:
                log_msg = await log_chan.send(embed=embed, view=view)
            elif perms[1]:
                log_msg = await log_chan.send(backup_text, files=attachments or None, view=view)
        except discord.HTTPException as e:
            # If this still fails, don't crash ticket closing.
            log.error(f"Failed to send log message: {e}")
            log_msg = None

        # Delete old log msg
        log_msg_id = ticket.logmsg
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

    if conf.dm:
        try:
            dm_upload_limit = DM_FILESIZE_LIMIT
            dm_embed = embed.copy()
            dm_text, dm_name = _fit_transcript_for_upload(text, fallback_text, filename, dm_upload_limit)
            if dm_text:
                dm_file = text_to_file(dm_text, dm_name)
                await member.send(embed=dm_embed, file=dm_file)
            else:
                await member.send(embed=dm_embed)

        except (discord.Forbidden, discord.HTTPException):
            pass

    # Mark channel as being closed to prevent race condition with delete listeners
    cog.closing_channels.add(cid)

    # Delete/close ticket channel
    try:
        if is_thread and conf.thread_close:
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
    finally:
        # Always remove from closing set
        cog.closing_channels.discard(cid)

    # Record analytics BEFORE removing the ticket from conf.opened
    record_ticket_closed(conf, ticket, cid, uid, closedby)

    # Update the config
    if uid in conf.opened:
        if cid in conf.opened[uid]:
            del conf.opened[uid][cid]
        # If user has no more tickets, clean up their key
        if not conf.opened[uid]:
            del conf.opened[uid]

    new_id = await update_active_overview(guild, conf)
    if new_id:
        conf.overview_msg = new_id

    await cog.save()


async def prune_invalid_tickets(
    guild: discord.Guild,
    conf: "GuildSettings",
    ctx: commands.Context | None = None,
) -> bool:
    """Prune tickets for channels that no longer exist.

    This function records closing analytics for pruned tickets to maintain
    accurate statistics when tickets are cleaned up due to:
    - Member leaving while bot was down
    - Channel being deleted externally

    Args:
        guild: The Discord guild
        conf: Guild settings model
        ctx: Optional command context for sending messages

    Returns:
        True if any tickets were pruned, False otherwise
    """
    opened_tickets = conf.opened
    if not opened_tickets:
        if ctx:
            await ctx.send(_("There are no tickets stored in the database."))
        return False

    users_to_remove: list[int] = []
    tickets_to_remove: list[tuple[int, int, OpenedTicket]] = []  # (user_id, channel_id, ticket)
    count = 0

    for user_id, tickets in list(opened_tickets.items()):
        member = guild.get_member(user_id)
        if not member:
            # Member has left the server - record analytics for all their tickets
            for channel_id, ticket in tickets.items():
                count += 1
                tickets_to_remove.append((user_id, channel_id, ticket))
                log.info(f"Cleaning up ticket {channel_id} for user {user_id} who left")
            users_to_remove.append(user_id)
            continue

        if not tickets:
            count += 1
            users_to_remove.append(user_id)
            log.info(f"Cleaning member {member} for having no tickets opened")
            continue

        for channel_id, ticket in list(tickets.items()):
            if guild.get_channel_or_thread(channel_id):
                continue

            count += 1
            log.info(f"Ticket channel {channel_id} no longer exists for {member}")
            tickets_to_remove.append((user_id, channel_id, ticket))

            panel = conf.panels.get(ticket.panel)
            if not panel:
                # Panel has been deleted
                continue
            log_message_id = ticket.logmsg
            log_channel_id = panel.log_channel
            if log_channel_id and log_message_id:
                log_channel = guild.get_channel(log_channel_id)
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    try:
                        log_message = await log_channel.fetch_message(log_message_id)
                        await log_message.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass

    # Record analytics for pruned tickets before removing them
    if tickets_to_remove:
        bot_id = guild.me.id if guild.me else 0
        for uid, cid, ticket in tickets_to_remove:
            # Record closing analytics (bot is the "closer" for pruned tickets)
            record_ticket_closed(conf, ticket, cid, uid, bot_id)

    # Now remove the tickets from opened
    if users_to_remove or tickets_to_remove:
        for uid in users_to_remove:
            if uid in conf.opened:
                del conf.opened[uid]
        for uid, cid, __ in tickets_to_remove:
            if uid not in conf.opened:
                # User was already removed
                continue
            if cid not in conf.opened[uid]:
                # Ticket was already removed
                continue
            del conf.opened[uid][cid]

    grammar = _("ticket") if count == 1 else _("tickets")
    if count and ctx:
        txt = _("Pruned `{}` invalid {}").format(count, grammar)
        await ctx.send(txt)
    elif not count and ctx:
        await ctx.send(_("There are no tickets to prune"))
    elif count and not ctx:
        log.info(f"{count} {grammar} pruned from {guild.name}")

    return True if count else False


def prep_overview_text(
    guild: discord.Guild, opened: dict[int, dict[int, "OpenedTicket"]], mention: bool = False
) -> str:
    """Prepare the text for the ticket overview panel."""
    active: list[list[t.Any]] = []
    for uid, opened_tickets in opened.items():
        member = guild.get_member(uid)
        if not member:
            continue
        for ticket_channel_id, ticket_info in opened_tickets.items():
            channel = guild.get_channel_or_thread(ticket_channel_id)
            if not channel:
                continue

            open_time_obj = ticket_info.opened
            panel_name = ticket_info.panel

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


async def update_active_overview(guild: discord.Guild, conf: "GuildSettings") -> int | None:
    """Update active ticket overview

    Args:
        guild: discord server
        conf: settings for the guild

    Returns:
        Message ID of the overview panel if created/updated
    """
    if not conf.overview_channel:
        return
    channel: discord.TextChannel = guild.get_channel(conf.overview_channel)
    if not channel:
        return
    if not channel.permissions_for(guild.me).send_messages:
        return

    txt = prep_overview_text(guild, conf.opened, conf.overview_mention)
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
    if msg_id := conf.overview_msg:
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
