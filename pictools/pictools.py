import asyncio
import contextlib
import json
import logging
import random
import sys
from datetime import datetime
from io import BytesIO
from time import monotonic
from typing import Union

import aiohttp
import discord
import matplotlib
import tabulate
from redbot.core.bot import Red
from redbot.core import commands
from pictools.generator import Generator

DPY2 = True if discord.__version__ > "1.7.3" else False


class PicTools(commands.Cog):
    """Image manipulation tools"""
    __author__ = "Vertyco#0117"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" \
               f"Cog Version: {self.__version__}\n" \
               f"Author: {self.__author__}\n" \
               f"Contributors: aikaterna#1393"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.gen = Generator()

    @staticmethod
    def get_content(ctx) -> list:
        """Get all attachments from context"""
        content = []
        if ctx.message.attachments:
            atchmts = [str(a.url) for a in ctx.message.attachments]
            content.extend(atchmts)
        if hasattr(ctx.message, "reference") and ctx.message.reference:
            try:
                atchmts = [str(a.url) for a in ctx.message.reference.resolved.attachments]
                content.extend(atchmts)
            except AttributeError:
                pass
        if not content:
            if DPY2:
                pfp = ctx.author.avatar.url if ctx.author.avatar else None
                if pfp:
                    content.append(str(pfp))
            else:
                pfp = ctx.author.avatar_url
                if pfp:
                    content.append(str(pfp))
        return content

    @commands.command()
    async def invert(self, ctx, *, url: str = None):
        """
        Invert an image

        **Arguments**
        `url` - Optional: A url to be processed
        *If no url is provided, the bot will check for attached images or referenced messages containing an attachment*
        """
        if url:
            content = [url.strip()]
        else:
            content = self.get_content(ctx)
        if not content:
            return await ctx.send("I could not find any media attached or referenced")
        url = content[0]
        async with ctx.typing():
            file = await self.bot.loop.run_in_executor(
                None,
                lambda: self.gen.invert_image(url)
            )
            if not file:
                return await ctx.send(f"Failed to get inverted image for `{url}`")
            await ctx.send(file=file)


