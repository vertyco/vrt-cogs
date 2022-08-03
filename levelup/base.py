import asyncio
import datetime
import logging
import math
import random

import discord
import tabulate
import validators
from redbot.core import commands
from redbot.core.i18n import Translator
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
    from .bmenu import menu
    DEFAULT_CONTROLS = None
    DPY2 = True
else:
    from .menu import menu, DEFAULT_CONTROLS
    DPY2 = False

log = logging.getLogger("red.vrt.levelup.commands")
_ = Translator("LevelUp", __file__)


class UserCommands(commands.Cog):

    # Generate level up image
    async def gen_levelup_img(self, args: dict):
        task = self.bot.loop.run_in_executor(None, lambda: Generator().generate_levelup(**args))
        try:
            img = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            return None
        img.seek(0)
        file = discord.File(img)
        return file

    # Generate profile image
    async def gen_profile_img(self, args: dict):
        task = self.bot.loop.run_in_executor(None, lambda: Generator().generate_profile(**args))
        try:
            img = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            return None
        img.seek(0)
        file = discord.File(img)
        return file

    # Function to test a given URL and see if it's valid
    async def valid_url(self, ctx: commands.Context, image_url: str):
        valid = validators.url(image_url)
        if not valid:
            await ctx.send(_("Uh Oh, looks like that is not a valid URL"))
            return
        try:
            # Try running it through profile generator blind to see if it errors
            args = {'bg_image': image_url, 'profile_image': ctx.author.avatar_url}
            await self.bot.loop.run_in_executor(None, lambda: Generator().generate_profile(**args))
        except Exception as e:
            if "cannot identify image file" in str(e):
                await ctx.send(_("Uh Oh, looks like that is not a valid image"))
                return
            else:
                log.warning(f"background set failed: {e}")
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
        guild_id = str(ctx.guild.id)
        if ctx.author == user:
            return await ctx.send(_("You can't give stars to yourself!"))
        if user.bot:
            return await ctx.send(_("You can't give stars to a bot!"))
        if guild_id not in self.stars:
            self.stars[guild_id] = {}
        if star_giver not in self.stars[guild_id]:
            self.stars[guild_id][star_giver] = now
        else:
            cooldown = self.settings[guild_id]["starcooldown"]
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
        mention = await self.config.guild(ctx.guild).mention()
        async with self.config.guild(ctx.guild).all() as conf:
            users = conf["users"]
            if user_id not in users:
                return await ctx.send(_("No data available for that user yet!"))
            if "stars" not in users[user_id]:
                users[user_id]["stars"] = 1
            else:
                users[user_id]["stars"] += 1
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
        args = {
            'bg_image': banner,
            'profile_image': user.avatar_url,
            'level': 69,
            'color': color,
        }
        task = self.bot.loop.run_in_executor(None, lambda: Generator().generate_levelup(**args))
        try:
            img = await asyncio.wait_for(task, timeout=30)
        except asyncio.TimeoutError:
            return await ctx.send("Image took too long to generate, try again in a few.")
        img.seek(0)
        file = discord.File(img)
        await ctx.send(file=file)

    @commands.group(name="myprofile", aliases=["mypf", "pfset"])
    @commands.guild_only()
    async def set_profile(self, ctx: commands.Context):
        """Customize your profile"""
        pass

    @set_profile.command(name="namecolor", aliases=["name"])
    async def set_name_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your username

        Here is a link to google's color picker:
        https://g.co/kgs/V6jdXj
        """
        user_id = str(ctx.author.id)
        async with self.config.guild(ctx.guild).users() as users:
            if user_id not in users:
                return await ctx.send(_("You have no information stored about your account yet. Talk for a bit first"))
            user = users[user_id]
            rgb = hex_to_rgb(hex_color)
            try:
                embed = discord.Embed(
                    description="This is the color you chose",
                    color=discord.Color.from_rgb(rgb[0], rgb[1], rgb[2])
                )
                await ctx.send(embed=embed)
            except Exception as e:
                await ctx.send(_(f"Failed to set color, the following error occurred:\n{box(str(e), lang='python')}"))
                return
            if "colors" not in user:
                user["colors"] = {
                    "name": hex_color,
                    "stat": None
                }
            else:
                user["colors"]["name"] = hex_color
            await ctx.tick()

    @set_profile.command(name="statcolor", aliases=["stat"])
    async def set_stat_color(self, ctx: commands.Context, hex_color: str):
        """
        Set a hex color for your server stats

        Here is a link to google's color picker:
        https://g.co/kgs/V6jdXj
        """
        user_id = str(ctx.author.id)
        async with self.config.guild(ctx.guild).users() as users:
            if user_id not in users:
                return await ctx.send(_("You have no information stored about your account yet. Talk for a bit first"))
            user = users[user_id]
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
            if "colors" not in user:
                user["colors"] = {
                    "name": None,
                    "stat": hex_color
                }
            else:
                user["colors"]["stat"] = hex_color
            await ctx.tick()

    @set_profile.command(name="background", aliases=["bg"])
    async def set_user_background(self, ctx: commands.Context, image_url: str = None):
        """
        Set a background for your profile

        This will override your profile banner as the background

        **WARNING**
        Profile backgrounds are wide landscapes (900 by 240 pixels) and using a portrait image will be skewed

        Tip: Googling "dual monitor backgrounds" gives good results for the right images

        Here are some good places to look.
        [dualmonitorbackgrounds](https://www.dualmonitorbackgrounds.com/)
        [setaswall](https://www.setaswall.com/dual-monitor-wallpapers/)
        [pexels](https://www.pexels.com/photo/panoramic-photography-of-trees-and-lake-358482/)
        [teahub](https://www.teahub.io/searchw/dual-monitor/)
        """
        # If image url is given, run some checks
        if image_url:
            if not await self.valid_url(ctx, image_url):
                return
        else:
            if ctx.message.attachments:
                image_url = ctx.message.attachments[0].url
                if not await self.valid_url(ctx, image_url):
                    return
        user = ctx.author
        async with self.config.guild(ctx.guild).users() as users:
            if str(user.id) not in users:
                return await ctx.send(_("You aren't logged in the database yet, give it some time."))
            if image_url:
                users[str(user.id)]["background"] = image_url
                await ctx.send("Your image has been set!")
            else:
                if "background" in users[str(user.id)]:
                    if not users[str(user.id)]["background"]:
                        await ctx.send_help()
                    else:
                        users[str(user.id)]["background"] = None
                        await ctx.send(_("Your background has been removed since you did not specify a url!"))
                else:
                    await ctx.send_help()

    @commands.command(name="pf")
    @commands.cooldown(1, 30, commands.BucketType.user)
    @commands.guild_only()
    async def get_profile(self, ctx: commands.Context, *, user: discord.Member = None):
        """View your profile"""
        can_send_attachments = ctx.channel.permissions_for(ctx.guild.me).attach_files
        conf = await self.config.guild(ctx.guild).all()
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
        pfp = user.avatar_url
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
        lvlpercent = stats["lp"]  # Int
        emoji = stats["e"]  # Str
        prestige = stats["pr"]  # Int
        bg = stats["bg"]  # Str
        if "stars" in stats:
            stars = "{:,}".format(stats["stars"])
        else:
            stars = 0
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
                lvlpercent,
                emoji,
                prestige,
                stars
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
                    circlecolor = hex_to_rgb(str(discord.Color.random()))
                else:
                    circlecolor = hex_to_rgb(str(user.colour))

                if "colors" in users[user_id]:
                    namecolor = users[user_id]["colors"]["name"]
                    if namecolor:
                        namecolor = hex_to_rgb(namecolor)
                    else:
                        namecolor = circlecolor

                    statcolor = users[user_id]["colors"]["stat"]
                    if statcolor:
                        statcolor = hex_to_rgb(statcolor)
                    else:
                        statcolor = circlecolor
                else:
                    namecolor = circlecolor
                    statcolor = circlecolor

                colors = {
                    "name": namecolor,
                    "stat": statcolor,
                    "circle": circlecolor
                }
                args = {
                    'bg_image': banner,  # Background image link
                    'profile_image': pfp,  # User profile picture link
                    'level': level,  # User current level
                    'current_xp': 0,  # Current level minimum xp
                    'user_xp': xp,  # User current xp
                    'next_xp': goal,  # xp required for next level
                    'user_position': position,  # User position in leaderboard
                    'user_name': user.name,  # user name with descriminator
                    'user_status': user.status,  # User status eg. online, offline, idle, streaming, dnd
                    'colors': colors,  # User's color
                    'messages': messages,
                    'voice': voice,
                    'prestige': prestige,
                    'stars': stars
                }

                file = await self.gen_profile_img(args)
                if not file:
                    return await ctx.send(f"Failed to generate profile image :( try again in a bit")
                try:
                    await ctx.reply(file=file, mention_author=mention)
                except Exception as e:
                    log.error(f"Failed to send profile pic: {e}")
                    await asyncio.sleep(5)
                    try:
                        await ctx.reply(file=file, mention_author=mention)
                    except Exception as e:
                        log.error(f"Failed again to send profile pic: {e}")
                        await ctx.send(f"Failed to send profile pic to discord. Try again in a few minutes.")

    @commands.command(name="prestige")
    @commands.guild_only()
    async def prestige_user(self, ctx: commands.Context):
        """
        Prestige your rank!
        Once you have reached this servers prestige level requirement, you can
        reset your level and experience to gain a prestige level and any perks associated with it
        """
        conf = await self.config.guild(ctx.guild).all()
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
        prestige = user["prestige"]
        pending_prestige = str(prestige + 1)
        # First add new prestige role
        if current_level >= required_level:
            if pending_prestige in prestige_data:
                role = prestige_data["role"]
                rid = role
                emoji = prestige_data["emoji"]
                if perms:
                    role = ctx.guild.get_role(role)
                    if role:
                        await ctx.author.add_roles(role)
                    else:
                        log.warning(f"Prestige {pending_prestige} role ID: {rid} no longer exists!")
                async with self.config.guild(ctx.guild).all() as conf:
                    conf[user_id]["prestige"] = pending_prestige
                    conf[user_id]["emoji"] = emoji
                    conf[user_id]["level"] = 1
                    conf[user_id]["xp"] = 0
            else:
                return await ctx.send(_(f"Prestige level {pending_prestige} has not been set yet!"))
        else:
            msg = f"**You are not eligible to prestige yet!**\n" \
                  f"`Your level:     `{current_level}\n" \
                  f"`Required Level: `{required_level}"
            embed = discord.Embed(
                description=_(msg),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # Then remove old prestige role if autoremove is toggled
        if prestige > 0 and conf["stackprestigeroles"]:
            if str(prestige) in prestige_data:
                role_id = prestige_data[str(prestige)]["role"]
                role = ctx.guild.get_role(role_id)
                if role and perms:
                    await ctx.author.remove_roled(role)

    @commands.command(name="lvltop", aliases=["topstats", "membertop", "topranks"])
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        """View the Leaderboard"""
        conf = await self.config.guild(ctx.guild).all()
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
        conf = await self.config.guild(ctx.guild).all()
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
