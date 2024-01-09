import asyncio
import contextlib
import json
import logging
import math
import random
import re
import sys
from datetime import datetime
from io import BytesIO
from time import monotonic, perf_counter
from typing import Dict, List, Optional, Set, Tuple, Union

import discord
import plotly.graph_objects as go
from aiohttp import ClientSession, ClientTimeout
from discord.ext import tasks
from perftracker import get_stats, perf
from redbot.core import Config, VersionInfo, commands, version_info
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    humanize_timedelta,
)
from redbot.core.utils.predicates import MessagePredicate
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from levelup.utils.formatter import (
    get_attachments,
    get_content_from_url,
    get_level,
    get_next_reset,
    get_twemoji,
    get_xp,
    hex_to_rgb,
    time_formatter,
    time_to_level,
)

from .abc import CompositeMetaClass
from .common import constants
from .common.base import UserCommands
from .common.generator import Generator

log = logging.getLogger("red.vrt.levelup")
_ = Translator("LevelUp", __file__)


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

# redgettext -D levelup.py common/generator.py common/base.py utils/formatter.py --command-docstring


@cog_i18n(_)
class LevelUp(UserCommands, Generator, commands.Cog, metaclass=CompositeMetaClass):
    """
    Your friendly neighborhood leveling system

    Earn experience by chatting in text and voice channels, compare levels with your friends, customize your profile and view various leaderboards!
    """

    __author__ = "Vertyco#0117"
    __version__ = "3.11.12"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = (
            f"{helpcmd}\n"
            f"Cog Version: {self.__version__}\n"
            f"Author: {self.__author__}\n"
            f"Contributors: aikaterna#1393"
        )
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        deleted = False
        for gid in self.data.copy().keys():
            if str(user_id) in self.data[gid]["users"]:
                del self.data[gid]["users"][user_id]
                deleted = True
        if deleted:
            await self.save_cache()

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        self.config.register_guild(**constants.default_guild)
        self.config.register_global(**constants.default_global)

        # Main cache (Guild ID keys are ints)
        self.data = {}

        # Global conf cache
        self.ignored_guilds = []
        self.cache_seconds = 15
        self.render_gifs = False

        # Keep background compilation cached
        self.bgdata = {"img": None, "names": []}
        # Keep font compilation cached
        self.fdata = {"img": None, "names": []}

        # Guild IDs as strings, user IDs as strings
        self.lastmsg = {}  # Last sent message for users
        self.voice = {}  # Voice channel info
        self.stars = {}  # Keep track of star cooldowns
        self.first_run = True
        self.profiles = {}

        # For importing user levels from Fixator's Leveler cog
        self._db_ready = False
        self.client = None
        self.db = None

        # Constants
        self.loading = "https://i.imgur.com/l3p6EMX.gif"
        self.dpy2 = True if version_info >= VersionInfo.from_str("3.5.0") else False
        self.daymap = {
            0: _("Monday"),
            1: _("Tuesday"),
            2: _("Wednesday"),
            3: _("Thursday"),
            4: _("Friday"),
            5: _("Saturday"),
            6: _("Sunday"),
        }

        # Loopies
        self.cache_dumper.start()
        self.voice_checker.start()
        self.weekly_checker.start()

    def cog_unload(self):
        self.cache_dumper.cancel()
        self.voice_checker.cancel()
        self.weekly_checker.cancel()
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

        uid = str(receiver.id)
        if uid not in self.data[gid]["users"]:
            return

        self.data[gid]["users"][uid]["stars"] += 1
        if self.data[gid]["weekly"]["on"]:
            weekly_users = self.data[gid]["weekly"]["users"]
            if uid not in weekly_users:
                self.init_user_weekly(gid, uid)
            self.data[gid]["weekly"]["users"][uid]["stars"] += 1

        if not self.data[gid]["starmention"]:
            return
        del_after = self.data[gid]["starmentionautodelete"]
        star_giver = f"**{giver.name}** "
        star_reciever = f" **{receiver.name}**!"
        if not chan.permissions_for(guild.me).send_messages:
            return
        if chan.id in self.data[gid]["ignoredchannels"]:
            return
        if giver.id in self.data[gid]["ignoredusers"]:
            return
        with contextlib.suppress(discord.HTTPException):
            if del_after:
                await chan.send(
                    star_giver + _("just gave a star to") + star_reciever,
                    delete_after=del_after,
                )
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
        # Ignore webhooks
        if not isinstance(message.author, discord.Member):
            return
        # Check if cog is disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # Check whether the message author isn't on allowlist/blocklist
        if not await self.bot.allowed_by_whitelist_blacklist(message.author):
            return
        gid = message.guild.id
        if gid not in self.data:
            await self.initialize()
        if message.author.id in self.data[gid]["ignoredusers"]:
            return
        if message.channel.id in self.data[gid]["ignoredchannels"]:
            return
        await self.message_handler(message)

    @perf()
    async def initialize(self):
        self.ignored_guilds = await self.config.ignored_guilds()
        self.cache_seconds = await self.config.cache_seconds()
        self.render_gifs = await self.config.render_gifs()
        allclean = []
        for guild in self.bot.guilds:
            gid = guild.id
            if gid in self.data:  # Already in cache
                continue
            data = await self.config.guild(guild).all()
            cleaned, newdata = self.cleanup(data.copy())
            if cleaned:
                data = newdata
                for i in cleaned:
                    if i not in allclean:
                        allclean.append(i)
                log.info(f"Cleaned up {guild.name} config")
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
                conf["prestigedata"][prestige_level]["emoji"] = {
                    "str": prestige_data["emoji"],
                    "url": None,
                }
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
                conf["users"][uid]["colors"] = {
                    "name": None,
                    "stat": None,
                    "levelbar": None,
                }
                cleaned.append("colors not in playerstats")
            if "levelbar" not in conf["users"][uid]["colors"]:
                conf["users"][uid]["colors"]["levelbar"] = None
                cleaned.append("levelbar not in colors")
            if "font" not in user:
                conf["users"][uid]["font"] = None
                cleaned.append("font not in user")
            if "blur" not in user:
                conf["users"][uid]["blur"] = False
                cleaned.append("blur not in user")

            # Make sure all related stats are not strings
            for k, v in user.items():
                skip = ["background", "emoji", "full", "colors", "font", "blur"]
                if k in skip:
                    continue
                if isinstance(v, int) or isinstance(v, float):
                    continue
                conf["users"][uid][k] = int(v.replace(",", "")) if v is not None else 0
                cleaned.append(f"{k} stat should be int")

            # Check prestige settings
            if not user["prestige"]:
                continue
            if user["emoji"] is None:
                continue
            # Fix profiles with the old prestige emoji string
            if isinstance(user["emoji"], str):
                conf["users"][uid]["emoji"] = {
                    "str": user["emoji"],
                    "url": None,
                }
                cleaned.append("old emoji schema in profile")
            prest_key = str(user["prestige"])
            if prest_key not in data["prestigedata"]:
                continue
            # See if there are updated prestige settings to get the new url from
            if conf["users"][uid]["emoji"]["url"] != data["prestigedata"][prest_key]["emoji"]["url"]:
                conf["users"][uid]["emoji"]["url"] = data["prestigedata"][prest_key]["emoji"]["url"]
                cleaned.append("updated profile emoji url")
        return cleaned, data

    @perf(max_entries=1000)
    async def save_cache(self, target_guild: discord.Guild = None):
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
            async with self.config.guild(guild).all() as conf:
                for k, v in data.copy().items():
                    conf[k] = v

    def init_user(self, guild_id: int, user_id: str):
        if user_id in self.data[guild_id]["users"]:
            return
        self.data[guild_id]["users"][user_id] = {
            "xp": 0,
            "voice": 0,  # Seconds
            "messages": 0,
            "level": 0,
            "prestige": 0,
            "emoji": None,
            "stars": 0,
            "background": "random",
            "full": True,
            "colors": {"name": None, "stat": None, "levelbar": None},
            "font": None,
            "blur": False,
        }

    def init_user_weekly(self, guild_id: int, user_id: str):
        if user_id in self.data[guild_id]["weekly"]["users"]:
            return
        self.data[guild_id]["weekly"]["users"][user_id] = {
            "xp": 0,
            "voice": 0,  # Seconds,
            "messages": 0,
            "stars": 0,
        }

    def give_star_to_user(self, guild: discord.Guild, user: discord.Member) -> bool:
        if guild.id not in self.data:
            return False
        if str(user.id) not in self.data[guild.id]["users"]:
            return False
        self.data[guild.id]["users"][str(user.id)]["stars"] += 1
        return True

    async def check_levelups(
        self,
        guild_id: int,
        user_id: str,
        message: discord.Message = None,
        channel_obj: discord.TextChannel = None,
    ):
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
        await self.level_up(guild, user_id, maybe_new_level, background, message, channel_obj)

    # User has leveled up, send message and check if any roles are associated with it
    @perf(max_entries=1000)
    async def level_up(
        self,
        guild: discord.Guild,
        user: str,
        new_level: int,
        bg: str = None,
        message: discord.Message = None,
        channel_obj: discord.TextChannel = None,
    ):
        conf = self.data[guild.id]
        levelroles = conf["levelroles"]
        roleperms = guild.me.guild_permissions.manage_roles
        autoremove = conf["autoremove"]
        dm = conf["notifydm"]
        mention = conf["mention"]
        channel = conf["notifylog"]
        notify = conf["notify"]

        channel = guild.get_channel_or_thread(channel) if channel else None
        if message and not channel:
            channel = message.channel
        if channel_obj and not channel:
            channel = channel_obj

        perms = [
            channel.permissions_for(guild.me).send_messages if channel else False,
            channel.permissions_for(guild.me).attach_files if channel else False,
            channel.permissions_for(guild.me).embed_links if channel else False,
        ]

        usepics = conf["usepics"]
        member = guild.get_member(int(user))
        if not member:
            return
        mentionuser = member.mention
        name = member.name
        pfp = None
        try:
            if self.dpy2:
                pfp = member.display_avatar.url
            else:
                pfp = member.avatar_url
        except AttributeError:
            log.warning(f"Failed to get avatar url for {member.name} in {guild.name}. DPY2 = {self.dpy2}")

        # Get roles to be added and removed
        roles_to_add = []
        roles_to_remove = []
        # Role adding/removal
        if not autoremove:  # Level roles stack
            for level, role_id in sorted(levelroles.items(), key=lambda x: x[0]):
                if int(level) <= int(new_level):  # Then give user that role since they should stack
                    role = guild.get_role(int(role_id))
                    if not role:
                        continue
                    if role not in member.roles:
                        roles_to_add.append(role)

        else:  # No stacking so add role and remove the others below that level
            role_applied = False
            if str(new_level) in levelroles:
                role_id = levelroles[str(new_level)]
                role = guild.get_role(int(role_id))
                if role not in member.roles:
                    roles_to_add.append(role)
                    # await member.add_roles(role)
                    role_applied = True

            # Remove any previous roles, but only if a new role was applied
            if new_level > 1 and role_applied:
                for role in member.roles:
                    for level, role_id in levelroles.items():
                        if role.id != role_id:
                            continue
                        if int(level) >= new_level:
                            continue
                        roles_to_remove.append(role)

        new_role = roles_to_add[-1].mention if roles_to_add else None

        # Send levelup messages
        if not usepics:
            if notify:
                if dm:
                    if new_role:
                        txt = _("You have just reached level {} in {} and obtained the {} role!").format(
                            new_level, guild.name, new_role
                        )
                    else:
                        txt = _("You have just reached level {} in {}!").format(new_level, guild.name)
                    dmembed = discord.Embed(description=txt, color=member.color)
                    dmembed.set_thumbnail(url=pfp)
                    try:
                        await member.send(embed=dmembed)
                    except discord.Forbidden:
                        pass
                elif all(perms) and channel:
                    if new_role:
                        txt = _("You have just reached level {} and obtained the {} role!").format(new_level, new_role)
                    else:
                        txt = _("Just reached level {}!").format(new_level)
                    channelembed = discord.Embed(description=txt, color=member.color)
                    channelembed.set_author(name=name, icon_url=pfp)
                    try:
                        if mention:
                            await channel.send(mentionuser, embed=channelembed)
                        else:
                            await channel.send(embed=channelembed)
                    except Exception as e:
                        log.warning(f"Failed to send levelup alert to {channel.name}!", exc_info=e)

        else:
            # Generate LevelUP Image
            banner = bg if bg else await self.get_banner(member)

            color = str(member.colour)
            if color == "#000000":  # Don't use default color
                color = str(discord.Color.random())
            color = hex_to_rgb(color)
            font = conf["users"][str(user)]["font"]
            args = {
                "bg_image": banner,
                "profile_image": pfp,
                "level": new_level,
                "color": color,
                "font_name": font,
            }
            img = await self.gen_levelup_img(args)
            temp = BytesIO()
            try:
                temp.name = f"{member.id}.webp"
                img.save(temp, format="WEBP")
            except KeyError:
                temp.name = f"{member.id}.png"
                img.save(temp, format="PNG")
            temp.seek(0)
            file = discord.File(temp)

            if notify:
                if dm:
                    if new_role:
                        txt = _("You have just leveled up in {} and obtained the {} role!").format(guild.name, new_role)
                    else:
                        txt = _("You just leveled up in {}!").format(guild.name)
                    try:
                        await member.send(txt, file=file)
                    except discord.Forbidden:
                        pass
                elif all(perms) and channel:
                    if new_role:
                        txt = _("**{} just leveled up and obtained the {} role!**").format(
                            mentionuser if mention else name, new_role
                        )
                    else:
                        txt = _("**{} just leveled up!**").format(mentionuser if mention else name)
                    try:
                        await channel.send(txt, file=file)
                    except Exception as e:
                        log.warning(f"Failed to send levelup alert to {channel.name}!", exc_info=e)

        if not roleperms:
            return
        if not levelroles:
            return

        leveltime = monotonic()
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason=_("Leveled Up!"))
            except discord.Forbidden:
                log.warning(f"Lacking permissions to add roles to {member.name} in {member.guild.name}")
        if roles_to_remove:
            try:
                await member.add_roles(*roles_to_remove, reason=_("Auto-remove previous level roles"))
            except discord.Forbidden:
                log.warning(f"Lacking permissions to remove roles from {member.name} in {member.guild.name}")

        t = int((monotonic() - leveltime) * 1000)
        get_stats().add("levelup.level_assignment", t)

    @perf(max_entries=1000)
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

        weekly_users = conf["weekly"]["users"]
        weekly_on = conf["weekly"]["on"]
        if weekly_on and uid not in weekly_users:
            self.init_user_weekly(gid, uid)

        # Whether to award xp
        addxp = False
        if uid not in self.lastmsg[gid]:
            addxp = True
        else:
            td = (now - self.lastmsg[gid][uid]).total_seconds()
            if td > conf["cooldown"]:
                addxp = True
        try:
            roles = list(message.author.roles)
        except AttributeError:  # User sent message and then left?
            return
        # Ignored stuff
        for role in roles:
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
            regex = r"<(@!|#)[0-9]{18}>|<a{0,1}:[a-zA-Z0-9_.]{2,32}:[0-9]{18,19}>"
            cleaned = re.sub(regex, "", message.content)
            if len(cleaned) < conf["length"]:
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
            try:
                cat_cid = str(message.channel.category.id) if message.channel.category else "0"
            except discord.ClientException:
                cat_cid = "0"
            if cid in channel_bonuses or cat_cid in channel_bonuses:
                bonus_id = cid if cid in channel_bonuses else cat_cid
                bonuschannelrange = channel_bonuses[bonus_id]
                bmin = int(bonuschannelrange[0])
                bmax = int(bonuschannelrange[1]) + 1
                bxp = random.choice(range(bmin, bmax))
                xp_to_give += bxp
            self.lastmsg[gid][uid] = now
            self.data[gid]["users"][uid]["xp"] += xp_to_give
            if weekly_on:
                self.data[gid]["weekly"]["users"][uid]["xp"] += xp_to_give

        self.data[gid]["users"][uid]["messages"] += 1
        if weekly_on:
            self.data[gid]["weekly"]["users"][uid]["messages"] += 1
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
        stream_bonus = conf["streambonus"]
        weekly_on = conf["weekly"]["on"]
        bonusrole = None
        async for member in AsyncIter(guild.members, steps=100, delay=0.001):
            member: discord.Member = member
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

            if weekly_on and uid not in self.data[gid]["weekly"]["users"]:
                self.init_user_weekly(gid, uid)

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
            if voice_state.channel:
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
                if stream_bonus and voice_state.self_stream:
                    bmin = int(stream_bonus[0])
                    bmax = int(stream_bonus[1]) + 1
                    bxp = random.choice(range(bmin, bmax))
                    xp_to_give += bxp
                self.data[gid]["users"][uid]["xp"] += xp_to_give
                if weekly_on:
                    self.data[gid]["weekly"]["users"][uid]["xp"] += xp_to_give
            self.data[gid]["users"][uid]["voice"] += td
            if weekly_on:
                self.data[gid]["weekly"]["users"][uid]["voice"] += td
            self.voice[gid][uid] = now
            jobs.append(self.check_levelups(gid, uid, channel_obj=voice_state.channel))
        await asyncio.gather(*jobs)

    @tasks.loop(seconds=20)
    async def voice_checker(self):
        await self.voice_check()

    @perf(max_entries=1000)
    async def voice_check(self):
        vtasks = []
        for guild in self.bot.guilds:
            vtasks.append(self.check_voice(guild))
        await asyncio.gather(*vtasks)

    @voice_checker.before_loop
    async def before_voice_checker(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(60)
        log.info("Voice checker running")

    @tasks.loop(minutes=3)
    async def cache_dumper(self):
        await self.save_cache()

    @cache_dumper.before_loop
    async def before_cache_dumper(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(300)
        log.info("Cache dumper ready")

    @tasks.loop(minutes=15)
    async def weekly_checker(self):
        await self.check_weekly()

    @weekly_checker.before_loop
    async def before_weekly_checker(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(60)

    @perf(max_entries=1000)
    async def check_weekly(self):
        for gid, data in self.data.items():
            w = data["weekly"]
            if not w["autoreset"] or not w["on"]:
                continue
            now = datetime.utcnow()
            last_reset = datetime.fromtimestamp(w["last_reset"])
            if last_reset.day == now.day:
                continue

            td = now - last_reset

            reset = False
            conditions = [
                w["reset_hour"] == now.hour,
                w["reset_day"] == now.weekday(),
            ]
            if all(conditions):
                reset = True

            # Check if the bot just missed the last reset
            if not reset and td.days > 7:
                log.info("More than 7 days since last reset have passed. Resetting.")
                reset = True

            if reset:
                guild = self.bot.get_guild(gid)
                if not guild:
                    continue
                await self.reset_weekly_stats(guild)

    @perf(max_entries=1000)
    async def reset_weekly_stats(self, guild: discord.Guild, ctx: commands.Context = None):
        """Announce and reset the weekly leaderboard"""
        w = self.data[guild.id]["weekly"].copy()
        users = {
            guild.get_member(int(k)): v for k, v in w["users"].items() if (v["xp"] > 0 and guild.get_member(int(k)))
        }
        channel = guild.get_channel(w["channel"]) if w["channel"] else None
        if not users:
            if ctx:
                await ctx.send(_("There are no users with exp"))
            self.data[guild.id]["weekly"]["last_reset"] = int(datetime.utcnow().timestamp())
            return

        total_xp = humanize_number(round(sum(v["xp"] for v in users.values())))
        total_messages = humanize_number(sum(v["messages"] for v in users.values()))
        total_voicetime = time_formatter(sum(v["voice"] for v in users.values()))
        total_stars = humanize_number(sum(v["stars"] for v in users.values()))

        title = _("Top Weekly Exp Earners")
        desc = _("`Total Exp:      `") + total_xp + "\n"
        desc += _("`Total Messages: `") + total_messages + "\n"
        desc += _("`Total Stars:    `") + total_stars + "\n"
        desc += _("`Total Voice:    `") + total_voicetime
        em = discord.Embed(title=title, description=desc, color=discord.Color.green())

        if ctx:
            guild = ctx.guild
        if self.dpy2:
            em.set_thumbnail(url=guild.icon)
        else:
            em.set_thumbnail(url=guild.icon_url)

        sorted_users = sorted(users.items(), key=lambda x: x[1]["xp"], reverse=True)
        top_uids = []
        for index, i in enumerate(sorted_users):
            place = index + 1
            if place > w["count"]:
                break
            user: discord.Member = i[0]
            d: dict = i[1]

            xp = humanize_number(round(d["xp"]))
            msg = humanize_number(d["messages"])
            stars = humanize_number(d["stars"])
            voice = time_formatter(d["voice"])

            value = _("`Exp:      `") + xp + "\n"
            value += _("`Messages: `") + msg + "\n"
            value += _("`Stars:    `") + stars + "\n"
            value += _("`Voice:    `") + voice
            em.add_field(name=f"#{place}. {user.name}", value=value, inline=False)
            top_uids.append(str(user.id))

        ignore = [discord.HTTPException, discord.Forbidden, discord.NotFound]
        if ctx:
            await ctx.send(embed=em)
        elif channel:
            with contextlib.suppress(*ignore):
                await channel.send(embed=em)

        top = sorted_users[: int(w["count"])]
        if w["role_all"]:
            winners: List[discord.Member] = [i[0] for i in top]
        else:
            winners: List[discord.Member] = [top[0][0]]

        role = guild.get_role(w["role"]) if w["role"] else None
        # Remove role from last winner and apply to new winner(If a role is set)
        if role:
            if w["remove"]:
                # Remove role from previous winner if toggled
                last_winners = [guild.get_member(i) for i in w["last_winners"] if guild.get_member(i)]
                for last_winner in last_winners:
                    with contextlib.suppress(*ignore):
                        await last_winner.remove_roles(role)
            # Give new winner or winners the role
            with contextlib.suppress(*ignore):
                for win in winners:
                    await win.add_roles(role)
        # Set new last winner
        new_winners = [win.id for win in winners]
        self.data[guild.id]["weekly"]["last_winners"] = new_winners
        bonus = w["bonus"]
        # Apply bonus xp to top members
        if bonus:
            for uid in top_uids:
                self.data[guild.id]["users"][uid]["xp"] += bonus

        self.data[guild.id]["weekly"]["last_reset"] = int(datetime.utcnow().timestamp())
        self.data[guild.id]["weekly"]["users"].clear()
        self.data[guild.id]["weekly"]["last_embed"] = em.to_dict()
        await self.save_cache(guild)

    @commands.group(name="lvlset", aliases=["lset", "levelup"])
    @commands.mod_or_permissions(manage_messages=True)
    @commands.guild_only()
    async def lvl_group(self, ctx: commands.Context):
        """Access LevelUp setting commands"""
        pass

    @lvl_group.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
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
        streambonus = conf["streambonus"]
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
        ptype = _("Image") if usepics else _("Embed")

        msg = _("**Main**\n")
        msg += _("`Profile Type:      `") + f"{ptype}\n"
        msg += _("`Include Balance:   `") + f"{showbal}\n"
        msg += _("`Progress Bar:      `") + f"{barlength} chars long\n"
        msg += _("**Messages**\n")
        msg += _("`Message XP:        `") + f"{xp[0]}-{xp[1]}\n"
        msg += _("`Min Msg Length:    `") + f"{length}\n"
        msg += _("`Cooldown:          `") + f"{cooldown} seconds\n"
        msg += _("**Voice**\n")
        msg += _("`Voice XP:          `") + f"{voicexp} per minute\n"
        msg += _("`Ignore Muted:      `") + f"{muted}\n"
        msg += _("`Ignore Solo:       `") + f"{solo}\n"
        msg += _("`Ignore Deafened:   `") + f"{deafended}\n"
        msg += _("`Ignore Invisible:  `") + f"{invisible}\n"
        msg += _("**Level Algorithm**\n")
        msg += _("`Base Multiplier:   `") + f"{base}\n"
        msg += _("`Exp Multiplier:    `") + f"{exp}\n"
        msg += _("**LevelUps**\n")
        msg += _("`LevelUp Notify:    `") + f"{lvlmessage}\n"
        msg += _("`Notify in DMs:     `") + f"{notifydm}\n"
        msg += _("`Mention User:      `") + f"{mention}\n"
        msg += _("`AutoRemove Roles:  `") + f"{autoremove}\n"
        msg += _("`LevelUp Channel:   `") + f"{notifylog}\n"
        msg += _("**Stars**\n")
        msg += _("`Cooldown:          `") + f"{sc}\n"
        msg += _("`React Mention:     `") + f"{starmention}\n"
        msg += _("`MentionAutoDelete: `") + f"{stardelete}\n"
        if levelroles:
            msg += _("**Levels**\n")
            for level, role_id in levelroles.items():
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                msg += _("`Level ") + f"{level}: `{role}\n"
        if prestige and pdata:
            msg += _("**Prestige**\n`Stack Roles: `") + f"{stacking}\n"
            msg += _("`Level Req:  `") + f"{prestige}\n"
            for level, data in pdata.items():
                role_id = data["role"]
                role = ctx.guild.get_role(role_id)
                if role:
                    role = role.mention
                else:
                    role = role_id
                emoji = data["emoji"]
                msg += _("`Prestige ") + f"{level}: `{role} - {emoji['str']}\n"
        embed = discord.Embed(
            title=_("LevelUp Settings"),
            description=msg,
            color=discord.Color.random(),
        )
        if voicexpbonus:
            text = ""
            for rid, bonusrange in voicexpbonus.items():
                role = ctx.guild.get_role(int(rid))
                if not role:
                    continue
                text += f"{role.mention} - {bonusrange}\n"
            if text:
                embed.add_field(name=_("Voice XP Bonus Roles"), value=text)
        if voicechanbonus:
            text = ""
            for cid, bonusrange in voicechanbonus.items():
                chan = ctx.guild.get_channel(int(cid))
                if not chan:
                    continue
                text += f"{chan.mention} - {bonusrange}"
            if text:
                embed.add_field(name=_("Voice XP Bonus Channels"), value=text)
        if streambonus:
            text = f"{streambonus[0]}-{streambonus[1]}"
            embed.add_field(name=_("Stream XP Bonus"), value=text)
        if xpbonus:
            text = ""
            for rid, bonusrange in xpbonus.items():
                role = ctx.guild.get_role(int(rid))
                if not role:
                    continue
                text += f"{role.mention} - {bonusrange}\n"
            if text:
                embed.add_field(name=_("Message XP Bonus Roles"), value=text)
        if xpchanbonus:
            text = ""
            for cid, bonusrange in xpchanbonus.items():
                chan = ctx.guild.get_channel(int(cid))
                if not chan:
                    continue
                text += f"{chan.mention} - {bonusrange}"
            if text:
                embed.add_field(name=_("Message XP Bonus Channels"), value=text)
        if igroles:
            ignored = [ctx.guild.get_role(rid).mention for rid in igroles if ctx.guild.get_role(rid)]
            text = humanize_list(ignored)
            if ignored:
                embed.add_field(name=_("Ignored Roles"), value=text, inline=False)
        if igchannels:
            ignored = [ctx.guild.get_channel(cid).mention for cid in igchannels if ctx.guild.get_channel(cid)]
            text = humanize_list(ignored)
            if ignored:
                embed.add_field(name=_("Ignored Channels"), value=text, inline=False)
        if igusers:
            ignored = [ctx.guild.get_member(uid).mention for uid in igusers if ctx.guild.get_member(uid)]
            text = humanize_list(ignored)
            if ignored:
                embed.add_field(name=_("Ignored Users"), value=text, inline=False)

        await ctx.send(embed=embed)

    @lvl_group.command(name="embedemojis")
    @commands.bot_has_permissions(embed_links=True)
    async def set_emojis(
        self,
        ctx: commands.Context,
        level: discord.Emoji | discord.PartialEmoji | str,
        prestige: discord.Emoji | discord.PartialEmoji | str,
        star: discord.Emoji | discord.PartialEmoji | str,
        chat: discord.Emoji | discord.PartialEmoji | str,
        voicetime: discord.Emoji | discord.PartialEmoji | str,
        experience: discord.Emoji | discord.PartialEmoji | str,
        balance: discord.Emoji | discord.PartialEmoji | str,
    ):
        """Set the emojis for embed profiles"""

        async def test_reactions(
            ctx: commands.Context,
            emojis: list[discord.Emoji | discord.PartialEmoji | str],
        ) -> bool:
            try:
                [await ctx.message.add_reaction(e) for e in emojis]
                return True
            except Exception as e:
                await ctx.send(f"Cannot add reactions: {e}")
                return False

        reactions = [level, prestige, star, chat, voicetime, experience, balance]
        if not await test_reactions(ctx, reactions):
            return
        conf = self.data[ctx.guild.id]
        conf["emojis"]["level"] = level if isinstance(level, str) else level.id
        conf["emojis"]["trophy"] = prestige if isinstance(prestige, str) else prestige.id
        conf["emojis"]["star"] = star if isinstance(star, str) else star.id
        conf["emojis"]["chat"] = chat if isinstance(chat, str) else chat.id
        conf["emojis"]["mic"] = voicetime if isinstance(voicetime, str) else voicetime.id
        conf["emojis"]["bulb"] = experience if isinstance(experience, str) else experience.id
        conf["emojis"]["money"] = balance if isinstance(balance, str) else balance.id
        await ctx.tick()
        await self.save_cache()

    @lvl_group.command(name="resetuserweekly")
    @commands.guildowner()
    async def reset_user_weekly(self, ctx: commands.Context, *, user: discord.Member):
        """Reset a user's weekly stats"""
        if not self.data[ctx.guild.id]["weekly"]["on"]:
            return await ctx.send(_("Weekly stats are not enabled"))
        if str(user.id) not in self.data[ctx.guild.id]["weekly"]["users"]:
            return await ctx.send(_("That user has no weekly stats"))
        self.data[ctx.guild.id]["weekly"]["users"][str(user.id)] = {
            "xp": 0,
            "voice": 0,
            "messages": 0,
            "stars": 0,
        }
        await ctx.send(_("Reset weekly stats for ") + user.name)
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="admin")
    @commands.guildowner()
    @commands.bot_has_permissions(embed_links=True)
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
        Anything less than 5 seconds will effectively disable the cache
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
            self.data[gid] = constants.default_guild
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
        self.data[ctx.guild.id] = constants.default_guild
        await msg.edit(content=_("All settings and stats reset"))
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @admin_group.command(name="statreset")
    async def reset_xp(self, ctx: commands.Context, confirm: bool):
        """Reset everyone's exp and level"""
        if not confirm:
            txt = _("Not resetting everyone's exp and levels")
            return await ctx.send(txt)
        users = self.data[ctx.guild.id]["users"].copy()
        count = len(users.keys())
        text = _("Are you sure you want to reset ") + str(count) + _(" users' stats?") + " (y/n)"
        text += _("\nThis will reset their exp, voice time, messages, level, prestige and stars")
        msg = await ctx.send(text)
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
            self.profiles.copy(),
        ]
        cachesize = self.get_size(sum(sys.getsizeof(i) for i in cache))
        ct = self.cache_seconds
        em = discord.Embed(description=_("Cog Stats"), color=ctx.author.color)

        cachetxt = _("`Profile Cache Time: `") + (_("Disabled\n") if not ct else f"{humanize_number(ct)} seconds\n")
        cachetxt += _("`Cache Size:         `") + cachesize
        em.add_field(name=_("Cache"), value=cachetxt, inline=False)

        render = _("(Disabled)")
        txt = _("Profiles will be static regardless of if the user has an animated profile")
        if self.render_gifs:
            render = _("(Enabled)")
            txt = _("Users with animated profiles will render as a gif")

        em.add_field(name=_("GIF Rendering ") + render, value=txt, inline=False)

        stats = get_stats()
        results = []
        for key in stats.function_times:
            split = key.split(".")
            module, func_name = split[0], split[-1]
            if module != "levelup":
                continue
            cpm = stats.cpm(key)
            avg = stats.avg_time(key)
            results.append((func_name, round(cpm), round(avg, 1)))

        sorted_stats = sorted(results, key=lambda x: x[2], reverse=True)
        txt = ""
        for func_name, cpm, avg in sorted_stats:
            txt += _("- {}: {}ms, {}cpm\n").format(func_name, avg, cpm)

        em.add_field(
            name=_("Performance Stats (Avg exe time | Calls per minute)"), value=box(txt, lang="json"), inline=False
        )

        await ctx.send(embed=em)

    @admin_group.command(name="globalbackup")
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def backup_cog(self, ctx):
        """Create a backup of the LevelUp config"""
        buffer = BytesIO(json.dumps(self.data).encode())
        buffer.name = f"LevelUp_GLOBAL_config_{int(datetime.now().timestamp())}.json"
        buffer.seek(0)
        file = discord.File(buffer)
        await ctx.send("Here is your LevelUp config", file=file)

    @admin_group.command(name="guildbackup")
    @commands.guildowner()
    @commands.bot_has_permissions(attach_files=True)
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
        content = get_attachments(ctx)
        if not content:
            return await ctx.send(_("Attach your backup file to the message when using this command."))
        raw = await get_content_from_url(content[0].url)
        config = json.loads(raw)

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
        content = get_attachments(ctx)
        if not content:
            return await ctx.send(_("Attach your backup file to the message when using this command."))
        raw = await get_content_from_url(content[0].url)
        config = json.loads(raw)

        default = self.config.defaults["GUILD"]
        if not all([key in default for key in config.keys()]):
            return await ctx.send(_("This is an invalid guild config!"))
        cleaned, newdata = self.cleanup(config.copy())
        if cleaned:
            config = newdata
        self.data[ctx.guild.id] = config
        await self.save_cache()
        await ctx.send(_("Config restored from backup file!"))

    @admin_group.command(name="importmalarne")
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def import_from_malarne(
        self,
        ctx: commands.Context,
        import_by: str,
        replace: bool,
        i_agree: bool,
    ):
        """
        Import levels and exp from Malarne's Leveler cog

        **Arguments**
        `export_by` - which stat to prioritize (`level` or `exp`)
        If exp is entered, it will import their experience and base their new level off of that.
        If level is entered, it will import their level and calculate their exp based off of that.
        `replace` - (True/False) if True, it will replace the user's exp or level, otherwise it will add it
        `i_agree` - (Yes/No) Just an extra option to make sure you want to execute this command
        """
        if not i_agree:
            return await ctx.send(_("Not importing levels"))
        path = cog_data_path(self).parent / "UserProfile" / "settings.json"
        if not path.exists():
            return await ctx.send(_("No config found for Malarne's Leveler cog!"))

        data = json.loads(path.read_text())["1099710897114110101"]["MEMBER"]
        imported = 0
        async with ctx.typing():
            for guild in self.bot.guilds:
                if guild.id not in self.data:
                    continue
                base = self.data[guild.id]["base"]
                exp = self.data[guild.id]["exp"]
                source_profiles = data.get(str(guild.id))
                if not source_profiles:
                    continue
                for user_id, data in source_profiles.items():
                    user = guild.get_member(int(user_id))
                    if not user:
                        continue
                    if user_id not in self.data[guild.id]["users"]:
                        self.init_user(guild.id, user_id)

                    old_level = data.get("level", 0)
                    old_exp = data.get("exp", 0)
                    if replace:
                        if "l" in import_by.lower():
                            self.data[guild.id]["users"][user_id]["level"] = old_level
                            new_xp = get_xp(old_level, base, exp)
                            self.data[guild.id]["users"][user_id]["xp"] = new_xp
                        else:
                            self.data[guild.id]["users"][user_id]["xp"] = old_exp
                            new_lvl = get_level(old_exp, base, exp)
                            self.data[guild.id]["users"][user_id]["level"] = new_lvl
                    else:
                        if "l" in import_by.lower():
                            self.data[guild.id]["users"][user_id]["level"] += old_level
                            new_xp = get_xp(self.data[guild.id]["users"][user_id]["level"], base, exp)
                            self.data[guild.id]["users"][user_id]["xp"] = new_xp
                        else:
                            self.data[guild.id]["users"][user_id]["xp"] += old_exp
                            new_lvl = get_level(self.data[guild.id]["users"][user_id]["xp"], base, exp)
                            self.data[guild.id]["users"][user_id]["level"] = new_lvl
                    imported += 1
        if not imported:
            return await ctx.send(_("There were no profiles to import"))
        txt = _("Imported {} profile(s)").format(imported)
        await ctx.send(txt)

    @retry(
        retry=retry_if_exception_type(json.JSONDecodeError),
        wait=wait_random_exponential(min=120, max=600),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def fetch_mee6_payload(self, guild_id: int, page: int):
        url = f"https://mee6.xyz/api/plugins/levels/leaderboard/{guild_id}?page={page}&limit=1000"
        timeout = ClientTimeout(total=60)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"Accept": "application/json"}) as res:
                status = res.status
                if status == 429:
                    log.warning("mee6 import is being rate limited!")
                data = await res.json(content_type=None)
                return data, status

    @retry(
        retry=retry_if_exception_type(json.JSONDecodeError),
        wait=wait_random_exponential(min=120, max=600),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def fetch_amari_payload(self, guild_id: int, page: int, key: str):
        url = f"https://amaribot.com/api/v1/guild/leaderboard/{guild_id}?page={page}&limit=1000"
        headers = {"Accept": "application/json", "Authorization": key}
        timeout = ClientTimeout(total=60)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as res:
                status = res.status
                if status == 429:
                    log.warning("amari import is being rate limited!")
                data = await res.json(content_type=None)
                return data, status

    @retry(
        retry=retry_if_exception_type(json.JSONDecodeError),
        wait=wait_random_exponential(min=120, max=600),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    async def fetch_polaris_payload(self, guild_id: int, page: int):
        url = f"https://gdcolon.com/polaris/api/leaderboard/{guild_id}?page={page}"
        timeout = ClientTimeout(total=60)
        async with ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"Accept": "application/json"}) as res:
                status = res.status
                if status == 429:
                    log.warning("polaris import is being rate limited!")
                data = await res.json(content_type=None)
                return data, status

    @admin_group.command(name="importmee6")
    @commands.guildowner()
    @commands.bot_has_permissions(embed_links=True)
    async def import_from_mee6(
        self,
        ctx: commands.Context,
        import_by: str,
        replace: bool,
        include_settings: bool,
        all_users: bool,
        i_agree: bool,
    ):
        """
        Import levels and exp from MEE6

        **Make sure your guild's leaderboard is public!**

        **Arguments**
        `import_by` - which stat to prioritize (`level` or `exp`)
        If exp is entered, it will import their experience and base their new level off of that.
        If level is entered, it will import their level and calculate their exp based off of that.
        `replace` - (True/False) if True, it will replace the user's exp or level, otherwise it will add it
        `include_settings` - (True/False) import level roles and exp settings from MEE6
        `all_users` - (True/False) if True, import ALL users regardless of if they are still in the server
        `i_agree` - (Yes/No) Just an extra option to make sure you want to execute this command

        **Note**
        Instead of typing true/false
        1 = True
        0 = False
        """
        if not i_agree:
            return await ctx.send(_("Not importing MEE6 levels"))

        msg = await ctx.send(_("Fetching mee6 leaderboard data, this could take a while..."))

        conf = self.data[ctx.guild.id]
        base = conf["base"]
        exp = conf["exp"]

        pages = math.ceil(len(ctx.guild.members) / 1000)
        players: List[dict] = []
        failed_pages = 0
        settings_imported = False

        async with ctx.typing():
            async for i in AsyncIter(range(pages), delay=5):
                try:
                    data, status = await self.fetch_mee6_payload(ctx.guild.id, i)
                except Exception as e:
                    log.warning(
                        f"Failed to import page {i} of mee6 leaderboard data in {ctx.guild}",
                        exc_info=e,
                    )
                    await ctx.send(f"Failed to import page {i} of mee6 leaderboard data: {e}")
                    failed_pages += 1
                    if isinstance(e, json.JSONDecodeError):
                        await msg.edit(content=_("Mee6 is rate limiting too heavily! Import Failed!"))
                        return
                    continue

                error = data.get("error", {})
                error_msg = error.get("message", None)
                if status != 200:
                    if status == 401:
                        return await ctx.send(_("Your leaderboard needs to be set to public!"))
                    elif error_msg:
                        return await ctx.send(error_msg)
                    else:
                        return await ctx.send(_("No data found!"))

                if include_settings and not settings_imported:
                    settings_imported = True
                    if xp_rate := data.get("xp_rate"):
                        self.data[ctx.guild.id]["base"] = round(xp_rate * 100)

                    if xp_per_message := data.get("xp_per_message"):
                        self.data[ctx.guild.id]["xp"] = xp_per_message

                    if role_rewards := data.get("role_rewards"):
                        for entry in role_rewards:
                            level_requirement = entry["rank"]
                            role_id = entry["role"]["id"]
                            self.data[ctx.guild.id]["levelroles"][str(level_requirement)] = int(role_id)
                    await ctx.send("Settings imported!")

                player_data = data.get("players")
                if not player_data:
                    break

                players.extend(player_data)

        if failed_pages:
            await ctx.send(
                _("{} pages failed to fetch from mee6 api, check logs for more info").format(str(failed_pages))
            )
        if not players:
            return await ctx.send(_("No leaderboard data found!"))

        await msg.edit(content=_("Data retrieved, importing..."))
        imported = 0
        failed = 0
        async with ctx.typing():
            async for user in AsyncIter(players):
                uid = str(user["id"])
                if not all_users:
                    member = ctx.guild.get_member(int(uid)) or self.bot.get_user(int(uid))
                    if not member:
                        failed += 1
                        continue

                lvl = user["level"]
                xp = user["xp"]
                if uid not in self.data[ctx.guild.id]["users"]:
                    self.init_user(ctx.guild.id, uid)

                if replace:  # Replace stats
                    if "l" in import_by.lower():
                        self.data[ctx.guild.id]["users"][uid]["level"] = lvl
                        newxp = get_xp(lvl, base, exp)
                        self.data[ctx.guild.id]["users"][uid]["xp"] = newxp
                    else:
                        self.data[ctx.guild.id]["users"][uid]["xp"] = xp
                        newlvl = get_level(xp, base, exp)
                        self.data[ctx.guild.id]["users"][uid]["level"] = newlvl
                    self.data[ctx.guild.id]["users"][uid]["messages"] = user["message_count"]
                else:  # Add stats
                    if "l" in import_by.lower():
                        self.data[ctx.guild.id]["users"][uid]["level"] += lvl
                        newxp = get_xp(self.data[ctx.guild.id]["users"][uid]["level"], base, exp)
                        self.data[ctx.guild.id]["users"][uid]["xp"] = newxp
                    else:
                        self.data[ctx.guild.id]["users"][uid]["xp"] += xp
                        newlvl = get_level(self.data[ctx.guild.id]["users"][uid]["xp"], base, exp)
                        self.data[ctx.guild.id]["users"][uid]["level"] = newlvl
                    self.data[ctx.guild.id]["users"][uid]["messages"] += user["message_count"]

                imported += 1

        if not imported and not failed:
            await msg.edit(content=_("No MEE6 stats were found"))
        else:
            txt = _("Imported {} User(s)").format(str(imported))
            if failed:
                txt += _(" ({} skipped since they are no longer in the discord)").format(str(failed))
            await msg.edit(content=txt)
            await ctx.tick()
            await self.save_cache(ctx.guild)

    @admin_group.command(name="importamari")
    @commands.guildowner()
    @commands.bot_has_permissions(embed_links=True)
    async def import_from_amari(
        self, ctx: commands.Context, import_by: str, replace: bool, i_agree: bool, api_key: str
    ):
        """
        Import levels and exp from AmariBot

        **Arguments**
        `import_by` - which stat to prioritize (`level` or `exp`)
        If exp is entered, it will import their experience and base their new level off of that.
        If level is entered, it will import their level and calculate their exp based off of that.
        `replace` - (True/False) if True, it will replace the user's exp or level, otherwise it will add it
        `i_agree` - (Yes/No) Just an extra option to make sure you want to execute this command
        `api_key` - Your [AmariBot API Key](https://docs.google.com/forms/d/e/1FAIpQLScQDCsIqaTb1QR9BfzbeohlUJYA3Etwr-iSb0CRKbgjA-fq7Q/viewform?usp=send_form)

        **Note**
        Instead of typing true/false
        1 = True
        0 = False
        """
        if not i_agree:
            return await ctx.send(_("Not importing AmariBot levels"))

        msg = await ctx.send(_("Fetching AmariBot leaderboard data, this could take a while..."))

        conf = self.data[ctx.guild.id]
        base = conf["base"]
        exp = conf["exp"]

        pages = math.ceil(len(ctx.guild.members) / 1000)
        players: List[dict] = []
        failed_pages = 0

        with contextlib.suppress(discord.Forbidden, discord.HTTPException):
            await ctx.message.delete()

        async with ctx.typing():
            async for i in AsyncIter(range(pages), delay=5):
                try:
                    data, status = await self.fetch_amari_payload(ctx.guild.id, i, api_key)
                except Exception as e:
                    log.warning(
                        f"Failed to import page {i} of AmariBot leaderboard data in {ctx.guild}",
                        exc_info=e,
                    )
                    await ctx.send(f"Failed to import page {i} of AmariBot leaderboard data: {e}")
                    failed_pages += 1
                    if isinstance(e, json.JSONDecodeError):
                        await msg.edit(content=_("AmariBot is rate limiting too heavily! Import Failed!"))
                        return
                    continue

                error_msg = data.get("error", None)
                if status == 501:
                    # No more users
                    break

                if status != 200:
                    if error_msg:
                        return await ctx.send(error_msg)
                    else:
                        return await ctx.send(_("No data found!"))

                player_data = data.get("data")
                if not player_data:
                    break

                players.extend(player_data)

        if failed_pages:
            await ctx.send(
                _("{} pages failed to fetch from AmariBot api, check logs for more info").format(str(failed_pages))
            )
        if not players:
            return await ctx.send(_("No leaderboard data found!"))

        await msg.edit(content=_("Data retrieved, importing..."))
        imported = 0
        failed = 0
        async with ctx.typing():
            async for user in AsyncIter(players):
                uid = user["id"]
                # username = user["username"]
                xp = user["exp"]
                lvl = user["level"]
                weekly_exp = user["weeklyExp"]

                member = ctx.guild.get_member(int(uid))
                if not member:
                    failed += 1
                    continue

                if uid not in self.data[ctx.guild.id]["users"]:
                    self.init_user(ctx.guild.id, uid)

                weekly_on = self.data[ctx.guild.id]["weekly"]["on"]

                if weekly_on and uid not in self.data[ctx.guild.id]["weekly"]["users"]:
                    self.init_user_weekly(ctx.guild.id, uid)

                if replace:  # Replace stats
                    if "l" in import_by.lower():
                        self.data[ctx.guild.id]["users"][uid]["level"] = lvl
                        newxp = get_xp(lvl, base, exp)
                        self.data[ctx.guild.id]["users"][uid]["xp"] = newxp
                    else:
                        self.data[ctx.guild.id]["users"][uid]["xp"] = xp
                        newlvl = get_level(xp, base, exp)
                        self.data[ctx.guild.id]["users"][uid]["level"] = newlvl

                    if weekly_on:
                        self.data[ctx.guild.id]["weekly"]["users"][uid]["xp"] = weekly_exp

                else:  # Add stats
                    if "l" in import_by.lower():
                        self.data[ctx.guild.id]["users"][uid]["level"] += lvl
                        newxp = get_xp(self.data[ctx.guild.id]["users"][uid]["level"], base, exp)
                        self.data[ctx.guild.id]["users"][uid]["xp"] = newxp
                    else:
                        self.data[ctx.guild.id]["users"][uid]["xp"] += xp
                        newlvl = get_level(self.data[ctx.guild.id]["users"][uid]["xp"], base, exp)
                        self.data[ctx.guild.id]["users"][uid]["level"] = newlvl

                    if weekly_on:
                        self.data[ctx.guild.id]["weekly"]["users"][uid]["xp"] += weekly_exp

                imported += 1

        if not imported and not failed:
            await msg.edit(content=_("No AmariBot stats were found"))
        else:
            txt = _("Imported {} User(s)").format(str(imported))
            if failed:
                txt += _(" ({} skipped since they are no longer in the discord)").format(str(failed))
            await msg.edit(content=txt)
            await ctx.tick()
            await self.save_cache(ctx.guild)

    @admin_group.command(name="importpolaris")
    @commands.guildowner()
    @commands.bot_has_permissions(embed_links=True)
    async def import_from_polaris(
        self,
        ctx: commands.Context,
        replace: bool,
        include_settings: bool,
        i_agree: bool,
    ):
        """
        Import levels and exp from [Polaris](https://gdcolon.com/polaris/)

        **Make sure your guild's leaderboard is public!**

        **Arguments**
        `replace` - (True/False) if True, it will replace the user's exp, otherwise it will add it
        `include_settings` - (True/False) import level roles and exp settings from Polaris
        `i_agree` - (Yes/No) Just an extra option to make sure you want to execute this command

        **Note**
        Instead of typing true/false
        1 = True
        0 = False
        """
        if not i_agree:
            return await ctx.send(_("Not importing Polaris levels"))

        msg = await ctx.send(_("Fetching Polaris leaderboard data, this could take a while..."))

        conf = self.data[ctx.guild.id]
        base = conf["base"]
        exp = conf["exp"]

        players: List[dict] = []
        failed_pages = 0
        settings_imported = False

        async with ctx.typing():
            async for i in AsyncIter(range(10), delay=5):
                page = i + 1
                try:
                    data, status = await self.fetch_polaris_payload(ctx.guild.id, page)
                except Exception as e:
                    log.warning(
                        f"Failed to import page {page} of Polaris leaderboard data in {ctx.guild}",
                        exc_info=e,
                    )
                    await ctx.send(f"Failed to import page {page} of Polaris leaderboard data: {e}")
                    failed_pages += 1
                    if isinstance(e, json.JSONDecodeError):
                        await msg.edit(content=_("Polaris is rate limiting too heavily! Import Failed!"))
                        return
                    continue

                error = data.get("error", {})
                error_msg = error.get("message", None)
                if status != 200:
                    if status == 401:
                        return await ctx.send(_("Your leaderboard needs to be set to public!"))
                    elif error_msg:
                        return await ctx.send(error_msg)
                    else:
                        return await ctx.send(_("No data found!"))

                if include_settings and not settings_imported:
                    settings_imported = True
                    if settings := data.get("settings"):
                        if gain := settings.get("gain"):
                            self.data[ctx.guild.id]["xp"] = [gain["min"], gain["max"]]
                            self.data[ctx.guild.id]["cooldown"] = gain["time"]

                        if curve := settings.get("curve"):
                            # The cubic curve doesn't translate to quadratic easily, so we won't import this
                            # cubed = curve["3"]
                            # squared = curve["2"]
                            # base = curve["1"]
                            self.data[ctx.guild.id]["base"] = curve["1"]

                    if role_rewards := data.get("rewards"):
                        for entry in role_rewards:
                            self.data[ctx.guild.id]["levelroles"][str(entry["level"])] = int(entry["id"])

                    await ctx.send("Settings imported!")

                player_data = data.get("leaderboard")
                if not player_data:
                    break

                players.extend(player_data)

        if failed_pages:
            await ctx.send(
                _("{} pages failed to fetch from Polaris api, check logs for more info").format(str(failed_pages))
            )
        if not players:
            return await ctx.send(_("No leaderboard data found!"))

        await msg.edit(content=_("Data retrieved, importing..."))
        imported = 0
        failed = 0
        async with ctx.typing():
            async for user in AsyncIter(players):
                uid = str(user["id"])
                member = ctx.guild.get_member(int(uid))
                if not member:
                    failed += 1
                    continue

                xp = user["xp"]
                if uid not in self.data[ctx.guild.id]["users"]:
                    self.init_user(ctx.guild.id, uid)

                if replace:  # Replace stats
                    self.data[ctx.guild.id]["users"][uid]["xp"] = xp
                    newlvl = get_level(xp, base, exp)
                    self.data[ctx.guild.id]["users"][uid]["level"] = newlvl
                else:  # Add stats
                    self.data[ctx.guild.id]["users"][uid]["xp"] += xp
                    newlvl = get_level(self.data[ctx.guild.id]["users"][uid]["xp"], base, exp)
                    self.data[ctx.guild.id]["users"][uid]["level"] = newlvl

                imported += 1

        if not imported and not failed:
            await msg.edit(content=_("No Polaris stats were found"))
        else:
            txt = _("Imported {} User(s)").format(str(imported))
            if failed:
                txt += _(" ({} skipped since they are no longer in the discord)").format(str(failed))
            await msg.edit(content=txt)
            await ctx.tick()
            await self.save_cache(ctx.guild)

    @admin_group.command(name="importfixator")
    @commands.is_owner()
    @commands.bot_has_permissions(embed_links=True)
    async def import_from_fixator(self, ctx: commands.Context, i_agree: bool):
        """
        Import data from Fixator's Leveler cog

        This will overwrite existing LevelUp level data and stars
        It will also import XP range level roles, and ignored channels
        *Obviously you will need MongoDB running while you run this command*
        """
        if not i_agree:
            return await ctx.send(_("Not importing users"))

        path = cog_data_path(self).parent / "Leveler" / "settings.json"
        if not path.exists():
            return await ctx.send(_("No config found for Fixator's Leveler cog!"))

        leveler_config_id = "78008101945374987542543513523680608657"
        config_root = json.loads(path.read_text())
        base_config = config_root[leveler_config_id]

        default_mongo_config = {
            "host": "localhost",
            "port": 27017,
            "username": None,
            "password": None,
            "db_name": "leveler",
        }

        mongo_config = base_config.get("MONGODB", default_mongo_config)
        global_config = base_config["GLOBAL"]
        guild_config = base_config["GUILD"]

        # If leveler is installed then libs should import fine
        try:
            from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
            from pymongo import errors as mongoerrors  # type: ignore
        except Exception as e:
            log.warning(f"pymongo Import Error: {e}")
            txt = _(
                "Failed to import `pymongo` and `motor` libraries. Run `{}pipinstall pymongo` and `{}pipinstall motor`"
            ).format(ctx.clean_prefix, ctx.clean_prefix)
            return await ctx.send(txt)

        # Try connecting to mongo
        if self._db_ready:
            self._db_ready = False
        self._disconnect_mongo()
        try:
            self.client = AsyncIOMotorClient(**{k: v for k, v in mongo_config.items() if not k == "db_name"})
            await self.client.server_info()
            self.db = self.client[mongo_config["db_name"]]
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
            description=_("Importing users from Leveler..."),
            color=discord.Color.orange(),
        )
        embed.set_thumbnail(url=self.loading)
        msg = await ctx.send(embed=embed)
        users_imported = 0
        # Now to start the importing
        async with ctx.typing():
            min_message_length = global_config.get("message_length", 0)
            mention = global_config.get("mention", False)
            xp_range = global_config.get("xp", [1, 5])
            for guild in self.bot.guilds:
                guild_id = str(guild.id)
                ignored_channels = guild_config.get(str(guild.id), {}).get("ignored_channels", [])
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
                description=_("Importing Complete!\n") + f"{users_imported}" + _(" users imported"),
                color=discord.Color.green(),
            )
            embed.set_thumbnail(url=self.loading)
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
        # cleaned_data, newdat = self.cleanup(self.data[ctx.guild.id].copy())
        if not cleanup and not cleaned:
            return await ctx.send(_("Nothing to clean"))

        txt = _("Deleted ") + str(cleaned) + _(" user IDs from the config that are no longer in the server.")
        await ctx.send(txt)
        await self.save_cache(ctx.guild)

    @lvl_group.group(name="messages", aliases=["message", "msg"])
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
        await ctx.send(_("Message XP range has been set to ") + f"{min_xp} - {max_xp}" + _(" per valid message"))
        await self.save_cache(ctx.guild)

    @message_group.command(name="rolebonus")
    async def msg_role_bonus(
        self,
        ctx: commands.Context,
        role: discord.Role,
        min_xp: int,
        max_xp: int,
    ):
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
    async def msg_chan_bonus(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.CategoryChannel],
        min_xp: int,
        max_xp: int,
    ):
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
    async def voice_role_bonus(
        self,
        ctx: commands.Context,
        role: discord.Role,
        min_xp: int,
        max_xp: int,
    ):
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
    async def voice_chan_bonus(
        self,
        ctx: commands.Context,
        channel: discord.VoiceChannel,
        min_xp: int,
        max_xp: int,
    ):
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

    @voice_group.command(name="streambonus")
    async def voice_stream_bonus(self, ctx: commands.Context, min_xp: int, max_xp: int):
        """
        Add a range of bonus XP to users who are Discord streaming

        This bonus applies to voice time xp

        Set both min and max to 0 to remove the bonus
        """
        if min_xp > max_xp:
            return await ctx.send(_("Max xp needs to be higher than min xp"))
        xp = [min_xp, max_xp]
        sb = self.data[ctx.guild.id]["streambonus"]
        if not min_xp and not max_xp:
            if not sb:
                return await ctx.send(_("There is no stream bonus set yet"))
            self.data[ctx.guild.id]["streambonus"] = []
            await ctx.send(_("Stream bonus has been removed"))
        else:
            self.data[ctx.guild.id]["streambonus"] = xp
            await ctx.send(_("Stream bonus has been set to ") + str(xp))
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
    async def add_xp(
        self,
        ctx: commands.Context,
        user_or_role: Union[discord.Member, discord.Role],
        xp: int,
    ):
        """Add XP to a user or role"""
        gid = ctx.guild.id
        if not user_or_role:
            return await ctx.send(_("I cannot find that user or role"))
        if isinstance(user_or_role, discord.Member):
            uid = str(user_or_role.id)
            if uid not in self.data[gid]["users"]:
                self.init_user(gid, uid)
            self.data[gid]["users"][uid]["xp"] += xp
            txt = str(xp) + _("xp has been added to ") + user_or_role.name
            await ctx.send(txt)
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
            txt = _("Added ") + str(xp) + _(" xp to ") + humanize_number(len(users)) + _(" users that had the ")
            txt += user_or_role.name + _("role")
            await ctx.send(txt)
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
        txt = _("User ") + user.name + _(" is now level ") + str(level)
        await ctx.send(txt)

    @lvl_group.command(name="setprestige")
    async def set_user_prestige(self, ctx: commands.Context, user: discord.Member, prestige: int):
        """
        Set a user to a specific prestige level

        Prestige roles will need to be manually added/removed when using this command
        """
        conf = self.data[ctx.guild.id]
        uid = str(user.id)
        if uid not in conf["users"]:
            return await ctx.send(_("There is no data for that user!"))
        prestige_data = conf["prestigedata"]
        if not prestige_data:
            return await ctx.send(_("Prestige levels have not been set yet!"))
        p = str(prestige)
        if p not in prestige_data:
            return await ctx.send(_("That prestige level isn't set!"))
        emoji = prestige_data[p]["emoji"]
        self.data[ctx.guild.id]["users"][uid]["prestige"] = int(prestige)
        self.data[ctx.guild.id]["users"][uid]["emoji"] = emoji
        await ctx.tick()
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
    async def set_exp(self, ctx: commands.Context, exponent_multiplier: Union[int, float]):
        """
        Exponent multiplier for the leveling algorithm

        Affects leveling on an exponential scale(higher values makes leveling take exponentially longer)
        """
        if exponent_multiplier <= 0:
            return await ctx.send(_("Your exponent needs to be higher than 0"))
        if exponent_multiplier > 10:
            return await ctx.send(_("Your exponent needs to be 10 or lower"))
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
            text += f"`{ctx.clean_prefix}levelset barlength`"
            return await ctx.send(text)
        if bar_length < 15 or bar_length > 50:
            return await ctx.send(_("Progress bar length must be a minimum of 15 and maximum of 40"))
        self.data[ctx.guild.id]["barlength"] = bar_length
        await ctx.send(_("Progress bar length has been set to ") + str(bar_length))
        await self.save_cache(ctx.guild)

    @lvl_group.command(name="seelevels")
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
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

        async with ctx.typing():
            level_text, x, y = await asyncio.to_thread(self.get_level_times, conf)
            file_bytes = await asyncio.to_thread(self.plot_levels, x, y)
            file = discord.File(BytesIO(file_bytes), filename="lvlexample.webp")

        img = "attachment://lvlexample.webp"
        example = _(
            "XP required for a level = Base * Level^ᵉˣᵖ\n\n"
            "Approx time is the time it would take for a user to reach a level with randomized breaks"
        )
        desc = _("`Base Multiplier:  `") + f"{base}\n"
        desc += _("`Exp Multiplier:   `") + f"{exp}\n"
        desc += _("`Experience Range: `") + f"{xp_range}\n"
        desc += _("`Message Cooldown: `") + f"{cd}\n" + f"{box(example)}\n" + f"{box(level_text, lang='python')}"
        embed = discord.Embed(
            title=_("Level Example"),
            description=desc,
            color=discord.Color.random(),
        )
        embed.set_image(url=img)
        await ctx.send(embed=embed, file=file)

    def get_level_times(self, conf: dict) -> Tuple[str, list, list]:
        base = conf["base"]
        exp = conf["exp"]
        cd = conf["cooldown"]
        xp_range = conf["xp"]
        txt = ""
        x = []
        y = []
        for level in range(1, 21):
            xp = get_xp(level, base, exp)
            time = time_to_level(level, base, exp, cd, xp_range)
            time = time_formatter(time)
            txt += _("- lvl {}, {} xp, {}\n").format(level, xp, time)
            x.append(level)
            y.append(xp)
        return txt, x, y

    @perf(max_entries=1000)
    def plot_levels(self, x: list, y: list) -> Optional[bytes]:
        try:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Total"))
            fig.update_layout(
                title=_("XP Curve"),
                xaxis_title=_("Level"),
                yaxis_title=_("Experience Required"),
                autosize=False,
                width=500,
                height=500,
                margin=dict(l=50, r=50, b=100, t=100, pad=4),
            )
            try:
                img_bytes = fig.to_image(format="WEBP")
            except KeyError:
                img_bytes = fig.to_image(format="PNG")
            return img_bytes
        except Exception as e:
            log.warning("Failed to plot levels", exc_info=e)

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
    async def set_level_channel(
        self,
        ctx: commands.Context,
        levelup_channel: discord.TextChannel = None,
    ):
        """
        Set LevelUP message channel
        Set a channel for all level up messages to send to
        """
        if not levelup_channel:
            self.data[ctx.guild.id]["notifylog"] = None
            await ctx.send(
                _(
                    "LevelUp channel has been **Disabled**\n"
                    "level up messages will now happen in the channel the user is in"
                )
            )
        else:
            perms = levelup_channel.permissions_for(ctx.guild.me).send_messages
            if not perms:
                return await ctx.send(_("I do not have permission to send messages to that channel."))
            self.data[ctx.guild.id]["notifylog"] = levelup_channel.id
            await ctx.send(_("LevelUp channel has been set to ") + levelup_channel.mention)
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
    @commands.admin_or_permissions(manage_roles=True)
    async def level_roles(self, ctx: commands.Context):
        """Level role assignment"""

    @level_roles.command(name="initialize")
    @commands.bot_has_permissions(manage_roles=True, embed_links=True)
    async def init_roles(self, ctx: commands.Context):
        """
        Initialize level roles

        This command is for if you added level roles after users have achieved that level,
        it will apply all necessary roles to a user according to their level and prestige
        """
        start = perf_counter()
        guild = ctx.guild
        perms = guild.me.guild_permissions.manage_roles
        if not perms:
            return await ctx.send(_("I dont have the proper permissions to manage roles!"))
        roles_added = 0
        roles_removed = 0
        embed = discord.Embed(
            description=_("Calculating roles, this may take a while..."),
            color=discord.Color.magenta(),
        )
        embed.set_thumbnail(url=self.loading)
        msg = await ctx.send(embed=embed)

        to_add: Dict[discord.Member, Set[discord.Role]] = {}
        to_remove: Dict[discord.Member, Set[discord.Role]] = {}

        conf = self.data[ctx.guild.id]
        level_roles = conf["levelroles"]
        prestiges = conf["prestigedata"]
        autoremove = conf["autoremove"]
        users = [i for i in conf["users"]]
        for user_id in users:
            user = guild.get_member(int(user_id))
            if not user:
                continue
            to_add[user] = set()
            to_remove[user] = set()

            data = conf["users"][user_id]
            user_level = data["level"]
            prestige_level = data["prestige"]
            if autoremove:
                highest_level = 0
                for level, role_id in level_roles.items():
                    if int(user_level) >= int(level) >= highest_level:
                        highest_level = int(level)

                if highest_level:
                    role_id = level_roles[str(highest_level)]
                    if role := guild.get_role(role_id):
                        to_add[user].add(role)
                        for user_role in user.roles:
                            if user_role.id in level_roles.values() and user_role.id != role.id:
                                to_remove[user].add(user_role)

                highest_prestige = 0
                for prestige_level_requirement in prestiges:
                    if int(prestige_level) >= int(prestige_level_requirement) >= highest_prestige:
                        highest_prestige = int(prestige_level_requirement)

                if highest_prestige:
                    prestige_role_ids = [i["role"] for i in prestiges.values()]
                    role_id = prestiges[str(highest_prestige)]
                    if role := guild.get_role(role_id):
                        to_add[user].add(role)
                        for user_role in user.roles:
                            if user_role.id in prestige_role_ids and user_role.id != role.id:
                                to_remove[user].add(user_role)

            else:
                user_role_ids = [role.id for role in user.roles]
                for lvl, role_id in level_roles.items():
                    if role := guild.get_role(int(role_id)):
                        if int(lvl) <= int(user_level) and role.id not in user_role_ids:
                            to_add[user].add(role)

                for lvl, prestige in prestiges.items():
                    if role := guild.get_role(int(prestige["role"])):
                        if int(lvl) <= int(prestige_level) and role.id not in user_role_ids:
                            to_add[user].add(role)

        embed.description = _("Assigning roles, this may take a while...")
        await msg.edit(embed=embed)

        add_fails = 0
        remove_fails = 0
        async with ctx.typing():
            bot_top_role = max(role for role in guild.me.roles)
            for user, adding in to_add.items():
                removing = to_remove[user]

                # Update what can actually be assigned/removed
                adding = [role for role in adding if role < bot_top_role]
                removing = [role for role in removing if role < bot_top_role]

                for role in removing:
                    if role in adding and role in user.roles:
                        adding.discard(role)

                for role in adding:
                    if role in removing and role not in user.roles:
                        removing.discard(role)

                try:
                    await user.add_roles(*adding)
                    roles_added += len(adding)
                except discord.Forbidden:
                    log.warning(
                        f"Failed to assign the following roles to {user} in {guild}: {humanize_list([r.name for r in adding])}"
                    )
                    add_fails += len(adding)

                try:
                    await user.remove_roles(*removing)
                    roles_removed += len(removing)
                except discord.Forbidden:
                    log.warning(
                        f"Failed to remove the following roles from {user} in {guild}: {humanize_list([r.name for r in removing])}"
                    )
                    remove_fails += len(removing)

        desc = _("Role initialization completed!")
        if roles_added:
            desc += _("\nAdded `{}`").format(roles_added)
            if add_fails:
                desc += _(" (`{}` failed)").format(add_fails)

        if roles_removed:
            desc += _("\nRemoved `{}`").format(roles_removed)
            if remove_fails:
                desc += _(" (`{}` failed)").format(remove_fails)

        if not roles_added and not roles_removed:
            desc += _("\nNo roles needed to be added or removed!")

        embed = discord.Embed(description=desc, color=discord.Color.green())
        td = round(perf_counter() - start)
        delta = humanize_timedelta(seconds=td)
        foot = _("Initialization took {} to complete.").format(delta)
        embed.set_footer(text=foot)
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
        if role >= ctx.author.top_role:
            return await ctx.send(_("The role you are trying to set is higher than the one you currently have!"))
        if role >= ctx.me.top_role:
            return await ctx.send(_("I cannot assign roles higher than my own!"))
        perms = ctx.guild.me.guild_permissions.manage_roles
        if not perms:
            return await ctx.send(_("I do not have permission to manage roles"))
        if level in self.data[ctx.guild.id]["levelroles"]:
            overwrite = _("Overwritten")
        else:
            overwrite = _("Set")
        self.data[ctx.guild.id]["levelroles"][level] = role.id
        txt = _("Level ") + str(level) + _(" has been ") + overwrite + _(" as ") + role.mention
        await ctx.send(txt)
        await self.save_cache(ctx.guild)

    @level_roles.command(name="del")
    async def del_level_role(self, ctx: commands.Context, level: str):
        """Unassign a role from a level"""
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

    @prestige_settings.command(name="add")
    async def add_pres_data(
        self,
        ctx: commands.Context,
        prestige_level: str,
        role: discord.Role,
        emoji: Union[discord.Emoji, discord.PartialEmoji, str],
    ):
        """
        Add a prestige level role
        Add a role and emoji associated with a specific prestige level

        When a user prestiges, they will get that role and the emoji will show on their profile
        """
        if not prestige_level.isdigit():
            return await ctx.send(_("prestige_level must be a number!"))
        url = get_twemoji(emoji) if isinstance(emoji, str) else emoji.url
        self.data[ctx.guild.id]["prestigedata"][prestige_level] = {
            "role": role.id,
            "emoji": {"str": str(emoji), "url": url},
        }
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @commands.command(name="etest", hidden=True)
    async def e_test(self, ctx, emoji: Union[discord.Emoji, discord.PartialEmoji, str]):
        """Test emojis to see if the bot is able to get a valid url for them"""
        if isinstance(emoji, str):
            em = get_twemoji(emoji)
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
    async def ignore_channel(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.VoiceChannel],
    ):
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

    @commands.group(name="weeklyset", aliases=["wset"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def weekly_set(self, ctx: commands.Context):
        """Access the weekly settings for levelUp"""
        pass

    @weekly_set.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def weekly_settings(self, ctx: commands.Context):
        """View the current weekly settings"""
        weekly = self.data[ctx.guild.id]["weekly"]
        status = _("**Enabled**") if weekly["on"] else _("**Disabled**")
        desc = _("Weekly stat tracking is currently ") + status
        em = discord.Embed(
            title=_("Weekly LevelUp settings"),
            description=desc,
            color=ctx.author.color,
        )
        channel = ctx.guild.get_channel(weekly["channel"]) if weekly["channel"] else None
        role = ctx.guild.get_role(weekly["role"]) if weekly["role"] else None
        last_winners = [ctx.guild.get_member(i).mention for i in weekly["last_winners"] if ctx.guild.get_member(i)]
        last_winners = [f"({index + 1}){i}" for index, i in enumerate(last_winners)]

        txt = _("`Winner Count:   `") + str(weekly["count"]) + "\n"
        txt += _("`Last Winner(s): `") + (humanize_list(last_winners) if last_winners else _("None")) + "\n"
        txt += _("`Channel:        `") + (channel.mention if channel else _("None")) + "\n"
        txt += _("`Role:           `") + (role.mention if role else _("None")) + "\n"
        txt += _("`RoleAllWinners: `") + str(weekly["role_all"]) + "\n"
        txt += _("`Auto Remove:    `") + str(weekly["remove"]) + "\n"
        txt += _("`Bonus Exp:      `") + humanize_number(weekly["bonus"])
        em.add_field(name=_("Settings"), value=txt, inline=False)

        dayname = self.daymap[weekly["reset_day"]]
        txt = _("`Reset Day:  `") + f"{weekly['reset_day']} ({dayname})\n"
        txt += _("`Reset Hour: `") + f"{weekly['reset_hour']}\n"
        txt += _("`Last Reset: `") + f"<t:{weekly['last_reset']}:F> UTC\n"
        reset_time = get_next_reset(weekly["reset_day"], weekly["reset_hour"])
        txt += _("`Next Reset: `") + f"<t:{reset_time}:F> UTC\n"
        status = _("(Enabled)") if weekly["autoreset"] else _("(Disabled)")
        em.add_field(name=_("Auto Reset ") + status, value=txt, inline=False)
        await ctx.send(embed=em)

    @weekly_set.command(name="reset")
    @commands.bot_has_permissions(embed_links=True)
    async def reset_weekly(self, ctx: commands.Context, yes_or_no: bool):
        """Reset the weekly leaderboard manually and announce winners"""
        if not yes_or_no:
            return await ctx.send(_("Not resetting weekly leaderboard"))
        # func to reset and announce winners
        await self.reset_weekly_stats(ctx.guild, ctx)

    @weekly_set.command(name="toggle")
    async def toggle_weekly(self, ctx: commands.Context):
        """Toggle weekly stat tracking"""
        toggle = self.data[ctx.guild.id]["weekly"]["on"]
        if toggle:
            self.data[ctx.guild.id]["weekly"]["on"] = False
            await ctx.send(_("Weekly stat tracking has been **Disabled**"))
        else:
            self.data[ctx.guild.id]["weekly"]["on"] = True
            await ctx.send(_("Weekly stat tracking has been **Enabled**"))
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="autoreset")
    async def toggle_autoreset(self, ctx: commands.Context):
        """Toggle weekly auto-reset"""
        toggle = self.data[ctx.guild.id]["weekly"]["autoreset"]
        if toggle:
            self.data[ctx.guild.id]["weekly"]["autoreset"] = False
            await ctx.send(_("Weekly auto-reset has been **Disabled**"))
        else:
            self.data[ctx.guild.id]["weekly"]["autoreset"] = True
            await ctx.send(_("Weekly auto-reset has been **Enabled**"))
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="hour")
    async def reset_hour(self, ctx: commands.Context, hour: int):
        """
        What hour the weekly stats reset
        Set the hour (0 - 23 in UTC) for the weekly reset to take place
        """
        if hour < 0 or hour > 23:
            return await ctx.send(_("Hour must be 0 to 23"))
        self.data[ctx.guild.id]["weekly"]["reset_hour"] = hour
        txt = _("Weekly stats auto reset hour is now ") + f"{hour} (UTC)"
        await ctx.send(txt)
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="day")
    async def reset_day(self, ctx: commands.Context, day_of_the_week: int):
        """
        What day of the week the weekly stats reset
        Set the day of the week (0 - 6 = Monday - Sunday) for weekly reset to take place
        """
        if day_of_the_week < 0 or day_of_the_week > 6:
            return await ctx.send(_("Day must be 0 to 6 (Monday to Sunday)"))
        self.data[ctx.guild.id]["weekly"]["reset_day"] = day_of_the_week
        txt = _("Weekly stats auto reset day is now ") + f"**{self.daymap[day_of_the_week]}**"
        await ctx.send(txt)
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="top")
    async def top_members(self, ctx: commands.Context, top_count: int):
        """
        Top weekly member count
        Set amount of members to include in the weekly top leaderboard
        """
        if top_count < 1:
            return await ctx.send(_("There must be at least one winner!"))
        elif top_count > 25:
            return await ctx.send(_("There can only be up to 25 winners!"))
        self.data[ctx.guild.id]["weekly"]["count"] = top_count
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="channel")
    async def weekly_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
        """Weekly winner announcement channel
        set the channel for weekly winners to be announced in when auto-reset is enabled
        """
        if not ctx.me.guild_permissions.send_messages:
            return await ctx.send(_("I do not have permission to send messages to that channel!"))
        if not ctx.me.guild_permissions.embed_links:
            return await ctx.send(_("I do not have permission to send embeds to that channel!"))
        self.data[ctx.guild.id]["weekly"]["channel"] = channel.id
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="role")
    async def winner_role(self, ctx: commands.Context, *, role: discord.Role):
        """Weekly winner role reward
        Set the role awarded to the top member of the weekly leaderboard"""
        if not ctx.me.guild_permissions.manage_roles:
            return await ctx.send(_("I do not have permission to manage roles!"))
        self.data[ctx.guild.id]["weekly"]["role"] = role.id
        await ctx.tick()
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="roleall")
    async def role_all(self, ctx: commands.Context):
        """Toggle whether to give the weekly winner role to all winners or only 1st place"""
        toggle = self.data[ctx.guild.id]["weekly"]["role_all"]
        if toggle:
            self.data[ctx.guild.id]["weekly"]["role_all"] = False
            await ctx.send(_("Only the 1st place winner of the weekly stats reset will receive the weekly role"))
        else:
            self.data[ctx.guild.id]["weekly"]["role_all"] = True
            await ctx.send(_("All top members listed in the weekly stat reset will receive the weekly role"))
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="autoremove")
    async def weekly_autoremove(self, ctx: commands.Context):
        """One role holder at a time
        Toggle whether the winner role is removed from the previous holder when a new winner is selected
        """
        toggle = self.data[ctx.guild.id]["weekly"]["remove"]
        if toggle:
            self.data[ctx.guild.id]["weekly"]["remove"] = False
            await ctx.send(_("Auto role removal from previous winner has been **Disabled**"))
        else:
            self.data[ctx.guild.id]["weekly"]["remove"] = True
            await ctx.send(_("Auto role removal from previous winner has been **Enabled**"))
        await self.save_cache(ctx.guild)

    @weekly_set.command(name="bonus")
    async def exp_bonus(self, ctx: commands.Context, exp_bonus: int):
        """
        Weekly winners bonus experience points
        Set to 0 to disable exp bonus
        """
        self.data[ctx.guild.id]["weekly"]["bonus"] = exp_bonus
        await ctx.tick()
        await self.save_cache(ctx.guild)

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
        txt = _("Forced ") + person.name + _(" to level up!")
        await ctx.send(txt)
        await self.save_cache(ctx.guild)

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
        txt = _("Forced ") + person.name + _(" to level down!")
        await ctx.send(txt)
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

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema = {
            "name": "get_user_profile",
            "description": "get a users level, xp, voice time and other stats about their LevelUp profile in the discord",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
        await cog.register_function("LevelUp", schema)

    async def get_user_profile(self, user: discord.Member, *args, **kwargs):
        if user.guild.id not in self.data:
            return "The LevelUp cog has been loaded but doesnt have any data yet"
        self.init_user(user.guild.id, str(user.id))
        user_data = self.data[user.guild.id]["users"][str(user.id)].copy()
        txt = (
            f"Experience: {round(user_data['xp'])}\n"
            f"Voice time: {humanize_timedelta(seconds=int(user_data['voice']))}\n"
            f"Message count: {humanize_number(user_data['messages'])}\n"
            f"Level: {user_data['level']}\n"
            f"Prestige: {user_data['prestige']}\n"
            f"Emoji: {user_data['emoji']}\n"
            f"Stars: {humanize_number(user_data['stars'])}"
        )
        return txt
