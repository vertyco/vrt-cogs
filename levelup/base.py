import asyncio
import datetime
import json
import logging
import math
import traceback
from io import BytesIO

import discord
import tabulate
import validators
from redbot.core import commands, bank
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box

from .formatter import (
    time_formatter,
    hex_to_rgb,
    get_level,
    get_xp,
    get_user_position,
    get_user_stats,
    profile_embed,
)
from .generator import Generator

if discord.__version__ > "1.7.3":
    from .dpymenu import menu, DEFAULT_CONTROLS

    DPY2 = True
else:
    # from .dislashmenu import menu, DEFAULT_CONTROLS
    from .menus import menu, DEFAULT_CONTROLS

    DPY2 = False

log = logging.getLogger("red.vrt.levelup.commands")
_ = Translator("LevelUp", __file__)


@cog_i18n(_)
class UserCommands(commands.Cog):
    # Generate level up image
    async def gen_levelup_img(self, args: dict):
        task = self.bot.loop.run_in_executor(None, lambda: Generator().generate_levelup(**args))
        try:
            img = await asyncio.wait_for(task, timeout=60)
        except asyncio.TimeoutError:
            return None
        return img

    # Generate profile image
    async def gen_profile_img(self, args: dict, full: bool = True):
        if full:
            task = self.bot.loop.run_in_executor(None, lambda: Generator().generate_profile(**args))
        else:
            task = self.bot.loop.run_in_executor(None, lambda: Generator().generate_slim_profile(**args))

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

            args = {'bg_image': image_url}
            await self.bot.loop.run_in_executor(None, lambda: Generator().generate_profile(**args))
        except Exception as e:
            if "cannot identify image file" in str(e):
                await ctx.send(_("Uh Oh, looks like that is not a valid image, cannot identify the file"))
                return
            else:
                log.warning(f"background set failed: {traceback.format_exc()}")
                await ctx.send(_("Uh Oh, looks like that is not a valid image"))
                return
        return True

    # Hacky way to get user banner
    async def get_banner(self, user: discord.Member) -> str:
        req = await self.bot.http.request(discord.http.Route("GET", "/users/{uid}", uid=user.id))
        banner_id = req["banner"]
        if banner_id:
            banner_url = f"https://cdn.discordapp.com/banners/{user.id}/{banner_id}?size=1024"
            return banner_url

    @commands.command(name="stars", aliases=["givestar", "addstar", "thanks"])
    @commands.guild_only()
    async def give_star(self, ctx: commands.Context, *, user: discord.Member):
        """
        Reward a good noodle
        Give a star to a user for being a good noodle
        """
        now = datetime.datetime.now()
        user_id = str(user.id)
        star_giver = str(ctx.author.id)
        guild_id = ctx.guild.id
        if guild_id not in self.data:
            return await ctx.send(_("Cache not loaded yet, wait a few more seconds."))
        if ctx.author == user:
            return await ctx.send(_("You can't give stars to yourself!"))
        if user.bot:
            return await ctx.send(_("You can't give stars to a bot!"))
        if guild_id not in self.stars:
            self.stars[guild_id] = {}
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
                msg = _(f"You need to wait **{tstring}** before you can give more stars!")
                return await ctx.send(msg)
        mention = self.data[guild_id]["mention"]
        users = self.data[guild_id]["users"]
        if user_id not in users:
            return await ctx.send(_("No data available for that user yet!"))
        self.data[guild_id]["users"][user_id]["stars"] += 1
        if mention:
            await ctx.send(_(f"You just gave a star to {user.mention}!"))
        else:
            await ctx.send(_(f"You just gave a star to **{user.name}**!"))

    # For testing purposes
    @commands.command(name="mocklvl", hidden=True)
    async def get_lvl_test(self, ctx, *, user: discord.Member = None):
        """Test levelup image gen"""
        if not user:
            user = ctx.author
        banner = await self.get_banner(user)
        color = str(user.colour)
        color = hex_to_rgb(color)
        if DPY2:
            pfp = user.avatar.url if user.avatar else None
        else:
            pfp = user.avatar_url
        args = {
            'bg_image': banner,
            'profile_image': pfp,
            'level': 69,
            'color': color,
        }
        img = await self.gen_levelup_img(args)
        temp = BytesIO()
        temp.name = f"{ctx.author.id}.webp"
        img.save(temp, format="WEBP")
        temp.seek(0)
        file = discord.File(temp)
        await ctx.send(file=file)

    @commands.group(name="myprofile", aliases=["mypf", "pfset"])
    @commands.guild_only()
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
            name = user["colors"]["name"]
            stat = user["colors"]["stat"]
            levelbar = user["colors"]["levelbar"]

            desc = f"`Profile Size:    `{full}\n" \
                   f"`Name Color:      `{name}\n" \
                   f"`Stat Color:      `{stat}\n" \
                   f"`Level Bar Color: `{levelbar}\n" \
                   f"`Background URL:  `{bg}"

            em = discord.Embed(
                title="Your Profile Settings",
                description=_(desc),
                color=ctx.author.color
            )
            if bg and bg != "random":
                em.set_image(url=bg)
            await ctx.send(embed=em)

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

    @set_profile.command(name="namecolor", aliases=["name"])
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
            return await ctx.send(
                _("That is an invalid color, please use a valid integer color code or hex color."))
        try:
            embed = discord.Embed(
                description="This is the color you chose",
                color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2])
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(_(f"Failed to set color, the following error occurred:\n{box(str(e), lang='python')}"))
            return
        self.data[ctx.guild.id]["users"][user_id]["colors"]["name"] = hex_color
        await ctx.tick()

    @set_profile.command(name="statcolor", aliases=["stat"])
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
            return await ctx.send(
                _("That is an invalid color, please use a valid integer color code or hex color."))

        try:
            embed = discord.Embed(
                description="This is the color you chose",
                color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2])
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(_(f"Failed to set color, the following error occurred:\n{box(str(e), lang='python')}"))
            return
        self.data[ctx.guild.id]["users"][user_id]["colors"]["stat"] = hex_color
        await ctx.tick()

    @set_profile.command(name="levelbar", aliases=["lvlbar", "bar"])
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
            return await ctx.send(
                _("That is an invalid color, please use a valid integer color code or hex color."))

        try:
            embed = discord.Embed(
                description="This is the color you chose",
                color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2])
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(_(f"Failed to set color, the following error occurred:\n{box(str(e), lang='python')}"))
            return
        self.data[ctx.guild.id]["users"][user_id]["colors"]["levelbar"] = hex_color
        await ctx.tick()

    @set_profile.command(name="background", aliases=["bg"])
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

        Leave image_url blank to reset back to randomized default profile backgrounds
        Set image_url as `random` to have a randomized background each time
        """
        if not self.data[ctx.guild.id]["usepics"]:
            return await ctx.send(_("Image profiles are disabled on this server, this setting has no effect"))

        users = self.data[ctx.guild.id]["users"]
        user_id = str(ctx.author.id)
        if user_id not in users:
            self.init_user(ctx.guild.id, user_id)

        # If image url is given, run some checks
        if image_url and image_url != "random":
            if not await self.valid_url(ctx, image_url):
                return
        else:
            if ctx.message.attachments:
                image_url = ctx.message.attachments[0].url
                if not await self.valid_url(ctx, image_url):
                    return

        if image_url:
            self.data[ctx.guild.id]["users"][user_id]["background"] = image_url
            if image_url == "random":
                await ctx.send("Your profile background will be randomized each time you run the profile command!")
            else:
                await ctx.send("Your image has been set!")
        else:
            self.data[ctx.guild.id]["users"][user_id]["background"] = None
            await ctx.send(_("Your background has been removed since you did not specify a url!"))

    @commands.command(name="pf")
    @commands.guild_only()
    async def get_profile(self, ctx: commands.Context, *, user: discord.Member = None):
        """View your profile"""
        can_send_attachments = ctx.channel.permissions_for(ctx.guild.me).attach_files
        gid = ctx.guild.id
        if gid not in self.data:
            await self.initialize()
        conf = self.data[gid]
        usepics = conf["usepics"]
        if usepics and not can_send_attachments:
            return await ctx.send(_("I don't have permission to send attachments to this channel."))
        users = conf["users"]
        mention = conf["mention"]
        if not user:
            user = ctx.author
        if user.bot:
            return await ctx.send("Bots can't have profiles!")
        user_id = str(user.id)
        if user_id not in users:
            return await ctx.send("No information available yet!")

        bal = await bank.get_balance(ctx.author)
        currency_name = await bank.get_currency_name(ctx.guild)

        if DPY2:
            pfp = user.avatar.url if user.avatar else None
        else:
            pfp = user.avatar_url

        role_icon = user.top_role.display_icon if DPY2 else None

        full = users[user_id]["full"]

        pos = await get_user_position(conf, user_id)
        position = "{:,}".format(pos["p"])  # int format
        percentage = pos["pr"]  # Float

        stats = await get_user_stats(conf, user_id)
        level = stats["l"]  # Int
        messages = "{:,}".format(stats["m"])  # Int format
        voice = stats["v"]  # Minutes at this point
        xp = stats["xp"]  # Int
        goal = stats["goal"]  # Int
        progress = f'{"{:,}".format(xp)}/{"{:,}".format(goal)}'
        lvlbar = stats["lb"]  # Str
        emoji = stats["e"]  # Str
        prestige = stats["pr"]  # Int
        bg = stats["bg"]  # Str
        stars = "{:,}".format(stats["stars"]) if stats["stars"] else 0

        if not usepics:
            embed = await profile_embed(
                user,
                position,
                percentage,
                level,
                messages,
                voice,
                progress,
                lvlbar,
                emoji["str"] if emoji and isinstance(emoji, dict) else None,
                prestige,
                stars,
                bal,
                currency_name,
                role_icon
            )
            try:
                await ctx.reply(embed=embed, mention_author=mention)
            except discord.HTTPException:
                await ctx.send(embed=embed)
        else:
            async with ctx.typing():
                if bg:
                    banner = bg
                else:
                    banner = await self.get_banner(user)

                if str(user.colour) == "#000000":  # Don't use default color for circle
                    basecolor = hex_to_rgb(str(discord.Color.random()))
                else:
                    basecolor = hex_to_rgb(str(user.colour))

                colors = users[user_id]["colors"]
                namecolor = hex_to_rgb(colors["name"]) if colors["name"] else None
                statcolor = hex_to_rgb(colors["stat"]) if colors["stat"] else None
                barcolor = hex_to_rgb(colors["levelbar"]) if colors["levelbar"] else None

                colors = {
                    "base": basecolor,
                    "name": namecolor,
                    "stat": statcolor,
                    "levelbar": barcolor
                }

                args = {
                    'bg_image': banner,  # Background image link
                    'profile_image': pfp,  # User profile picture link
                    'level': level,  # User current level
                    'current_xp': 0,  # Current level minimum xp
                    'user_xp': xp,  # User current xp
                    'next_xp': goal,  # xp required for next level
                    'user_position': position,  # User position in leaderboard
                    'user_name': user.name,  # username with discriminator
                    'user_status': str(user.status).strip(),  # User status eg. online, offline, idle, streaming, dnd
                    'colors': colors,  # User's color
                    'messages': messages,
                    'voice': voice,
                    'prestige': prestige,
                    'emoji': emoji["url"] if emoji and isinstance(emoji, dict) else None,
                    'stars': stars,
                    'balance': bal,
                    'currency': currency_name,
                    'role_icon': role_icon
                }

                now = datetime.datetime.now()
                if gid not in self.profiles:
                    self.profiles[gid] = {}

                if user_id not in self.profiles[gid]:
                    file_obj = await self.gen_profile_img(args, full)
                    self.profiles[gid][user_id] = {"file": file_obj, "last": now}

                last = self.profiles[gid][user_id]["last"]
                td = (now - last).total_seconds()
                if td > self.cache_seconds:
                    file_obj = await self.gen_profile_img(args, full)
                    self.profiles[gid][user_id]["file"] = file_obj
                    self.profiles[gid][user_id]["last"] = now
                else:
                    file_obj = self.profiles[gid][user_id]["file"]

                if not file_obj:
                    file_obj = await self.gen_profile_img(args, full)
                    self.profiles[gid][user_id] = {"file": file_obj, "last": now}

                # If file_obj is STILL None
                if not file_obj:
                    msg = f"Something went wrong while generating your profile image!\n" \
                          f"Image may be returning `None` if it takes longer than 60 seconds to generate.\n" \
                          f"**Debug Data**\n{box(json.dumps(args, indent=2))}"
                    return await ctx.send(msg)

                temp = BytesIO()
                file_obj.save(temp, format="WEBP")
                temp.name = f"{ctx.author.id}.webp"
                temp.seek(0)
                file = discord.File(temp)
                if not file:
                    return await ctx.send(f"Failed to generate profile image :( try again in a bit")
                try:
                    await ctx.reply(file=file, mention_author=mention)
                except Exception as e:
                    if "In message_reference: Unknown message" not in str(e):
                        log.error(f"Failed to send profile pic: {e}")
                    try:
                        temp = BytesIO()
                        file_obj.save(temp, format="WEBP")
                        temp.name = f"{ctx.author.id}.webp"
                        temp.seek(0)
                        file = discord.File(temp)
                        if mention:
                            await ctx.send(ctx.author.mention, file=file)
                        else:
                            await ctx.send(file=file)
                    except Exception as e:
                        log.error(f"Failed AGAIN to send profile pic: {e}")
                    await asyncio.sleep(5)

    @commands.command(name="prestige")
    @commands.guild_only()
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
            msg = f"**You are not eligible to prestige yet!**\n" \
                  f"`Your level:     `{current_level}\n" \
                  f"`Required Level: `{required_level}"
            embed = discord.Embed(
                description=_(msg),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if pending_prestige not in prestige_data:
            return await ctx.send(_(f"Prestige level {pending_prestige} has not been set yet!"))

        role_id = prestige_data[pending_prestige]["role"]
        role = ctx.guild.get_role(role_id) if role_id else None
        emoji = prestige_data[pending_prestige]["emoji"]
        if perms and role:
            try:
                await ctx.author.add_roles(role)
            except discord.Forbidden:
                await ctx.send(_(f"I do not have the proper permissions to assign you the {role.mention} role"))

        current_xp = user["xp"]
        xp_at_prestige = get_xp(required_level, conf["base"], conf["exp"])
        leftover_xp = current_xp - xp_at_prestige if current_xp > xp_at_prestige else 0
        newlevel = get_level(leftover_xp, conf["base"], conf["exp"]) if leftover_xp > 0 else 1

        self.data[ctx.guild.id]["users"][user_id]["prestige"] = int(pending_prestige)
        self.data[ctx.guild.id]["users"][user_id]["emoji"] = emoji
        self.data[ctx.guild.id]["users"][user_id]["level"] = newlevel
        self.data[ctx.guild.id]["users"][user_id]["xp"] = leftover_xp
        embed = discord.Embed(
            description=f"You have reached Prestige {pending_prestige}!",
            color=ctx.author.color
        )
        await ctx.send(embed=embed)

        # Then remove old prestige role if autoremove is toggled
        if prestige > 0 and not conf["stackprestigeroles"]:
            if str(prestige) in prestige_data:
                role_id = prestige_data[str(prestige)]["role"]
                role = ctx.guild.get_role(role_id)
                if role and perms:
                    await ctx.author.remove_roled(role)

    @commands.command(name="lvltop", aliases=["topstats", "membertop", "topranks"])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        """View the Leaderboard"""
        conf = self.data[ctx.guild.id]
        base = conf["base"]
        exp = conf["exp"]
        embeds = []
        prestige_req = conf["prestige"]
        leaderboard = {}
        total_messages = 0
        total_voice = 0  # Seconds
        for user, data in conf["users"].items():
            prestige = data["prestige"]
            xp = int(data["xp"])
            if prestige:
                add_xp = get_xp(prestige_req, base, exp)
                xp = int(xp + (prestige * add_xp))
            if xp > 0:
                leaderboard[user] = xp
            messages = data["messages"]
            voice = data["voice"]
            total_voice += voice
            total_messages += messages
        if not leaderboard:
            return await ctx.send(_("No user data yet!"))
        voice = time_formatter(total_voice)
        sorted_users = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)

        # Get your place in the LB
        you = ""
        for i in sorted_users:
            uid = i[0]
            if str(uid) == str(ctx.author.id):
                i = sorted_users.index(i)
                you = f"You: {i + 1}/{len(sorted_users)}\n"

        pages = math.ceil(len(sorted_users) / 10)
        start = 0
        stop = 10
        for p in range(pages):
            title = f"**Total Messages:** `{'{:,}'.format(total_messages)}`\n" \
                    f"**Total VoiceTime:** `{voice}`\n"
            if stop > len(sorted_users):
                stop = len(sorted_users)
            table = []
            for i in range(start, stop, 1):
                label = i + 1
                uid = sorted_users[i][0]
                user = ctx.guild.get_member(int(uid))
                if user:
                    user = user.name
                else:
                    user = uid
                xp = sorted_users[i][1]
                xptext = str(xp)
                if xp > 1000:
                    xptext = f"{round(xp / 1000, 1)}K"
                if xp > 1000000:
                    xptext = f"{round(xp / 1000000, 1)}M"
                level = get_level(int(xp), base, exp)
                level = f"{level}"
                table.append([label, f"{level}", xptext, user])

            headers = ["#", "Lvl", "XP", "Name"]
            msg = tabulate.tabulate(
                tabular_data=table,
                headers=headers,
                tablefmt="presto",
                numalign="left",
                stralign="left"
            )
            embed = discord.Embed(
                title="LevelUp Leaderboard",
                description=f"{_(title)}{box(msg, lang='python')}",
                color=discord.Color.random()
            )
            if DPY2:
                if ctx.guild.icon:
                    embed.set_thumbnail(url=ctx.guild.icon.url)
            else:
                embed.set_thumbnail(url=ctx.guild.icon_url)

            if you:
                embed.set_footer(text=_(f"Pages {p + 1}/{pages} ｜ {you}"))
            else:
                embed.set_footer(text=_(f"Pages {p + 1}/{pages}"))
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

    @commands.command(name="startop", aliases=["starlb"])
    @commands.guild_only()
    async def star_leaderboard(self, ctx: commands.Context):
        """View the star leaderboard"""
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

        pages = math.ceil(len(sorted_users) / 10)
        start = 0
        stop = 10
        startotal = "{:,}".format(total_stars)
        for p in range(pages):
            title = f"**Star Leaderboard**\n" \
                    f"**Total ⭐'s: {startotal}**\n"
            if stop > len(sorted_users):
                stop = len(sorted_users)
            table = []
            for i in range(start, stop, 1):
                uid = sorted_users[i][0]
                user = ctx.guild.get_member(int(uid))
                if user:
                    user = user.name
                else:
                    user = uid
                stars = sorted_users[i][1]
                stars = f"{stars} ⭐"
                table.append([stars, user])
            data = tabulate.tabulate(table, tablefmt="presto", colalign=("right",))
            embed = discord.Embed(
                description=f"{_(title)}{box(data, lang='python')}",
                color=discord.Color.random()
            )
            if DPY2:
                if ctx.guild.icon:
                    embed.set_thumbnail(url=ctx.guild.icon.url)
            else:
                embed.set_thumbnail(url=ctx.guild.icon_url)

            if you:
                embed.set_footer(text=_(f"Pages {p + 1}/{pages} ｜ {you}"))
            else:
                embed.set_footer(text=_(f"Pages {p + 1}/{pages}"))
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
