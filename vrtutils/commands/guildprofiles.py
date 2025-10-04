from __future__ import annotations

from base64 import b64encode
from pathlib import Path

import discord
from discord.http import Route
from redbot.core import commands

from ..abc import MixinMeta
from ..common.utils import get_attachments

endpoint = "/guilds/{}/members/@me"


class GuildProfiles(MixinMeta):
    @commands.group(name="perserverbotprofile")
    @commands.is_owner()
    @commands.guild_only()
    async def per_server_bot_profile(self, ctx: commands.Context):
        """Manage bot's per server bio, banner, and avatar."""
        pass

    @per_server_bot_profile.command(name="avatar")
    async def per_server_bot_profile_avatar(self, ctx: commands.Context):
        """Set the bot's avatar for this server."""
        attachments = get_attachments(ctx.message)
        route: Route = Route(method="PATCH", path=endpoint.format(ctx.guild.id))
        if attachments and len(attachments) > 1:
            return await ctx.send("Please only provide one attachment.")
        if attachments:
            image_bytes = await attachments[0].read()
            imageb64 = b64encode(image_bytes).decode("utf-8")
            extension = Path(attachments[0].filename).suffix
            image = f"data:image/{extension};base64,{imageb64}"
            txt = "My avatar has been updated for this server!"
        else:
            default_avatar = self.bot.user.avatar
            if default_avatar is None:
                image = ""
                txt = "I do not have a global avatar to reset to, so my avatar for this server has been cleared!"
            else:
                image_bytes = await default_avatar.read()
                imageb64 = b64encode(image_bytes).decode("utf-8")
                image = f"data:image/png;base64,{imageb64}"
                txt = "My avatar for this server has been reset to my global avatar!"
        payload = {"avatar": image}
        try:
            await self.bot.http.request(route, json=payload)
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to update avatar ({e.status}): {e.text}")
        await ctx.send(txt)

    @per_server_bot_profile.command(name="banner")
    async def per_server_bot_profile_banner(self, ctx: commands.Context):
        """Set the bot's banner for this server."""
        attachments = get_attachments(ctx.message)
        route: Route = Route(method="PATCH", path=endpoint.format(ctx.guild.id))
        if attachments and len(attachments) > 1:
            return await ctx.send("Please only provide one attachment.")
        if attachments:
            image_bytes = await attachments[0].read()
            imageb64 = b64encode(image_bytes).decode("utf-8")
            extension = Path(attachments[0].filename).suffix
            image = f"data:image/{extension};base64,{imageb64}"
            txt = "My banner has been updated for this server!"
        else:
            default_banner = self.bot.user.banner
            if default_banner is None:
                image = ""
                txt = "I do not have a global banner to reset to, so my banner for this server has been cleared!"
            else:
                image_bytes = await default_banner.read()
                imageb64 = b64encode(image_bytes).decode("utf-8")
                image = f"data:image/png;base64,{imageb64}"
                txt = "My banner for this server has been reset to my global banner!"
        payload = {"banner": image}
        try:
            await self.bot.http.request(route, json=payload)
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to update banner ({e.status}): {e.text}")
        await ctx.send(txt)

    @per_server_bot_profile.command(name="bio")
    async def per_server_bot_profile_bio(self, ctx: commands.Context, *, bio: str = None):
        """Set the bot's bio for this server."""
        route: Route = Route(method="PATCH", path=endpoint.format(ctx.guild.id))
        if bio is None:
            bio = ""
            txt = "My bio for this server has been cleared!"
        else:
            if len(bio) > 190:
                return await ctx.send("Bio cannot be longer than 190 characters.")
            txt = "My bio has been updated for this server!"
        payload = {"bio": bio}
        try:
            await self.bot.http.request(route, json=payload)
        except discord.HTTPException as e:
            return await ctx.send(f"Failed to update bio ({e.status}): {e.text}")
        await ctx.send(txt)
