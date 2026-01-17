from __future__ import annotations

import logging
import math
import typing as t
from pathlib import Path

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box

from ..abc import MixinMeta
from ..common.dynamic_menu import DynamicMenu
from ..common.utils import get_attachments

log = logging.getLogger("red.vrt.vrtutils.botemojis")


class EmojiManager(MixinMeta):
    @commands.group(name="botemojis", aliases=["botemoji", "bmoji"])
    @commands.is_owner()
    async def manage_emojis(self, ctx: commands.Context):
        """
        Add/Edit/List/Delete bot emojis
        """

    @manage_emojis.command(name="list")
    async def list_emojis(self, ctx: commands.Context):
        """List all existing bot emojis"""
        async with ctx.typing():
            emojis: list[discord.Emoji] = await self.bot.fetch_application_emojis()
            if not emojis:
                return await ctx.send("This bot has no emojis.")
            log.info(f"Fetched {len(emojis)} bot emojis for listing.")
            emojis.sort(key=lambda e: e.name.lower())
            pages = []
            start = 0
            stop = 10
            page_count = math.ceil(len(emojis) / 10)
            for p in range(page_count):
                stop = min(stop, len(emojis))
                embed = discord.Embed(title="Bot Emojis", color=await self.bot.get_embed_color(ctx))
                embed.set_footer(text=f"Page {p + 1}/{page_count}")
                for emoji in emojis[start:stop]:
                    value = (
                        f"• Emoji: {emoji}\n"
                        f"• ID: {emoji.id}\n"
                        f"• Roles: {', '.join(emoji.roles) if emoji.roles else 'None'}\n"
                        f"• Animated: {emoji.animated}\n"
                        f"• Managed: {emoji.managed}\n"
                        f"• Available: {emoji.available}\n"
                        f"• User: {emoji.user.name} ({emoji.user.id})"
                    )
                    embed.add_field(name=emoji.name, value=value, inline=False)
                pages.append(embed)
                start += 10
                stop += 10
            menu = DynamicMenu(ctx, pages)
            await menu.refresh()
            await menu.wait()
            await ctx.tick()

    @manage_emojis.command(name="add")
    async def add_emoji(self, ctx: commands.Context, name: str = None):
        """
        Create a new emoji from an image attachment

        If a name is not specified, the image's filename will be used
        """
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send("Please either include an existing emoji or attach an image to the command message!")
        if name and " " in name:
            return await ctx.send("Emoji name cannot contain spaces!")
        emoji_name = name or Path(attachments[0].filename).stem
        image = await attachments[0].read()
        try:
            await self.bot.create_application_emoji(name=emoji_name, image=image)
            await ctx.send(f"Emoji '{emoji_name}' added!")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to add emoji ({e.status}): {e.text}")

    @manage_emojis.command(name="fromemoji", aliases=["addfrom", "addemoji"])
    async def add_from_emoji(self, ctx: commands.Context, emoji: t.Union[discord.Emoji, discord.PartialEmoji]):
        """Create a new bot emoji from an existing one"""
        name = emoji.name
        image = await emoji.read()
        try:
            await self.bot.create_application_emoji(name=name, image=image)
            await ctx.send(f"Emoji '{name}' added!")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to add emoji ({e.status}): {e.text}")

    @manage_emojis.command(name="delete")
    async def delete_emoji(self, ctx: commands.Context, emoji_id: int):
        """Delete an bot emoji"""
        try:
            emoji = await self.bot.fetch_application_emoji(emoji_id)
        except discord.NotFound:
            return await ctx.send(f"No bot emoji found with ID {emoji_id}")
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to fetch emoji ({e.status}): {e}")
        if not emoji.is_application_owned():
            return await ctx.send(f"Emoji '{emoji.name}' is not a bot emoji!")
        try:
            await emoji.delete(reason=f"Deleted by bot owner {ctx.author} ({ctx.author.id})")
            await ctx.send(f"Emoji '{emoji.name}' deleted.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to delete emoji ({e.status}): {e}")

    @manage_emojis.command(name="edit")
    async def edit_emoji(self, ctx: commands.Context, emoji_id: int, name: str):
        """Edit a bot emoji's name"""
        try:
            emoji = await self.bot.fetch_application_emoji(emoji_id)
        except discord.NotFound:
            return await ctx.send(f"No bot emoji found with ID {emoji_id}")
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to fetch emoji ({e.status}): {e}")
        if not emoji.is_application_owned():
            return await ctx.send(f"Emoji ID {emoji_id} is not a bot emoji!")
        try:
            await emoji.edit(name=name, reason=f"Renamed by bot owner {ctx.author} ({ctx.author.id})")
            await ctx.send(f"Emoji ID {emoji_id} renamed to '{name}'.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to edit emoji ID {emoji_id} ({e.status}): {e}")

    @manage_emojis.command(name="get")
    async def get_emoji(self, ctx: commands.Context, emoji_id: int):
        """Get details about a bot emoji"""
        try:
            emoji: discord.Emoji = await self.bot.fetch_application_emoji(emoji_id)
        except discord.NotFound:
            return await ctx.send(f"No bot emoji found with ID {emoji_id}")
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to fetch emoji ({e.status}): {e}")
        txt = f"• Emoji: {emoji}\n"
        txt += f"• ID: {emoji.id}\n"
        txt += f"• Roles: {', '.join(emoji.roles) if emoji.roles else 'None'}\n"
        txt += f"• Animated: {emoji.animated}\n"
        txt += f"• Managed: {emoji.managed}\n"
        txt += f"• Available: {emoji.available}\n"
        txt += f"• User: {emoji.user.name} ({emoji.user.id})\n"
        await ctx.send(box(txt, lang="ini"))
