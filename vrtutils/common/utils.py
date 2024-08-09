import asyncio
import subprocess
import typing as t
from pathlib import Path
from sys import executable

import discord
from redbot.core import commands


async def wait_reply(ctx: commands.Context, timeout: int = 60):
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        try:
            await reply.delete()
        except (
            discord.Forbidden,
            discord.NotFound,
            discord.DiscordServerError,
        ):
            pass
        return res
    except asyncio.TimeoutError:
        return None


def get_attachments(message: discord.Message) -> t.List[discord.Attachment]:
    """Get all attachments from context"""
    attachments = []
    if message.attachments:
        direct_attachments = [a for a in message.attachments]
        attachments.extend(direct_attachments)
    if hasattr(message, "reference"):
        try:
            referenced_attachments = [a for a in message.reference.resolved.attachments]
            attachments.extend(referenced_attachments)
        except AttributeError:
            pass
    return attachments


async def do_shell_command(command: str):
    cmd = f"{executable} -m {command}"

    def exe():
        results = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        return results.stdout.decode("utf-8") or results.stderr.decode("utf-8")

    res = await asyncio.to_thread(exe)
    return res


def get_bar(progress, total, perc=None, width: int = 20) -> str:
    fill = "▰"
    space = "▱"
    if perc is not None:
        ratio = perc / 100
    else:
        ratio = progress / total
    bar = fill * round(ratio * width) + space * round(width - (ratio * width))
    return f"{bar} {round(100 * ratio, 1)}%"


def get_size(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if abs(num) < 1024.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1024.0
    return "{0:.1f}{1}".format(num, "YB")


def get_bitsize(num: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
        if abs(num) < 1000.0:
            return "{0:.1f}{1}".format(num, unit)
        num /= 1000.0
    return "{0:.1f}{1}".format(num, "YB")


def calculate_directory_size(path: Path) -> int:
    total_size = 0

    for file in path.rglob("*"):
        if file.is_file():
            total_size += file.stat().st_size

    return total_size
