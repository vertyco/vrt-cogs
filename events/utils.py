import asyncio
import contextlib
import logging
from typing import Optional, Union

import discord
from aiocache import cached
from aiohttp import ClientSession
from redbot.core import VersionInfo, commands, version_info
from redbot.core.utils.chat_formatting import humanize_list

log = logging.getLogger("red.vrt.events")
DPY2 = True if version_info >= VersionInfo.from_str("3.5.0") else False


class GetReply:
    """
    Async context manager for getting message replies and auto deleting the user's response
    """

    def __init__(self, ctx: commands.Context, timeout: int = 120):
        self.ctx = ctx
        self.timeout = timeout
        self.reply = None

    def check(self, message: discord.Message):
        conditions = [
            message.author == self.ctx.author and message.channel == self.ctx.channel,
            message.author == self.ctx.author and not message.guild,
        ]
        return any(conditions)

    async def __aenter__(self) -> Optional[discord.Message]:
        tasks = [asyncio.ensure_future(self.ctx.bot.wait_for("message", check=self.check))]
        done, pending = await asyncio.wait(tasks, timeout=self.timeout)
        [task.cancel() for task in pending]
        self.reply = done.pop().result() if len(done) > 0 else None
        return self.reply

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.reply:
            if self.reply.guild:
                with contextlib.suppress(
                    discord.HTTPException, discord.NotFound, discord.Forbidden
                ):
                    await self.reply.delete(delay=30)
            else:
                await self.reply.add_reaction("✅")


def get_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if abs(num) < 1024.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1024.0
    return "{0:.1f}{1}".format(num, "YB")


def get_place(num: int):
    mapping = {"1": "st", "2": "nd", "3": "rd"}
    n = str(num)
    suf = "th"
    if n[-1] in mapping and not n.endswith("11") and not 11 < num < 14:
        suf = mapping[n[-1]]
    return f"{num}{suf}"


def guild_icon(guild: discord.Guild) -> Optional[str]:
    if DPY2:
        icon = guild.icon.url if guild.icon else None
    else:
        icon = guild.icon_url
    return icon


def profile_icon(user: discord.Member) -> Optional[str]:
    if DPY2:
        icon = user.display_avatar.url
    else:
        icon = user.avatar_url
    return icon


async def select_event(
    ctx: commands.Context, events: dict, skip_completed: bool = True
) -> Union[dict, None]:
    selectable = {}
    if len(events.keys()) > 1:
        grammar = "are"
        grammar2 = "events"
    else:
        grammar = "is"
        grammar2 = "event"
    embed = discord.Embed(
        title="Select an Event",
        description=f"There {grammar} currently {len(events.keys())} {grammar2} to choose from.",
        color=ctx.author.color,
    )
    e = [i for i in events.values() if not (skip_completed and i["completed"])]
    for index, info in enumerate(e):
        if skip_completed and info["completed"]:
            continue
        status = "**COMPLETED**" if info["completed"] else "In Progress"
        etype = "File submissions" if info["file_submission"] else "Text submissions"
        field = (
            f"`Status:     `{status}\n"
            f"`Started on: `<t:{info['start_date']}:f>\n"
            f"`Ends on:    `<t:{info['end_date']}:f>\n"
            f"`Event Type: `{etype}\n"
            f"`Winners:    `{info['winners']}\n"
            f"`Entries:    `{info['submissions_per_user']} per user\n"
        )

        days_in_server = info["days_in_server"]
        if days_in_server:
            grammar = "days" if days_in_server > 1 else "day"
            field += f"• Must be in the server for at least {days_in_server} {grammar}\n"

        roles = [
            ctx.guild.get_role(rid).mention
            for rid in info["roles_required"]
            if ctx.guild.get_role(rid)
        ]
        if info["need_all_roles"] and roles:
            field += f"• Need All roles: {humanize_list(roles)}\n"
        elif not info["need_all_roles"] and roles:
            field += f"• Need at least one role: {humanize_list(roles)}"

        embed.add_field(name=f"#{index + 1}. {info['event_name']}", value=field, inline=False)
        selectable[str(index + 1)] = info

    if not selectable:
        await ctx.send("There are no in-progress events to select")
        return None

    embed.set_footer(text="TYPE THE NUMBER OF THE EVENT BELOW")
    msg = await ctx.send(embed=embed)
    async with GetReply(ctx) as reply:
        if reply is None:
            await msg.delete()
            return None
        if reply.content.lower() == "cancel":
            await msg.edit(content="Event selection cancelled", embed=None)
            return None
        if not reply.content.isdigit():
            await msg.edit(content="That's not a number!", embed=None)
            return None
        if reply.content not in selectable:
            await msg.edit(content="That number doesn't correspond to an event!", embed=None)
            return None
        key = reply.content
    return {"event": selectable[key], "msg": msg}


def get_attachments(message: discord.Message) -> list:
    """Get all attachments from context"""
    content = []
    if message.attachments:
        attachments = [a for a in message.attachments]
        content.extend(attachments)
    if hasattr(message, "reference"):
        try:
            attachments = [a for a in message.reference.resolved.attachments]
            content.extend(attachments)
        except AttributeError:
            pass
    return content


@cached(ttl=3600)
async def get_content_from_url(url: str):
    try:
        async with ClientSession() as session:
            async with session.get(url) as resp:
                file = await resp.content.read()
                return file
    except Exception as e:
        log.error(f"Could not get file content from url: {e}", exc_info=True)
        return None
