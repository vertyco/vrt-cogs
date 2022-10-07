import asyncio
import contextlib
import json
import logging
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from time import monotonic
from typing import Union

import aiohttp
import discord
import matplotlib
import matplotlib.pyplot as plt
import tabulate
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import box, humanize_number, humanize_list
from redbot.core.utils.predicates import MessagePredicate

from levelup.utils.formatter import (
    time_formatter,
    hex_to_rgb,
    get_level,
    get_xp,
    time_to_level
)
from .base import UserCommands

matplotlib.use("agg")
plt.switch_backend("agg")
log = logging.getLogger("red.vrt.levelup")
LOADING = "https://i.imgur.com/l3p6EMX.gif"
_ = Translator("LevelUp", __file__)
DPY2 = True if discord.__version__ > "1.7.3" else False


async def confirm(ctx: commands.Context):
    pred = MessagePredicate.yes_or_no(ctx)
    try:
        await ctx.bot.wait_for("message", check=pred, timeout=30)
    except asyncio.TimeoutError:
        return None
    else:
        return pred.result


# CREDITS
# Thanks aikaterna#1393 and epic guy#0715 for the caching advice :)
# Thanks Fixator10#7133 for having a Leveler cog to get a reference for what kinda settings a leveler cog might need!
# Thanks Zephyrkul#1089 for the leaderboard formatting ideas!

