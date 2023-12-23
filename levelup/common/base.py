import asyncio
import datetime
import logging
import math
import random
import traceback
from abc import ABC
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Optional, Union

import discord
import validators
from aiocache import cached
from redbot.core import VersionInfo, bank, commands, version_info
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_list, humanize_number

from levelup.utils.formatter import (
    get_attachments,
    get_bar,
    get_content_from_url,
    get_leaderboard,
    get_level,
    get_twemoji,
    get_user_position,
    get_xp,
    hex_to_rgb,
    time_formatter,
)

from ..abc import MixinMeta
from .constants import default_guild

if version_info >= VersionInfo.from_str("3.5.0"):
    from .dpymenu import DEFAULT_CONTROLS, menu

    DPY2 = True
else:
    from .menus import DEFAULT_CONTROLS, menu

    DPY2 = False

log = logging.getLogger("red.vrt.levelup.commands")
_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class UserCommands(MixinMeta, ABC):
    # Generate level up image
    async def gen_levelup_img(self, params: dict):
        task = asyncio.to_thread(self.generate_levelup, **params)
        try:
            img = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None
        return img

    # Generate profile image
    async def gen_profile_img(self, params: dict, full: bool = True):
        method = self.generate_profile if full else self.generate_slim_profile
        task = asyncio.to_thread(method, **params)
        try:
            img = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None
        return img

    # Function to test a given URL and see if it's valid
    async def valid_url(self, ctx: commands.Context, image_url: str):
        valid = validators.url(image_url)
        if not valid:
            await ctx.send(_("Uh Oh, looks like that is not a valid URL"))
            return
        try:
            # Try running it through profile generator blind to see if it errors

            params = {"bg_image": image_url}
            await asyncio.to_thread(self.generate_profile, **params)
        except Exception as e:
            if "cannot identify image file" in str(e):
                await ctx.send(_("Uh Oh, looks like that is not a valid image, cannot identify the file"))
                return
            else:
                log.warning(f"background set failed: {traceback.format_exc()}")
                await ctx.send(_("Uh Oh, looks like that is not a valid image"))
                return
        return True

    async def get_or_fetch_fonts(self):
        maindir = bundled_data_path(self)
        savedir = cog_data_path(self)
        fonts = maindir / "fonts"
        saved_fonts = savedir / "fonts"
        available = list(fonts.iterdir()) + list(saved_fonts.iterdir())
        match = all(i.name in self.fdata["names"] for i in available)
        if match and self.fdata["img"]:
            return self.fdata["img"]

        try:
            task = asyncio.to_thread(self.get_all_fonts)
            img = await asyncio.wait_for(task, timeout=60)
            self.fdata["img"] = img
            self.fdata["names"] = [i.name for i in available]
            return img
        except asyncio.TimeoutError:
            log.warning("get_or_fetch_fonts took too long to generate!")

    async def get_or_fetch_backgrounds(self):
        maindir = bundled_data_path(self)
        savedir = cog_data_path(self)
        backgrounds = maindir / "backgrounds"
        saved_backgrounds = savedir / "backgrounds"
        available = list(backgrounds.iterdir()) + list(saved_backgrounds.iterdir())
        match = all(i.name in self.bgdata["names"] for i in available)
        if match and self.bgdata["img"]:
            return self.bgdata["img"]

        try:
            task = asyncio.to_thread(self.get_all_backgrounds)
            img = await asyncio.wait_for(task, timeout=60)
            self.bgdata["img"] = img
            self.bgdata["names"] = [i.name for i in available]
            return img
        except asyncio.TimeoutError:
            log.warning("get_or_fetch_backgrounds took too long to generate!")

    async def get_or_fetch_profile(self, user: discord.Member, args: dict, full: bool) -> Union[discord.File, None]:
        gid = user.guild.id
        uid = str(user.id)
        now = datetime.datetime.now()
        if gid not in self.profiles:
            self.profiles[gid] = {}
        if uid not in self.profiles[gid]:
            self.profiles[gid][uid] = {"img": None, "ts": now}

        cache = self.profiles[gid][uid]
        td = (now - cache["ts"]).total_seconds()
        if td > self.cache_seconds or not cache["img"]:
            img = await self.gen_profile_img(args, full)
            self.profiles[gid][uid] = {"img": img, "ts": now}
        else:
            img = self.profiles[gid][uid]["img"]

        if not img:
            return None
        animated = getattr(img, "is_animated", False)
        ext = "GIF" if animated else "WEBP"
        buffer = BytesIO()
        buffer.name = f"{user.id}.{ext.lower()}"
        try:
            img.save(buffer, save_all=True, format=ext)
        except KeyError:
            img.save(buffer, save_all=True, format="PNG")
        buffer.seek(0)
        return discord.File(buffer, filename=buffer.name)

    # Hacky way to get user banner
    @cached(ttl=7200)
    async def get_banner(self, user: discord.Member) -> str:
        req = await self.bot.http.request(discord.http.Route("GET", "/users/{uid}", uid=user.id))
        banner_id = req["banner"]
        if banner_id:
            banner_url = f"https://cdn.discordapp.com/banners/{user.id}/{banner_id}?size=1024"
            return banner_url

    @commands.command(name="stars", aliases=["givestar", "addstar", "thanks"])
    @commands.guild_only()
    async def give_star(self, ctx: commands.Context, *, user: discord.Member = None):
        """
        Reward a good noodle
        Give a star to a user for being a good noodle
        """
        now = datetime.datetime.now()

        star_giver = str(ctx.author.id)
        guild_id = ctx.guild.id

        if guild_id not in self.data:
            return await ctx.send(_("Cache not loaded yet, wait a few more seconds."))

        if guild_id not in self.stars:
            self.stars[guild_id] = {}

        if not user:
            if star_giver in self.stars[guild_id]:
                # If no user is given and they have a cooldown, show time left
                cooldown = self.data[guild_id]["starcooldown"]
                lastused = self.stars[guild_id][star_giver]
                td = now - lastused
                td = td.total_seconds()
                if td < cooldown:
                    time_left = cooldown - td
                    tstring = time_formatter(time_left)
                    msg = _("You can give more stars in {}").format(f"**{tstring}**")
                    return await ctx.send(msg)
                else:
                    msg = _("You can give more stars now! Just mention a user in this command.")
                    return await ctx.send(msg)
            else:
                # If no user is given and they have no cooldown, show help
                return await ctx.send_help()

        if ctx.author == user:
            return await ctx.send(_("You can't give stars to yourself!"))
        if user.bot:
            return await ctx.send(_("You can't give stars to a bot!"))

        if star_giver not in self.stars[guild_id]:
            self.stars[guild_id][star_giver] = now
        else:
            cooldown = self.data[guild_id]["starcooldown"]
            lastused = self.stars[guild_id][star_giver]
            td = now - lastused
            td = td.total_seconds()
            if td > cooldown:
                self.stars[guild_id][star_giver] = now
            else:
                time_left = cooldown - td
                tstring = time_formatter(time_left)
                msg = _("You need to wait ") + f"**{tstring}**" + _(" before you can give more stars!")
                return await ctx.send(msg)

        mention = self.data[guild_id]["mention"]
        users = self.data[guild_id]["users"]
        user_id = str(user.id)
        if user_id not in users:
            return await ctx.send(_("No data available for that user yet!"))
        self.data[guild_id]["users"][user_id]["stars"] += 1
        if self.data[guild_id]["weekly"]["on"]:
            if guild_id not in self.data[guild_id]["weekly"]["users"]:
                self.init_user_weekly(guild_id, user_id)
            self.data[guild_id]["weekly"]["users"][user_id]["stars"] += 1

        name = user.mention if mention else f"**{user.name}**"
        await ctx.send(_("You just gave a star to {}!").format(name))

    # For testing purposes
    @commands.command(name="mocklvl", hidden=True)
    async def get_lvl_test(self, ctx, *, user: discord.Member = None):
        """Test levelup image gen"""
        if not user:
            user = ctx.author
        banner = await self.get_banner(user)
        color = str(user.colour)
        color = hex_to_rgb(color)
        font = None
        uid = str(user.id)
        conf = self.data[ctx.guild.id]["users"]
        if uid in conf:
            font = conf[uid]["font"]
        if DPY2:
            pfp = user.display_avatar.url
        else:
            pfp = user.avatar_url
        args = {
            "bg_image": banner,
            "profile_image": pfp,
            "level": random.randint(1, 999),
            "color": color,
            "font_name": font,
        }
        img = await self.gen_levelup_img(args)
        temp = BytesIO()
        temp.name = f"{ctx.author.id}.webp"
        try:
            img.save(temp, format="WEBP")
        except KeyError:
            img.save(temp, format="PNG")
        temp.seek(0)
        file = discord.File(temp)
        await ctx.send(file=file)

    @commands.group(name="myprofile", aliases=["mypf", "pfset"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def set_profile(self, ctx: commands.Context):
        """
        Customize your profile colors

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**
        """
        uid = str(ctx.author.id)
        gid = ctx.guild.id
        if ctx.invoked_subcommand is None and uid in self.data[gid]["users"]:
            uid = str(ctx.author.id)
            gid = ctx.guild.id
            users = self.data[gid]["users"]
            user = users[uid]
            bg = user["background"]
            full = "full" if user["full"] else "slim"

            colors = user["colors"]
            name = colors["name"] if colors["name"] else _("Not Set")
            stat = colors["stat"] if colors["stat"] else _("Not Set")
            levelbar = colors["levelbar"] if colors["levelbar"] else _("Not Set")
            font = user["font"] if user["font"] else _("Not Set")
            blur = user["blur"]

            desc = _("`Profile Size:    `") + full + "\n"
            desc += _("`Name Color:      `") + name + "\n"
            desc += _("`Stat Color:      `") + stat + "\n"
            desc += _("`Level Bar Color: `") + levelbar + "\n"
            desc += _("`Font:            `") + font + "\n"
            desc += _("`Background:      `") + str(bg) + "\n"
            desc += _("`Blur:            `") + str(blur)

            em = discord.Embed(
                title=_("Your Profile Settings"),
                description=desc,
                color=ctx.author.color,
            )

            maindir = bundled_data_path(self)
            savedir = cog_data_path(self)
            backgrounds = maindir / "backgrounds"
            saved_backgrounds = savedir / "backgrounds"
            available = list(backgrounds.iterdir()) + list(saved_backgrounds.iterdir())

            file = None
            if bg:
                if bg.lower().startswith("http"):
                    em.set_image(url=bg)
                elif bg != "random":
                    for bgfile in available:
                        if bg.lower() in bgfile.name:
                            try:
                                file = discord.File(bgfile, filename=bgfile.name)
                                em.set_image(url=f"attachment://{bg}")
                                break
                            except (WindowsError, PermissionError, OSError):
                                pass

            await ctx.send(embed=em, file=file)

    @set_profile.command(name="defaultbgpath")
    @commands.is_owner()
    async def get_bg_path(self, ctx: commands.Context):
        """Get folder path for this cog's default backgrounds"""
        bgpath = bundled_data_path(self) / "backgrounds"
        txt = _("Your default background folder path is \n")
        await ctx.send(f"{txt}`{bgpath}`")

    @set_profile.command(name="savedbgpath")
    @commands.is_owner()
    async def get_saved_bg_path(self, ctx: commands.Context):
        """Get folder path for this cog's saved backgrounds"""
        bgpath = cog_data_path(self) / "backgrounds"
        txt = _("Your saved background folder path is \n")
        await ctx.send(f"{txt}`{bgpath}`")

    @set_profile.command(name="addbackground")
    @commands.is_owner()
    async def add_background(self, ctx: commands.Context, preferred_filename: str = None):
        """
        Add a custom background to the cog from discord

        **Arguments**
        `preferred_filename` - If a name is given, it will be saved as this name instead of the filename

        **DISCLAIMER**
        - Do not replace any existing file names with custom images
        - If you add broken or corrupt images it can break the cog
        - Do not include the file extension in the preferred name, it will be added automatically
        """
        content = get_attachments(ctx)
        if not content:
            return await ctx.send(_("I was not able to find any attachments"))
        valid = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        url = content[0].url
        filename = content[0].filename
        if not any(filename.lower().endswith(i) for i in valid):
            return await ctx.send(
                _("That is not a valid format, must be on of the following extensions: ") + humanize_list(valid)
            )
        ext = ".png"
        for ext in valid:
            if ext in filename.lower():
                break
        bytes_file = await get_content_from_url(url)
        if not bytes_file:
            return await ctx.send(_("I was not able to get the file from Discord"))
        if preferred_filename:
            if Path(filename).suffix.lower() == Path(preferred_filename).suffix.lower():
                filename = preferred_filename
            else:
                filename = f"{preferred_filename}{ext}"
        filepath = cog_data_path(self) / "backgrounds" / filename
        filepath.write_bytes(bytes_file)
        await ctx.send(_("Your custom background has been saved as ") + f"`{filename}`")

    @set_profile.command(name="rembackground")
    @commands.is_owner()
    async def remove_background(self, ctx: commands.Context, *, filename: str):
        """Remove a default background from the cog's backgrounds folder"""
        savedir = cog_data_path(self) / "backgrounds"
        for file in savedir.iterdir():
            if filename.lower() in file.name.lower():
                break
        else:
            return await ctx.send(_("I could not find any background images with that name"))

        try:
            file.unlink(missing_ok=True)
        except Exception as e:
            return await ctx.send(_("Could not delete file: ") + str(e))
        await ctx.send(_("Background named {} has been removed!").format(f"`{file.name}`"))

    @set_profile.command(name="defaultfontpath")
    @commands.is_owner()
    async def get_font_path(self, ctx: commands.Context):
        """Get folder path for this cog's default fonts"""
        fpath = bundled_data_path(self) / "fonts"
        txt = _("Your default font folder path is \n")
        await ctx.send(f"{txt}`{fpath}`")

    @set_profile.command(name="savedfontpath")
    @commands.is_owner()
    async def get_saved_font_path(self, ctx: commands.Context):
        """Get folder path for this cog's saved fonts"""
        fpath = bundled_data_path(self) / "fonts"
        txt = _("Your custom font folder path is \n")
        await ctx.send(f"{txt}`{fpath}`")

    @set_profile.command(name="addfont")
    @commands.is_owner()
    async def add_font(self, ctx: commands.Context, preferred_filename: str = None):
        """
        Add a custom font to the cog from discord

        **Arguments**
        `preferred_filename` - If a name is given, it will be saved as this name instead of the filename
        **Note:** do not include the file extension in the preferred name, it will be added automatically
        """
        content = get_attachments(ctx)
        if not content:
            return await ctx.send(_("I was not able to find any attachments"))
        valid = [".ttf", ".otf"]
        url = content[0].url
        filename = content[0].filename
        if not any([i in filename.lower() for i in valid]):
            return await ctx.send(_("That is not a valid format, must be `.ttf` or `.otf` extensions"))
        ext = ".ttf"
        for ext in valid:
            if ext in filename.lower():
                break
        bytes_file = await get_content_from_url(url)
        if not bytes_file:
            return await ctx.send(_("I was not able to get the file from Discord"))
        if preferred_filename:
            if Path(filename).suffix.lower() == Path(preferred_filename).suffix.lower():
                filename = preferred_filename
            else:
                filename = f"{preferred_filename}{ext}"

        filepath = cog_data_path(self) / "fonts" / filename
        filepath.write_bytes(bytes_file)
        await ctx.send(_("Your custom font file has been saved as ") + f"`{filename}`")

    @set_profile.command(name="remfont")
    @commands.is_owner()
    async def remove_font(self, ctx: commands.Context, *, filename: str):
        """Remove a font from the cog's font folder"""
        savedir = cog_data_path(self) / "fonts"
        for file in savedir.iterdir():
            if filename.lower() in file.name.lower():
                break
        else:
            return await ctx.send(_("I could not find any fonts with that name"))

        try:
            file.unlink(missing_ok=True)
        except Exception as e:
            return await ctx.send(_("Could not delete file: ") + str(e))
        await ctx.send(_("Font named {} has been removed!").format(f"`{file.name}`"))

    @set_profile.command(name="backgrounds")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True)
    async def view_all_backgrounds(self, ctx: commands.Context):
        """View the all available backgrounds"""
        if not self.data[ctx.guild.id]["usepics"]:
            txt = _("Image profiles are disabled on this server so this command is off")
            if ctx.author.guild_permissions.manage_messages:
                txt += _("\nUse the `{}` command to toggle image profiles and enable this command.").format(
                    f"{ctx.clean_prefix}lset embeds"
                )
            return await ctx.send(txt)

        async with ctx.typing():
            img = await self.get_or_fetch_backgrounds()
            if img is None:
                await ctx.send(_("Failed to generate background samples"))
            buffer = BytesIO()
            try:
                img.save(buffer, format="WEBP")
                buffer.name = f"{ctx.author.id}.webp"
            except (ValueError, KeyError):
                img.save(buffer, format="PNG", quality=50)
                buffer.name = f"{ctx.author.id}.png"
            buffer.seek(0)
            file = discord.File(buffer)
            txt = _("Here are the current default backgrounds, to set one permanently you can use the ")
            txt += f"`{ctx.clean_prefix}mypf background <filename>` " + _("command")
            try:
                await ctx.send(txt, file=file)
            except discord.HTTPException:
                await ctx.send(_("Could not send background collage, file size may be too large."))

    @set_profile.command(name="fonts")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True)
    async def view_fonts(self, ctx: commands.Context):
        """View available fonts to use"""
        if not self.data[ctx.guild.id]["usepics"]:
            txt = _("Image profiles are disabled on this server so this command is off")
            if ctx.author.guild_permissions.manage_messages:
                txt += _("\nUse the `{}` command to toggle image profiles and enable this command.").format(
                    f"{ctx.clean_prefix}lset embeds"
                )
            await ctx.send(txt)
        async with ctx.typing():
            img = await self.get_or_fetch_fonts()
            if img is None:
                await ctx.send(_("Failed to generate background samples"))
            buffer = BytesIO()
            try:
                img.save(buffer, format="WEBP")
                buffer.name = f"{ctx.author.id}.webp"
            except (ValueError, KeyError):
                img.save(buffer, format="PNG", quality=50)
                buffer.name = f"{ctx.author.id}.png"
            buffer.seek(0)
            file = discord.File(buffer)
            txt = _("Here are the current fonts, to set one permanently you can use the ")
            txt += f"`{ctx.clean_prefix}mypf font <fontname>` " + _("command")
            try:
                await ctx.send(txt, file=file)
            except discord.HTTPException:
                await ctx.send(_("Could not send font collage, file size may be too large."))

    @set_profile.command(name="type")
    async def toggle_profile_type(self, ctx: commands.Context):
        """
        Toggle your profile image type (full/slim)

        Full size includes your balance, role icon and prestige icon
        Slim is a smaller slimmed down version
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))
        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            return await ctx.send(_("You have no information stored about your account yet. Talk for a bit first"))
        full = users[user_id]["full"]
        if full:
            self.data[ctx.guild.id]["users"][user_id]["full"] = False
            await ctx.send(_("Your profile image has been set to **Slim**"))
        else:
            self.data[ctx.guild.id]["users"][user_id]["full"] = True
            await ctx.send(_("Your profile image has been set to **Full**"))
        await ctx.tick()

    @set_profile.command(name="namecolor", aliases=["name"])
    @commands.bot_has_permissions(embed_links=True)
    async def set_name_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your username

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**

        Set to `default` to randomize your name color each time you run the command
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))
        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        if hex_color == "default":
            self.data[ctx.guild.id]["users"][user_id]["colors"]["name"] = None
            return await ctx.send(_("Your name color has been reset to default"))

        try:
            rgb = hex_to_rgb(hex_color)
        except ValueError:
            return await ctx.send(_("That is an invalid color, please use a valid integer color code or hex color."))
        try:
            embed = discord.Embed(
                description="This is the color you chose",
                color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2]),
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(_("Failed to set color, the following error occurred:\n") + f"{box(str(e), lang='python')}")
            return
        self.data[ctx.guild.id]["users"][user_id]["colors"]["name"] = hex_color
        await ctx.tick()

    @set_profile.command(name="statcolor", aliases=["stat"])
    @commands.bot_has_permissions(embed_links=True)
    async def set_stat_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your server stats

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**

        Set to `default` to randomize your name color each time you run the command
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))
        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        if hex_color == "default":
            self.data[ctx.guild.id]["users"][user_id]["colors"]["stat"] = None
            return await ctx.send(_("Your stats color has been reset to default"))

        try:
            rgb = hex_to_rgb(hex_color)
        except ValueError:
            return await ctx.send(_("That is an invalid color, please use a valid integer color code or hex color."))

        try:
            embed = discord.Embed(
                description="This is the color you chose",
                color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2]),
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(_("Failed to set color, the following error occurred:\n") + f"{box(str(e), lang='python')}")
            return
        self.data[ctx.guild.id]["users"][user_id]["colors"]["stat"] = hex_color
        await ctx.tick()

    @set_profile.command(name="levelbar", aliases=["lvlbar", "bar"])
    @commands.bot_has_permissions(embed_links=True)
    async def set_levelbar_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your level bar

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**

        Set to `default` to randomize your name color each time you run the command
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))
        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        if hex_color == "default":
            self.data[ctx.guild.id]["users"][user_id]["colors"]["levelbar"] = None
            return await ctx.send(_("Your level bar color has been reset to default"))

        try:
            rgb = hex_to_rgb(hex_color)
        except ValueError:
            return await ctx.send(_("That is an invalid color, please use a valid integer color code or hex color."))

        try:
            embed = discord.Embed(
                description="This is the color you chose",
                color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2]),
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(_("Failed to set color, the following error occurred:\n") + f"{box(str(e), lang='python')}")
            return
        self.data[ctx.guild.id]["users"][user_id]["colors"]["levelbar"] = hex_color
        await ctx.tick()

    @set_profile.command(name="background", aliases=["bg"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def set_user_background(self, ctx: commands.Context, image_url: str = None):
        """
        Set a background for your profile

        This will override your profile banner as the background

        **WARNING**
        Profile backgrounds are wide landscapes (1050 by 450 pixels) with an aspect ratio of 21:9
        Using portrait images will be cropped.

        Tip: Googling "dual monitor backgrounds" gives good results for the right images

        Here are some good places to look.
        [dualmonitorbackgrounds](https://www.dualmonitorbackgrounds.com/)
        [setaswall](https://www.setaswall.com/dual-monitor-wallpapers/)
        [pexels](https://www.pexels.com/photo/panoramic-photography-of-trees-and-lake-358482/)
        [teahub](https://www.teahub.io/searchw/dual-monitor/)

        **Additional Options**
         - Leave image_url blank to reset back to using your profile banner (or random if you don't have one)
         - `random` will randomly select from a pool of default backgrounds each time
         - `filename` run `[p]mypf backgrounds` to view default options you can use by including their filename
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))

        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        default_bg = bundled_data_path(self) / "backgrounds"
        saved_bg = cog_data_path(self) / "backgrounds"

        backgrounds = list(default_bg.iterdir()) + list(saved_bg.iterdir())

        # If image url is given, run some checks
        if not image_url and not get_attachments(ctx):
            return await ctx.send(_("You must provide a url, filename, or attach a file"))

        filepath = None
        if att := get_attachments(ctx):
            image_url = att[0].url
            if not await self.valid_url(ctx, image_url):
                return
        elif image_url.lower().startswith("http"):
            if not await self.valid_url(ctx, image_url):
                return
        else:
            for file in backgrounds:
                if image_url.lower() in file.name.lower():
                    image_url = file.name
                    filepath = file
                    break

        if image_url:
            self.data[ctx.guild.id]["users"][user_id]["background"] = image_url
            if image_url == "random":
                await ctx.send("Your profile background will be randomized each time you run the profile command!")
            else:
                # Either a valid url or a specified default file
                if filepath:
                    file = discord.File(filepath)
                    await ctx.send(_("Your background image has been set to `{}`!").format(image_url), file=file)
                else:
                    await ctx.send(_("Your background image has been set to `{}`!").format(image_url))
        else:
            self.data[ctx.guild.id]["users"][user_id]["background"] = None
            await ctx.send(_("Your background has been removed since you did not specify a url!"))
        await ctx.tick()

    @set_profile.command(name="font")
    async def set_user_font(self, ctx: commands.Context, *, font_name: str):
        """
        Set a font for your profile

        To view available fonts, type `[p]myprofile fonts`
        To revert to the default font, use `default` for the `font_name` argument
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))

        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        if font_name.lower() == "default":
            self.data[ctx.guild.id]["users"][user_id]["font"] = None
            return await ctx.send(_("Your profile font has been reverted to default"))

        default_fonts = bundled_data_path(self) / "fonts"
        saved_fonts = cog_data_path(self) / "fonts"

        fonts = list(default_fonts.iterdir()) + list(saved_fonts.iterdir())
        for file in fonts:
            if font_name.lower() in file.name.lower():
                break
        else:
            return await ctx.send(_("I could not find a font file with that name"))

        self.data[ctx.guild.id]["users"][user_id]["font"] = file.name
        await ctx.send(_("Your profile font has been set to ") + f"`{file.name}`")

    @set_profile.command(name="blur")
    async def set_user_blur(self, ctx: commands.Context):
        """
        Toggle a slight blur effect on the background image where the text is displayed.
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))

        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        current = self.data[ctx.guild.id]["users"][user_id]["blur"]
        self.data[ctx.guild.id]["users"][user_id]["blur"] = not current
        await ctx.send(_("Your profile background blur has been set to ") + str(not current))

    @commands.command(name="pf")
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def get_profile(self, ctx: commands.Context, *, user: discord.Member = None):
        """View your profile"""
        if not user:
            user = ctx.author
        if user.bot:
            return await ctx.send("Bots can't have profiles!")

        gid = ctx.guild.id
        if gid not in self.data:
            await self.initialize()

        # Main config stuff
        conf = self.data[gid]
        buttons = conf["emojis"]
        usepics = conf["usepics"]
        users = conf["users"]
        mention = conf["mention"]
        showbal = conf["showbal"]
        barlength = conf["barlength"]
        user_id = str(user.id)
        if user_id not in users:
            return await ctx.send(_("No information available yet!"))

        if usepics and not ctx.channel.permissions_for(ctx.me).attach_files:
            return await ctx.send(_("I do not have permission to send images to this channel"))
        if not usepics and not ctx.channel.permissions_for(ctx.me).embed_links:
            return await ctx.send(_("I do not have permission to send embeds to this channel"))

        bal = await bank.get_balance(user)
        currency_name = await bank.get_currency_name(ctx.guild)

        role_icon = None
        if DPY2:
            pfp = user.display_avatar
            role_icon = user.top_role.display_icon
            if isinstance(role_icon, str):
                role_icon = get_twemoji(role_icon)
        else:
            pfp = user.avatar_url

        p = users[user_id]
        full = p["full"]
        pos = await get_user_position(conf, user_id)
        position = humanize_number(pos["p"])  # Int
        percentage = pos["pr"]  # Float

        # User stats
        level: int = p["level"]  # Int
        xp: int = int(p["xp"])  # Float in the config but force int
        messages: int = p["messages"]  # Int
        voice: int = p["voice"]  # Int
        prestige: int = p["prestige"]  # Int
        stars: int = p["stars"]  # Int
        emoji: dict = p["emoji"]  # Dict
        bg = p["background"]  # Either None, random, or a filename
        font = p["font"]  # Either None or a filename
        blur = p["blur"]  # Bool

        # Calculate remaining needed stats
        next_level = level + 1
        xp_prev = get_xp(level, base=conf["base"], exp=conf["exp"])
        xp_needed = get_xp(next_level, base=conf["base"], exp=conf["exp"])

        user_xp_progress = xp - xp_prev
        next_xp_diff = xp_needed - xp_prev
        lvlbar = get_bar(user_xp_progress, next_xp_diff, width=barlength)

        def get_emoji(name: str):
            raw = buttons[name]
            if isinstance(raw, str) and raw.isdigit():
                emoji = self.bot.get_emoji(int(raw))
            elif isinstance(raw, int):
                emoji = self.bot.get_emoji(raw)
            else:
                emoji = raw

            if not emoji:
                # Get default
                emoji = default_guild["emojis"][name]

            return emoji

        level_emoji = get_emoji("level")
        trophy_emoji = get_emoji("trophy")
        star_emoji = get_emoji("star")
        chat_emoji = get_emoji("chat")
        mic_emoji = get_emoji("mic")
        bulb_emoji = get_emoji("bulb")
        money_emoji = get_emoji("money")

        async with ctx.typing():
            if not usepics:
                msg = f"{level_emoji}｜" + _("Level ") + humanize_number(level) + "\n"
                if prestige:
                    msg += f"{trophy_emoji}｜" + _("Prestige ") + humanize_number(prestige) + f" {emoji['str']}\n"
                msg += f"{star_emoji}｜{humanize_number(stars)}" + _(" stars\n")
                msg += f"{chat_emoji}｜{humanize_number(messages)}" + _(" messages sent\n")
                msg += f"{mic_emoji}｜{time_formatter(voice)}" + _(" in voice\n")
                msg += f"{bulb_emoji}｜{humanize_number(user_xp_progress)}/{humanize_number(next_xp_diff)} Exp ({humanize_number(xp)} total)\n"
                if showbal:
                    msg += f"{money_emoji}｜{humanize_number(bal)} {currency_name}"
                em = discord.Embed(description=msg, color=user.color)
                footer = _("Rank ") + position + _(", with ") + str(percentage) + _("% of global server Exp")
                author_name = _("{}'s Profile").format(user.display_name)
                em.set_author(name=author_name, icon_url=pfp)
                em.set_footer(text=footer, icon_url=role_icon)
                em.add_field(name=_("Progress"), value=box(lvlbar, "py"))

                try:
                    await ctx.reply(embed=em, mention_author=mention)
                except discord.HTTPException:
                    await ctx.send(embed=em)

            else:
                bg_image = bg if bg else await self.get_banner(user)
                colors = users[user_id]["colors"]
                usercolors = {
                    "base": hex_to_rgb(str(user.colour)),
                    "name": hex_to_rgb(colors["name"]) if colors["name"] else None,
                    "stat": hex_to_rgb(colors["stat"]) if colors["stat"] else None,
                    "levelbar": hex_to_rgb(colors["levelbar"]) if colors["levelbar"] else None,
                }

                args = {
                    "bg_image": bg_image,  # Background image link
                    "profile_image": pfp,  # User profile picture link
                    "level": level,  # User current level
                    "prev_xp": xp_prev,  # Preveious levels cap
                    "user_xp": xp,  # User current xp
                    "next_xp": xp_needed,  # xp required for next level
                    "user_position": position,  # User position in leaderboard
                    "user_name": user.name,  # username with discriminator
                    "user_status": str(user.status).strip(),  # User status eg. online, offline, idle, streaming, dnd
                    "colors": usercolors,  # User's color
                    "messages": humanize_number(messages),
                    "voice": time_formatter(voice),
                    "prestige": prestige,
                    "emoji": emoji["url"] if emoji and isinstance(emoji, dict) else None,
                    "stars": stars,
                    "balance": bal if showbal else 0,
                    "currency": currency_name,
                    "role_icon": role_icon,
                    "font_name": font,
                    "render_gifs": self.render_gifs,
                    "blur": blur,
                }
                start = perf_counter()
                file = await self.get_or_fetch_profile(user, args, full)
                rtime = round((perf_counter() - start) * 1000)
                if not file:
                    return await ctx.send("Failed to generate profile image :( try again in a bit")
                start2 = perf_counter()
                try:
                    await ctx.reply(file=file, mention_author=mention)
                except Exception as e:
                    if "In message_reference: Unknown message" not in str(e):
                        log.error(f"Failed to send profile pic: {e}")
                    try:
                        file = await self.get_or_fetch_profile(user, args, full)
                        if mention:
                            await ctx.send(ctx.author.mention, file=file)
                        else:
                            await ctx.send(file=file)
                    except Exception as e:
                        log.error(f"Failed AGAIN to send profile pic: {e}")
                mtime = round((perf_counter() - start2) * 1000)
                if ctx.author.id == 350053505815281665:
                    log.info(f"Render time: {humanize_number(rtime)}ms\n" f"Send Time: {humanize_number(mtime)}ms")

    @commands.command(name="prestige")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def prestige_user(self, ctx: commands.Context):
        """
        Prestige your rank!
        Once you have reached this servers prestige level requirement, you can
        reset your level and experience to gain a prestige level and any perks associated with it

        If you are over level and xp when you prestige, your xp and levels will carry over
        """
        conf = self.data[ctx.guild.id]
        perms = ctx.channel.permissions_for(ctx.guild.me).manage_roles
        if not perms:
            log.warning("Insufficient perms to assign prestige ranks!")

        required_level = conf["prestige"]
        if not required_level:
            return await ctx.send(_("Prestige is disabled on this server!"))
        prestige_data = conf["prestigedata"]
        if not prestige_data:
            return await ctx.send(_("Prestige levels have not been set yet!"))
        user_id = str(ctx.author.id)
        users = conf["users"]
        if user_id not in users:
            return await ctx.send(_("No information available for you yet!"))
        user = users[user_id]
        current_level = user["level"]
        prestige = int(user["prestige"])
        pending_prestige = str(prestige + 1)
        # First add new prestige role
        if current_level < required_level:
            msg = _("**You are not eligible to prestige yet!**\n")
            msg += _("`Your level:     `") + f"{current_level}\n"
            msg += _("`Required Level: `") + f"{required_level}"
            embed = discord.Embed(description=msg, color=discord.Color.red())
            return await ctx.send(embed=embed)

        if pending_prestige not in prestige_data:
            return await ctx.send(_("Prestige level ") + str(pending_prestige) + _(" has not been set yet!"))

        role_id = prestige_data[pending_prestige]["role"]
        prestige_role = ctx.guild.get_role(role_id) if role_id else None
        emoji = prestige_data[pending_prestige]["emoji"]
        if perms and prestige_role:
            try:
                await ctx.author.add_roles(prestige_role)
            except discord.Forbidden:
                await ctx.send(
                    _("I do not have the proper permissions to assign you to the {} role!").format(
                        prestige_role.mention
                    )
                )

        current_xp = user["xp"]
        xp_at_prestige = get_xp(required_level, conf["base"], conf["exp"])
        leftover_xp = current_xp - xp_at_prestige if current_xp > xp_at_prestige else 0
        newlevel = get_level(leftover_xp, conf["base"], conf["exp"]) if leftover_xp > 0 else 1

        self.data[ctx.guild.id]["users"][user_id]["prestige"] = int(pending_prestige)
        self.data[ctx.guild.id]["users"][user_id]["emoji"] = emoji
        self.data[ctx.guild.id]["users"][user_id]["level"] = newlevel
        self.data[ctx.guild.id]["users"][user_id]["xp"] = leftover_xp
        embed = discord.Embed(
            description=_("You have reached Prestige ") + f"{pending_prestige}!",
            color=ctx.author.color,
        )
        await ctx.send(embed=embed)

        # Then remove old prestige role if autoremove is toggled
        if prestige > 0 and not conf["stackprestigeroles"]:
            if str(prestige) in prestige_data:
                role_id = prestige_data[str(prestige)]["role"]
                role = ctx.guild.get_role(role_id)
                if role and perms:
                    await ctx.author.remove_roles(role)

        # Handle roles
        level_roles = conf["levelroles"]

        # Remove all level roles from user
        role_ids_to_remove = [int(role_id) for level, role_id in level_roles.items() if int(level) > newlevel]
        to_remove = [role for role in ctx.author.roles if role.id in role_ids_to_remove]
        try:
            await ctx.author.remove_roles(*to_remove)
        except discord.Forbidden:
            await ctx.send(_("I don't have permissions to remove your old roles!"))

        # If autoremove is on then the new highest role might need to be reassigned
        highest_level = 0
        for level, role_id in level_roles.items():
            if newlevel >= int(level) >= highest_level:
                highest_level = int(level)

        if highest_level:
            role_id = level_roles[str(highest_level)]
            role = ctx.guild.get_role(role_id)
            try:
                await ctx.author.add_roles(role)
            except discord.Forbidden:
                await ctx.send(_("I was not able to re-add the {} role to your profile!").format(role.mention))

    @commands.command(name="lvltop", aliases=["topstats", "membertop", "topranks"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def leaderboard(
        self,
        ctx: commands.Context,
        stat: Optional[str] = None,
        global_stats: Optional[bool] = False,
    ):
        """
        View the Leaderboard

        **Arguments**
        `stat`: What kind of stat to display the weekly leaderboard for
        - Valid options are `exp`, `messages`, and `voice`

        `global_stats`: Include stats for all servers.

        Abbreviations of those arguments may also be used
        """
        if not stat:
            stat = "exp"
        if "star" in stat.lower():
            txt = _("Use the `") + str(ctx.clean_prefix) + _("startop` command for that")
            return await ctx.send(txt)

        if global_stats:
            conf = {"users": {}, "weekly": {"users": {}}}
            for data in self.data.values():
                # Load user stats
                for uid, stats in data["users"].items():
                    if uid in conf["users"]:
                        conf["users"][uid]["xp"] += stats["xp"]
                        conf["users"][uid]["voice"] += stats["voice"]
                        conf["users"][uid]["messages"] += stats["messages"]
                    else:
                        conf["users"][uid] = {
                            "xp": stats["xp"],
                            "voice": stats["voice"],
                            "messages": stats["messages"],
                        }
        else:
            conf = self.data[ctx.guild.id]

        async with ctx.typing():
            embeds = await asyncio.to_thread(get_leaderboard, ctx, conf, stat, "normal", global_stats)
        if isinstance(embeds, str):
            return await ctx.send(embeds)
        if not embeds:
            return await ctx.send(_("No user data yet!"))

        if len(embeds) == 1:
            embed = embeds[0]
            await ctx.send(embed=embed)
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="startop", aliases=["starlb"])
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def star_leaderboard(
        self,
        ctx: commands.Context,
        global_stars: Optional[bool] = False,
    ):
        """View the star leaderboard"""
        if global_stars:
            conf = {"users": {}, "weekly": {"users": {}}}
            for data in self.data.values():
                # Load user stats
                for uid, stats in data["users"].items():
                    if uid in conf["users"]:
                        conf["users"][uid]["stars"] += stats["stars"]
                    else:
                        conf["users"][uid] = {"stars": stats["stars"]}
        else:
            conf = self.data[ctx.guild.id]

        embeds = []
        leaderboard = {}
        total_stars = 0
        for user, data in conf["users"].items():
            if "stars" in data:
                stars = data["stars"]
                if stars:
                    leaderboard[user] = stars
                    total_stars += stars
        if not leaderboard:
            return await ctx.send(_("Nobody has stars yet 😕"))
        sorted_users = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)

        # Get your place in the LB
        you = ""
        for i in sorted_users:
            uid = i[0]
            if str(uid) == str(ctx.author.id):
                i = sorted_users.index(i)
                you = f"You: {i + 1}/{len(sorted_users)}\n"

        if DPY2:
            icon = ctx.guild.icon
        else:
            icon = ctx.guild.icon_url

        pages = math.ceil(len(sorted_users) / 10)
        start = 0
        stop = 10
        title = _("Global Star Leaderboard") if global_stars else _("Star Leaderboard")
        base_desc = _("Total ⭐'s: {}\n").format(f"`{humanize_number(total_stars)}`")

        for p in range(pages):
            if stop > len(sorted_users):
                stop = len(sorted_users)
            txt = ""
            for i in range(start, stop, 1):
                uid = sorted_users[i][0]
                user = ctx.guild.get_member(int(uid)) or self.bot.get_user(int(uid))
                if user:
                    user = user.name
                else:
                    user = uid
                stars = sorted_users[i][1]
                txt += f"{i + 1}. {user} ({stars})\n"

            embed = discord.Embed(
                title=title,
                description=base_desc + box(txt, lang="python"),
                color=discord.Color.random(),
            )

            if you:
                embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages} ｜ {you}", icon_url=icon)
            else:
                embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages}", icon_url=icon)
            embeds.append(embed)
            start += 10
            stop += 10

        if embeds:
            if len(embeds) == 1:
                embed = embeds[0]
                await ctx.send(embed=embed)
            else:
                await menu(ctx, embeds, DEFAULT_CONTROLS)
        else:
            return await ctx.send(_("No user data yet!"))

    @commands.command(name="weekly")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def weekly_lb(
        self,
        ctx: commands.Context,
        stat: Optional[str] = None,
        global_stats: Optional[bool] = False,
    ):
        """
        View the weekly leaderboard

        **Arguments**
        `stat`: What kind of stat to display the weekly leaderboard for
        - Valid options are `exp`, `messages`, `stars`, and `voice`

        `global_stats`: Include stats for all servers.


        Abbreviations of those arguments may also be used
        """
        if not stat:
            stat = "exp"
        if global_stats:
            conf = {"users": {}, "weekly": {"users": {}}}
            for data in self.data.values():
                # Load user stats
                for uid, stats in data["users"].items():
                    if uid in conf["users"]:
                        conf["users"][uid]["xp"] += stats["xp"]
                        conf["users"][uid]["voice"] += stats["voice"]
                        conf["users"][uid]["messages"] += stats["messages"]
                    else:
                        conf["users"][uid] = {
                            "xp": stats["xp"],
                            "voice": stats["voice"],
                            "messages": stats["messages"],
                        }
        else:
            conf = self.data[ctx.guild.id]
            if not conf["weekly"]["on"]:
                return await ctx.send(_("Weekly stats are disabled for this guild"))
            if not conf["weekly"]["users"]:
                return await ctx.send(_("There is no data for the weekly leaderboard yet, please chat a bit first."))

        embeds = await asyncio.to_thread(get_leaderboard, ctx, conf, stat, "weekly", global_stats)
        if isinstance(embeds, str):
            return await ctx.send(embeds)

        if len(embeds) == 1:
            embed = embeds[0]
            await ctx.send(embed=embed)
        else:
            await menu(ctx, embeds, DEFAULT_CONTROLS)

    @commands.command(name="lastweekly")
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def last_weekly(self, ctx: commands.Context):
        """View the last weekly embed"""
        conf = self.data[ctx.guild.id]
        if not conf["weekly"]["on"]:
            return await ctx.send(_("Weekly stats are disabled for this guild"))
        if not conf["weekly"]["last_embed"]:
            return await ctx.send(_("There is no recorded weekly embed saved"))
        embed = discord.Embed.from_dict(conf["weekly"]["last_embed"])
        embed.title = _("Last Weekly Winners")
        new_desc = _("{}\n`Last Reset:     `{}").format(embed.description, f"<t:{conf['weekly']['last_reset']}:R>")
        embed.description = new_desc
        await ctx.send(embed=embed)
