import asyncio
import datetime
import logging
import math
import random
import typing

import discord
from discord.ext import tasks
from redbot.core import commands, Config
from matplotlib import pyplot as plt
from .menus import menu, DEFAULT_CONTROLS
import io
from .generator import Generator
from .formatter import (
    hex_to_rgb,
    get_level,
    get_xp,
    get_user_position,
    get_user_stats,
    profile_embed,
)

log = logging.getLogger("red.vrt.levelup")


# CREDITS
# Thanks aikaterna#1393 and epic guy#0715 for the caching advice :)
# Used Fixator10#7133's Leveler cog to get a reference for what kinda settings a leveler cog might need!


class LevelUp(commands.Cog):
    """Local Discord Leveling System"""
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_guild = {
            "users": {},
            "levelroles": {},
            "ignoredchannels": [],  # Channels that dont gain XP
            "ignoredroles": [],  # Roles that dont gain XP
            "ignoredusers": [],  # Ignored users wont gain XP
            "prestige": 0,  # Level required to prestige, 0 is disabled
            "prestigedata": {},  # Prestige tiers, the role associated with them, and emoji for them
            "xp": [3, 6],  # Min/Max XP per message
            "voicexp": 2,  # XP per minute in voice
            "cooldown": 60,  # Only gives XP every 30 seconds
            "base": 100,  # Base denominator for level algorithm, higher takes longer to level
            "exp": 2,  # Exponent for level algorithm, higher is a more exponential/steeper curve
            "length": 0,  # Minimum length of message to be considered eligible for XP gain,
            "usepics": False,  # Use Pics instead of embeds for leveling, Embeds are default
            "autoremove": False,  # Remove previous role on level up
            "stackprestigeroles": True,  # Toggle whether to stack prestige roles
            "muted": True,  # Ignore XP while being muted in voice
            "solo": True,  # Ignore XP while in a voice chat alone
            "deafened": True,  # Ignore XP while deafened in a voice chat
            "invisible": True,  # Ignore XP while status is invisible in voice chat
            "notifydm": False,  # Toggle notify member of level up in DMs
            "mention": False,  # Toggle whether to mention the user
            "notifylog": None,  # Notify member of level up in a set channel
        }
        self.config.register_guild(**default_guild)

        # Guild id's as strings, user id's as strings
        self.settings = {}  # Cache settings
        self.cache = {}  # Dumps to config every 60 seconds
        self.lastmsg = {}  # Last sent message for users
        self.voice = {}  # Voice channel info

        # Cachey wakey dumpy wumpy loopy woopy
        self.cache_dumper.start()
        self.voice_checker.start()

    def cog_unload(self):
        self.cache_dumper.cancel()
        self.voice_checker.cancel()

    # Add a user to cache
    async def cache_user(self, guild: str, user: str):
        if guild not in self.cache:  # Alredy in init_settings but just in case
            self.cache[guild] = {}
        self.cache[guild][user] = {
            "xp": 0,
            "voice": 0,  # Seconds
            "messages": 0,
            "level": 0,
            "prestige": 0,
            "emoji": None
        }

    # Hacky way to get user banner, generate backdrop based on users color if they dont have one
    async def get_banner(self, user: discord.Member) -> str:
        req = await self.bot.http.request(discord.http.Route("GET", "/users/{uid}", uid=user.id))
        banner_id = req["banner"]
        if banner_id:
            banner_url = f"https://cdn.discordapp.com/banners/{user.id}/{banner_id}?size=1024"
        else:
            color = str(user.colour).strip("#")
            banner_url = f"https://singlecolorimage.com/get/{color}/400x100"
        return banner_url

    # Generate rinky dink profile image
    async def gen_profile_img(self, args: dict):

        def exe():
            image = Generator().generate_profile(**args)
            file = discord.File(fp=image, filename="image.png")
            return file

        profile = await self.bot.loop.run_in_executor(None, exe)
        return profile

    # Generate rinky dink level up image
    async def gen_levelup_img(self, args: dict):

        def exe():
            image = Generator().generate_levelup(**args)
            file = discord.File(fp=image, filename="image.png")
            return file

        lvlup = await self.bot.loop.run_in_executor(None, exe)
        return lvlup

    # Dump cache to config
    async def dump_cache(self):
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            if guild_id not in self.cache:
                continue
            if self.cache[guild_id]:  # If there is anything to cache
                conf = self.settings[guild_id]
                base = conf["base"]
                exp = conf["exp"]
                async with self.config.guild(guild).users() as users:
                    for user, data in self.cache[guild_id].items():
                        if user not in users:
                            users[user] = data
                        else:
                            users[user]["xp"] += data["xp"]
                            users[user]["voice"] += data["voice"]
                            users[user]["messages"] += data["messages"]
                        saved_level = users[user]["level"]
                        new_level = get_level(users[user]["xp"], base, exp)
                        if new_level > saved_level:
                            await self.level_up(guild, user, new_level)
                            users[user]["level"] = new_level
                self.cache[guild_id].clear()

    # User has leveled up, send message and check if any roles are associated with it
    async def level_up(self, guild: discord.guild, user: str, new_level: int):
        conf = self.settings[str(guild.id)]
        levelroles = conf["levelroles"]
        roleperms = guild.me.guild_permissions.manage_roles
        if not roleperms:
            log.warning(f"Bot can't manage roles in {guild.name}")
        autoremove = conf["autoremove"]
        dm = conf["notifydm"]
        mention = conf["mention"]
        channel = conf["notifylog"]
        usepics = conf["usepics"]
        member = guild.get_member(int(user))
        if not member:
            return
        # Send levelup messages
        if not usepics:
            if dm:
                await member.send(f"You have just reached level {new_level} in {guild.name}!")
            if channel:
                channel = guild.get_channel(channel)
                if mention:
                    person = member.mention
                else:
                    person = member.name
                color = member.colour
                pfp = member.avatar_url
                embed = discord.Embed(
                    description=f"**{person} has just reached level {new_level}!**",
                    color=color
                )
                embed.set_thumbnail(url=pfp)
                if channel:
                    send = channel.permissions_for(guild.me).send_messages
                    if send:
                        await channel.send(embed=embed)
                    else:
                        log.warning(f"Bot cant send LevelUp alert to log channel in {guild.name}")
        else:
            # Generate LevelUP Image
            banner = await self.get_banner(member)
            color = str(member.colour)
            color = hex_to_rgb(color)
            args = {
                'bg_image': banner,
                'profile_image': member.avatar_url,
                'level': new_level,
                'color': color,
            }
            if dm:
                file = await self.gen_levelup_img(args)
                await member.send(f"You just leveled up in {guild.name}!", file=file)
            if channel:
                channel = guild.get_channel(channel)
                if mention:
                    person = member.mention
                else:
                    person = member.name
                if channel:
                    send = channel.permissions_for(guild.me).send_messages
                    if send:
                        file = await self.gen_levelup_img(args)
                        await channel.send(f"**{person} just leveled up!**", file=file)
                    else:
                        log.warning(f"Bot cant send LevelUp alert to log channel in {guild.name}")

        # Role adding/removal
        if roleperms and levelroles:
            if str(new_level) in levelroles:
                role_id = levelroles[str(new_level)]
                role = guild.get_role(int(role_id))
                if not role:
                    return
                if role not in member.roles:
                    await member.add_roles(role)
            if new_level > 1 and autoremove:
                for role in member.roles:
                    for level, role_id in levelroles:
                        if int(level) < new_level and str(role.id) == str(role_id):
                            await member.remove_roles(role)

    # Cache main settings
    async def init_settings(self):
        for guild in self.bot.guilds:
            settings = await self.config.guild(guild).all()
            # Some of these dont get used yet in cache, just adding em for future sake
            self.settings[str(guild.id)] = {
                "levelroles": settings["levelroles"],
                "ignoredchannels": settings["ignoredchannels"],
                "ignoredroles": settings["ignoredroles"],
                "ignoredusers": settings["ignoredusers"],
                "prestige": settings["prestige"],
                "prestigedata": settings["prestigedata"],
                "xp": settings["xp"],
                "base": settings["base"],
                "exp": settings["exp"],
                "length": settings["length"],
                "usepics": settings["usepics"],
                "voicexp": settings["voicexp"],
                "cooldown": settings["cooldown"],
                "autoremove": settings["autoremove"],
                "stackprestige": settings["stackprestigeroles"],
                "muted": settings["muted"],
                "solo": settings["solo"],
                "deafened": settings["deafened"],
                "invisible": settings["invisible"],
                "notifydm": settings["notifydm"],
                "mention": settings["mention"],
                "notifylog": settings["notifylog"],
            }
            if str(guild.id) not in self.cache:
                self.cache[str(guild.id)] = {}

    @commands.Cog.listener("on_message")
    async def messages(self, message: discord.Message):
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # If message has no content for some reason?
        if not message:
            return
        return await self.message_handler(message)

    async def message_handler(self, message: discord.Message):
        now = datetime.datetime.now()
        guild = message.guild
        guild_id = str(guild.id)
        if guild_id not in self.cache:
            return
        user = str(message.author.id)
        conf = self.settings[guild_id]
        xpmin = int(conf["xp"][0])
        xpmax = int(conf["xp"][1]) + 1
        xp = random.choice(range(xpmin, xpmax))
        addxp = False
        if user not in self.cache[guild_id]:
            await self.cache_user(guild_id, user)
        if user not in self.lastmsg:
            self.lastmsg[user] = now
            addxp = True
        td = now - self.lastmsg[user]
        td = int(td.total_seconds())
        if td > conf["cooldown"]:
            addxp = True
        for role in message.author.roles:
            if role.id in conf["ignoredroles"]:
                addxp = False
        if message.channel.id in conf["ignoredchannels"]:
            addxp = False
        if int(user) in conf["ignoredusers"]:
            addxp = False
        if conf["length"]:  # Make sure message meets minimum length requirements
            if len(message.content) < conf["length"]:
                addxp = False
        if addxp:  # Give XP
            self.cache[guild_id][user]["xp"] += xp
        self.cache[guild_id][user]["messages"] += 1

    # Yoinked from aika's VoiceLogs for the most part
    @commands.Cog.listener()
    async def on_voice_state_update(
            self,
            member: discord.Member,
            before: discord.VoiceState,
            after: discord.VoiceState
    ):
        if before.channel == after.channel:
            return
        now = datetime.datetime.now()
        guild_id = str(member.guild.id)
        member_id = str(member.id)
        if guild_id not in self.voice:
            self.voice[guild_id] = {}
        if member_id not in self.voice[guild_id]:
            self.voice[guild_id][member_id] = now
        # User left channel
        if before.channel:
            self.voice[guild_id][member_id] = None
        # User joined channel
        if after.channel:
            self.voice[guild_id][member_id] = now

    async def check_voice(self):
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            conf = self.settings[guild_id]
            xp_per_minute = conf["voicexp"]
            if guild_id not in self.voice:
                self.voice[guild_id] = {}
                continue
            if not self.voice[guild_id]:
                continue
            for user, ts in self.voice[guild_id].items():
                if not ts:
                    continue
                member = guild.get_member(int(user))
                if not member:
                    continue
                voice_state = member.voice
                if not voice_state:  # User isn't really in that voice channel anymore
                    continue
                if user not in self.cache[guild_id]:
                    await self.cache_user(guild_id, user)
                now = datetime.datetime.now()
                td = now - ts
                td = int(td.total_seconds())
                xp_to_give = (td / 60) * xp_per_minute
                addxp = True
                if conf["muted"] and voice_state.self_mute:
                    addxp = False
                if conf["deafened"] and voice_state.self_deaf:
                    addxp = False
                if conf["invisible"] and member.status.name == "offline":
                    addxp = False
                if len(voice_state.channel.members) == 1:
                    addxp = False
                for role in member.roles:
                    if role.id in conf["ignoredroles"]:
                        addxp = False
                if int(user) in conf["ignoredusers"]:
                    addxp = False
                if voice_state.channel.id in conf["ignoredchannels"]:
                    addxp = False
                if addxp:
                    self.cache[guild_id][user]["xp"] += xp_to_give
                self.cache[guild_id][user]["voice"] += td
                self.voice[guild_id][user] = now

    @tasks.loop(seconds=10)
    async def voice_checker(self):
        await self.check_voice()

    @voice_checker.before_loop
    async def before_voice_checker(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)

    @tasks.loop(seconds=30)
    async def cache_dumper(self):
        await self.dump_cache()

    @cache_dumper.before_loop
    async def before_dumper(self):
        await self.bot.wait_until_red_ready()
        await self.init_settings()
        await asyncio.sleep(30)

    @commands.group(name="levelset", aliases=["lset"])
    @commands.admin()
    @commands.guild_only()
    async def lvl_group(self, ctx: commands.Context):
        """Access LevelUP setting commands"""
        pass

    @lvl_group.command(name="seelevels")
    async def see_levels(self, ctx: commands.Context):
        """View the first 20 levels using the current algorithm to test experience curve"""
        conf = await self.config.guild(ctx.guild).all()
        base = conf["base"]
        exp = conf["exp"]
        msg = ""
        x = []
        y = []
        for i in range(21):
            xp = get_xp(i, base, exp)
            msg += f"`Level {i}: `{xp} XP Needed\n"
            x.append(i)
            y.append(xp)
        with plt.style.context("dark_background"):
            plt.plot(x, y, color="xkcd:green", label="Total", linewidth=0.7)
            plt.xlabel(f"Level", fontsize=10)
            plt.ylabel(f"Experience", fontsize=10)
            plt.title("XP Curve")
            plt.grid(axis="y")
            plt.grid(axis="x")
            result = io.BytesIO()
            plt.savefig(result, format="png", dpi=200)
            plt.close()
            result.seek(0)
            file = discord.File(result, filename="lvlexample.png")
            img = "attachment://lvlexample.png"
        embed = discord.Embed(
            title="Level Example",
            description=f"**Base Multiplier:** {base}\n"
                        f"**Exp Multiplier:** {exp}\n"
                        f"XPForALevel = Base * Level^Exp\n"
                        f"Level = Inverse of that\n"
                        f"{msg}",
            color=discord.Color.random()
        )
        embed.set_image(url=img)
        await ctx.send(embed=embed, file=file)

    @lvl_group.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View all LevelUP settings"""
        conf = await self.config.guild(ctx.guild).all()
        levelroles = conf["levelroles"]
        igchannels = conf["ignoredchannels"]
        igroles = conf["ignoredroles"]
        igusers = conf["ignoredusers"]
        prestige = conf["prestige"]
        pdata = conf["prestigedata"]
        stacking = conf["stackprestigeroles"]
        xp = conf["xp"]
        voicexp = conf["voicexp"]
        cooldown = conf["cooldown"]
        base = conf["base"]
        exp = conf["exp"]
        length = conf["length"]
        autoremove = conf["autoremove"]
        muted = conf["muted"]
        solo = conf["solo"]
        deafended = conf["deafened"]
        invisible = conf["invisible"]
        notifydm = conf["notifydm"]
        mention = conf["mention"]
        notifylog = ctx.guild.get_channel(conf["notifylog"])
        if not notifylog:
            notifylog = conf["notifylog"]
        else:
            notifylog = notifylog.mention
        msg = f"**Messages**\n" \
              f"`Message XP:       `{xp[0]}-{xp[1]}\n" \
              f"`Min Msg Length:   `{length}\n" \
              f"`Cooldown:         `{cooldown} seconds\n" \
              f"**Voice**\n" \
              f"`Voice XP:         `{voicexp} per minute\n" \
              f"`Ignore Muted:     `{muted}\n" \
              f"`Ignore Solo:      `{solo}\n" \
              f"`Ignore Deafened:  `{deafended}\n" \
              f"`Ignore Invisible: `{invisible}\n" \
              f"`AutoRemove Roles: `{autoremove}\n" \
              f"**Level Algorithm**\n" \
              f"`Base Multiplier:  `{base}\n" \
              f"`Exp Multiplier:   `{exp}\n" \
              f"**LevelUps**\n" \
              f"`Notify in DMs:    `{notifydm}\n" \
              f"`Mention User:     `{mention}\n" \
              f"`LevelUp Channel:  `{notifylog}\n"
        if levelroles:
            msg += "**Levels**\n"
            for level, role_id in levelroles:
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                msg += f"`Level {level}: `{role}\n"
        if igchannels:
            msg += "**Ignored Channels\n"
            for channel_id in igchannels:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    channel = channel.mention
                else:
                    channel = channel_id
                msg += f"{channel}\n"
        if igroles:
            msg += "**Ignored Roles**\n"
            for role_id in igroles:
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                msg += f"{role}\n"
        if igusers:
            msg += "**Ignored Users**\n"
            for user_id in igusers:
                user = ctx.guild.get_member(user_id)
                if user:
                    user = user.mention
                else:
                    user = user_id
                msg += f"{user}\n"
        if prestige and pdata:
            msg += "**Prestige**\n" \
                   f"`Stack Roles: `{stacking}\n" \
                   f"`Level Req:  `{prestige}\n"
            for level, data in pdata.items():
                role_id = data["role"]
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                emoji = data["emoji"]
                msg += f"`Prestige {level}: `{role} - {emoji}\n"
        embed = discord.Embed(
            title="LevelUp Settings",
            description=msg,
            color=discord.Color.random()
        )
        await ctx.send(embed=embed)

    @lvl_group.command(name="fullreset")
    @commands.is_owner()
    async def reset_all(self, ctx: commands.Context):
        """(Bot Owner Only) Reset entire cog user data"""
        for guild in self.bot.guilds:
            await self.config.guild(guild).users.set({})
            await ctx.tick()

    @lvl_group.command(name="reset")
    @commands.guildowner()
    async def reset_guild(self, ctx: commands.Context):
        """(Guild Owner Only) Reset user data"""
        await self.config.guild(ctx.guild).users.set({})
        await ctx.tick()

    @lvl_group.command(name="xp")
    async def set_xp(self, ctx: commands.Context, min_xp: int = 3, max_xp: int = 6):
        """Set the Min and Max amount of XP that a message can gain"""
        xp = [min_xp, max_xp]
        await self.config.guild(ctx.guild).xp.set(xp)
        await ctx.send(f"Message XP range has been set to {min_xp} - {max_xp} per valid message")
        await self.init_settings()

    @lvl_group.command(name="voicexp")
    async def set_voice_xp(self, ctx: commands.Context, voice_xp: int):
        """Set the amount of XP gained per minute in a voice channel (default is 2)"""
        await self.config.guild(ctx.guild).voicexp.set(voice_xp)
        await ctx.tick()
        await self.init_settings()

    @lvl_group.command(name="cooldown")
    async def set_cooldown(self, ctx: commands.Context, cooldown: int):
        """
        Set the cooldown threshold for message XP to be gained

        When a user sends a message they will have to wait X seconds before their message
        counts as XP gained
        """
        await self.config.guild(ctx.guild).cooldown.set(cooldown)
        await ctx.tick()
        await self.init_settings()

    @lvl_group.command(name="base")
    async def set_base(self, ctx: commands.Context, base_multiplier: int):
        """
        Set the base multiplier for the leveling algorithm

        Affects leveling on a more linear scale(higher values makes leveling take longer)
        """
        await self.config.guild(ctx.guild).base.set(base_multiplier)
        await ctx.tick()
        await self.init_settings()

    @lvl_group.command(name="exp")
    async def set_exp(self, ctx: commands.Context, exponent_multiplier: typing.Union[int, float]):
        """
        Set the exponent multiplier for the leveling algorithm

        Affects leveling on an exponential scale(higher values makes leveling take exponentially longer)
        """
        await self.config.guild(ctx.guild).exp.set(exponent_multiplier)
        await ctx.tick()
        await self.init_settings()

    @lvl_group.command(name="length")
    async def set_length(self, ctx: commands.Context, minimum_length: int):
        """
        Set the minimum length a message must be to count towards XP gained

        Set to 0 to disable
        """
        await self.config.guild(ctx.guild).length.set(minimum_length)
        await ctx.tick()
        await self.init_settings()

    @lvl_group.command(name="embeds")
    async def toggle_embeds(self, ctx: commands.Context):
        """Toggle whether to use embeds or generated pics for leveling"""
        usepics = await self.config.guild(ctx.guild).usepics()
        if usepics:
            await self.config.guild(ctx.guild).usepics.set(False)
            await ctx.send("LevelUp will now use embeds instead of generated images")
        else:
            await self.config.guild(ctx.guild).usepics.set(True)
            await ctx.send("LevelUp will now use generated images instead of embeds")
        await self.init_settings()

    @lvl_group.command(name="autoremove")
    async def toggle_autoremove(self, ctx: commands.Context):
        """Toggle automatic removal of previous level roles"""
        autoremove = await self.config.guild(ctx.guild).autoremove()
        if autoremove:
            await self.config.guild(ctx.guild).autoremove.set(False)
            await ctx.send("Automatic role removal **Disabled**")
        else:
            await self.config.guild(ctx.guild).autoremove.set(True)
            await ctx.send("Automatic role removal **Enabled**")
        await self.init_settings()

    @lvl_group.command(name="muted")
    async def ignore_muted(self, ctx: commands.Context):
        """Toggle whether self-muted users in a voice channel can gain voice XP"""
        muted = await self.config.guild(ctx.guild).muted()
        if muted:
            await self.config.guild(ctx.guild).muted.set(False)
            await ctx.send("Self-Muted users can now gain XP while in a voice channel")
        else:
            await self.config.guild(ctx.guild).muted.set(True)
            await ctx.send("Self-Muted users can no longer gain XP while in a voice channel")
        await self.init_settings()

    @lvl_group.command(name="solo")
    async def ignore_solo(self, ctx: commands.Context):
        """Toggle whether solo users in a voice channel can gain voice XP"""
        solo = await self.config.guild(ctx.guild).solo()
        if solo:
            await self.config.guild(ctx.guild).solo.set(False)
            await ctx.send("Solo users can now gain XP while in a voice channel")
        else:
            await self.config.guild(ctx.guild).solo.set(True)
            await ctx.send("Solo users can no longer gain XP while in a voice channel")
        await self.init_settings()

    @lvl_group.command(name="deafened")
    async def ignore_deafened(self, ctx: commands.Context):
        """Toggle whether deafened users in a voice channel can gain voice XP"""
        deafened = await self.config.guild(ctx.guild).deafened()
        if deafened:
            await self.config.guild(ctx.guild).deafened.set(False)
            await ctx.send("Deafened users can now gain XP while in a voice channel")
        else:
            await self.config.guild(ctx.guild).deafened.set(True)
            await ctx.send("Deafened users can no longer gain XP while in a voice channel")
        await self.init_settings()

    @lvl_group.command(name="invisible")
    async def ignore_invisible(self, ctx: commands.Context):
        """Toggle whether invisible users in a voice channel can gain voice XP"""
        invisible = await self.config.guild(ctx.guild).invisible()
        if invisible:
            await self.config.guild(ctx.guild).invisible.set(False)
            await ctx.send("Invisible users can now gain XP while in a voice channel")
        else:
            await self.config.guild(ctx.guild).invisible.set(True)
            await ctx.send("Invisible users can no longer gain XP while in a voice channel")
        await self.init_settings()

    @lvl_group.command(name="dm")
    async def toggle_dm(self, ctx: commands.Context):
        """Toggle whether LevelUp messages are DM'd to the user"""
        notifydm = await self.config.guild(ctx.guild).notifydm()
        if notifydm:
            await self.config.guild(ctx.guild).notifydm.set(False)
            await ctx.send("Users will no longer be DM'd when they level up")
        else:
            await self.config.guild(ctx.guild).notifydm.set(True)
            await ctx.send("Users will now be DM'd when they level up")
        await self.init_settings()

    @lvl_group.command(name="mention")
    async def toggle_mention(self, ctx: commands.Context):
        """Toggle whether the user in mentioned in LevelUp messages"""
        mention = await self.config.guild(ctx.guild).mention()
        if mention:
            await self.config.guild(ctx.guild).mention.set(False)
            await ctx.send("Users will no longer be mentioned when they level up")
        else:
            await self.config.guild(ctx.guild).mention.set(True)
            await ctx.send("Users will now be mentioned when they level up")
        await self.init_settings()

    @lvl_group.command(name="levelchannel")
    async def set_level_channel(self, ctx: commands.Context, levelup_channel: discord.TextChannel = None):
        """Set a channel for all level up messages to send to"""
        if not levelup_channel:
            await self.config.guild(ctx.guild).notifylog.set(None)
            await ctx.send("LevelUp channel has been **Disabled**")
        else:
            await self.config.guild(ctx.guild).notifylog.set(levelup_channel.id)
            await ctx.send(f"LevelUp channel has been set to {levelup_channel.mention}")
        await self.init_settings()

    @lvl_group.group(name="prestige")
    async def prestige_settings(self, ctx: commands.Context):
        """Level Prestige Settings"""
        pass

    @prestige_settings.command(name="level")
    async def prestige_level(self, ctx: commands.Context, level: int):
        """
        Set the level required to prestige
        Set to 0 to disable prestige
        """
        await self.config.guild(ctx.guild).prestige.set(level)
        await ctx.tick()

    @prestige_settings.command(name="addprestigedata")
    async def add_pres_data(
            self,
            ctx: commands.Context,
            prestige_level: int,
            role: discord.Role,
            emoji: str
    ):
        """
        Add a role and emoji associated with a specific prestige level

        When a user prestiges, they will get that role and the emoji will show on their profile
        """
        async with self.config.guild(ctx.guild).prestigedata() as data:
            data[prestige_level] = {
                "role": role.id,
                "emoji": emoji
            }
        await ctx.tick()

    @prestige_settings.command(name="delprestigedata")
    async def del_pres_data(self, ctx: commands.Context, prestige_level: str):
        """Delete a prestige level data set"""
        async with self.config.guild(ctx.guild).prestigedata() as data:
            if prestige_level in data:
                del data[prestige_level]
            else:
                return await ctx.send("That prestige level doesnt exist!")
        await ctx.tick()

    @lvl_group.group(name="ignored")
    async def ignore_group(self, ctx: commands.Context):
        """Base command for all ignore lists"""
        pass

    @ignore_group.command(name="channel")
    async def ignore_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Add/Remove a channel from the ignore list
        Channels in the ignore list dont gain XP

        Use the command with a channel already in the ignore list to remove it
        """
        async with self.config.guild(ctx.guild).ignoredchannels() as ignored:
            if channel.id in ignored:
                ignored.remove(channel.id)
                await ctx.send("Channel removed from ignore list")
            else:
                ignored.append(channel.id)
                await ctx.send("Channel added to ignore list")
        await self.init_settings()

    @ignore_group.command(name="role")
    async def ignore_role(self, ctx: commands.Context, role: discord.Role):
        """
        Add/Remove a role from the ignore list
        Roles in the ignore list dont gain XP

        Use the command with a role already in the ignore list to remove it
        """
        async with self.config.guild(ctx.guild).ignoredroles() as ignored:
            if role.id in ignored:
                ignored.remove(role.id)
                await ctx.send("Role removed from ignore list")
            else:
                ignored.append(role.id)
                await ctx.send("Role added to ignore list")
        await self.init_settings()

    @ignore_group.command(name="member")
    async def ignore_role(self, ctx: commands.Context, member: discord.Member):
        """
        Add/Remove a member from the ignore list
        Members in the ignore list dont gain XP

        Use the command with a member already in the ignore list to remove them
        """
        async with self.config.guild(ctx.guild).ignoredusers() as ignored:
            if member.id in ignored:
                ignored.remove(member.id)
                await ctx.send("Member removed from ignore list")
            else:
                ignored.append(member.id)
                await ctx.send("Member added to ignore list")
        await self.init_settings()

    @commands.command(name="mocklvl")
    async def get_lvl_test(self, ctx, *, user: discord.Member = None):
        """get lvl"""
        if not user:
            user = ctx.author
        banner = await self.get_banner(user)
        color = str(user.colour)
        color = hex_to_rgb(color)
        args = {
            'bg_image': banner,
            'profile_image': user.avatar_url,
            'level': 4,
            'color': color,
        }
        file = await self.gen_levelup_img(args)
        await ctx.send(file=file)

    @commands.command(name="pf")
    @commands.guild_only()
    async def get_profile(self, ctx: commands.Context, *, user: discord.Member = None):
        """View your profile info"""
        conf = await self.config.guild(ctx.guild).all()
        users = conf["users"]
        if not user:
            user = ctx.author
        user_id = str(user.id)
        if user_id not in users:
            return await ctx.send("No information available yet!")
        pos = await get_user_position(conf, user_id)
        position = pos["p"]
        percentage = pos["pr"]
        stats = await get_user_stats(conf, user_id)
        level = stats["l"]
        messages = stats["m"]
        voice = stats["v"]
        xp = stats["xp"]
        goal = stats["goal"]
        progress = f'{"{:,}".format(xp)}/{"{:,}".format(goal)}'
        lvlbar = stats["lb"]
        lvlpercent = stats["lp"]
        emoji = stats["e"]
        prestige = stats["pr"]
        if not conf["usepics"]:
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
                prestige
            )
            await ctx.send(embed=embed)
        else:
            async with ctx.typing():
                banner = await self.get_banner(user)
                color = str(user.colour)
                color = hex_to_rgb(color)
                args = {
                    'bg_image': banner,  # Background image link
                    'profile_image': user.avatar_url,  # User profile picture link
                    'level': level,  # User current level
                    'current_xp': 0,  # Current level minimum xp
                    'user_xp': xp,  # User current xp
                    'next_xp': goal,  # xp required for next level
                    'user_position': position,  # User position in leaderboard
                    'user_name': user.name,  # user name with descriminator
                    'user_status': user.status.name,  # User status eg. online, offline, idle, streaming, dnd
                    'color': color,  # User's color
                    'messages': messages,
                    'voice': voice,
                    'prestige': prestige,
                }
                file = await self.gen_profile_img(args)
                await ctx.send(file=file)

    @commands.command(name="prestige")
    @commands.guild_only()
    async def prestige_user(self, ctx: commands.Context):
        """
        Once you have reached this servers prestige level requirement, you can
        reset your stats to gain a prestige level and any perks associated with it
        """
        conf = await self.config.guild(ctx.guild).all()
        perms = ctx.channel.permissions_for(ctx.guild.me).manage_roles
        if not perms:
            log.warning("Insufficient perms to assign prestige ranks!")
        required_level = conf["prestige"]
        if not required_level:
            return await ctx.send("Prestige is disabled on this server!")
        prestige_data = conf["prestigedata"]
        if not prestige_data:
            return await ctx.send("Prestige levels have not been set yet!")
        user_id = str(ctx.author.id)
        users = conf["users"]
        if user_id not in users:
            return await ctx.send("No information available for you yet!")
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
            else:
                return await ctx.send(f"Prestige level {pending_prestige} has not been set yet!")
        else:
            msg = f"**You are not eligible to prestige yet!**\n" \
                  f"`Your level:     `{current_level}\n" \
                  f"`Required Level: `{required_level}"
            embed = discord.Embed(
                description=msg,
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
        total_voice = 0
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
            return await ctx.send("No user data yet!")
        voice = int(total_voice / 60)
        sorted_users = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
        pages = math.ceil(len(sorted_users) / 10)
        start = 0
        stop = 10
        you = ""
        for p in range(pages):
            msg = f"**Total Messages:** `{total_messages}`\n" \
                  f"**Total VoiceMinutes:** `{voice}`\n"
            if stop > len(sorted_users):
                stop = len(sorted_users)
            for i in range(start, stop, 1):
                uid = sorted_users[i][0]
                if str(uid) == str(ctx.author.id):
                    you = f"You: {i + 1}/{len(sorted_users)}\n"
                user = ctx.guild.get_member(int(uid))
                if user:
                    user = user.name
                else:
                    user = uid
                xp = sorted_users[i][1]
                level = get_level(xp, base, exp)
                emoji = conf["users"][uid]["emoji"]
                if emoji:
                    msg += f"`{i + 1} ➤ Lvl {level}｜{xp} xp｜{user}`{emoji}\n"
                else:
                    msg += f"`{i + 1} ➤ Lvl {level}｜{xp} xp｜{user}`\n"
            embed = discord.Embed(
                title="LevelUp Leaderboard",
                description=msg,
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=ctx.guild.icon_url)
            if you:
                embed.set_footer(text=f"Pages {p + 1}/{pages} ｜ {you}")
            else:
                embed.set_footer(text=f"Pages {p + 1}/{pages}")
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
            return await ctx.send("No user data yet!")
