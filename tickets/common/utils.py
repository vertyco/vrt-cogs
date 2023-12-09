import asyncio
import logging
import zipfile
from contextlib import suppress
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Union

import discord
from discord.utils import escape_markdown
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify, text_to_file
from redbot.core.utils.mod import is_admin_or_superior

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", __file__)


async def can_close(
    bot: Red,
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    author: discord.Member,
    owner_id: str,
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


async def fetch_channel_history(channel: discord.TextChannel, limit: int = None) -> List[discord.Message]:
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
    member: Union[discord.Member, discord.User],
    guild: discord.Guild,
    channel: Union[discord.TextChannel, discord.Thread],
    conf: dict,
    reason: str,
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
        return await channel.send(_("I am missing the `Manage Channels` permission to close this ticket!"))
    if not channel.permissions_for(guild.me).manage_threads and isinstance(channel, discord.Thread):
        return await channel.send(_("I am missing the `Manage Threads` permission to close this ticket!"))

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
        member.display_name,
        member.id,
        panel_name,
        opened,
        closed,
        closer_name,
        str(reason),
    )
    if isinstance(channel, discord.Thread) and conf["thread_close"]:
        desc += _("`Thread:    `{}").format(channel.mention)

    backup_text = _("Ticket Closed\n{}\nCurrently missing permissions to send embeds to this channel!").format(desc)
    embed = discord.Embed(
        title=_("Ticket Closed"),
        description=desc,
        color=discord.Color.green(),
    )
    embed.set_thumbnail(url=pfp)
    log_chan = guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None
    text = ""
    files: List[dict] = []
    filename = f"{member.name}-{member.id}.txt"
    filename = filename.replace("/", "")
    if conf["transcript"]:
        em = discord.Embed(
            description=_("Archiving channel..."),
            color=discord.Color.magenta(),
        )
        em.set_footer(text=_("This channel will be deleted once complete"))
        em.set_thumbnail(url=LOADING)
        temp_message = await channel.send(embed=em)
        answers = ticket.get("answers")
        if answers:
            for q, a in answers.items():
                text += _("Question: {}\nResponse: {}\n").format(q, a)
        history = await fetch_channel_history(channel)
        for msg in history:
            if msg.author.bot:
                continue
            if not msg:
                continue
            att = []
            for i in msg.attachments:
                att.append(i.filename)
                if i.size < guild.filesize_limit:
                    files.append(
                        {
                            "filename": i.filename,
                            "content": await i.read(),
                        }
                    )
            if msg.content:
                text += f"{msg.author.name}: {msg.content}\n"
            if att:
                text += _("Files uploaded: ") + humanize_list(att) + "\n"
        with suppress(discord.HTTPException):
            await temp_message.delete()
    else:
        history = await fetch_channel_history(channel, limit=1)

    def zip_files():
        if files:
            # Create a zip archive in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
                for file_dict in files:
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
    if history and isinstance(channel, discord.Thread) and conf["thread_close"]:
        jump_url = history[0].jump_url
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="View Thread",
                style=discord.ButtonStyle.link,
                url=jump_url,
            )
        )
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
        # attachment://image.webp
        try:
            if all(perms):
                await log_chan.send(embed=embed, files=attachments or None, view=view)
            elif perms[0]:
                await log_chan.send(embed=embed, view=view)
            elif perms[1]:
                await log_chan.send(backup_text, files=attachments or None, view=view)
        except discord.HTTPException as e:
            if "Payload Too Large" in e.text:
                # Pop last element and try again
                if text_file:
                    attachments.pop(-1)
                else:
                    attachments = None
                if all(perms):
                    await log_chan.send(embed=embed, files=attachments or None, view=view)
                elif perms[0]:
                    await log_chan.send(embed=embed, view=view)
                elif perms[1]:
                    await log_chan.send(backup_text, files=attachments or None, view=view)
            else:
                raise e

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
    if isinstance(channel, discord.Thread) and conf["thread_close"]:
        try:
            await channel.edit(archived=True, locked=True)
        except Exception as e:
            log.error("Failed to archive thread ticket", exc_info=e)
    else:
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
                member.display_name,
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
        message = await channel.send(embeds=embeds, files=attachments)
        return message.id
