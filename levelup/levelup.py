import asyncio
import contextlib
# import datetime
import io
import json
import logging
import random
import sys
import typing
from datetime import datetime
from time import monotonic

import aiohttp
import discord
import matplotlib
import matplotlib.pyplot as plt
import tabulate
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box

from .base import UserCommands
from .formatter import (
    time_formatter,
    hex_to_rgb,
    get_level,
    get_xp,
    time_to_level
)

matplotlib.use("agg")
plt.switch_backend("agg")
log = logging.getLogger("red.vrt.levelup")
LOADING = "https://i.imgur.com/l3p6EMX.gif"
_ = Translator("LevelUp", __file__)

if discord.__version__ > "1.7.3":
    DPY2 = True
else:
    DPY2 = False


# CREDITS
# Thanks aikaterna#1393 and epic guy#0715 for the caching advice :)
# Thanks Fixator10#7133 for having a Leveler cog to get a reference for what kinda settings a leveler cog might need!
# Thanks Zephyrkul#1089 for the help with leaderboard formatting!

@cog_i18n(_)
class LevelUp(UserCommands, commands.Cog):
    """Local Discord Leveling System"""
    __author__ = "Vertyco#0117"
    __version__ = "1.4.33"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" \
               f"Cog Version: {self.__version__}\n" \
               f"Author: {self.__author__}\n" \
               f"Contributors: aikaterna#1393"
        return _(info)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        deleted = False
        for gid, data in self.data.copy().items():
            if str(user_id) in self.data[gid]["users"]:
                del self.data[gid]["users"][user_id]
                deleted = True
        if deleted:
            await self.save_cache()

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_guild = {
            "users": {},  # All user level data
            "levelroles": {},  # Roles associated with levels
            "ignoredchannels": [],  # Channels that dont gain XP
            "ignoredroles": [],  # Roles that dont gain XP
            "ignoredusers": [],  # Ignored users won't gain XP
            "prestige": 0,  # Level required to prestige, 0 is disabled
            "prestigedata": {},  # Prestige tiers, the role associated with them, and emoji for them
            "xp": [3, 6],  # Min/Max XP per message
            "voicexp": 2,  # XP per minute in voice
            "rolebonuses": {"msg": {}, "voice": {}},  # Roles that give a bonus range of XP
            "cooldown": 60,  # Only gives XP every 30 seconds
            "base": 100,  # Base denominator for level algorithm, higher takes longer to level
            "exp": 2,  # Exponent for level algorithm, higher is a more exponential/steeper curve
            "length": 0,  # Minimum length of message to be considered eligible for XP gain
            "starcooldown": 3600,  # Cooldown in seconds for users to give each other stars
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
        default_global = {"ignored_guilds": []}
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        # Main cache
        self.data = {}

        # Guild id's as strings, user id's as strings
        self.lastmsg = {}  # Last sent message for users
        self.voice = {}  # Voice channel info
        self.stars = {}  # Keep track of star cooldowns
        self.ignored_guilds = []
        self.first_run = True
        self.profiles = {}

        self.looptimes = {
            "checkvoice": 0,
            "cachedump": 0,
            "lvlassignavg": 0
        }

        # For importing user levels from Fixator's Leveler cog
        self._db_ready = False
        self.client = None
        self.db = None

        # Cachey wakey dumpy wumpy
        self.cache_dumper.start()
        self.voice_checker.start()

    def cog_unload(self):
        self.cache_dumper.cancel()
        self.voice_checker.cancel()
        asyncio.create_task(self.save_cache())

    @staticmethod
    def get_size(num: float) -> str:
        for unit in ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB"]:
            if abs(num) < 1024.0:
                return "{0:.1f}{1}".format(num, unit)
            num /= 1024.0
        return "{0:.1f}{1}".format(num, "YB")

    @commands.Cog.listener()
    async def on_guild_join(self, new_guild: discord.Guild):
        if new_guild.id not in self.data:
            await self.initialize()

    @commands.Cog.listener()
    async def on_guild_remove(self, old_guild: discord.Guild):
        if old_guild.id in self.data:
            await self.save_cache(old_guild)
            del self.data[old_guild.id]

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if not payload:
            return
        if payload.emoji.name != "\N{WHITE MEDIUM STAR}":
            return
        # Ignore reactions added by the bot
        if payload.user_id == self.bot.user.id:
            return
        # Ignore reactions added in DMs
        if not payload.guild_id:
            return
        if not payload.member:
            return
        if payload.member.bot:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        chan = guild.get_channel(payload.channel_id)
        if not chan:
            return
        try:
            msg = await chan.fetch_message(payload.message_id)
            if not msg:
                return
        except (discord.NotFound, discord.Forbidden):
            return
        # Ignore reactions added to a message that a bot sent
        if msg.author.bot:
            return
        # Ignore people adding reactions to their own messages
        if msg.author.id == payload.user_id:
            return

        now = datetime.now()
        gid = payload.guild_id
        giver_id = str(payload.user_id)
        giver = payload.member
        receiver = msg.author

        can_give = False
        if giver_id not in self.stars[gid]:
            self.stars[gid][giver_id] = now
            can_give = True

        if not can_give:
            cooldown = self.data[gid]["starcooldown"]
            last_given = self.stars[gid][giver_id]
            td = (now - last_given).total_seconds()
            if td > cooldown:
                self.stars[gid][giver_id] = now
                can_give = True

        if not can_give:
            return

        self.data[gid]["users"][str(receiver.id)]["stars"] += 1
        if chan.permissions_for(guild.me).send_messages:
            with contextlib.suppress(discord.HTTPException):
                await chan.send(
                    _(
                        f"**{giver.name}** just gave a star to **{receiver.name}**!"
                    ),
                    delete_after=60
                )

    @commands.Cog.listener("on_message")
    async def messages(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # Check if guild is in the master ignore list
        if str(message.guild.id) in self.ignored_guilds:
            return
        # Check whether the cog isn't disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # Check whether the channel isn't on the ignore list
        if not await self.bot.ignored_channel_or_guild(message):
            return
        # Check whether the message author isn't on allowlist/blocklist
        if not await self.bot.allowed_by_whitelist_blacklist(message.author):
            return
        await self.message_handler(message)

    async def initialize(self):
        self.ignored_guilds = await self.config.ignored_guilds()
        global_conf = await self.config.all_guilds()
        for guild in self.bot.guilds:
            gid = guild.id
            if gid in global_conf:
                data = global_conf[gid]
            else:
                data = await self.config.guild(guild).all()
            if gid not in self.data:
                self.data[gid] = data
                self.stars[gid] = {}
                self.voice[gid] = {}
                self.lastmsg[gid] = {}
        log.info("Settings initialized to cache")
        self.first_run = False

    async def save_cache(self, target_guild: discord.guild = None):
        cache = self.data.copy()
        for gid, data in cache.items():
            if target_guild and target_guild.id != gid:
                continue
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
            await self.config.guild(guild).set(data)

    def init_user(self, guild_id: int, user_id: str):
        self.data[guild_id]["users"][user_id] = {
            "xp": 0,
            "voice": 0,  # Seconds
            "messages": 0,
            "level": 0,
            "prestige": 0,
            "emoji": None,
            "background": None,
            "stars": 0,
            "colors": {"name": None, "stat": None}
        }

    async def check_levelups(self, guild_id: int, user_id: str):
        base = self.data[guild_id]["base"]
        exp = self.data[guild_id]["exp"]
        user = self.data[guild_id]["users"][user_id]
        background = user["background"]
        level = user["level"]
        xp = user["xp"]
        maybe_new_level = get_level(int(xp), base, exp)
        if maybe_new_level == level:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        self.data[guild_id]["users"][user_id]["level"] = maybe_new_level
        await self.level_up(guild, user_id, maybe_new_level, background)

    # User has leveled up, send message and check if any roles are associated with it
    async def level_up(self, guild: discord.guild, user: str, new_level: int, bg: str = None):
        t1 = monotonic()
        conf = self.data[guild.id]
        levelroles = conf["levelroles"]
        roleperms = guild.me.guild_permissions.manage_roles
        autoremove = conf["autoremove"]
        dm = conf["notifydm"]
        mention = conf["mention"]
        channel = conf["notifylog"]
        can_send = False
        if channel:
            channel = guild.get_channel(channel)
            perms = channel.permissions_for(guild.me).send_messages
            if perms:
                can_send = True

        usepics = conf["usepics"]
        can_send_attachments = False
        if channel:
            can_send_attachments = channel.permissions_for(guild.me).attach_files
        member = guild.get_member(int(user))
        if not member:
            return
        mentionuser = member.mention
        name = member.name
        pfp = None
        try:
            if DPY2:
                if member.avatar:
                    pfp = member.avatar.url
            else:
                pfp = member.avatar_url
        except AttributeError:
            log.warning(f"Failed to get avatar url for {member.name} in {guild.name}. DPY2 = {DPY2}")

        # Send levelup messages
        if not usepics:
            if dm:
                await member.send(_(f"You have just reached level {new_level} in {guild.name}!"))
            color = member.colour
            embed = discord.Embed(
                description=_(f"**Just reached level {new_level}!**"),
                color=color
            )
            embed.set_author(name=name, icon_url=pfp)
            if channel and can_send:
                if mention:
                    await channel.send(mentionuser, embed=embed)
                else:
                    await channel.send(embed=embed)

        else:
            # Generate LevelUP Image
            if bg:
                banner = bg
            else:
                banner = await self.get_banner(member)
            color = str(member.colour)
            if color == "#000000":  # Don't use default color
                color = str(discord.Color.random())
            color = hex_to_rgb(color)
            args = {
                'bg_image': banner,
                'profile_image': pfp,
                'level': new_level,
                'color': color,
            }
            if dm:
                file = await self.gen_levelup_img(args)
                await member.send(f"You just leveled up in {guild.name}!", file=file)
                if channel and can_send and can_send_attachments:
                    if mention:
                        await channel.send(_(f"**{mentionuser} just leveled up!**"), file=file)
                    else:
                        await channel.send(_(f"**{name} just leveled up!**"), file=file)
                else:
                    log.warning(f"Bot cant send LevelUp alert to log channel in {guild.name}")

        if not roleperms:
            # log.warning(f"Bot can't manage roles in {guild.name}")
            return
        if not levelroles:
            return
        # Role adding/removal
        if not autoremove:  # Level roles stack
            for level, role_id in levelroles.items():
                if int(level) <= int(new_level):  # Then give user that role since they should stack
                    role = guild.get_role(int(role_id))
                    if not role:
                        continue
                    if role not in member.roles:
                        await member.add_roles(role)
        else:  # No stacking so add role and remove the others below that level
            role_applied = False
            if str(new_level) in levelroles:
                role_id = levelroles[str(new_level)]
                role = guild.get_role(int(role_id))
                if role not in member.roles:
                    await member.add_roles(role)
                    role_applied = True

            # Remove any previous roles, but only if a new role was applied
            if new_level > 1 and role_applied:
                for role in member.roles:
                    for level, role_id in levelroles.items():
                        if role.id != role_id:
                            continue
                        if int(level) >= new_level:
                            continue
                        await member.remove_roles(role)

        t = int((monotonic() - t1) * 1000)
        loop = self.looptimes["lvlassignavg"]
        if not loop:
            self.looptimes["lvlassignavg"] = t
        else:
            self.looptimes["lvlassignavg"] = int((loop + t) / 2)

    async def message_handler(self, message: discord.Message):
        now = datetime.now()
        guild = message.guild
        gid = guild.id
        if gid not in self.data:
            await self.initialize()
        conf = self.data[gid]
        xpmin = int(conf["xp"][0])
        xpmax = int(conf["xp"][1]) + 1
        xp = random.choice(range(xpmin, xpmax))
        bonuses = conf["rolebonuses"]["msg"]
        bonusrole = None

        users = self.data[gid]["users"]
        uid = str(message.author.id)
        if uid not in users:
            self.init_user(gid, uid)

        # Whether to award xp
        addxp = False
        if uid not in self.lastmsg[gid]:
            addxp = True
        else:
            td = (now - self.lastmsg[gid][uid]).total_seconds()
            if td > conf["cooldown"]:
                addxp = True

        # Ignored stuff
        for role in message.author.roles:
            rid = str(role.id)
            if role.id in conf["ignoredroles"]:
                addxp = False
            if rid in bonuses:
                bonusrole = rid
        if message.channel.id in conf["ignoredchannels"]:
            addxp = False
        if int(uid) in conf["ignoredusers"]:
            addxp = False

        if conf["length"]:  # Make sure message meets minimum length requirements
            if len(message.content) < conf["length"]:
                addxp = False

        if addxp:  # Give XP
            self.lastmsg[gid][uid] = now
            self.data[gid]["users"][uid]["xp"] += xp
            if bonusrole:
                bonusrange = bonuses[bonusrole]
                bmin = int(bonusrange[0])
                bmax = int(bonusrange[1]) + 1
                bxp = random.choice(range(bmin, bmax))
                self.data[gid]["users"][uid]["xp"] += bxp
        self.data[gid]["users"][uid]["messages"] += 1
        await self.check_levelups(gid, uid)

    async def check_voice(self, guild: discord.guild):
        jobs = []
        gid = guild.id
        if str(gid) in self.ignored_guilds:
            return
        if gid not in self.data:
            await self.initialize()

        conf = self.data[gid]
        xp_per_minute = conf["voicexp"]
        bonuses = conf["rolebonuses"]["voice"]
        bonusrole = None
        for member in guild.members:
            if member.bot:
                continue
            now = datetime.now()
            uid = str(member.id)
            voice_state = member.voice
            if not voice_state:  # Only cache if user is in a vc
                if uid in self.voice[gid]:
                    del self.voice[gid][uid]
                continue

            if uid not in self.voice[gid]:
                self.voice[gid][uid] = now
            if uid not in self.data[gid]["users"]:
                self.init_user(gid, uid)

            ts = self.voice[gid][uid]
            td = (now - ts).total_seconds()
            xp_to_give = (td / 60) * xp_per_minute
            addxp = True
            # Ignore muted users
            if conf["muted"] and voice_state.self_mute:
                addxp = False
            # Ignore deafened users
            if conf["deafened"] and voice_state.self_deaf:
                addxp = False
            # Ignore offline/invisible users
            if conf["invisible"] and member.status.name == "offline":
                addxp = False
            # Ignore if user is only one in channel
            in_voice = 0
            for mem in voice_state.channel.members:
                if mem.bot:
                    continue
                in_voice += 1
            if conf["solo"] and in_voice <= 1:
                addxp = False
            # Check ignored roles
            for role in member.roles:
                rid = str(role.id)
                if role.id in conf["ignoredroles"]:
                    addxp = False
                if rid in bonuses:
                    bonusrole = rid
            # Check ignored users
            if int(uid) in conf["ignoredusers"]:
                addxp = False
            # Check ignored channels
            if voice_state.channel.id in conf["ignoredchannels"]:
                addxp = False
            if addxp:
                self.data[gid]["users"][uid]["xp"] += xp_to_give
                if bonusrole:
                    bonusrange = bonuses[bonusrole]
                    bmin = int(bonusrange[0])
                    bmax = int(bonusrange[1]) + 1
                    bxp = random.choice(range(bmin, bmax))
                    self.data[gid]["users"][uid]["xp"] += bxp
            self.data[gid]["users"][uid]["voice"] += td
            self.voice[gid][uid] = now
            jobs.append(self.check_levelups(gid, uid))
        await asyncio.gather(*jobs)

    @tasks.loop(seconds=20)
    async def voice_checker(self):
        t = monotonic()
        vtasks = []
        for guild in self.bot.guilds:
            vtasks.append(self.check_voice(guild))
        await asyncio.gather(*vtasks)
        t = int((monotonic() - t) * 1000)
        loop = self.looptimes["checkvoice"]
        if not loop:
            self.looptimes["checkvoice"] = t
        else:
            self.looptimes["checkvoice"] = int((loop + t) / 2)

    @voice_checker.before_loop
    async def before_voice_checker(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(60)
        if self.first_run:
            await self.initialize()
        log.info("Voice checker running")

    @tasks.loop(minutes=5)
    async def cache_dumper(self):
        t = monotonic()
        await self.save_cache()
        t = int((monotonic() - t) * 1000)
        loop = self.looptimes["cachedump"]
        if not loop:
            self.looptimes["cachedump"] = t
        else:
            self.looptimes["cachedump"] = int((loop + t) / 2)

    @cache_dumper.before_loop
    async def before_cache_dumper(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(300)
        log.info("Cache dumber ready")

    @commands.group(name="levelset", aliases=["lset", "lvlset", "levelup"])
    @commands.admin()
    @commands.guild_only()
    async def lvl_group(self, ctx: commands.Context):
        """Access LevelUP setting commands"""
        pass

    @lvl_group.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View all LevelUP settings"""
        conf = self.data[ctx.guild.id]

        levelroles = conf["levelroles"]
        igchannels = conf["ignoredchannels"]
        igroles = conf["ignoredroles"]
        igusers = conf["ignoredusers"]
        prestige = conf["prestige"]
        pdata = conf["prestigedata"]
        stacking = conf["stackprestigeroles"]
        xp = conf["xp"]
        xpbonus = conf["rolebonuses"]["msg"]
        voicexp = conf["voicexp"]
        voicexpbonus = conf["rolebonuses"]["voice"]
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
        starcooldown = conf["starcooldown"]
        sc = time_formatter(starcooldown)
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
              f"**Level Algorithm**\n" \
              f"`Base Multiplier:  `{base}\n" \
              f"`Exp Multiplier:   `{exp}\n" \
              f"**LevelUps**\n" \
              f"`Notify in DMs:    `{notifydm}\n" \
              f"`Mention User:     `{mention}\n" \
              f"`AutoRemove Roles: `{autoremove}\n" \
              f"`LevelUp Channel:  `{notifylog}\n" \
              f"**Stars**\n" \
              f"`Cooldown:         `{sc}\n"
        if levelroles:
            msg += "**Levels**\n"
            for level, role_id in levelroles.items():
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                msg += f"`Level {level}: `{role}\n"
        if igchannels:
            msg += "**Ignored Channels**\n"
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
            description=_(msg),
            color=discord.Color.random()
        )
        if voicexpbonus:
            text = ""
            for rid, bonusrange in voicexpbonus.items():
                role = ctx.guild.get_role(int(rid))
                if not role:
                    continue
                text += f"{role.name} - {bonusrange}\n"
            if text:
                embed.add_field(
                    name=_("Voice XP Bonus Roles"),
                    value=text
                )
        if xpbonus:
            text = ""
            for rid, bonusrange in xpbonus.items():
                role = ctx.guild.get_role(int(rid))
                if not role:
                    continue
                text += f"{role.name} - {bonusrange}\n"
            if text:
                embed.add_field(
                    name=_("Message XP Bonus Roles"),
                    value=text
                )
        await ctx.send(embed=embed)

    @lvl_group.group(name="admin")
    @commands.guildowner()
    async def admin_group(self, ctx: commands.Context):
        """
        Cog admin commands

        Reset levels, backup and restore cog data
        """
        pass

    @admin_group.command(name="globalreset")
    @commands.is_owner()
    async def reset_all(self, ctx: commands.Context):
        """Reset cog data for all guilds"""
        for data in self.data.values():
            data.clear()
        await ctx.tick()
        await self.save_cache()

    @admin_group.command(name="guildreset")
    async def reset_guild(self, ctx: commands.Context):
        """Reset cog data for this guild"""
        self.data[ctx.guild.id] = {}
        await ctx.tick()
        await self.save_cache()

    @admin_group.command(name="looptimes")
    async def get_looptimes(self, ctx: commands.Context):
        """View current looptimes"""
        lt = self.looptimes
        text = f"`Voice Checker: `{lt['checkvoice']}ms\n" \
               f"`Cache Dumper:  `{lt['cachedump']}ms\n" \
               f"`Lvl Assignment: `{lt['lvlassignavg']}ms"
        embed = discord.Embed(
            title="Task Loop Times",
            description=_(text),
            color=discord.Color.random()
        )
        embed.set_footer(text=_("Units are the average times in milliseconds"))
        await ctx.send(embed=embed)

    @admin_group.command(name="globalbackup")
    @commands.is_owner()
    async def backup_all_settings(self, ctx: commands.Context):
        """
        Backup global cog data

        Sends the .json to discord
        """
        today = datetime.now().strftime('%m-%d-%y')
        settings = self.data
        settings = json.dumps(settings)
        filename = f"LevelUp_GLOBAL_{today}.json"
        iofile = io.StringIO(settings)
        file = discord.File(iofile, filename=filename)
        await ctx.send("Here is the global LevelUp config for all guilds", file=file)

    @admin_group.command(name="guildbackup")
    @commands.guildowner()
    async def backup_settings(self, ctx: commands.Context):
        """
        Backup guild data

        Sends the .json to discord
        """
        today = datetime.now().strftime('%m-%d-%y')
        settings = self.data[ctx.guild.id]
        settings = json.dumps(settings)
        filename = f"LevelUp_GUILD_{today}.json"
        iofile = io.StringIO(settings)
        file = discord.File(iofile, filename=filename)
        await ctx.send("Here is the global LevelUp config for this guilds", file=file)

    @admin_group.command(name="globalrestore")
    @commands.is_owner()
    async def restore_all_settings(self, ctx: commands.Context):
        """
        Restore a global backup

        Attach the .json file to the command message to import
        """
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            for guild in self.bot.guilds:
                gid = guild.id
                if str(gid) in config:
                    self.data[gid] = config[str(gid)]
            await ctx.send(_("Config restored from backup file!"))
            await self.save_cache()
        else:
            await ctx.send(_("Attach your backup file to the message when using this command."))

    @admin_group.command(name="guildrestore")
    @commands.guildowner()
    async def restore_settings(self, ctx: commands.Context):
        """
        Restore a guild backup

        Attach the .json file to the command message to import
        """
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            self.data[ctx.guild.id] = config
            await ctx.send(_("Config restored from backup file!"))
            await self.save_cache()
        else:
            await ctx.send(_("Attach your backup file to the message when using this command."))

    @admin_group.command(name="cache")
    @commands.is_owner()
    async def get_cache_size(self, ctx: commands.Context):
        """See how much RAM this cog's cache is using"""
        main = sys.getsizeof(self.data)
        voice = sys.getsizeof(self.voice)
        stars = sys.getsizeof(self.stars)
        profile = sys.getsizeof(self.profiles)

        total = sum([main, voice, stars, profile])

        text = f"`Main:     `{self.get_size(main)}\n" \
               f"`Voice:    `{self.get_size(voice)}\n" \
               f"`Stars:    `{self.get_size(stars)}\n" \
               f"`Profiles: `{self.get_size(profile)}\n" \
               f"`Total:    `{self.get_size(total)}"

        em = discord.Embed(title=f"LevelUp {_('Cache')}", description=_(text), color=ctx.author.color)
        await ctx.send(embed=em)

    @admin_group.command(name="importleveler")
    @commands.is_owner()
    async def import_from_leveler(self, ctx: commands.Context, yes_or_no: str):
        """
        Import data from Fixator's Leveler cog

        This will overwrite existing LevelUp level data and stars
        It will also import XP range level roles, and ignored channels
        *Obviously you will need Leveler loaded while you run this command*
        """
        if "y" not in yes_or_no:
            return await ctx.send(_("Not importing users"))
        leveler = self.bot.get_cog("Leveler")
        if not leveler:
            return await ctx.send(_("Leveler is not loaded, please load it and try again!"))
        config = await leveler.config.custom("MONGODB").all()
        if not config:
            return await ctx.send(_("Couldnt find mongo config"))

        # If leveler is installed then libs should import fine
        try:
            import subprocess
            from motor.motor_asyncio import AsyncIOMotorClient
            from pymongo import errors as mongoerrors
        except Exception as e:
            log.warning(f"pymongo Import Error: {e}")
            return await ctx.send(_("Failed to import modules"))

        # Try connecting to mongo
        if self._db_ready:
            self._db_ready = False
        self._disconnect_mongo()
        try:
            self.client = AsyncIOMotorClient(
                **{k: v for k, v in config.items() if not k == "db_name"}
            )
            await self.client.server_info()
            self.db = self.client[config["db_name"]]
            self._db_ready = True
        except (
                mongoerrors.ServerSelectionTimeoutError,
                mongoerrors.ConfigurationError,
                mongoerrors.OperationFailure,
        ) as e:
            log.warning(f"Failed to connect to MongoDB: {e}")
            self.client = None
            self.db = None
            return await ctx.send(_("Failed to connect to MongoDB"))

        # If everything is okay so far let the user know its working
        embed = discord.Embed(
            description=_(f"Importing users from Leveler..."),
            color=discord.Color.orange()
        )
        embed.set_thumbnail(url=LOADING)
        msg = await ctx.send(embed=embed)
        users_imported = 0
        # Now to start the importing
        async with ctx.typing():
            min_message_length = await leveler.config.message_length()
            mention = await leveler.config.mention()
            xp_range = await leveler.config.xp()
            for guild in self.bot.guilds:
                guild_id = str(guild.id)
                ignored_channels = await leveler.config.guild(guild).ignored_channels()
                self.data[guild.id]["ignoredchannels"] = ignored_channels
                self.data[guild.id]["length"] = int(min_message_length)
                self.data[guild.id]["mention"] = mention
                self.data[guild.id]["xp"] = xp_range

                server_roles = await self.db.roles.find_one({"server_id": guild_id})
                if server_roles:
                    for rolename, data in server_roles["roles"].items():
                        role = guild.get_role(rolename)
                        if not role:
                            continue
                        level_req = data["level"]
                        self.data[guild.id]["levelroles"][level_req] = role.id

                for user in guild.members:
                    user_id = str(user.id)
                    try:
                        userinfo = await self.db.users.find_one({"user_id": user_id})
                    except Exception as e:
                        log.info(f"No data found for {user.name}: {e}")
                        continue
                    if not userinfo:
                        continue
                    if user_id not in self.data[guild.id]["users"]:
                        self.init_user(guild.id, user_id)
                    servers = userinfo["servers"]

                    # Import levels
                    if guild_id in servers:
                        level = servers[guild_id]["level"]
                    else:
                        level = None
                    if level:
                        base = self.data[guild.id]["base"]
                        exp = self.data[guild.id]["exp"]
                        xp = get_xp(level, base, exp)
                        self.data[guild.id]["users"][user_id]["level"] = int(level)
                        self.data[guild.id]["users"][user_id]["xp"] = xp

                    # Import rep
                    self.data[guild.id]["users"][user_id]["stars"] = int(userinfo["rep"])
                    users_imported += 1

            embed = discord.Embed(
                description=_(f"Importing Complete!\n"
                              f"{users_imported} users imported"),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            self._disconnect_mongo()

    def _disconnect_mongo(self):
        if self.client:
            self.client.close()

    @admin_group.command(name="cleanup")
    @commands.guildowner()
    async def cleanup_guild(self, ctx: commands.Context):
        """Delete users no longer in the server"""
        guild = ctx.guild
        members = [u.id for u in guild.members]
        cleanup = []
        savedusers = self.data[ctx.guild.id]["users"].copy()
        for user_id in savedusers:
            if int(user_id) not in members:
                cleanup.append(user_id)
        if not cleanup:
            return await ctx.send(_("Nothing to clean"))
        cleaned = 0
        for uid in cleanup:
            del self.data[ctx.guild.id]["users"][uid]
            cleaned += 1
        await ctx.send(_(f"Deleted {cleaned} user ID's from the config that are no longer in the server"))
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="messages")
    async def message_group(self, ctx: commands.Context):
        """Message settings"""

    @message_group.command(name="xp")
    async def set_xp(self, ctx: commands.Context, min_xp: int = 3, max_xp: int = 6):
        """
        Set message XP range
        Set the Min and Max amount of XP that a message can gain
        """
        xp = [min_xp, max_xp]
        self.data[ctx.guild.id]["xp"] = xp
        await ctx.send(_(f"Message XP range has been set to {min_xp} - {max_xp} per valid message"))
        await self.save_cache(ctx.guild)

    @message_group.command(name="rolebonus")
    async def msg_role_bonus(self, ctx: commands.Context, role: discord.Role, min_xp: int, max_xp: int):
        """
        Add a range of bonus XP to apply to certain roles

        This bonus applies to both messages and voice time

        Set both min and max to 0 to remove the role bonus
        """
        if not role:
            return await ctx.send(_("I cannot find that role"))
        if min_xp > max_xp:
            return await ctx.send(_("Max xp needs to be higher than min xp"))
        rid = str(role.id)
        xp = [min_xp, max_xp]
        rb = self.data[ctx.guild.id]["rolebonuses"]["msg"]

        if not min_xp and not max_xp:
            if rid not in rb:
                return await ctx.send(_("That role has no bonus xp associated with it"))
            del self.data[ctx.guild.id]["rolebonuses"]["msg"][rid]
            await ctx.send(_(f"Bonus xp for {role.name} has been removed"))
        else:
            self.data[ctx.guild.id]["rolebonuses"]["msg"][rid] = xp
            await ctx.send(_(f"Bonus xp for {role.name} has been set to {min_xp} - {max_xp}"))
        await self.save_cache(ctx.guild)

    @message_group.command(name="cooldown")
    async def set_cooldown(self, ctx: commands.Context, cooldown: int):
        """
        Cooldown threshold for message XP

        When a user sends a message they will have to wait X seconds before their message
        counts as XP gained
        """
        self.data[ctx.guild.id]["cooldown"] = cooldown
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @message_group.command(name="length")
    async def set_length(self, ctx: commands.Context, minimum_length: int):
        """
        Set minimum message length for XP
        Minimum length a message must be to count towards XP gained

        Set to 0 to disable
        """
        self.data[ctx.guild.id]["length"] = minimum_length
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="voice")
    async def voice_group(self, ctx: commands.Context):
        """Voice settings"""
        pass

    @voice_group.command(name="xp")
    async def set_voice_xp(self, ctx: commands.Context, voice_xp: int):
        """
        Set voice XP gain
        Sets the amount of XP gained per minute in a voice channel (default is 2)
        """
        self.data[ctx.guild.id]["voicexp"] = voice_xp
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @voice_group.command(name="rolebonus")
    async def voice_role_bonus(self, ctx: commands.Context, role: discord.Role, min_xp: int, max_xp: int):
        """
        Add a range of bonus XP to apply to certain roles

        This bonus applies to voice time xp

        Set both min and max to 0 to remove the role bonus
        """
        if not role:
            return await ctx.send(_("I cannot find that role"))
        if min_xp > max_xp:
            return await ctx.send(_("Max xp needs to be higher than min xp"))
        rid = str(role.id)
        xp = [min_xp, max_xp]

        rb = self.data[ctx.guild.id]["rolebonuses"]["voice"]
        if not min_xp and not max_xp:
            if rid not in rb:
                return await ctx.send(_("That role has no bonus xp associated with it"))
            del self.data[ctx.guild.id]["rolebonuses"]["voice"][rid]
            await ctx.send(_(f"Bonus xp for {role.name} has been removed"))
        else:
            self.data[ctx.guild.id]["rolebonuses"]["voice"][rid] = xp
            await ctx.send(_(f"Bonus xp for {role.name} has been set to {min_xp} - {max_xp}"))
        await self.save_cache(ctx.guild)

    @voice_group.command(name="muted")
    async def ignore_muted(self, ctx: commands.Context):
        """
        Ignore muted voice users
        Toggle whether self-muted users in a voice channel can gain voice XP
        """
        muted = self.data[ctx.guild.id]["muted"]
        if muted:
            self.data[ctx.guild.id]["muted"] = False
            await ctx.send(_("Self-Muted users can now gain XP while in a voice channel"))
        else:
            self.data[ctx.guild.id]["muted"] = True
            await ctx.send(_("Self-Muted users can no longer gain XP while in a voice channel"))
        await self.save_cache(ctx.guild)

    @voice_group.command(name="solo")
    async def ignore_solo(self, ctx: commands.Context):
        """
        Ignore solo voice users
        Toggle whether solo users in a voice channel can gain voice XP
        """
        solo = self.data[ctx.guild.id]["solo"]
        if solo:
            self.data[ctx.guild.id]["solo"] = False
            await ctx.send(_("Solo users can now gain XP while in a voice channel"))
        else:
            self.data[ctx.guild.id]["solo"] = True
            await ctx.send(_("Solo users can no longer gain XP while in a voice channel"))
        await self.save_cache(ctx.guild)

    @voice_group.command(name="deafened")
    async def ignore_deafened(self, ctx: commands.Context):
        """
        Ignore deafened voice users
        Toggle whether deafened users in a voice channel can gain voice XP
        """
        deafened = self.data[ctx.guild.id]["deafened"]
        if deafened:
            self.data[ctx.guild.id]["deafened"] = False
            await ctx.send(_("Deafened users can now gain XP while in a voice channel"))
        else:
            self.data[ctx.guild.id]["deafened"] = True
            await ctx.send(_("Deafened users can no longer gain XP while in a voice channel"))
        await self.save_cache(ctx.guild)

    @voice_group.command(name="invisible")
    async def ignore_invisible(self, ctx: commands.Context):
        """
        Ignore invisible voice users
        Toggle whether invisible users in a voice channel can gain voice XP
        """
        invisible = self.data[ctx.guild.id]["invisible"]
        if invisible:
            self.data[ctx.guild.id]["invisible"] = False
            await ctx.send(_("Invisible users can now gain XP while in a voice channel"))
        else:
            self.data[ctx.guild.id]["invisible"] = True
            await ctx.send(_("Invisible users can no longer gain XP while in a voice channel"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="addxp")
    async def add_xp(self, ctx: commands.Context, user_or_role: typing.Union[discord.Member, discord.Role], xp: int):
        """Add XP to a user or role"""
        gid = ctx.guild.id
        if not user_or_role:
            return await ctx.send(_("I cannot find that user or role"))
        if isinstance(user_or_role, discord.Member):
            uid = str(user_or_role.id)
            if uid not in self.data[gid]["users"]:
                self.init_user(gid, uid)
            self.data[gid]["users"][uid]["xp"] += xp
            await ctx.send(_(f"{xp} xp has been added to {user_or_role.name}"))
        else:
            users = []
            for user in ctx.guild.members:
                if user.bot:
                    continue
                if user_or_role in user.roles:
                    users.append(str(user.id))
            for uid in users:
                if uid not in self.data[gid]["users"]:
                    self.init_user(gid, uid)
                self.data[gid]["users"][uid]["xp"] += xp
            await ctx.send(_(f"Added {xp} xp to {len(users)} users that had the {user_or_role.name} role"))
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="algorithm")
    async def algo_edit(self, ctx: commands.Context):
        """Customize the leveling algorithm for your guild"""
        pass

    @algo_edit.command(name="base")
    async def set_base(self, ctx: commands.Context, base_multiplier: int):
        """
        Base multiplier for the leveling algorithm

        Affects leveling on a more linear scale(higher values makes leveling take longer)
        """
        self.data[ctx.guild.id]["base"] = base_multiplier
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @algo_edit.command(name="exp")
    async def set_exp(self, ctx: commands.Context, exponent_multiplier: typing.Union[int, float]):
        """
        Exponent multiplier for the leveling algorithm

        Affects leveling on an exponential scale(higher values makes leveling take exponentially longer)
        """
        self.data[ctx.guild.id]["exp"] = exponent_multiplier
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="embeds")
    async def toggle_embeds(self, ctx: commands.Context):
        """Toggle using embeds or generated pics"""
        usepics = self.data[ctx.guild.id]["usepics"]
        if usepics:
            self.data[ctx.guild.id]["usepics"] = False
            await ctx.send(_("LevelUp will now use **embeds** instead of generated images"))
        else:
            self.data[ctx.guild.id]["usepics"] = True
            await ctx.send(_("LevelUp will now use **generated images** instead of embeds"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="seelevels")
    async def see_levels(self, ctx: commands.Context):
        """
        Test the level algorithm
        View the first 20 levels using the current algorithm to test experience curve
        """
        conf = self.data[ctx.guild.id]
        base = conf["base"]
        exp = conf["exp"]
        cd = conf["cooldown"]
        xp_range = conf["xp"]
        msg = ""
        table = []
        x = []
        y = []
        for i in range(1, 21):
            xp = get_xp(i, base, exp)
            msg += f"Level {i}: {xp} XP Needed\n"
            time = time_to_level(i, base, exp, cd, xp_range)
            time = time_formatter(time)
            table.append([i, xp, time])
            x.append(i)
            y.append(xp)
        headers = ["Level", "XP Needed", "AproxTime"]
        data = tabulate.tabulate(table, headers, tablefmt="presto")
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
        example = "XP required for a level = Base * Level^Exp\n\n" \
                  "Approx time is the time it would take for a user to reach a level if they " \
                  "typed every time the cooldown expired non stop without sleeping or taking " \
                  "potty breaks."
        embed = discord.Embed(
            title="Level Example",
            description=_(f"`Base Multiplier:  `{base}\n"
                          f"`Exp Multiplier:   `{exp}\n"
                          f"`Experience Range: `{xp_range}\n"
                          f"`Message Cooldown: `{cd}\n"
                          f"{box(example)}\n"
                          f"{box(data, lang='python')}"),
            color=discord.Color.random()
        )
        embed.set_image(url=img)
        await ctx.send(embed=embed, file=file)

    @lvl_group.command(name="dm")
    async def toggle_dm(self, ctx: commands.Context):
        """
        Toggle DM notifications
        Toggle whether LevelUp messages are DM'd to the user
        """
        notifydm = self.data[ctx.guild.id]["notifydm"]
        if notifydm:
            self.data[ctx.guild.id]["notifydm"] = False
            await ctx.send(_("Users will no longer be DM'd when they level up"))
        else:
            self.data[ctx.guild.id]["notifydm"] = True
            await ctx.send(_("Users will now be DM'd when they level up"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="mention")
    async def toggle_mention(self, ctx: commands.Context):
        """
        Toggle levelup mentions
        Toggle whether the user in mentioned in LevelUp messages
        """
        mention = self.data[ctx.guild.id]["mention"]
        if mention:
            self.data[ctx.guild.id]["mention"] = False
            await ctx.send(_("Mentions **Disabled**"))
        else:
            self.data[ctx.guild.id]["mention"] = True
            await ctx.send(_("Mentions **Enabled**"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="levelchannel")
    async def set_level_channel(self, ctx: commands.Context, levelup_channel: discord.TextChannel = None):
        """
        Set LevelUP message channel
        Set a channel for all level up messages to send to
        """
        if not levelup_channel:
            self.data[ctx.guild.id]["notifylog"] = None
            await ctx.send(_("LevelUp channel has been **Disabled**"))
        else:
            perms = levelup_channel.permissions_for(ctx.guild.me).send_messages
            if not perms:
                return await ctx.send(_(f"I do not have permission to send messages to that channel."))
            self.data[ctx.guild.id]["notifylog"] = levelup_channel.id
            await ctx.send(_(f"LevelUp channel has been set to {levelup_channel.mention}"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="starcooldown")
    async def set_star_cooldown(self, ctx: commands.Context, time_in_seconds: int):
        """
        Set the star cooldown

        Users can give another user a star every X seconds
        """
        self.data[ctx.guild.id]["starcooldown"] = time_in_seconds
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="roles")
    async def level_roles(self, ctx: commands.Context):
        """Level role assignment"""

    @level_roles.command(name="initialize")
    async def init_roles(self, ctx: commands.Context):
        """
        Initialize level roles

        This command is for if you added level roles after users have achieved that level,
        it will apply all necessary roles to a user according to their level and prestige
        """
        guild = ctx.guild
        perms = guild.me.guild_permissions.manage_roles
        if not perms:
            return await ctx.send(_("I dont have the proper permissions to manage roles!"))
        roles_added = 0
        roles_removed = 0
        embed = discord.Embed(
            description="Adding roles, this may take a while...",
            color=discord.Color.magenta()
        )
        embed.set_thumbnail(url=LOADING)
        msg = await ctx.send(embed=embed)
        async with ctx.typing():
            conf = self.data[ctx.guild.id].copy()
            level_roles = conf["levelroles"]
            prestiges = conf["prestigedata"]
            autoremove = conf["autoremove"]
            users = conf["users"]
            for user_id, data in users.items():
                user = guild.get_member(int(user_id))
                if not user:
                    continue
                user_level = data["level"]
                prestige_level = data["prestige"]
                if autoremove:
                    highest_level = ""
                    for lvl, role_id in level_roles.items():
                        if int(lvl) <= int(user_level):
                            highest_level = lvl
                    if highest_level:
                        role = level_roles[highest_level]
                        role = guild.get_role(int(role))
                        if role:
                            await user.add_roles(role)
                            roles_added += 1
                            for r in user.roles:
                                if r.id in level_roles.values() and r.id != role.id:
                                    await user.remove_roles(r)
                                    roles_removed += 1
                    highest_prestige = ""
                    for plvl, prole in prestiges.items():
                        if int(plvl) <= int(prestige_level):
                            highest_prestige = plvl
                    if highest_prestige:
                        role = prestiges[highest_prestige]
                        role = guild.get_role(int(role))
                        if role:
                            await user.add_roles(role)
                            roles_added += 1
                else:
                    for lvl, role_id in level_roles.items():
                        role = guild.get_role(int(role_id))
                        if role and int(lvl) <= int(user_level):
                            await user.add_roles(role)
                            roles_added += 1
                    for lvl, role_id in prestiges.items():
                        role = guild.get_role(int(role_id))
                        if role and int(lvl) <= int(prestige_level):
                            await user.add_roles(role)
                            roles_added += 1
        embed = discord.Embed(
            description=_(f"Initialization complete! Added {roles_added} roles and removed {roles_removed}."),
            color=discord.Color.green()
        )
        await msg.edit(embed=embed)

    @level_roles.command(name="autoremove")
    async def toggle_autoremove(self, ctx: commands.Context):
        """Automatic removal of previous level roles"""
        autoremove = self.data[ctx.guild.id]["autoremove"]
        if autoremove:
            self.data[ctx.guild.id]["autoremove"] = False
            await ctx.send(_("Automatic role removal **Disabled**"))
        else:
            self.data[ctx.guild.id]["autoremove"] = True
            await ctx.send(_("Automatic role removal **Enabled**"))
        await self.save_cache(ctx.guild)

    @level_roles.command(name="add")
    async def add_level_role(self, ctx: commands.Context, level: str, role: discord.Role):
        """Assign a role to a level"""
        perms = ctx.guild.me.guild_permissions.manage_roles
        if not perms:
            return await ctx.send(_("I do not have permission to manage roles"))
        if level in self.data[ctx.guild.id]["levelroles"]:
            overwrite = "Overwritten"
        else:
            overwrite = "Set"
        self.data[ctx.guild.id]["levelroles"][level] = role.id
        await ctx.send(_(f"Level {level} has been {overwrite} as {role.mention}"))
        await self.save_cache(ctx.guild)

    @level_roles.command(name="del")
    async def del_level_role(self, ctx: commands.Context, level: str):
        """Assign a role to a level"""
        if level in self.data[ctx.guild.id]["levelroles"]:
            del self.data[ctx.guild.id]["levelroles"][level]
            await ctx.send(_("Level role has been deleted!"))
            await self.save_cache(ctx.guild)
        else:
            await ctx.send(_("Level doesnt exist!"))

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
        self.data[ctx.guild.id]["prestige"] = level
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @prestige_settings.command(name="add")
    async def add_pres_data(
            self,
            ctx: commands.Context,
            prestige_level: int,
            role: discord.Role,
            emoji: str
    ):
        """
        Add a prestige level role
        Add a role and emoji associated with a specific prestige level

        When a user prestiges, they will get that role and the emoji will show on their profile
        """
        self.data[ctx.guild.id]["prestigedata"][prestige_level] = {
            "role": role.id,
            "emoji": emoji
        }
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @prestige_settings.command(name="del")
    async def del_pres_data(self, ctx: commands.Context, prestige_level: str):
        """Delete a prestige level role"""
        pd = self.data[ctx.guild.id]["prestigedata"]
        if prestige_level in pd:
            del self.data[ctx.guild.id]["prestigedata"][prestige_level]
        else:
            return await ctx.send(_("That prestige level doesnt exist!"))
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="ignored")
    async def ignore_group(self, ctx: commands.Context):
        """Base command for all ignore lists"""
        pass

    @ignore_group.command(name="guild")
    @commands.is_owner()
    async def ignore_guild(self, ctx: commands.Context, guild_id: str):
        """
        Add/Remove a guild in the ignore list

        **THIS IS A GLOBAL SETTING ONLY BOT OWNERS CAN USE**

        Use the command with a guild already in the ignore list to remove it
        """
        async with self.config.ignored_guilds() as ignored:
            if guild_id in ignored:
                ignored.remove(guild_id)
                await ctx.send(_("Guild removed from ignore list"))
            else:
                ignored.append(guild_id)
                await ctx.send(_("Guild added to ignore list"))
            await self.initialize()

    @ignore_group.command(name="channel")
    async def ignore_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Add/Remove a channel in the ignore list
        Channels in the ignore list dont gain XP

        Use the command with a channel already in the ignore list to remove it
        """
        ig = self.data[ctx.guild.id]["ignoredchannels"]
        if channel.id in ig:
            self.data[ctx.guild.id]["ignoredchannels"].remove(channel.id)
            await ctx.send(_("Channel removed from ignore list"))
        else:
            self.data[ctx.guild.id]["ignoredchannels"].append(channel.id)
            await ctx.send(_("Channel added to ignore list"))
        await self.save_cache(ctx.guild)

    @ignore_group.command(name="role")
    async def ignore_role(self, ctx: commands.Context, role: discord.Role):
        """
        Add/Remove a role from the ignore list
        Roles in the ignore list dont gain XP

        Use the command with a role already in the ignore list to remove it
        """
        ig = self.data[ctx.guild.id]["ignoredroles"]
        if role.id in ig:
            self.data[ctx.guild.id]["ignoredroles"].remove(role.id)
            await ctx.send(_("Role removed from ignore list"))
        else:
            self.data[ctx.guild.id]["ignoredroles"].append(role.id)
            await ctx.send(_("Role added to ignore list"))
        await self.save_cache(ctx.guild)

    @ignore_group.command(name="member")
    async def ignore_member(self, ctx: commands.Context, member: discord.Member):
        """
        Add/Remove a member from the ignore list
        Members in the ignore list dont gain XP

        Use the command with a member already in the ignore list to remove them
        """
        ig = self.data[ctx.guild.id]["ignoredusers"]
        if member.id in ig:
            self.data[ctx.guild.id]["ignoredusers"].remove(member.id)
            await ctx.send(_("Member removed from ignore list"))
        else:
            self.data[ctx.guild.id]["ignoredusers"].append(member.id)
            await ctx.send(_("Member added to ignore list"))
        await self.save_cache(ctx.guild)

    # For testing purposes
    @commands.command(name="mocklvlup", hidden=True)
    @commands.is_owner()
    @commands.guild_only()
    async def mock_lvl_up(self, ctx, *, person: discord.Member = None):
        """Force level a user or yourself"""
        if not person:
            person = ctx.author
        uid = str(person.id)
        gid = ctx.guild.id
        conf = self.data[gid]
        base = conf["base"]
        exp = conf["exp"]
        users = conf["users"]
        if uid not in users:
            self.init_user(gid, uid)
        user = users[uid]
        currentxp = user["xp"]
        level = user["level"]
        level = level + 1
        new_xp = get_xp(level, base, exp)
        xp = new_xp - currentxp + 10
        self.data[gid]["users"][uid]["xp"] = xp
        await asyncio.sleep(2)
        await ctx.send(_(f"Forced {person.name} to level up!"))
        await self.save_cache(ctx.guild)

    # For testing purposes
    @commands.command(name="mocklvldown", hidden=True)
    @commands.is_owner()
    @commands.guild_only()
    async def mock_lvl_down(self, ctx, *, person: discord.Member = None):
        """Force de-level a user or yourself"""
        if not person:
            person = ctx.author
        uid = str(person.id)
        gid = ctx.guild.id
        conf = self.data[gid]
        base = conf["base"]
        exp = conf["exp"]
        users = conf["users"]
        if uid not in users:
            self.init_user(gid, uid)
        user = users[uid]
        currentxp = user["xp"]
        level = user["level"]
        level = level - 1
        new_xp = get_xp(level, base, exp)
        xp = new_xp - currentxp + 10
        self.data[gid]["users"][uid]["xp"] = xp
        await asyncio.sleep(2)
        await ctx.send(_(f"Forced {person.name} to level down!"))
        await self.save_cache(ctx.guild)

    # For testing purposes
    @commands.command(name="forceinit", hidden=True)
    @commands.is_owner()
    async def force_init(self, ctx):
        """Force Initialization"""
        await self.initialize()
        await ctx.tick()
