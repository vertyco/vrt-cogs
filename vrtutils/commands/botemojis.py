from __future__ import annotations

import json
import logging
import math
import typing as t
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path

import discord
from discord.http import Route
from redbot.core import commands
from redbot.core.utils.chat_formatting import box

from ..abc import MixinMeta
from ..common.dynamic_menu import DynamicMenu
from ..common.utils import get_attachments

log = logging.getLogger("red.vrt.vrtutils.botemojis")


@dataclass
class AvatarDeco:
    asset: str
    sku_id: str
    expires_at: t.Optional[t.Any]

    @staticmethod
    def from_dict(data: t.Dict[str, t.Any]) -> AvatarDeco:
        return AvatarDeco(**data)


@dataclass
class PayloadUser:
    id: str
    username: str
    avatar: str
    discriminator: str
    public_flags: int
    flags: t.Optional[int] = None
    bot: t.Optional[bool] = False
    banner: t.Optional[str] = None
    accent_color: t.Optional[str] = None
    global_name: t.Optional[str] = None
    avatar_decoration_data: t.Optional[AvatarDeco] = None
    banner_color: t.Optional[str] = None
    clan: t.Optional[t.Any] = None

    @staticmethod
    def from_dict(data: t.Dict[str, t.Any]) -> PayloadUser:
        if "avatar_decoration_data" in data and data["avatar_decoration_data"]:
            data["avatar_decoration_data"] = AvatarDeco.from_dict(data["avatar_decoration_data"])
        return PayloadUser(**data)


@dataclass
class EmojiPayload:
    id: str
    name: str
    roles: t.List[str]
    require_colons: bool
    managed: bool
    animated: bool
    available: bool
    user: t.Optional[PayloadUser] = None

    @staticmethod
    def from_dict(data: t.Dict[str, t.Any]) -> EmojiPayload:
        if "user" in data:
            data["user"] = PayloadUser.from_dict(data["user"])
        return EmojiPayload(**data)

    def string(self) -> str:
        """Format the emoji to render in Discord"""
        return f"<{'a' if self.animated else ''}:{self.name}:{self.id}>"


@dataclass
class ListEmojiPayload:
    items: t.List[EmojiPayload]

    @staticmethod
    def from_dict(data: t.Dict[str, t.Any]) -> ListEmojiPayload:
        items = [EmojiPayload.from_dict(item) for item in data.get("items", [])]
        return ListEmojiPayload(items)


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
        app_info = await self.bot.application_info()
        kwargs = {"application_id": str(app_info.id)}
        route: Route = Route(method="GET", path="/applications/{application_id}/emojis", **kwargs)
        data = await self.bot.http.request(route)
        if not data["items"]:
            return await ctx.send("No emojis found")
        emojis = ListEmojiPayload.from_dict(data)
        emojis.items.sort(key=lambda e: e.name)
        pages = []
        start = 0
        stop = 10
        page_count = math.ceil(len(emojis.items) / 10)
        for p in range(page_count):
            stop = min(stop, len(emojis.items))
            embed = discord.Embed(title="Bot Emojis", color=await self.bot.get_embed_color(ctx))
            embed.set_footer(text=f"Page {p + 1}/{page_count}")
            for emoji in emojis.items[start:stop]:
                value = (
                    f"• Emoji: {emoji.string()}\n"
                    f"• ID: {emoji.id}\n"
                    f"• Roles: {', '.join(emoji.roles) if emoji.roles else 'None'}\n"
                    f"• Animated: {emoji.animated}\n"
                    f"• Managed: {emoji.managed}\n"
                    f"• Available: {emoji.available}\n"
                    f"• User: {emoji.user.username} ({emoji.user.id})"
                )
                embed.add_field(name=emoji.name, value=value, inline=False)
            pages.append(embed)
            start += 10
            stop += 10
        menu = DynamicMenu(ctx, pages, ctx.channel)
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
        imageb64 = b64encode(image).decode("utf-8")
        extension = Path(attachments[0].filename).suffix
        await self._add(ctx, emoji_name, imageb64, extension)

    @manage_emojis.command(name="fromemoji", aliases=["addfrom", "addemoji"])
    async def add_from_emoji(self, ctx: commands.Context, emoji: t.Union[discord.Emoji, discord.PartialEmoji]):
        """Create a new bot emoji from an existing one"""
        name = emoji.name
        image = await emoji.read()
        imageb64 = b64encode(image).decode("utf-8")
        extension = ".gif" if emoji.animated else ".png"
        await self._add(ctx, name, imageb64, extension)

    async def _add(self, ctx: commands.Context, name: str, imageb64: str, extension: str):
        app_info = await self.bot.application_info()
        kwargs = {"application_id": str(app_info.id)}
        payload = {"name": name, "image": f"data:image/{extension};base64,{imageb64}"}
        route: Route = Route(method="POST", path="/applications/{application_id}/emojis", **kwargs)
        try:
            data = await self.bot.http.request(route, json=payload)
            dump = json.dumps(data, indent=4)
            await ctx.send(f"Emoji added\n{box(dump, lang='py')}")
            await ctx.tick()
        except discord.HTTPException as e:
            if e.status == 400:
                return await ctx.send(e.text)
            return await ctx.send(f"Failed to add emoji ({e.response.status}): {e.text}")

    @manage_emojis.command(name="delete")
    async def delete_emoji(self, ctx: commands.Context, emoji_id: int):
        """Delete an bot emoji"""
        app_info = await self.bot.application_info()
        kwargs = {"application_id": str(app_info.id), "emoji_id": str(emoji_id)}
        route: Route = Route(method="DELETE", path="/applications/{application_id}/emojis/{emoji_id}", **kwargs)
        try:
            await self.bot.http.request(route)
            await ctx.send("Emoji deleted.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to delete emoji ({e.response.status}): {e}")

    @manage_emojis.command(name="edit")
    async def edit_emoji(self, ctx: commands.Context, emoji_id: int, name: str):
        """Edit a bot emoji's name"""
        app_info = await self.bot.application_info()
        kwargs = {"application_id": str(app_info.id), "emoji_id": str(emoji_id)}
        payload = {"name": name}
        route: Route = Route(method="PATCH", path="/applications/{application_id}/emojis/{emoji_id}", **kwargs)
        try:
            data = await self.bot.http.request(route, json=payload)
            dump = json.dumps(data, indent=4)
            await ctx.send(f"Emoji renamed\n{box(dump, lang='py')}")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to edit emoji ID {emoji_id} ({e.response.status}): {e}")

    @manage_emojis.command(name="get")
    async def get_emoji(self, ctx: commands.Context, emoji_id: int):
        """Get details about a bot emoji"""
        app_info = await self.bot.application_info()
        kwargs = {"application_id": str(app_info.id), "emoji_id": str(emoji_id)}
        route: Route = Route(method="GET", path="/applications/{application_id}/emojis/{emoji_id}", **kwargs)
        data = await self.bot.http.request(route)
        dump = json.dumps(data, indent=4)
        emoji = EmojiPayload.from_dict(data)
        await ctx.send(f"{emoji.string()}\n{box(dump, lang='py')}")
