import asyncio
import logging
import typing as t
from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_list

from ..abc import MixinMeta
from ..common import const, formatter, utils
from ..generator import imgtools
from ..generator.tenor.converter import sanitize_url
from ..views.dynamic_menu import DynamicMenu

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.commands.user")


@app_commands.context_menu(name="View Profile")
async def view_profile_context(interaction: discord.Interaction, member: discord.Member):
    """View a user's profile"""
    await interaction.response.defer(ephemeral=True)
    bot: Red = interaction.client
    result = await bot.get_cog("LevelUp").get_user_profile_cached(member)
    if isinstance(result, discord.Embed):
        await interaction.followup.send(embed=result, ephemeral=True)
    else:
        await interaction.followup.send(file=result, ephemeral=True)


@cog_i18n(_)
class User(MixinMeta):
    @commands.hybrid_command(name="leveltop", aliases=["lvltop", "topstats", "membertop", "topranks"])
    @commands.guild_only()
    async def leveltop(
        self,
        ctx: commands.Context,
        stat: str = "exp",
        globalstats: bool = False,
        displayname: bool = True,
    ):
        """View the LevelUp leaderboard"""
        stat = stat.lower()
        pages = await asyncio.to_thread(
            formatter.get_leaderboard,
            bot=self.bot,
            guild=ctx.guild,
            db=self.db,
            stat=stat,
            lbtype="lb",
            is_global=globalstats,
            member=ctx.author,
            use_displayname=displayname,
            color=await self.bot.get_embed_color(ctx),
        )
        if isinstance(pages, str):
            return await ctx.send(pages)
        await DynamicMenu(ctx.author, pages, ctx.channel).refresh()

    @commands.command(name="roletop")
    @commands.guild_only()
    async def role_group_leaderboard(self, ctx: commands.Context):
        """View the leaderboard for roles"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.role_groups:
            return await ctx.send(_("Role groups have not been configured in this server yet!"))
        pages = await asyncio.to_thread(
            formatter.get_role_leaderboard,
            rolegroups=conf.role_groups,
            color=await self.bot.get_embed_color(ctx),
        )
        await DynamicMenu(ctx.author, pages, ctx.channel).refresh()

    @commands.hybrid_command(name="profile", aliases=["pf"])
    @commands.guild_only()
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def profile(self, ctx: commands.Context, *, user: discord.Member = None):
        """View User Profile"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.enabled:
            txt = _("Leveling is disabled in this server!")
            if await self.bot.is_admin(ctx.author):
                txt += _("\nYou can enable it with `{}`").format(f"{ctx.clean_prefix}lset toggle")
            return await ctx.send(txt)

        if user is None:
            user = ctx.author

        new_user_txt = None
        if user.id == ctx.author.id and user.id not in conf.users:
            # New user, tell them about how they can customize their profile
            new_user_txt = _(
                "Welcome to LevelUp!\nUse {} to view your profile settings and the available customization commands!"
            ).format(f"`{ctx.clean_prefix}mypf`")

        try:
            if ctx.interaction is None:
                async with ctx.typing():
                    result = await self.get_user_profile_cached(user)
                    conf = self.db.get_conf(ctx.guild)
                    if isinstance(result, discord.Embed):
                        try:
                            await ctx.reply(content=new_user_txt, embed=result, mention_author=conf.notifymention)
                        except discord.HTTPException:
                            await ctx.send(content=new_user_txt, embed=result)
                    else:  # File
                        try:
                            await ctx.reply(content=new_user_txt, file=result, mention_author=conf.notifymention)
                        except discord.HTTPException:
                            result.fp.seek(0)
                            await ctx.send(content=new_user_txt, file=result)
            else:
                await ctx.defer(ephemeral=True)
                result = await self.get_user_profile_cached(user)
                if isinstance(result, discord.Embed):
                    await ctx.send(content=new_user_txt, embed=result, ephemeral=True)
                else:  # File
                    await ctx.send(content=new_user_txt, file=result, ephemeral=True)
        except Exception as e:
            log.error("Error generating profile", exc_info=e)
            if "Payload Too Large" in str(e):
                txt = _("Your profile image is too large to send!")
            else:
                txt = _("An error occurred while generating your profile!\n{}").format(str(e))
            await ctx.send(txt)

    @commands.hybrid_command(name="prestige")
    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def prestige(self, ctx: commands.Context):
        """
        Prestige your rank!
        Once you have reached this servers prestige level requirement, you can
        reset your level and experience to gain a prestige level and any perks associated with it

        If you are over level and xp when you prestige, your xp and levels will carry over
        """
        conf = self.db.get_conf(ctx.guild)
        if ctx.author.id not in conf.users:
            return await ctx.send(_("You have no level data yet!"))
        if not conf.prestigelevel or not conf.prestigedata:
            return await ctx.send(_("Prestige has not been configured for this server!"))
        profile = conf.get_profile(ctx.author)
        if profile.level < conf.prestigelevel:
            return await ctx.send(_("You need to be at least level {} to prestige!").format(conf.prestigelevel))

        next_prestige = profile.prestige + 1
        if next_prestige not in conf.prestigedata:
            return await ctx.send(_("You have reached the maximum prestige level!"))

        pdata = conf.prestigedata[next_prestige]
        role = ctx.guild.get_role(pdata.role)

        current_xp = int(profile.xp)
        xp_at_prestige = conf.algorithm.get_xp(conf.prestigelevel)
        leftover_xp = current_xp - xp_at_prestige if current_xp > xp_at_prestige else 0
        newlevel = conf.algorithm.get_level(leftover_xp)

        profile.level = newlevel
        profile.xp = leftover_xp
        profile.prestige = next_prestige
        self.save()

        txt = _("You have reached Prestige {}!\n").format(f"**{next_prestige}**")

        if conf.stackprestigeroles and role:
            # Just add the new role to the user
            if role not in ctx.author.roles:
                try:
                    await ctx.author.add_roles(role, reason=_("Prestige Level"))
                    txt += _("- {} role added!").format(role.mention)
                except discord.HTTPException:
                    txt += _("- I was unable to give you the {} role!").format(role.mention)
        elif not conf.stackprestigeroles:
            # Remove all roles and give the new one if it exists
            to_remove = [r for r in ctx.author.roles if r.id in conf.levelroles.values() and r != role]
            to_add = [role] if role not in ctx.author.roles else []
            try:
                await ctx.author.add_roles(*to_add, reason=_("Prestige Level"))
                txt += _("- {} role added!").format(role.mention)
            except discord.HTTPException:
                txt += _("- I was unable to give you the {} role!").format(role.mention)
            if to_remove:
                try:
                    await ctx.author.remove_roles(*to_remove, reason=_("Prestige Level"))
                    txt += _("\n- I have removed your old prestige roles")
                except discord.HTTPException:
                    txt += _("\n- I was unable to remove your old prestige roles")
        embed = discord.Embed(description=txt, color=await self.bot.get_embed_color(ctx))
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="setprofile", aliases=["myprofile", "mypf", "pfset"])
    @commands.guild_only()
    async def set_profile(self, ctx: commands.Context):
        """Customize your profile"""
        if ctx.invoked_subcommand is None:
            conf = self.db.get_conf(ctx.guild)
            profile = conf.get_profile(ctx.author)

            desc = _(
                "`Profile Style:   `{}\n"
                "`Show Nickname:   `{}\n"
                "`Blur:            `{}\n"
                "`Name Color:      `{}\n"
                "`Stat Color:      `{}\n"
                "`LevelBar Color:  `{}\n"
                "`Font:            `{}\n"
                "`Background:      `{}\n"
            ).format(
                profile.style,
                profile.show_displayname,
                _("Enabled") if profile.blur else _("Disabled"),
                profile.namecolor,
                profile.statcolor,
                profile.barcolor,
                profile.font,
                profile.background,
            )
            embed = discord.Embed(
                title=_("Your Profile Settings"),
                description=desc,
                color=await self.bot.get_embed_color(ctx),
            )
            bg = profile.background
            file = None
            if bg.startswith("http"):
                embed.set_image(url=bg)
            elif bg not in ("default", "random"):
                available = list(self.backgrounds.iterdir()) + list(self.custom_backgrounds.iterdir())
                for path in available:
                    if bg.lower() in path.name.lower():
                        embed.set_image(url=f"attachment://{path.name}")
                        file = discord.File(str(path), filename=path.name)
                        break
            if ctx.channel.permissions_for(ctx.me).attach_files:
                await ctx.send(embed=embed, file=file)
            elif ctx.channel.permissions_for(ctx.me).embed_links:
                await ctx.send(embed=embed)
            else:
                await ctx.send(embed.description)

    @set_profile.command(name="bgpath")
    @commands.is_owner()
    async def get_bg_path(self, ctx: commands.Context):
        """Get folder path for this cog's backgrounds"""
        txt = ""
        txt += _("- Defaults: {}\n").format(self.backgrounds)
        txt += _("- Custom: {}\n").format(self.custom_backgrounds)
        await ctx.send(txt)

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
        content = utils.get_attachments(ctx)
        if not content:
            return await ctx.send(_("No images found in the message!"))
        valid = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
        filename = content[0].filename
        if not filename.endswith(tuple(valid)):
            return await ctx.send(
                _("That is not a valid format, must be on of the following extensions: ") + humanize_list(valid)
            )
        for ext in valid:
            if ext in filename.lower():
                break
        else:
            ext = ".png"
        filebytes = await content[0].read()
        if preferred_filename:
            if Path(filename).suffix.lower() == Path(preferred_filename).suffix.lower():
                # User already included the extension
                filename = preferred_filename
            else:
                filename = preferred_filename + ext
        path = self.custom_backgrounds / filename
        path.write_bytes(filebytes)
        await ctx.send(_("Your custom background has been saved as {}").format(f"`{filename}`"))

    @set_profile.command(name="rembackground")
    @commands.is_owner()
    async def remove_background(self, ctx: commands.Context, *, filename: str):
        """Remove a default background from the cog's backgrounds folder"""
        for path in self.custom_backgrounds.iterdir():
            if filename.lower() in path.name.lower():
                break
        else:
            return await ctx.send(_("No background found with that name!"))
        msg = await ctx.send(_("Are you sure you want to delete {}?").format(f"`{path}`"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Cancelled"))
        path.unlink()
        await msg.edit(content=_("The background {} has been deleted").format(f"`{path}`"))

    @set_profile.command(name="fontpath")
    @commands.is_owner()
    async def get_font_path(self, ctx: commands.Context):
        """Get folder path for this cog's fonts"""
        txt = ""
        txt += _("- Defaults: {}\n").format(self.fonts)
        txt += _("- Custom: {}\n").format(self.custom_fonts)
        await ctx.send(txt)

    @set_profile.command(name="addfont")
    @commands.is_owner()
    async def add_font(self, ctx: commands.Context, preferred_filename: str = None):
        """
        Add a custom font to the cog from discord

        **Arguments**
        `preferred_filename` - If a name is given, it will be saved as this name instead of the filename
        **Note:** do not include the file extension in the preferred name, it will be added automatically
        """
        content = utils.get_attachments(ctx)
        if not content:
            return await ctx.send(_("No fonts found in the message!"))
        valid = [".ttf", ".otf"]
        filename = content[0].filename
        if not filename.endswith(tuple(valid)):
            return await ctx.send(
                _("That is not a valid format, must be on of the following extensions: ") + humanize_list(valid)
            )
        for ext in valid:
            if ext in filename.lower():
                break
        else:
            ext = ".ttf"
        filebytes = await content[0].read()
        if preferred_filename:
            if Path(filename).suffix.lower() == Path(preferred_filename).suffix.lower():
                # User already included the extension
                filename = preferred_filename
            else:
                filename = preferred_filename + ext
        path = self.custom_fonts / filename
        path.write_bytes(filebytes)
        await ctx.send(_("Your custom font has been saved as {}").format(f"`{filename}`"))

    @set_profile.command(name="remfont")
    @commands.is_owner()
    async def remove_font(self, ctx: commands.Context, *, filename: str):
        """Remove a default font from the cog's fonts folder"""
        for path in self.custom_fonts.iterdir():
            if filename.lower() in path.name.lower():
                break
        else:
            return await ctx.send(_("No font found with that name!"))
        msg = await ctx.send(_("Are you sure you want to delete {}?").format(f"`{path}`"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Cancelled"))
        path.unlink()
        await msg.edit(content=_("The font {} has been deleted").format(f"`{path}`"))

    @set_profile.command(name="backgrounds")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True)
    async def view_all_backgrounds(self, ctx: commands.Context):
        """View the all available backgrounds"""
        paths = list(self.backgrounds.iterdir()) + list(self.custom_backgrounds.iterdir())
        paths = [str(x) for x in paths]

        def _run() -> discord.File:
            img = imgtools.format_backgrounds(paths)
            buffer = BytesIO()
            img.save(buffer, format="WEBP")
            buffer.seek(0)
            return discord.File(buffer, filename="backgrounds.webp")

        async with ctx.typing():
            file = await asyncio.to_thread(_run)
            txt = _("Here are all the available backgrounds!\nYou can use {} to set your background").format(
                f"`{ctx.clean_prefix}setprofile background <image name>`"
            )
            await ctx.send(txt, file=file)

    @set_profile.command(name="fonts")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.bot_has_permissions(attach_files=True)
    async def view_fonts(self, ctx: commands.Context):
        """View available fonts to use"""
        paths = list(self.fonts.iterdir()) + list(self.custom_fonts.iterdir())
        paths = [str(x) for x in paths]

        def _run() -> discord.File:
            img = imgtools.format_fonts(paths)
            buffer = BytesIO()
            img.save(buffer, format="WEBP")
            buffer.seek(0)
            return discord.File(buffer, filename="fonts.webp")

        async with ctx.typing():
            file = await asyncio.to_thread(_run)
            txt = _("Here are all the available fonts!\nYou can use {} to set your font").format(
                f"`{ctx.clean_prefix}setprofile font <font name>`"
            )
            await ctx.send(txt, file=file)

    @set_profile.command(name="style")
    async def toggle_profile_style(self, ctx: commands.Context, style: t.Literal["default", "runescape"]):
        """
        Set your profile image style

        - `default` is the default profile style, very customizable
        - `runescape` is a runescape style profile, less customizable but more nostalgic
        - (WIP) - more to come

        """
        if style not in const.PROFILE_TYPES:
            txt = _("That is not a valid profile style, please choose from the following: {}").format(
                humanize_list(const.PROFILE_TYPES)
            )
        conf = self.db.get_conf(ctx.guild)
        if conf.use_embeds:
            txt = _("Image profiles are disabled here, this setting has no effect!")
            return await ctx.send(txt)

        profile = conf.get_profile(ctx.author)
        profile.style = style
        self.save()
        await ctx.send(_("Your profile type has been set to {}").format(style.capitalize()))

    @set_profile.command(name="shownick")
    async def toggle_show_nickname(self, ctx: commands.Context):
        """Toggle showing your nickname in your profile"""
        conf = self.db.get_conf(ctx.guild)
        profile = conf.get_profile(ctx.author)
        profile.show_displayname = not profile.show_displayname
        self.save()
        txt = (
            _("Your nickname will now be shown in your profile!")
            if profile.show_displayname
            else _("Your username will now be shown in your profile!")
        )
        await ctx.send(txt)

    @set_profile.command(name="namecolor", aliases=["name"])
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def set_name_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your username

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**

        Set to `default` to randomize your name color each time you run the command
        """
        conf = self.db.get_conf(ctx.guild)
        profile = conf.get_profile(ctx.author)
        if profile.style in const.STATIC_FONT_STYLES:
            return await ctx.send(_("You cannot change your name color with the current profile style!"))
        if hex_color == "default":
            profile.namecolor = None
            self.save()
            return await ctx.send(_("Your name color has been set to random!"))
        try:
            rgb = utils.string_to_rgb(hex_color)
        except ValueError:
            file = discord.File(imgtools.COLORTABLE)
            return await ctx.send(
                _("That is an invalid color, please use a valid name, integer, or hex color."), file=file
            )
        embed = discord.Embed(
            description=_("Name color updated! This is the color you chose."),
            color=discord.Color.from_rgb(*rgb),
        )
        profile.namecolor = hex_color
        self.save()
        await ctx.send(embed=embed)

    @set_profile.command(name="statcolor", aliases=["stat"])
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def set_stat_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your server stats

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**

        Set to `default` to randomize your name color each time you run the command
        """
        conf = self.db.get_conf(ctx.guild)
        profile = conf.get_profile(ctx.author)
        if hex_color == "default":
            profile.statcolor = None
            self.save()
            return await ctx.send(_("Your stat color has been set to random!"))
        try:
            rgb = utils.string_to_rgb(hex_color)
        except ValueError:
            file = discord.File(imgtools.COLORTABLE)
            return await ctx.send(
                _("That is an invalid color, please use a valid name, integer, or hex color."), file=file
            )
        embed = discord.Embed(
            description=_("Stat color updated! This is the color you chose."),
            color=discord.Color.from_rgb(*rgb),
        )
        profile.statcolor = hex_color
        self.save()
        await ctx.send(embed=embed)

    @set_profile.command(name="barcolor", aliases=["levelbar", "lvlbar", "bar"])
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def set_levelbar_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your level bar

        Here is a link to google's color picker:
        **[Hex Color Picker](https://htmlcolorcodes.com/)**

        Set to `default` to randomize your name color each time you run the command
        """
        conf = self.db.get_conf(ctx.guild)
        profile = conf.get_profile(ctx.author)
        if profile.style in const.STATIC_FONT_STYLES:
            return await ctx.send(_("You cannot change your name color with the current profile style!"))
        if hex_color == "default":
            profile.barcolor = None
            self.save()
            return await ctx.send(_("Your level bar color has been set to random!"))
        try:
            rgb = utils.string_to_rgb(hex_color)
        except ValueError:
            file = discord.File(imgtools.COLORTABLE)
            return await ctx.send(
                _("That is an invalid color, please use a valid name, integer, or hex color."), file=file
            )
        embed = discord.Embed(
            description=_("Level bar color updated! This is the color you chose."),
            color=discord.Color.from_rgb(*rgb),
        )
        profile.barcolor = hex_color
        self.save()
        await ctx.send(embed=embed)

    @set_profile.command(name="background", aliases=["bg"])
    @commands.bot_has_permissions(embed_links=True)
    async def set_user_background(self, ctx: commands.Context, url: t.Optional[str] = None):
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
        conf = self.db.get_conf(ctx.guild)
        if conf.use_embeds:
            txt = _("Image profiles are disabled here, this setting has no effect!")
            return await ctx.send(txt)
        profile = conf.get_profile(ctx.author)
        if profile.style in const.STATIC_FONT_STYLES:
            return await ctx.send(_("You cannot change your name color with the current profile style!"))

        if url and url == "random":
            profile.background = "random"
            self.save()
            return await ctx.send(_("Your profile background has been set to random!"))
        if url and url == "default":
            profile.background = "default"
            self.save()
            return await ctx.send(_("Your profile background has been set to default!"))

        attachments = utils.get_attachments(ctx)

        # If image url is given, run some checks
        if not url and not attachments:
            if profile.background == "default":
                return await ctx.send(_("You must provide a url, filename, or attach a file"))
            else:
                profile.background = "default"
                self.save()
                return await ctx.send(_("Your background has been reset to default!"))

        if url is None:
            if attachments[0].size > ctx.guild.filesize_limit:
                return await ctx.send(_("That image is too large for this server's upload limit!"))
            profile.background = attachments[0].url
            try:
                file: discord.File = await self.get_user_profile(ctx.author, reraise=True)
                if file.__sizeof__() > ctx.guild.filesize_limit:
                    profile.background = "default"
                    return await ctx.send(_("That image is too large for this server's upload limit!"))
            except Exception as e:
                profile.background = "default"
                return await ctx.send(_("That image is not a valid profile background!\n{}").format(str(e)))
            self.save()
            return await ctx.send(_("Your profile background has been set!"))

        if url.startswith("http"):
            log.debug("Sanitizing link")
            url = await sanitize_url(url, ctx)
            profile.background = url
            try:
                file: discord.File = await self.get_user_profile(ctx.author, reraise=True)
                if file.__sizeof__() > ctx.guild.filesize_limit:
                    profile.background = "default"
                    return await ctx.send(_("That image is too large for this server's upload limit!"))
            except Exception as e:
                profile.background = "default"
                return await ctx.send(_("That image is not a valid profile background!\n{}").format(str(e)))
            self.save()
            return await ctx.send(_("Your profile background has been set!"))

        # Check if the user provided a filename
        backgrounds = list(self.backgrounds.iterdir()) + list(self.custom_backgrounds.iterdir())
        for path in backgrounds:
            if url.lower() in path.name.lower():
                break
        else:
            return await ctx.send(_("No background found with that name!"))
        file = discord.File(path)
        profile.background = path.stem
        self.save()
        txt = _("Your profile background has been set to {}").format(f"`{path.name}`")
        await ctx.send(txt, file=file)

    @set_profile.command(name="font")
    async def set_user_font(self, ctx: commands.Context, *, font_name: str):
        """
        Set a font for your profile

        To view available fonts, type `[p]myprofile fonts`
        To revert to the default font, use `default` for the `font_name` argument
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.use_embeds:
            txt = _("Image profiles are disabled here, this setting has no effect!")
            return await ctx.send(txt)
        profile = conf.get_profile(ctx.author)
        if profile.style in const.STATIC_FONT_STYLES:
            return await ctx.send(_("You cannot change your name color with the current profile style!"))

        if font_name == "default":
            profile.font = "default"
            self.save()
            return await ctx.send(_("Your font has been reset to default!"))
        fonts = list(self.fonts.iterdir()) + list(self.custom_fonts.iterdir())
        for path in fonts:
            if font_name.lower() in path.name.lower():
                break
        else:
            return await ctx.send(_("No font found with that name!"))
        profile.font = path.name
        self.save()
        txt = _("Your font has been set to {}").format(f"`{path.name}`")
        await ctx.send(txt)

    @set_profile.command(name="blur")
    async def set_user_blur(self, ctx: commands.Context):
        """
        Toggle a slight blur effect on the background image where the text is displayed.
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.use_embeds:
            txt = _("Image profiles are disabled here, this setting has no effect!")
            return await ctx.send(txt)
        profile = conf.get_profile(ctx.author)
        if profile.style in const.STATIC_FONT_STYLES:
            return await ctx.send(_("You cannot change your name color with the current profile style!"))
        profile.blur = not profile.blur
        self.save()
        txt = _("Your profile blur has been set to {}").format(_("Enabled") if profile.blur else _("Disabled"))
        await ctx.send(txt)
