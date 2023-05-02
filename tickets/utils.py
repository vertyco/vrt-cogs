import logging
from datetime import datetime
from io import BytesIO
from typing import List, Optional, Union

import discord
from discord.utils import escape_markdown
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_list, pagify

from .abc import MixinMeta

LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.tickets.base")
_ = Translator("Tickets", __file__)


class Utils(MixinMeta):
    async def close_ticket(
        self,
        member: Union[discord.Member, discord.User],
        channel: discord.TextChannel,
        conf: dict,
        reason: str,
        closedby: str,
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
        opened = ticket["opened"]
        panel_name = ticket["panel"]
        panel = conf["panels"][panel_name]
        threads = panel.get("threads")

        if (
            not channel.permissions_for(member.guild.me).manage_channels
            and not threads
        ):
            return await channel.send(
                _(
                    "I am missing the `Manage Channels` permission to close this ticket!"
                )
            )
        if (
            not channel.permissions_for(member.guild.me).manage_threads
            and threads
        ):
            return await channel.send(
                _(
                    "I am missing the `Manage Threads` permission to close this ticket!"
                )
            )

        opened = int(datetime.fromisoformat(opened).timestamp())
        closed = int(datetime.now().timestamp())
        closer_name = escape_markdown(closedby)
        desc = (
            _("Ticket created by ")
            + f"**{member.name}-{member.id}**"
            + _(" has been closed.\n")
        )
        desc += _("`PanelType: `") + f"{panel_name}\n"
        desc += _("`Opened on: `") + f"<t:{opened}:F>\n"
        desc += _("`Closed on: `") + f"<t:{closed}:F>\n"
        desc += _("`Closed by: `") + f"{closer_name}\n"
        desc += _("`Reason:    `") + str(reason)
        embed = discord.Embed(
            title=_("Ticket Closed"),
            description=desc,
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=pfp)
        log_chan = (
            self.bot.get_channel(panel["log_channel"])
            if panel["log_channel"]
            else None
        )
        text = ""
        filename = f"{member.name}-{member.id}.txt"
        filename = filename.replace("/", "")
        if conf["transcript"]:
            em = discord.Embed(
                description=_("Archiving channel..."),
                color=discord.Color.magenta(),
            )
            em.set_footer(text=_("This channel will be deleted once complete"))
            em.set_thumbnail(url=LOADING)
            await channel.send(embed=em, delete_after=60)
            answers = ticket.get("answers")
            if answers:
                r = _("Response")
                for q, a in answers.items():
                    text += (
                        f"{self.bot.user.display_name}: {q}\n" f"{r}: {a}\n"
                    )
            history = await self.fetch_channel_history(channel)
            for msg in history:
                if msg.author.id == self.bot.user.id:
                    continue
                if not msg:
                    continue
                att = [a.filename for a in msg.attachments]
                if msg.content:
                    text += f"{msg.author.name}: {msg.content}\n"
                if att:
                    text += _("Files uploaded: ") + humanize_list(att) + "\n"
        else:
            history = await self.fetch_channel_history(channel, limit=1)

        # Send off new messages
        view = None
        if (
            history
            and isinstance(channel, discord.Thread)
            and conf["thread_close"]
        ):
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
            if text:
                file = discord.File(BytesIO(text.encode()), filename=filename)
                await log_chan.send(embed=embed, file=file, view=view)
            else:
                await log_chan.send(embed=embed, view=view)

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
                    file = discord.File(
                        BytesIO(text.encode()), filename=filename
                    )
                    await member.send(embed=embed, file=file)
                else:
                    await member.send(embed=embed)
            except discord.Forbidden:
                pass

        # Delete ticket channel
        try:
            if isinstance(channel, discord.Thread) and conf["thread_close"]:
                await channel.edit(archived=True, locked=True)
            else:
                await channel.delete()
        except Exception as e:
            log.warning(f"Failed to delete ticket channel: {e}")

        async with self.config.guild(member.guild).all() as conf:
            tickets = conf["opened"]
            if uid not in tickets:
                return
            if cid not in tickets[uid]:
                return
            del tickets[uid][cid]

            new_id = await update_active_overview(member.guild, conf)
            if new_id:
                conf["overview_msg"] = new_id

    @staticmethod
    async def fetch_channel_history(
        channel: discord.TextChannel, limit: int = None
    ) -> List[discord.Message]:
        history = []
        async for msg in channel.history(oldest_first=True, limit=limit):
            history.append(msg)
        return history

    @staticmethod
    async def ticket_owner_hastyped(
        channel: discord.TextChannel, user: discord.Member
    ) -> bool:
        async for msg in channel.history(limit=50, oldest_first=True):
            if msg.author.id == user.id:
                return True
        return False

    @staticmethod
    def get_ticket_owner(opened: dict, channel_id: str) -> Optional[str]:
        for uid, tickets in opened.items():
            if channel_id in tickets:
                return uid

    async def prune_invalid_tickets(
        self, guild: discord.Guild, ctx: Optional[commands.Context] = None
    ) -> None:
        opened_tickets = await self.config.guild(guild).opened()
        if not opened_tickets:
            if ctx:
                await ctx.send(
                    _("There are no tickets stored in the database.")
                )
            return

        valid_opened_tickets = {}
        count = 0
        for user_id, tickets in opened_tickets.items():
            if not guild.get_member(int(user_id)):
                count += len(list(tickets.keys()))
                continue

            valid_user_tickets = {}
            for channel_id, ticket in tickets.items():
                if not guild.get_channel_or_thread(int(channel_id)):
                    count += 1
                    continue
                else:
                    valid_user_tickets[channel_id] = ticket

            if valid_user_tickets:
                valid_opened_tickets[user_id] = valid_user_tickets

        if count:
            await self.config.guild(guild).opened.set(valid_opened_tickets)

        if count and ctx:
            txt = (
                _("Pruned `")
                + str(count)
                + _("` invalid ")
                + f"{_('ticket') if count == 1 else _('tickets')}."
            )
            await ctx.send(txt)
        elif not count and ctx:
            await ctx.send(_("There are no tickets to prune"))
        elif count and not ctx:
            log.info(f"{count} tickets pruned from {guild.name}")


def prep_overview_embeds(
    guild: discord.Guild, opened: dict
) -> List[discord.Embed]:
    title = _("Ticket Overview")
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
                channel.mention,
                panel_name,
                int(open_time_obj.timestamp()),
                member.display_name,
            ]
            active.append(entry)

    if not active:
        embed = discord.Embed(
            title=title,
            description=_("There are no active tickets."),
            color=discord.Color.greyple(),
            timestamp=datetime.now(),
        )
        return [embed]

    sorted_active = sorted(active, key=lambda x: x[2])

    desc = ""
    for index, i in enumerate(sorted_active):
        mention = i[0]
        panel = i[1]
        ts = i[2]
        username = i[3]
        desc += f"{index + 1}. {mention}({panel}) <t:{ts}:R> - {username}\n"

    embeds = []
    for p in pagify(desc, page_length=4000):
        embed = discord.Embed(
            title=title,
            description=p,
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )
        embeds.append(embed)
    return embeds


async def update_active_overview(
    guild: discord.Guild, conf: dict
) -> Optional[int]:
    """Update active ticket overview

    Args:
        guild (discord.Guild): discord server
        conf (dict): settings for the guild

    Returns:
        int: Message ID of the overview panel
    """
    if not conf["overview_channel"]:
        return
    channel = guild.get_channel(conf["overview_channel"])
    if not channel:
        return

    embeds = prep_overview_embeds(guild, conf["opened"])

    message = None
    if msg_id := conf["overview_msg"]:
        try:
            message = await channel.fetch_message(msg_id)
        except (discord.NotFound, discord.HTTPException):
            pass

    if message:
        await message.edit(embeds=embeds)
    else:
        message = await channel.send(embeds=embeds)
        return message.id
