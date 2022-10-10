import asyncio
import contextlib
from typing import Optional

import discord
from redbot.core import commands


class GetReply:
    """
    A simple async context manager I use for getting message responses while deleting the replies

    Default timeout is 120 seconds
    If timeout occurs, reply will be None
    """

    def __init__(self, ctx: commands.Context, timeout: int = 120):
        self.ctx = ctx
        self.timeout = timeout
        self.reply = None

    def check(self, message: discord.Message):
        return message.author == self.ctx.author and message.channel == self.ctx.channel

    async def __aenter__(self) -> Optional[discord.Message]:
        fs = [asyncio.ensure_future(self.ctx.bot.wait_for("message", check=self.check))]
        done, pending = await asyncio.wait(fs, timeout=self.timeout)
        [task.cancel() for task in pending]
        self.reply = done.pop().result() if len(done) > 0 else None
        return self.reply

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.reply:
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await self.reply.delete()


"""
# Example usage in Red
@commands.command(name="test")
async def test_command(self, ctx):
    msg = await ctx.send("Reply 'yes' to this message")
    async with GetReply(ctx) as reply:
        if reply is None:
            return await msg.edit(content="Took too long to reply")
        if reply.content != "yes":
            return await msg.edit(content="You did not reply with 'yes'")
        await msg.edit(content="Yay you replied with 'yes'")

# Example with custom timeout of 60 seconds
@commands.command(name="test")
async def test_command(self, ctx):
    msg = await ctx.send("Reply 'yes' to this message")
    async with GetReply(ctx, timeout=60) as reply:  # Timeout is now 60 seconds
        if reply is None:
            return await msg.edit(content="Took too long to reply")
        if reply.content != "yes":
            return await msg.edit(content="You did not reply with 'yes'")
        await msg.edit(content="Yay you replied with 'yes'")
"""