@cog_i18n(_)
class LevelUp(UserCommands, commands.Cog):
    """Local Discord Leveling System"""
    __author__ = "Vertyco#0117"
    __version__ = "1.15.37"

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
            "schema": "v1",
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
            "channelbonuses": {"msg": {}, "voice": {}},  # ChannelID keys, list values for bonus xp range
            "cooldown": 60,  # Only gives XP every 30 seconds
            "base": 100,  # Base denominator for level algorithm, higher takes longer to level
            "exp": 2,  # Exponent for level algorithm, higher is a more exponential/steeper curve
            "length": 0,  # Minimum length of message to be considered eligible for XP gain
            "starcooldown": 3600,  # Cooldown in seconds for users to give each other stars
            "starmention": True,  # Mention when users add a star
            "starmentionautodelete": 30,  # Auto delete star mention reactions (0 to disable)
            "usepics": False,  # Use Pics instead of embeds for leveling, Embeds are default
            "barlength": 15,  # Progress bar length for embed profiles
            "autoremove": False,  # Remove previous role on level up
            "stackprestigeroles": True,  # Toggle whether to stack prestige roles
            "muted": True,  # Ignore XP while being muted in voice
            "solo": True,  # Ignore XP while in a voice chat alone
            "deafened": True,  # Ignore XP while deafened in a voice chat
            "invisible": True,  # Ignore XP while status is invisible in voice chat
            "notifydm": False,  # Toggle notify member of level up in DMs
            "mention": False,  # Toggle whether to mention the user
            "notifylog": None,  # Notify member of level up in a set channel
            "notify": True,  # Toggle whether to notify member of levelups if notify log channel is not set,
            "showbal": True,  # Show economy balance
        }
        default_global = {"ignored_guilds": [], "cache_seconds": 15, "render_gifs": False}
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        self.threadpool = ThreadPoolExecutor(thread_name_prefix="levelup")

        # Main cache
        self.data = {}

        # Global conf cache
        self.ignored_guilds = []
        self.cache_seconds = 15
        self.render_gifs = False
        self.bgdata = {
            "img": None,
            "names": []
        }
        self.fdata = {
            "img": None,
            "names": []
        }

        # Guild id's as strings, user id's as strings
        self.lastmsg = {}  # Last sent message for users
        self.voice = {}  # Voice channel info
        self.stars = {}  # Keep track of star cooldowns
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
        if str(guild.id) in self.ignored_guilds:
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

        if guild.id not in self.data:
            await self.initialize()

        if chan.id in self.data[gid]["ignoredchannels"]:
            return
        if giver.id in self.data[gid]["ignoredusers"]:
            return

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

        if not self.data[gid]["starmention"]:
            return
        del_after = self.data[gid]["starmentionautodelete"]
        star_giver = f"**{giver.name}** "
        star_reciever = f" **{receiver.name}**!"
        if not chan.permissions_for(guild.me).send_messages:
            return
        with contextlib.suppress(discord.HTTPException):
            if del_after:
                await chan.send(star_giver + _("just gave a star to") + star_reciever, del_after=del_after)
            else:
                await chan.send(star_giver + _("just gave a star to") + star_reciever)

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
        # Check if cog is disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # Check whether the message author isn't on allowlist/blocklist
        if not await self.bot.allowed_by_whitelist_blacklist(message.author):
            return
        gid = message.guild.id
        uid = message.author.id
        cid = message.channel.id
        if gid not in self.data:
            await self.initialize()
        if uid in self.data[gid]["ignoredusers"]:
            return
        if cid in self.data[gid]["ignoredchannels"]:
            return
        await self.message_handler(message)

    async def initialize(self):
        self.ignored_guilds = await self.config.ignored_guilds()
        self.cache_seconds = await self.config.cache_seconds()
        self.render_gifs = await self.config.render_gifs()
        allclean = []
        for guild in self.bot.guilds:
            gid = guild.id
            data = await self.config.guild(guild).all()
            cleaned, newdata = self.cleanup(data.copy())
            if cleaned:
                data = newdata
                for i in cleaned:
                    if i not in allclean:
                        allclean.append(i)
                log.info(f"Cleaned up {guild.name} config")
            if gid not in self.data:
                self.data[gid] = data
                self.stars[gid] = {}
                self.voice[gid] = {}
                self.lastmsg[gid] = {}
        if allclean and self.first_run:
            log.info(allclean)
            await self.save_cache()
        if self.first_run:
            log.info("Config initialized")
        self.first_run = False

    @staticmethod
    def cleanup(data: dict) -> tuple:
        conf = data.copy()
        if isinstance(conf["channelbonuses"]["msg"], list):
            conf["channelbonuses"]["msg"] = {}
        if isinstance(conf["channelbonuses"]["voice"], list):
            conf["channelbonuses"]["voice"] = {}
        cleaned = []
        # Check prestige data
        if conf["prestigedata"]:
            for prestige_level, prestige_data in conf["prestigedata"].items():
                # Make sure emoji data is a dict
                if isinstance(prestige_data["emoji"], dict):
                    continue
                # Fix old string emoji data
                conf["prestigedata"][prestige_level]["emoji"] = {"str": prestige_data["emoji"], "url": None}
                t = "prestige data fix"
                if t not in cleaned:
                    cleaned.append(t)

        # Check players
        for uid, user in conf["users"].items():
            # Fix any missing keys
            if "full" not in user:
                conf["users"][uid]["full"] = True
                cleaned.append("background not in playerstats")
            if "background" not in user:
                conf["users"][uid]["background"] = None
                cleaned.append("background not in playerstats")
            if "stars" not in user:
                conf["users"][uid]["stars"] = 0
                cleaned.append("stars not in playerstats")
            if "colors" not in user:
                conf["users"][uid]["colors"] = {"name": None, "stat": None, "levelbar": None}
                cleaned.append("colors not in playerstats")
            if "levelbar" not in conf["users"][uid]["colors"]:
                conf["users"][uid]["colors"]["levelbar"] = None
                cleaned.append("levelbar not in colors")
            if "font" not in user:
                conf["users"][uid]["font"] = None
                cleaned.append("font not in user")

            # Make sure all related stats are not strings
            for k, v in user.items():
                skip = ["background", "emoji", "full", "colors", "font"]
                if k in skip:
                    continue
                if isinstance(v, int) or isinstance(v, float):
                    continue
                conf["users"][uid][k] = int(v) if v is not None else 0
                cleaned.append(f"{k} stat should be int")

            # Check prestige settings
            if not user["prestige"]:
                continue
            if user["emoji"] is None:
                continue
            # Fix profiles with the old prestige emoji string
            if isinstance(user["emoji"], str):
                conf["users"][uid]["emoji"] = {"str": user["emoji"], "url": None}
                cleaned.append("old emoji schema in profile")
            prest_key = str(user["prestige"])
            if prest_key not in data["prestigedata"]:
                continue
            # See if there are updated prestige settings to get the new url from
            if conf["users"][uid]["emoji"]["url"] != data["prestigedata"][prest_key]["emoji"]["url"]:
                conf["users"][uid]["emoji"]["url"] = data["prestigedata"][prest_key]["emoji"]["url"]
                cleaned.append("updated profile emoji url")
        return cleaned, data

    async def save_cache(self, target_guild: discord.guild = None):
        if not target_guild:
            await self.config.ignored_guilds.set(self.ignored_guilds)
            await self.config.cache_seconds.set(self.cache_seconds)
            await self.config.render_gifs.set(self.render_gifs)

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
            "stars": 0,
            "background": None,
            "full": True,
            "colors": {"name": None, "stat": None, "levelbar": None},
            "font": None
        }

    async def check_levelups(self, guild_id: int, user_id: str, message: discord.Message = None):
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
        await self.level_up(guild, user_id, maybe_new_level, background, message)

    # User has leveled up, send message and check if any roles are associated with it
    async def level_up(
            self, guild: discord.guild, user: str, new_level: int, bg: str = None, message: discord.Message = None):
        t1 = monotonic()
        conf = self.data[guild.id]
        levelroles = conf["levelroles"]
        roleperms = guild.me.guild_permissions.manage_roles
        autoremove = conf["autoremove"]
        dm = conf["notifydm"]
        mention = conf["mention"]
        channel = conf["notifylog"]
        notify = conf["notify"]

        channel = guild.get_channel(channel) if channel else None
        if message and not channel:
            channel = message.channel

        perms = [
            channel.permissions_for(guild.me).send_messages if channel else False,
            channel.permissions_for(guild.me).attach_files if channel else False,
            channel.permissions_for(guild.me).embed_links if channel else False
        ]

        usepics = conf["usepics"]
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
            if notify:
                if dm:
                    dmtxt = _("You have just reached level ") + str(new_level) + _(" in ") + guild.name + "!"
                    dmembed = discord.Embed(description=dmtxt, color=member.color)
                    dmembed.set_thumbnail(url=pfp)
                    try:
                        await member.send(embed=dmembed)
                    except discord.Forbidden:
                        pass
                elif all(perms) and channel:
                    channeltxt = _("Just reached level ") + str(new_level) + "!"
                    channelembed = discord.Embed(description=channeltxt, color=member.color)
                    channelembed.set_author(name=name, icon_url=pfp)
                    if mention:
                        await channel.send(mentionuser, embed=channelembed)
                    else:
                        await channel.send(embed=channelembed)

        else:
            # Generate LevelUP Image
            banner = bg if bg else await self.get_banner(member)

            color = str(member.colour)
            if color == "#000000":  # Don't use default color
                color = str(discord.Color.random())
            color = hex_to_rgb(color)
            font = conf["users"][str(user)]["font"]
            args = {
                'bg_image': banner,
                'profile_image': pfp,
                'level': new_level,
                'color': color,
                'font_name': font
            }
            img = await self.gen_levelup_img(args)
            temp = BytesIO()
            temp.name = f"{member.id}.webp"
            img.save(temp, format="WEBP")
            temp.seek(0)
            file = discord.File(temp)

            if notify:
                if dm:
                    txt = _("You just leveled up in ") + guild.name
                    try:
                        await member.send(txt, file=file)
                    except discord.Forbidden:
                        pass
                elif all(perms) and channel:
                    if mention:
                        await channel.send(f"**{mentionuser}" + _(" just leveled up!**"), file=file)
                    else:
                        await channel.send(f"**{name}" + _(" just leveled up!**"), file=file)

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
        channel_bonuses = conf["channelbonuses"]["msg"]
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
            xp_to_give = xp
            if bonusrole:
                bonusrange = bonuses[bonusrole]
                bmin = int(bonusrange[0])
                bmax = int(bonusrange[1]) + 1
                bxp = random.choice(range(bmin, bmax))
                xp_to_give += bxp
            cid = str(message.channel.id)
            if cid in channel_bonuses:
                bonuschannelrange = channel_bonuses[cid]
                bmin = int(bonuschannelrange[0])
                bmax = int(bonuschannelrange[1]) + 1
                bxp = random.choice(range(bmin, bmax))
                xp_to_give += bxp
            self.lastmsg[gid][uid] = now
            self.data[gid]["users"][uid]["xp"] += xp_to_give

        self.data[gid]["users"][uid]["messages"] += 1
        await self.check_levelups(gid, uid, message)

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
        channel_bonuses = conf["channelbonuses"]["voice"]
        bonusrole = None
        async for member in AsyncIter(guild.members):
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
                if bonusrole:
                    bonusrange = bonuses[bonusrole]
                    bmin = int(bonusrange[0])
                    bmax = int(bonusrange[1]) + 1
                    bxp = random.choice(range(bmin, bmax))
                    xp_to_give += bxp
                cid = str(voice_state.channel.id)
                if cid in channel_bonuses:
                    bonuschannelrange = channel_bonuses[cid]
                    bmin = int(bonuschannelrange[0])
                    bmax = int(bonuschannelrange[1]) + 1
                    bxp = random.choice(range(bmin, bmax))
                    xp_to_give += bxp
                self.data[gid]["users"][uid]["xp"] += xp_to_give
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
        # if self.first_run:
        #     await self.initialize()
        log.info("Voice checker running")

    @tasks.loop(minutes=3)
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
        usepics = conf["usepics"]
        levelroles = conf["levelroles"]
        igchannels = conf["ignoredchannels"]
        igroles = conf["ignoredroles"]
        igusers = conf["ignoredusers"]
        prestige = conf["prestige"]
        pdata = conf["prestigedata"]
        stacking = conf["stackprestigeroles"]
        xp = conf["xp"]
        xpbonus = conf["rolebonuses"]["msg"]
        xpchanbonus = conf["channelbonuses"]["msg"]
        voicexp = conf["voicexp"]
        voicexpbonus = conf["rolebonuses"]["voice"]
        voicechanbonus = conf["channelbonuses"]["voice"]
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
        lvlmessage = conf["notify"]
        mention = conf["mention"]
        starcooldown = conf["starcooldown"]
        starmention = conf["starmention"]
        stardelete = conf["starmentionautodelete"] if conf["starmentionautodelete"] else "Disabled"
        showbal = conf["showbal"]
        barlength = conf["barlength"]
        sc = time_formatter(starcooldown)
        notifylog = ctx.guild.get_channel(conf["notifylog"])
        if not notifylog:
            notifylog = conf["notifylog"]
        else:
            notifylog = notifylog.mention
        ptype = "Image" if usepics else "Embed"

        msg = f"**Cog**\n" \
              f"`Profile Type:      `{ptype}\n" \
              f"`Include Balance:   `{showbal}\n" \
              f"`Progress Bar:      `{barlength} chars long\n" \
              f"**Messages**\n" \
              f"`Message XP:        `{xp[0]}-{xp[1]}\n" \
              f"`Min Msg Length:    `{length}\n" \
              f"`Cooldown:          `{cooldown} seconds\n" \
              f"**Voice**\n" \
              f"`Voice XP:          `{voicexp} per minute\n" \
              f"`Ignore Muted:      `{muted}\n" \
              f"`Ignore Solo:       `{solo}\n" \
              f"`Ignore Deafened:   `{deafended}\n" \
              f"`Ignore Invisible:  `{invisible}\n" \
              f"**Level Algorithm**\n" \
              f"`Base Multiplier:   `{base}\n" \
              f"`Exp Multiplier:    `{exp}\n" \
              f"**LevelUps**\n" \
              f"`LevelUp Notify:    `{lvlmessage}\n" \
              f"`Notify in DMs:     `{notifydm}\n" \
              f"`Mention User:      `{mention}\n" \
              f"`AutoRemove Roles:  `{autoremove}\n" \
              f"`LevelUp Channel:   `{notifylog}\n" \
              f"**Stars**\n" \
              f"`Cooldown:          `{sc}\n" \
              f"`React Mention:     `{starmention}\n" \
              f"`MentionAutoDelete: `{stardelete}\n"
        if levelroles:
            msg += "**Levels**\n"
            for level, role_id in levelroles.items():
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                msg += f"`Level {level}: `{role}\n"
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
                msg += f"`Prestige {level}: `{role} - {emoji['str']}\n"
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
                text += f"{role.mention} - {bonusrange}\n"
            if text:
                embed.add_field(
                    name=_("Voice XP Bonus Roles"),
                    value=text
                )
        if voicechanbonus:
            text = ""
            for cid, bonusrange in voicechanbonus.items():
                chan = ctx.guild.get_channel(int(cid))
                if not chan:
                    continue
                text += f"{chan.mention} - {bonusrange}"
            if text:
                embed.add_field(
                    name=_("Voice XP Bonus Channels"),
                    value=text
                )
        if xpbonus:
            text = ""
            for rid, bonusrange in xpbonus.items():
                role = ctx.guild.get_role(int(rid))
                if not role:
                    continue
                text += f"{role.mention} - {bonusrange}\n"
            if text:
                embed.add_field(
                    name=_("Message XP Bonus Roles"),
                    value=text
                )
        if xpchanbonus:
            text = ""
            for cid, bonusrange in xpchanbonus.items():
                chan = ctx.guild.get_channel(int(cid))
                if not chan:
                    continue
                text += f"{chan.mention} - {bonusrange}"
            if text:
                embed.add_field(
                    name=_("Message XP Bonus Channels"),
                    value=text
                )
        if igroles:
            ignored = [ctx.guild.get_role(rid).mention for rid in igroles if ctx.guild.get_role(rid)]
            text = humanize_list(ignored)
            if ignored:
                embed.add_field(
                    name=_("Ignored Roles"),
                    value=text,
                    inline=False
                )
        if igchannels:
            ignored = [ctx.guild.get_channel(cid).mention for cid in igchannels if ctx.guild.get_channel(cid)]
            text = humanize_list(ignored)
            if ignored:
                embed.add_field(
                    name=_("Ignored Channels"),
                    value=text,
                    inline=False
                )
        if igusers:
            ignored = [ctx.guild.get_member(uid).mention for uid in igusers if ctx.guild.get_member(uid)]
            text = humanize_list(ignored)
            if ignored:
                embed.add_field(
                    name=_("Ignored Users"),
                    value=text,
                    inline=False
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

    @admin_group.command(name="profilecache")
    @commands.is_owner()
    async def set_profile_cache(self, ctx: commands.Context, seconds: int):
        """
        Set how long to keep profile images in cache
        When a user runs the profile command their generated image will be stored in cache to be reused for X seconds

        If profile embeds are enabled this setting will have no effect
        Anything less than 10 seconds will effectively disable the cache
        """
        self.cache_seconds = int(seconds)
        await ctx.tick()
        await self.save_cache()

    @admin_group.command(name="rendergifs")
    @commands.is_owner()
    async def toggle_gif_render(self, ctx: commands.Context):
        """Toggle whether to render profiles as gifs if the user's discord profile is animated"""
        r = self.render_gifs
        if r:
            self.render_gifs = False
            await ctx.send(_("I will no longer render profiles with GIFs"))
        else:
            self.render_gifs = True
            await ctx.send(_("I will now render GIFs with user profiles"))
        await ctx.tick()
        await self.save_cache()

    @admin_group.command(name="globalreset")
    @commands.is_owner()
    async def reset_all(self, ctx: commands.Context):
        """Reset cog data for all guilds"""
        text = _("Are you sure you want to reset all stats and settings for the entire cog?") + " (y/n)"
        msg = await ctx.send(text)
        yes = await confirm(ctx)
        if not yes:
            text = _("Not resetting all guilds")
            return await msg.edit(content=text)
        for gid in self.data.copy():
            self.data[gid] = self.config.defaults["GUILD"]
        await msg.edit(content=_("Settings and stats for all guilds have been reset"))
        await ctx.tick()
        await self.save_cache()

    @admin_group.command(name="guildreset")
    async def reset_guild(self, ctx: commands.Context):
        """Reset cog data for this guild"""
        text = _("Are you sure you want to reset all stats and settings for this guild?") + " (y/n)"
        msg = await ctx.send(text)
        yes = await confirm(ctx)
        if not yes:
            text = _("Not resetting config")
            return await msg.edit(content=text)
        self.data[ctx.guild.id] = self.config.defaults["GUILD"]
        await msg.edit(content=_("All settings and stats reset"))
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @admin_group.command(name="statreset")
    async def reset_xp(self, ctx: commands.Context):
        """Reset everyone's exp and level"""
        users = self.data[ctx.guild.id]["users"].copy()
        count = len(users.keys())
        text = _("Are you sure you want to reset ") + str(count) + _(" users' stats?") + " (y/n)"
        text += _("\nThis will reset their exp, voice time, messages, level, prestige and stars")
        msg = await ctx.send(text)
        yes = await confirm(ctx)
        if not yes:
            text = _("Not resetting user stats")
            return await msg.edit(content=text)
        async with ctx.typing():
            deleted = 0
            for uid, data in users.items():
                self.data[ctx.guild.id]["users"][uid]["xp"] = 0
                self.data[ctx.guild.id]["users"][uid]["voice"] = 0
                self.data[ctx.guild.id]["users"][uid]["messages"] = 0
                self.data[ctx.guild.id]["users"][uid]["level"] = 0
                self.data[ctx.guild.id]["users"][uid]["prestige"] = 0
                self.data[ctx.guild.id]["users"][uid]["stars"] = 0
                deleted += 1
            text = _("Reset stats for ") + str(deleted) + _(" users")
            await msg.edit(content=text)
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @admin_group.command(name="view")
    async def admin_view(self, ctx: commands.Context):
        """View current loop times and cached data"""
        cache = [
            self.data.copy(),
            self.voice.copy(),
            self.stars.copy(),
            self.profiles.copy()
        ]
        cachesize = self.get_size(sum(sys.getsizeof(i) for i in cache))
        lt = self.looptimes
        ct = self.cache_seconds

        em = discord.Embed(description=_("Cog Stats"), color=ctx.author.color)

        looptimes = _("`Voice Checker: `") + humanize_number(lt["checkvoice"]) + "ms\n"
        looptimes += _("`Cache Dumping: `") + humanize_number(lt["cachedump"]) + "ms\n"
        looptimes += _("`Lvl Assign:    `") + humanize_number(lt["lvlassignavg"]) + "ms\n"
        em.add_field(name=_("Loop Times"), value=looptimes, inline=False)

        cachetxt = _("`Profile Cache Time: `") + (_("Disabled\n") if not ct else f"{humanize_number(ct)} seconds\n")
        cachetxt += _("`Cache Size:         `") + cachesize
        em.add_field(name=_("Cache"), value=cachetxt, inline=False)

        render = _("(Disabled)")
        txt = _("Profiles will be static regardless of if the user has an animated profile")
        if self.render_gifs:
            render = _("(Enabled)")
            txt = _("Users with animated profiles will render as a gif")

        em.add_field(name=_("GIF Rendering ") + render, value=txt, inline=False)

        await ctx.send(embed=em)

    @admin_group.command(name="globalbackup")
    @commands.is_owner()
    async def backup_cog(self, ctx):
        """Create a backup of the LevelUp config"""
        buffer = BytesIO(json.dumps(self.data).encode())
        buffer.name = f"LevelUp_GLOBAL_config_{int(datetime.now().timestamp())}.json"
        buffer.seek(0)
        file = discord.File(buffer)
        await ctx.send("Here is your LevelUp config", file=file)

    @admin_group.command(name="guildbackup")
    @commands.is_owner()
    async def backup_guild(self, ctx):
        """Create a backup of the LevelUp config"""
        buffer = BytesIO(json.dumps(self.data[ctx.guild.id]).encode())
        buffer.name = f"LevelUp_guild_config_{int(datetime.now().timestamp())}.json"
        buffer.seek(0)
        file = discord.File(buffer)
        await ctx.send("Here is your LevelUp config", file=file)

    @admin_group.command(name="globalrestore")
    @commands.is_owner()
    async def restore_cog(self, ctx: commands.Context):
        """
        Restore a global backup

        Attach the .json file to the command message to import
        """
        if not ctx.message.attachments:
            return await ctx.send(_("Attach your backup file to the message when using this command."))

        attachment_url = ctx.message.attachments[0].url
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
        except Exception as e:
            return await ctx.send(f"Error:{box(str(e), lang='python')}")

        if not all([key.isdigit() for key in config.keys()]):
            return await ctx.send(_("This is an invalid global config!"))

        for gid, data in config.items():
            cleaned, newdata = self.cleanup(data.copy())
            if cleaned:
                data = newdata

            self.data[int(gid)] = data

        await self.save_cache()
        await ctx.send(_("Config restored from backup file!"))

    @admin_group.command(name="guildrestore")
    @commands.guildowner()
    async def restore_guild(self, ctx: commands.Context):
        """
        Restore a guild backup

        Attach the .json file to the command message to import
        """
        if not ctx.message.attachments:
            return await ctx.send(_("Attach your backup file to the message when using this command."))

        attachment_url = ctx.message.attachments[0].url
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
        except Exception as e:
            return await ctx.send(f"Error:{box(str(e), lang='python')}")

        default = self.config.defaults["GUILD"]
        if not all([key in default for key in config.keys()]):
            return await ctx.send(_("This is an invalid guild config!"))
        cleaned, newdata = self.cleanup(config.copy())
        if cleaned:
            config = newdata
        self.data[ctx.guild.id] = config
        await self.save_cache()
        await ctx.send(_("Config restored from backup file!"))

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
                    self.data[guild.id]["users"][user_id]["stars"] = int(userinfo["rep"]) if userinfo["rep"] else 0
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
        """
        Delete users no longer in the server

        Also cleans up any missing keys or discrepancies in the config
        """
        guild = ctx.guild
        members = [u.id for u in guild.members]
        cleanup = []
        savedusers = self.data[ctx.guild.id]["users"].copy()
        for user_id in savedusers:
            if int(user_id) not in members:
                cleanup.append(user_id)
        cleaned = 0
        for uid in cleanup:
            del self.data[ctx.guild.id]["users"][uid]
            cleaned += 1
        cleaned_data, newdat = self.cleanup(self.data[ctx.guild.id].copy())
        if not cleanup and not cleaned:
            return await ctx.send(_("Nothing to clean"))
        if cleaned:
            await ctx.send(
                _(
                    f"Deleted {cleaned} user IDs from the config that are no longer in the server.\n"
                    f"Also cleaned {len(cleaned_data)} config discrepancies in the process."
                )
            )
        else:
            await ctx.send(_(f"Deleted {cleaned} user IDs from the config that are no longer in the server"))
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

        This bonus applies to message xp

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
            await ctx.send(_("Bonus xp for ") + role.mention + _(" has been removed"))
        else:
            self.data[ctx.guild.id]["rolebonuses"]["msg"][rid] = xp
            await ctx.send(_("Bonus xp for ") + role.mention + _(" has been set to ") + str(xp))
        await self.save_cache(ctx.guild)

    @message_group.command(name="channelbonus")
    async def msg_chan_bonus(self, ctx: commands.Context, channel: discord.TextChannel, min_xp: int, max_xp: int):
        """
        Add a range of bonus XP to apply to certain channels

        This bonus applies to message xp

        Set both min and max to 0 to remove the role bonus
        """
        if not channel:
            return await ctx.send(_("I cannot find that channel"))
        if min_xp > max_xp:
            return await ctx.send(_("Max xp needs to be higher than min xp"))
        cid = str(channel.id)
        xp = [min_xp, max_xp]
        cb = self.data[ctx.guild.id]["channelbonuses"]["msg"]
        if not min_xp and not max_xp:
            if cid not in cb:
                return await ctx.send(_("That channel has no bonus xp associated with it"))
            del self.data[ctx.guild.id]["channelbonuses"]["msg"][cid]
            await ctx.send(_("Bonus xp for ") + channel.mention + _(" has been removed"))
        else:
            self.data[ctx.guild.id]["channelbonuses"]["msg"][cid] = xp
            await ctx.send(_("Bonus xp for ") + channel.mention + _(" has been set to ") + str(xp))
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
            await ctx.send(_("Bonus xp for ") + role.mention + _(" has been removed"))
        else:
            self.data[ctx.guild.id]["rolebonuses"]["voice"][rid] = xp
            await ctx.send(_("Bonus xp for ") + role.mention + _(" has been set to ") + str(xp))
        await self.save_cache(ctx.guild)

    @voice_group.command(name="channelbonus")
    async def voice_chan_bonus(self, ctx: commands.Context, channel: discord.VoiceChannel, min_xp: int, max_xp: int):
        """
        Add a range of bonus XP to apply to certain channels

        This bonus applies to voice time xp

        Set both min and max to 0 to remove the role bonus
        """
        if not channel:
            return await ctx.send(_("I cannot find that role"))
        if min_xp > max_xp:
            return await ctx.send(_("Max xp needs to be higher than min xp"))
        cid = str(channel.id)
        xp = [min_xp, max_xp]
        cb = self.data[ctx.guild.id]["channelbonuses"]["voice"]
        if not min_xp and not max_xp:
            if cid not in cb:
                return await ctx.send(_("That channel has no bonus xp associated with it"))
            del self.data[ctx.guild.id]["channelbonuses"]["voice"][cid]
            await ctx.send(_("Bonus xp for ") + channel.mention + _(" has been removed"))
        else:
            self.data[ctx.guild.id]["channelbonuses"]["voice"][cid] = xp
            await ctx.send(_("Bonus xp for ") + channel.mention + _(" has been set to ") + str(xp))
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
    async def add_xp(self, ctx: commands.Context, user_or_role: Union[discord.Member, discord.Role], xp: int):
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

    @lvl_group.command(name="setlevel")
    async def set_user_level(self, ctx: commands.Context, user: discord.Member, level: int):
        """Set a user to a specific level"""
        conf = self.data[ctx.guild.id]
        uid = str(user.id)
        if uid not in conf["users"]:
            return await ctx.send(_("There is no data for that user!"))

        base = conf["base"]
        exp = conf["exp"]
        xp = get_xp(int(level), base, exp)
        conf["users"][uid]["level"] = int(level)
        conf["users"][uid]["xp"] = xp
        await ctx.send(_(f"User {user.name} is now level {level}"))

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
    async def set_exp(self, ctx: commands.Context, exponent_multiplier: Union[int, float]):
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

    @lvl_group.command(name="barlength")
    async def set_bar_length(self, ctx: commands.Context, bar_length: int):
        """Set the progress bar length for embed profiles"""
        conf = self.data[ctx.guild.id]
        if conf["usepics"]:
            text = _("Embed profiles are disabled. Enable them to set the progress bar length with ")
            text += f"`{ctx.prefix}levelset barlength`"
            return await ctx.send(text)
        if not 15 <= bar_length >= 40:
            return await ctx.send(_("Progress bar length must be a minimum of 15 and maximum of 40"))
        self.data[ctx.guild.id]["barlength"] = bar_length
        await ctx.send(_("Progress bar length has been set to ") + str(bar_length))
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
            plt.ylabel(f"Experience Required", fontsize=10)
            plt.title("XP Curve")
            plt.grid(axis="y")
            plt.grid(axis="x")
            result = BytesIO()
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

    @lvl_group.command(name="starmention")
    async def toggle_starmention(self, ctx: commands.Context):
        """
        Toggle star reaction mentions
        Toggle whether the bot mentions that a user reacted to a message with a star
        """
        mention = self.data[ctx.guild.id]["starmention"]
        if mention:
            self.data[ctx.guild.id]["starmention"] = False
            await ctx.send(_("Star reaction mentions **Disabled**"))
        else:
            self.data[ctx.guild.id]["starmention"] = True
            await ctx.send(_("Star reaction mention **Enabled**"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="starmentiondelete")
    async def toggle_starmention_autodelete(self, ctx: commands.Context, deleted_after: int):
        """
        Toggle whether the bot auto-deletes the star mentions
        Set to 0 to disable auto-delete
        """
        self.data[ctx.guild.id]["starmentionautodelete"] = int(deleted_after)
        if deleted_after:
            await ctx.send(_("Star reaction mentions will auto-delete after ") + str(deleted_after) + _(" seconds"))
        else:
            await ctx.send(_("Star reaction mentions will not be deleted"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="levelchannel")
    async def set_level_channel(self, ctx: commands.Context, levelup_channel: discord.TextChannel = None):
        """
        Set LevelUP message channel
        Set a channel for all level up messages to send to
        """
        if not levelup_channel:
            self.data[ctx.guild.id]["notifylog"] = None
            await ctx.send(
                _("LevelUp channel has been **Disabled**\n"
                  "level up messages will now happen in the channel the user is in")
            )
        else:
            perms = levelup_channel.permissions_for(ctx.guild.me).send_messages
            if not perms:
                return await ctx.send(_(f"I do not have permission to send messages to that channel."))
            self.data[ctx.guild.id]["notifylog"] = levelup_channel.id
            await ctx.send(_(f"LevelUp channel has been set to {levelup_channel.mention}"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="showbalance")
    async def toggle_profile_balance(self, ctx: commands.Context):
        """Toggle whether to show user's economy credit balance in their profile"""
        showbal = self.data[ctx.guild.id]["showbal"]
        if showbal:
            self.data[ctx.guild.id]["showbal"] = False
            await ctx.send(_("I will no longer include economy balance in user profiles"))
        else:
            self.data[ctx.guild.id]["showbal"] = True
            await ctx.send(_("I will now include economy balance in user profiles"))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="levelnotify")
    async def toggle_levelup_notifications(self, ctx: commands.Context):
        """Toggle the level up message when a user levels up"""
        notify = self.data[ctx.guild.id]["notify"]
        if notify:
            self.data[ctx.guild.id]["notify"] = False
            await ctx.send("LevelUp notifications have been **Disabled**")
        else:
            self.data[ctx.guild.id]["notify"] = True
            await ctx.send("LevelUp notifications have been **Enabled**")
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

    @prestige_settings.command(name="autoremove")
    async def toggle_prestige_autoremove(self, ctx: commands.Context):
        """Automatic removal of previous prestige level roles"""
        autoremove = self.data[ctx.guild.id]["stackprestigeroles"]
        if autoremove:
            self.data[ctx.guild.id]["stackprestigeroles"] = False
            await ctx.send(_("Automatic prestige role removal **Disabled**"))
        else:
            self.data[ctx.guild.id]["stackprestigeroles"] = True
            await ctx.send(_("Automatic prestige role removal **Enabled**"))
        await self.save_cache(ctx.guild)

    @staticmethod
    def get_twemoji(emoji: str):
        # Thanks Fixator!
        emoji_unicode = []
        for char in emoji:
            char = hex(ord(char))[2:]
            emoji_unicode.append(char)
        if "200d" not in emoji_unicode:
            emoji_unicode = list(filter(lambda c: c != "fe0f", emoji_unicode))
        emoji_unicode = "-".join(emoji_unicode)
        return f"https://twemoji.maxcdn.com/v/latest/72x72/{emoji_unicode}.png"

    @prestige_settings.command(name="add")
    async def add_pres_data(
            self,
            ctx: commands.Context,
            prestige_level: str,
            role: discord.Role,
            emoji: Union[discord.Emoji, discord.PartialEmoji, str]
    ):
        """
        Add a prestige level role
        Add a role and emoji associated with a specific prestige level

        When a user prestiges, they will get that role and the emoji will show on their profile
        """
        if not prestige_level.isdigit():
            return await ctx.send(_("prestige_level must be a number!"))
        url = self.get_twemoji(emoji) if isinstance(emoji, str) else emoji.url
        self.data[ctx.guild.id]["prestigedata"][prestige_level] = {
            "role": role.id,
            "emoji": {"str": str(emoji), "url": url}
        }
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @commands.command(name="etest", hidden=True)
    async def e_test(self, ctx, emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        """Test emoji urls"""
        if isinstance(emoji, str):
            em = self.get_twemoji(emoji)
            await ctx.send(em)
        else:
            await ctx.send(emoji.url)

    @prestige_settings.command(name="del")
    async def del_pres_data(self, ctx: commands.Context, prestige_level: str):
        """Delete a prestige level role"""
        if not prestige_level.isdigit():
            return await ctx.send(_("prestige_level must be a number!"))
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
        if guild_id in self.ignored_guilds:
            self.ignored_guilds.remove(guild_id)
            await ctx.send(_("Guild removed from ignore list"))
        else:
            self.ignored_guilds.append(guild_id)
            await ctx.send(_("Guild added to ignore list"))
        await self.save_cache()

    @ignore_group.command(name="channel")
    async def ignore_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Add/Remove a channel in the ignore list
        Channels in the ignore list don't gain XP

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
        Roles in the ignore list don't gain XP

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
        Members in the ignore list don't gain XP

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
        level = user["level"]
        level = level + 1
        xp = get_xp(level, base, exp)
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
        level = user["level"]
        level = level - 1
        xp = get_xp(level, base, exp)
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

    @commands.command(name="forcesave", hidden=True)
    @commands.is_owner()
    async def force_save(self, ctx):
        """Force save the cache"""
        await self.save_cache()
        await ctx.tick()
