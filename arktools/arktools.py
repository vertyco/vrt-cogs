import asyncio
import datetime
import json
import logging
import math
import random
import re
import socket
import sys
import typing

import aiohttp
import discord
import numpy as np
import pytz
from discord.ext import tasks
from rcon import Client
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box, pagify
from xbox.webapi.api.client import XboxLiveClient
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.authentication.models import OAuth2TokenResponse

from .calls import (
    add_friend,
    remove_friend,
    manual_rcon,
    get_followers,
    block_player,
    unblock_player
)
from .formatter import (
    decode,
    profile_format,
    expired_players,
    overview_format,
    lb_format,
    tribe_lb_format,
    cstats_format,
    player_stats,
    detect_friends,
    fix_timestamp,
    get_graph,
    time_formatter,
    detect_sus,
    cleanup_config,
    IMSTUCK_BLUEPRINTS
)
from .menus import menu, DEFAULT_CONTROLS

log = logging.getLogger("red.vrt.arktools")

LOADING = "https://i.imgur.com/l3p6EMX.gif"
LIVE = "https://i.imgur.com/LPzCcgU.gif"
FAILED = "https://i.imgur.com/TcnAyVO.png"
SUCCESS = "https://i.imgur.com/NrLAEpq.gif"

REDIRECT_URI = "http://localhost/auth/callback"


class ArkTools(commands.Cog):
    """
    RCON/API tools and cross-chat for Ark: Survival Evolved!
    """
    __author__ = "Vertyco"
    __version__ = "2.9.43"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117117117117, force_registration=True)
        default_guild = {
            "alt": {  # System for detecting suspicious Xbox accounts
                "on": False,  # Alt-detection system toggle
                "autoban": False,  # Auto ban suspicious users toggle
                "silver": False,  # Xbox silver account detection toggle
                "msgtoggle": False,  # Whether to send warning message or not
                "mings": 1000,  # Minimum gamerscore threshold
                "minfollowers": 5,  # Minimum follower threshold
                "minfollowing": 10,  # Minimum following threshold
                "msg": None,  # Message to send users if their account is sus
                "whitelist": []  # Ignore list for the alt detector
            },
            "welcomemsg": None,  # When a new player is detected this is the welcome message it will send
            "status": {"channel": None, "message": None, "multi": [], "time": 1},  # Server status live-embed stuff
            "masterlog": None,  # (Steam Only) - Discord channel for all tribe logs
            "eventlog": None,  # All in-game events will be logged to this discord channel
            "fullaccessrole": None,  # Discord role for full rcon command access
            "autowelcome": False,  # Toggle for whether to send a welcome message to new users
            "autofriend": False,  # Toggle for whether to auto add new players as a friend by the host gamertags
            "unfriendafter": 30,  # Unfriend players after X days of inactivity
            "clusters": {},  # All server data gets stored here
            "clustertypes": "both",  # If cluster types available are either Xbox, Steam, or both
            "modroles": [],  # All mod role ID's get stored here
            "modcommands": [],  # All commands that the mods are allowed to use go here
            "badnames": [],  # Blacklist for bad character names
            "tribes": {},  # Personal tribe settings(steam only)
            "players": {},  # All player data stored here(playtime, gamertag, xuid, implant ID's ect)
            "ranks": {},  # Rank data for timeplayed <-> Discord role ID is stored here
            "autorename": False,  # Automatically rename players to their ranks
            "autoremove": False,  # Automatically remove old rank roles from discord users when they rank up
            "cooldowns": {},  # Cooldowns for in-game commands like payday and imstuck
            "votecooldown": 120,  # Cooldown for in-game voting commands so people dont spam the shit
            "kit": {"enabled": False, "claimed": [], "paths": []},  # Starter kit settings for new players
            "payday": {"enabled": False, "random": False, "cooldown": 12, "paths": []},  # in-game Payday settings
            "serverstats": {"dates": [], "counts": [], "expiration": 30},  # Playercount data for graphing
            "timezone": "UTC"  # Default timezone for player count graph
        }
        # Microsoft Azure application Client ID and Secret for accessing the Xbox API
        default_global = {
            "clientid": None,
            "secret": None
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        # Cache on cog load/core setting changes to reduce config reads
        self.activeguilds = []
        self.servers = []
        self.channels = []
        self.servercount = 0
        self.playerlist = {}
        self.downtime = {}
        self.time = ""

        # Offline servers go into a queue to wait a minute before bot attempts to reconnect
        self.queue = {}

        # In-Game voting sessions
        self.votes = {}
        self.lastran = {}

        # Task Loops. Yeah theres a lot, sue me.
        self.getchat.start()
        self.listplayers.start()
        self.status_channel.start()
        self.player_stats.start()
        self.maintenance.start()
        self.autofriend.start()
        self.vote_sessions.start()
        self.graphdata_prune.start()

        # Windows is dumb, set asyncio event loop selector policy for it, not even sure if this helps tbh
        if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and sys.platform.startswith("win"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            log.info(f"Setting EventLoopSelector For {sys.platform}")

    def cog_unload(self):
        self.getchat.cancel()
        self.listplayers.cancel()
        self.status_channel.cancel()
        self.player_stats.cancel()
        self.maintenance.cancel()
        self.autofriend.cancel()
        self.vote_sessions.cancel()
        self.graphdata_prune.cancel()

    # Just grab azure credentials from the config, only bot owner needs to set this and its optional
    async def get_azure_credentials(self):
        client_id = await self.config.clientid()
        client_secret = await self.config.secret()
        return client_id, client_secret

    # Validate/refresh the user tokens and obtain XSTS token for api calls
    @staticmethod
    async def refresh_tokens(session, client_id, client_secret, tokens, redirect_uri):
        auth_mgr = AuthenticationManager(session, client_id, client_secret, redirect_uri)
        try:
            auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        except Exception as e:
            if "validation error" in str(e):
                return "validation error", None, None
        try:
            await auth_mgr.refresh_tokens()
        except Exception as e:
            if "Service Unavailable" in str(e):
                return "unavailable", None, None
        xbl_client = XboxLiveClient(auth_mgr)
        try:
            xsts_token = auth_mgr.xsts_token.authorization_header_value
        except AttributeError:
            return "unauthorized", None, None
        refreshed_tokens = json.loads(auth_mgr.oauth.json())
        return xbl_client, xsts_token, refreshed_tokens

    # Handles token renewal and returns xbox client session with xsts token
    async def auth_manager(
            self,
            session: aiohttp.ClientSession,
            cname: str,
            sname: str,
            tokens: dict,
            ctx: commands.Context = None,
            guild: discord.guild = None
    ):
        client_id, client_secret = await self.get_azure_credentials()
        if not client_id:  # Owner hasnt set client id yet
            await ctx.send(f"Client ID and Secret have not been set yet!\n"
                           f"Bot owner needs to run `{ctx.prefix}arktools api addtokens`")
            return None, None
        xbl_client, xsts_token, refreshed_tokens = await self.refresh_tokens(
            session,
            client_id,
            client_secret,
            tokens,
            REDIRECT_URI
        )
        if xbl_client == "validation error":
            if ctx:
                await ctx.send(
                    f"Client ID and Secret have not been authorized yet!\n"
                    f"Bot owner needs to run `{ctx.prefix}apiset authorize`"
                )
            return None, None
        elif xbl_client == "Service Unavailable":
            return None, None
        elif xbl_client == "unauthorized":
            if ctx:
                await ctx.send(
                    "Failed to authorize tokens!\n"
                    "Try re-authorizing your host gamertags"
                )
            return None, None
        else:
            if not guild:
                guild = ctx.guild
            async with self.config.guild(guild).clusters() as clusters:
                clusters[cname]["servers"][sname]["tokens"] = refreshed_tokens
        return xbl_client, xsts_token

    # If a server goes offline it will be added to the queue and task loops will wait before trying to call it again
    def in_queue(self, channel: str):
        now = datetime.datetime.now()
        if channel in self.queue:
            td = now - self.queue[channel]
            td = td.total_seconds()
            if td < 120:
                return True
            else:
                return False

    async def tribelog_sendoff(self, guild, settings, server, logs):
        for msg in logs:
            try:
                tribe_id, embed = await self.tribelog_format(server, msg)
            except TypeError:
                continue
            masterlog = guild.get_channel(settings["masterlog"])
            if masterlog:
                perms = masterlog.permissions_for(guild.me).send_messages
                if perms:
                    await masterlog.send(embed=embed)
            if tribe_id in settings["tribes"]:
                tribechannel = guild.get_channel(settings["tribes"][tribe_id]["channel"])
                if tribechannel:
                    perms = tribechannel.permissions_for(guild.me).send_messages
                    if perms:
                        await tribechannel.send(embed=embed)

    # Handles tribe log formatting/itemizing
    async def tribelog_format(self, server: dict, msg: str):
        if "froze" in msg:
            regex = r'(?i)Tribe (.+), ID (.+): (Day .+, ..:..:..): (.+)\)'
        else:
            regex = r'(?i)Tribe (.+), ID (.+): (Day .+, ..:..:..): .+>(.+)<'
        tribe = re.findall(regex, msg)
        if not tribe:
            return
        name = tribe[0][0]
        tribe_id = tribe[0][1]
        time = tribe[0][2]
        action = tribe[0][3]
        guild = server["guild"]
        servername = f"{server['name']} {server['cluster']}"
        server_id = str(server["chatchannel"])
        playerdata = {
            "implant": None,
            "name": None,
            "previous_names": [],
            "stats": {
                "pvpkills": 0,
                "pvpdeaths": 0,
                "pvedeaths": 0,
                "tamed": 0
            }
        }
        async with self.config.guild(guild).all() as settings:
            tribes = settings["tribes"]
            players = settings["players"]
            if tribe_id not in tribes:
                tribes[tribe_id] = {
                    "tribename": name,
                    "owner": None,
                    "channel": None,
                    "allowed": [],
                    "members": [],
                    "kills": 0,
                    "servername": servername
                }
            if tribes[tribe_id]["tribename"] != name:
                tribes[tribe_id]["tribename"] = name
            tr = tribes[tribe_id]
            if "members" not in tr:
                tr["members"] = []
            if "servername" not in tribes[tribe_id]:
                tribes[tribe_id]["servername"] = servername
            if not tribes[tribe_id]["servername"]:
                tribes[tribe_id]["servername"] = servername
            if "was killed" in action.lower():  # Player or dino was killed
                if action.lower().startswith("tribemember"):  # Player was killed by something
                    # Amount of parenthesis in the action was a quick and easy way to determine kill/death type
                    braces = action.count("(")
                    # PVE DEATH
                    if braces == 0:  # player killed by wild dino so pve death
                        reg = r'Tribemember (.+) -.+was'
                        victim = re.search(reg, action).group(1)
                        if victim not in tr["members"]:
                            tr["members"].append(victim)
                        uid = await self.get_uid(players, victim)
                        if uid:
                            if server_id not in players[uid]["ingame"]:
                                players[uid]["ingame"][server_id] = playerdata
                            players[uid]["ingame"][server_id]["stats"]["pvedeaths"] += 1
                    # PVP DEATH AND PVP KILL
                    if braces == 1:  # player killed by another player so pvp death and kill
                        reg = r'Tribemember (.+) - .+ was .+ by (.+) -'
                        data = re.findall(reg, action)
                        victim = data[0]  # PVP DEATH
                        if victim not in tr["members"]:
                            tr["members"].append(victim)
                        uid = await self.get_uid(players, victim)
                        if uid:
                            if server_id not in players[uid]["ingame"]:
                                players[uid]["ingame"][server_id] = playerdata
                            players[uid]["ingame"][server_id]["stats"]["pvpdeaths"] += 1
                        killer = data[1]  # PVP KILL
                        uid = await self.get_uid(players, killer)
                        if uid:
                            if server_id not in players[uid]["ingame"]:
                                players[uid]["ingame"][server_id] = playerdata
                            players[uid]["ingame"][server_id]["stats"]["pvpkills"] += 1
                    # PVP DEATH
                    if braces == 2:  # player killed by a tribe's dino so pvp death
                        log.info(msg)  # Still trying to figure out possible strings to parse
                        reg = r'Tribemember (.+) -.+was'
                        victim = re.search(reg, action).group(1)
                        if victim not in tr["members"]:
                            tr["members"].append(victim)
                        uid = await self.get_uid(players, victim)
                        if uid:
                            if server_id not in players[uid]["ingame"]:
                                players[uid]["ingame"][server_id] = playerdata
                            if "stats" in players[uid]["ingame"][server_id]:
                                players[uid]["ingame"][server_id]["stats"]["pvpdeaths"] += 1
                color = discord.Color.from_rgb(255, 13, 0)  # bright red
            elif "tribe killed" in action.lower():
                # TRIBE KILL
                valid = True
                if "Baby" in action:
                    valid = False
                if "Juvenile" in action:
                    valid = False
                if "Adolescent" in action:
                    valid = False
                if name in action:
                    valid = False
                if valid:
                    # Add to tribe kills
                    tribes[tribe_id]["kills"] += 1
                color = discord.Color.from_rgb(246, 255, 0)  # gold
            elif "starved" in action.lower():
                color = discord.Color.from_rgb(140, 7, 0)  # dark red
            elif "demolished" in action.lower():
                color = discord.Color.from_rgb(133, 86, 5)  # brown
            elif "destroyed" in action.lower():
                color = discord.Color.from_rgb(115, 114, 112)  # grey
            elif "tamed" in action.lower():
                reg = r'(.+) Tamed'
                tamer = re.search(reg, action).group(1)
                uid = await self.get_uid(players, tamer)
                if uid:
                    if server_id not in players[uid]["ingame"]:
                        players[uid]["ingame"][server_id] = playerdata
                    # Add to player tame count
                    players[uid]["ingame"][server_id]["stats"]["tamed"] += 1
                color = discord.Color.from_rgb(0, 242, 117)  # lime
            elif "froze" in action.lower():
                color = discord.Color.from_rgb(0, 247, 255)  # cyan
            elif "claimed" in action.lower():
                color = discord.Color.from_rgb(255, 0, 225)  # pink
            elif "unclaimed" in action.lower():
                color = discord.Color.from_rgb(102, 0, 90)  # dark purple
            elif "uploaded" in action.lower():
                color = discord.Color.from_rgb(255, 255, 255)  # white
            elif "downloaded" in action.lower():
                color = discord.Color.from_rgb(2, 2, 117)  # dark blue
            else:
                color = discord.Color.purple()
        embed = discord.Embed(
            title=f"{server['cluster'].upper()} {server['name'].capitalize()}: {name}",
            color=color,
            description=f"```py\n{action}\n```"
        )
        embed.set_footer(text=f"{time} | Tribe ID: {tribe_id}")
        return tribe_id, embed

    # Fetch a user ID from a given character name if it exists
    @staticmethod
    async def get_uid(players: dict, character_name: str) -> str:
        if character_name.lower() in ["human", "humano"]:
            return ""  # Dont bother logging players that dont name their character
        for uid, data in players.items():
            ig = data["ingame"]
            for channel, details in ig.items():
                if "name" in details:
                    name = details["name"]
                    if name == character_name:
                        return uid

    # Cleans up the most recent live embed posted in the status channel
    @staticmethod
    async def status_cleaner(status: dict, dest_channel: discord.TextChannel):
        message = status["message"]
        multi = status["multi"]
        try:
            if message:
                msg_to_delete = await dest_channel.fetch_message(message)
                if msg_to_delete:
                    await msg_to_delete.delete()
            else:
                for msg in multi:
                    msg_to_delete = await dest_channel.fetch_message(msg)
                    if msg_to_delete:
                        await msg_to_delete.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        except Exception as e:
            cleanup_type = "Status" if message else "Multi-Status"
            log.warning(f"{cleanup_type} Cleanup: {e}")

    # Pull the first (authorized) token found (for api calls where the token owner doesnt matter)
    @staticmethod
    def pull_key(clusters: dict):
        for cname, cluster in clusters.items():
            for sname, server in cluster["servers"].items():
                if "tokens" in server:
                    tokens = server["tokens"]
                    return tokens, cname, sname

    # Parse in-game commands as efficiently as possible
    # only command that can have multiple words as an arg is "rename"
    @staticmethod
    def parse_cmd(command_string: str):
        cmd = command_string.split()
        # Sent an empty string for some reason so just return
        if not cmd:
            return None, None
        command = cmd[0].lower()
        # Command has no arguments so return arg as None
        if len(cmd) == 1:
            return command, None
        # Pull command name and append the rest to a string for the rename
        if command == "rename":
            args = cmd[1:]
            newname = ""
            for i in args:
                newname += f"{i} "
            newname = newname.strip()
            arg = newname
        # All other commands just have 1 arg
        else:
            arg = cmd[1]
        return command, arg

    # Find xuid from given gamertag
    @staticmethod
    async def get_player(gamertag: str, players: dict):
        for xuid, stats in players.items():
            if gamertag.lower() == stats["username"].lower():
                return xuid, stats
        else:
            return None, None

    # Is player registered in-game on a server?
    @staticmethod
    def get_implant(playerdata: dict, channel: str):
        # idk why playerdata would be none, but eh
        if not playerdata:
            return None
        # Person hasnt registered their implant ID on any maps
        if "ingame" not in playerdata:
            return None
        # See if the person has registered their implant for that channel id
        if channel not in playerdata["ingame"]:
            return None
        implant = playerdata["ingame"][channel]["implant"]
        if implant:
            return implant

    @staticmethod
    async def check_reg_status(settings: dict, uid: int):
        stats = settings["players"]
        for xuid, stat in stats.items():
            if "discord" in stat:
                if stat["discord"] == uid:
                    return stat["username"]

    # Hard coded item send for those hard times
    # Sends some in-game items that can help get a player unstuck, or just kill themselves
    @commands.command(name="imstuck")
    @commands.cooldown(1, 1800, commands.BucketType.user)
    @commands.guild_only()
    async def im_stuck(self, ctx: commands.Context):
        """
        For those tough times when Ark is being Ark

        Sends you tools to get unstuck, or off yourself.
        """
        settings = await self.config.guild(ctx.guild).all()
        if len(settings["clusters"]) == 0:
            return await ctx.send("No clusters have been set!")
        embed = discord.Embed(
            description=f"**Type your Implant ID in chat.**"
        )
        embed.set_footer(text="Hint: your implant id can be seen by hovering over it in your inventory!")
        embed.set_thumbnail(url="https://i.imgur.com/kfanq99.png")
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        # Wait for the person to reply with their implant ID
        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="Ok guess ya didn't need help then."))

        if reply.content.isdigit():  # check if player is retarded or not
            implant_id = reply.content
            try:
                await reply.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await ctx.send("I don't have permissions to delete your reply ¯\\_(ツ)_/¯")
            embed = discord.Embed(
                description=f"Sit tight, your care package is on the way!"
            )
            embed.set_thumbnail(url="https://i.imgur.com/8ofOx6X.png")
            await msg.edit(embed=embed)

            # Gather current servers into a list
            serverlist = []
            for cname, cdata in settings["clusters"].items():
                for sname, sdata in cdata["servers"].items():
                    serverlist.append(sdata)
            if len(serverlist) == 0:
                return await ctx.send("I dont see any servers, make sure an admin has set them up!")

            # Just iterates through all servers so user doesnt have to select a specific server
            stucktasks = []
            for server in serverlist:
                for path in IMSTUCK_BLUEPRINTS:
                    stucktasks.append(self.executor(ctx.guild, server, f"GiveItemToPlayer {implant_id} {path}"))

            async with ctx.typing():
                await asyncio.gather(*stucktasks)
            return
        else:
            return await msg.edit(embed=discord.Embed(description="Ok guess ya didn't need help then."))

    # Deletes all player data in the config
    @commands.command(name="wipestats")
    @commands.guildowner()
    @commands.guild_only()
    async def wipe_all_stats(self, ctx: commands.Context):
        """Wipe all player stats including last seen data and registration."""
        async with self.config.guild(ctx.guild).all() as data:
            data["players"].clear()
            await ctx.send(embed=discord.Embed(description="All player data has been wiped."))

    # Reset graph data
    @commands.command(name="wipegraphdata")
    @commands.guildowner()
    @commands.guild_only()
    async def wipe_graph_data(self, ctx: commands.Context):
        """Reset the player count graph data"""
        async with self.config.guild(ctx.guild).all() as settings:
            for sname, slist in settings["serverstats"].items():
                if sname != "expiration":
                    slist.clear()
            await ctx.tick()

    # Reset tribe data
    @commands.command(name="wipetribedata")
    @commands.guildowner()
    @commands.guild_only()
    async def wipe_tribe_data(self, ctx: commands.Context):
        """Reset all tribe data"""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            tribes.clear()
            await ctx.tick()

    # Remove a discord user from a Gamertag
    @commands.command(name="unregister")
    @commands.admin()
    @commands.guild_only()
    async def unregister_user(self, ctx: commands.Context, member: discord.Member):
        """Unregister a discord user from any gamertags theyre associated with"""
        async with self.config.guild(ctx.guild).players() as players:
            unreg = []
            for xuid, data in players.items():
                if "discord" in data:
                    if data["discord"] == member.id:
                        unreg.append((xuid, data["username"]))
            if len(unreg) == 0:
                return await ctx.send(f"{member.mention} not found registered to any Gamertag!")
            for xuid, gamertag in unreg:
                await ctx.send(f"{member.mention} has been unregistered from the Gamertag {gamertag}")
                del players[xuid]["discord"]

    # Lets a player unregister themselves
    @commands.command(name="unregisterme")
    @commands.guild_only()
    async def unregister_user_self(self, ctx: commands.Context):
        """Unregister a yourself from any gamertags you have registered to"""
        myself = ctx.author.id
        async with self.config.guild(ctx.guild).players() as players:
            unreg = []
            for xuid, data in players.items():
                if "discord" in data:
                    if data["discord"] == myself:
                        unreg.append((xuid, data["username"]))
            if len(unreg) == 0:
                return await ctx.send(f"You arent registered to any Gamertag!")
            for xuid, gamertag in unreg:
                await ctx.send(f"Unregistered you from {gamertag}!")
                del players[xuid]["discord"]

    @commands.command(name="unregistergt")
    @commands.admin()
    @commands.guild_only()
    async def unregister_gamertag(self, ctx: commands.Context, gamertag: str):
        """Unregister any discord account associated with a specific gamertag"""
        async with self.config.guild(ctx.guild).players() as players:
            unreg = []
            for xuid, data in players.items():
                if "discord" in data:
                    if data["username"].lower() == gamertag.lower():
                        unreg.append((xuid, data["discord"]))
            if len(unreg) == 0:
                return await ctx.send(f"{gamertag} not found registered to any Gamertag!")
            for xuid, user in unreg:
                user = ctx.guild.get_member(user)
                await ctx.send(f"Removed {user} from {gamertag}")
                del players[xuid]["discord"]

    # Delete a player from the player data
    @commands.command(name="deleteplayer")
    @commands.admin()
    @commands.guild_only()
    async def delete_player(self, ctx: commands.Context, xuid: str):
        """Delete player data from the server stats"""
        async with self.config.guild(ctx.guild).players() as players:
            for pid, data in players.items():
                if str(xuid) == str(pid):
                    del players[pid]
                    return await ctx.tick()

    # Initializes a player to the stats section, or appends their discord ID to existing gamertag in database
    @commands.command(name="register")
    @commands.guild_only()
    async def register_user(self, ctx: commands.Context):
        """Register your Gamertag or steam ID in the database."""

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        settings = await self.config.guild(ctx.guild).all()
        user = await self.check_reg_status(settings, ctx.author.id)
        if user:
            return await ctx.send(f"You are already registered as {user}\n"
                                  f"If you want to re-register, type `{ctx.prefix}unregisterme` "
                                  f"and then try again.")

        ctype = settings["clustertypes"]
        if ctype == "xbox":
            # do xbox method
            await self.xbox_reg(ctx)
        elif ctype == "steam":
            await self.manual_or_steam_reg(ctx, "steam")
        else:  # Both steam and xbox servers available
            title = "Xbox or Steam?"
            desc = "Type what type of server you want to register for in chat below."
            embed = discord.Embed(
                title=title,
                description=desc
            )
            msg = await ctx.send(embed=embed)
            try:
                reply = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
            if "x" in reply.content.lower():
                await self.xbox_reg(ctx)
            elif "s" in reply.content.lower():
                await self.manual_or_steam_reg(ctx, "steam")
            else:
                desc = "Registration Cancelled"
                embed = discord.Embed(description=desc)
                return await msg.edit(embed=embed)

    async def xbox_reg(self, ctx: commands.Context):

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        clusters = await self.config.guild(ctx.guild).clusters()
        xsapi_available = False
        for cluster in clusters.values():
            for server in cluster["servers"].values():
                if "tokens" in server:
                    xsapi_available = True
                    break

        if xsapi_available:
            embed = discord.Embed(
                description="**Type your Xbox Gamertag chat below.**"
            )
            msg = await ctx.send(embed=embed)
            try:
                reply = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
            rpl = reply.content.lower()
            if rpl == "no" or rpl == "cancel":
                return await msg.edit(embed=discord.Embed(description="Registration Cancelled"))
            gamertag = reply.content
            embed = discord.Embed(color=discord.Color.green(),
                                  description=f"Searching...")
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            async with aiohttp.ClientSession() as session:
                tokens, cname, sname = self.pull_key(clusters)
                xbl_client, _ = await self.auth_manager(session, cname, sname, tokens, ctx)
                if not xbl_client:
                    return
                try:
                    profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
                except aiohttp.ClientResponseError:
                    embed = discord.Embed(
                        description=f"Invalid Gamertag. Try again.",
                        color=discord.Color.red()
                    )
                    return await msg.edit(embed=embed)
                # Format json data
                gt, xuid, gs, pfp = profile_format(profile_data)
                async with self.config.guild(ctx.guild).players() as players:
                    if xuid in players:
                        if "discord" in players[xuid]:
                            if players[xuid]["discord"] != ctx.author.id:
                                claimed = ctx.guild.get_member(players[xuid]["discord"])
                                embed = discord.Embed(
                                    description=f"{claimed.mention} has already claimed this Gamertag",
                                    color=discord.Color.orange()
                                )
                                return await msg.edit(embed=embed)
                            if players[xuid]["discord"] == ctx.author.id:
                                embed = discord.Embed(
                                    description=f"You have already claimed this Gamertag",
                                    color=discord.Color.green()
                                )
                                return await msg.edit(embed=embed)
                        players[xuid]["discord"] = ctx.author.id
                    else:
                        players[xuid] = {
                            "discord": ctx.author.id,
                            "username": gt,
                            "playtime": {"total": 0},
                            "lastseen": {
                                "time": datetime.datetime.now(pytz.timezone("UTC")).isoformat(),
                                "map": None
                            },
                            "ingame": {}
                        }
            embed = discord.Embed(
                color=discord.Color.green(),
                description=f"✅ Gamertag set to `{gamertag}`\n"
                            f"XUID: `{xuid}`\n"
                            f"Gamerscore: `{gs}`\n\n"
            )
            embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
            embed.set_thumbnail(url=pfp)
            await msg.edit(embed=embed)
            embed = discord.Embed(
                description=f"You can now type `{ctx.prefix}addme` to have a host Gamertag add you.",
                color=discord.Color.magenta()
            )
            embed.set_footer(text="Then you can follow it back and join session from its profile page!")
            await ctx.send(embed=embed)
        else:
            await ctx.send("No API tokens found. Switching to manual registration.")
            await self.manual_or_steam_reg(ctx, "xbox")

    async def manual_or_steam_reg(self, ctx: commands.Context, ctype: str):

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        if ctype == "xbox":
            prompt1 = "**Type your Xbox User ID (XUID) in chat below.**"
            prompt2 = "**Type your Xbox Gamertag chat below.**"
            nametype = "Gamertag"
            id_type = "XUID"
        else:
            prompt1 = "**Type your STEAM ID in chat below.**"
            prompt2 = "**Type your Steam Username in chat below.**"
            nametype = "Username"
            id_type = "Steam ID"

        embed = discord.Embed(
            description=prompt1
        )
        msg = await ctx.send(embed=embed)
        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
        rpl = reply.content.lower()
        if rpl == "no" or rpl == "cancel":
            return await msg.edit(embed=discord.Embed(description="Registration Cancelled"))
        if not reply.content.isdigit():
            desc = "That is **NOT** a number... Registration cancelled :expressionless:"
            embed = discord.Embed(description=desc)
            return await msg.edit(embed=embed)
        length = len(reply.content)
        if ctype == "xbox" and length != 16:
            desc = "Incorrect number of digits for a valid XUID, Try again."
            embed = discord.Embed(description=desc)
            return await msg.edit(embed=embed)
        if ctype == "steam":
            if length > 19 or length < 17:
                desc = "Incorrect number of digits for a valid Steam ID, Try again."
                embed = discord.Embed(description=desc)
                return await msg.edit(embed=embed)

        uid = reply.content
        players = await self.config.guild(ctx.guild).players()
        if uid in players and "discord" in players[uid]:
            if players[uid]["discord"] != ctx.author.id:
                claimed = ctx.guild.get_member(players[uid]["discord"])
                embed = discord.Embed(
                    description=f"{claimed.mention} has already claimed this ID",
                    color=discord.Color.orange()
                )
                return await msg.edit(embed=embed)
            if players[uid]["discord"] == ctx.author.id:
                embed = discord.Embed(
                    description=f"You have already claimed this ID",
                    color=discord.Color.green()
                )
                return await msg.edit(embed=embed)

        embed = discord.Embed(
            description=prompt2
        )
        await msg.edit(embed=embed)
        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        username = reply.content
        async with self.config.guild(ctx.guild).players() as players:
            if uid in players:
                players[uid]["discord"] = ctx.author.id
            else:
                players[uid] = {
                    "discord": ctx.author.id,
                    "username": username,
                    "playtime": {"total": 0},
                    "lastseen": {
                        "time": datetime.datetime.now(pytz.timezone("UTC")).isoformat(),
                        "map": None
                    },
                    "ingame": {}
                }
        embed = discord.Embed(
            description=f"Your {nametype} has been set to `{username}`\n"
                        f"{id_type}: `{uid}`",
            color=discord.Color.green()
        )
        embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
        await msg.edit(embed=embed)

    # Force the host Gamertag(s) to add the user as a friend using XSAPI
    @commands.command(name="addme")
    @commands.guild_only()
    async def add_user(self, ctx: commands.Context):
        """
        (Xbox/Win10 CROSSPLAY ONLY)Add yourself as a friend from the host gamertags

        This command requires api keys to be set for the servers
        """
        players = await self.config.guild(ctx.guild).players()
        for xuid in players:
            if "discord" in players[xuid]:
                if ctx.author.id == players[xuid]["discord"]:
                    ptag = players[xuid]["username"]
                    break
        else:
            embed = discord.Embed(description=f"You havent registered yet!\n\n"
                                              f"Register with the `{ctx.prefix}register` command.")
            embed.set_thumbnail(url=FAILED)
            return await ctx.send(embed=embed)
        # Enumerate maps and display them in an embed
        clusters = await self.config.guild(ctx.guild).clusters()
        map_options = "**Gamertag** - `Map/Cluster`\n"
        servernum = 1
        serverlist = []
        for cname, cluster in clusters.items():
            for sname, server in cluster["servers"].items():
                if "tokens" in server:
                    tokendata = server["tokens"]
                    map_options += f"**{servernum}.** `{server['gamertag']}` - `{sname} {cname}`\n"
                    serverlist.append((servernum, server['gamertag'], tokendata, cname, sname))
                    servernum += 1
        if len(serverlist) == 0:
            return await ctx.send("No clusters have been created yet!")
        map_options += f"**All** - `Adds All Servers`"
        embed = discord.Embed(
            title=f"Add Yourself as a Friend",
            description=f"**TYPE THE NUMBER that corresponds with the server you want.**\n\n"
                        f"{map_options}"
        )
        embed.set_footer(text="Type your reply below")
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        reply = None
        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            try:
                await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
            except discord.NotFound:
                return
        if not reply:
            return
        if reply.content.lower() == "all":
            embed = discord.Embed(
                description="Gathering Data..."
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)

            addstatus = ""
            # Iterate through server tokens and send off friend requests
            for cname, cluster in clusters.items():
                for sname, server in cluster["servers"].items():
                    if "tokens" in server:
                        tokendata = server["tokens"]
                        async with aiohttp.ClientSession() as session:
                            xbl_client, token = await self.auth_manager(session, cname, sname, tokendata, ctx)
                            if not xbl_client:
                                addstatus += f"`{server['gamertag']}: `❌\n"
                                continue
                            status = await add_friend(xuid, token)
                            if 200 <= status <= 204:
                                embed = discord.Embed(
                                    description=f"Friend request sent from... `{server['gamertag']}`",
                                    color=discord.Color.green()
                                )
                                embed.set_thumbnail(url=LOADING)
                                addstatus += f"`{server['gamertag']}: `✅\n"
                            else:
                                embed = discord.Embed(
                                    description=f"Friend request from `{server['gamertag']}` may have failed!",
                                    color=discord.Color.red()
                                )
                                embed.set_thumbnail(url=FAILED)
                                addstatus += f"`{server['gamertag']}: `❌\n"
                            await msg.edit(embed=embed)
            embed = discord.Embed(color=discord.Color.green(),
                                  description=f"✅ Finished adding `{players[xuid]['username']}` for All Gamertags.\n"
                                              f"You should now be able to join from the Gamertags' profile page.")
            if addstatus != "":
                embed.add_field(name="Add Status", value=addstatus)
            embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
            embed.set_thumbnail(url=SUCCESS)
            await msg.edit(embed=embed)
        elif reply.content.isdigit():
            embed = discord.Embed(
                description="Gathering Data..."
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            for data in serverlist:
                if int(reply.content) == data[0]:
                    gt = data[1]
                    tokendata = data[2]
                    cname = data[3]
                    sname = data[4]
                    break
            else:
                color = discord.Color.red()
                embed = discord.Embed(description=f"Could not find the server corresponding to {reply.content}!",
                                      color=color)
                return await ctx.send(embed=embed)
            embed = discord.Embed(
                description=f"Sending friend request from {gt}..."
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            async with aiohttp.ClientSession() as session:
                xbl_client, token = await self.auth_manager(session, cname, sname, tokendata, ctx)
                if not xbl_client:
                    embed = discord.Embed(
                        description=f"Friend request from `{gt}` may have failed!",
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(url=FAILED)
                    return await msg.edit(embed=embed)
                status = await add_friend(xuid, token)
                if 200 <= status <= 204:
                    embed = discord.Embed(color=discord.Color.green(),
                                          description=f"✅ `{gt}` Successfully added `{ptag}`\n"
                                                      f"You should now be able to join from the Gamertag's"
                                                      f" profile page.\n\n"
                                                      f"**TO ADD MORE:** type `{ctx.prefix}addme` again.")
                    embed.set_author(name="Success", icon_url=ctx.author.avatar_url)
                    embed.set_thumbnail(url=SUCCESS)
                else:
                    embed = discord.Embed(
                        description=f"Friend request from `{gt}` may have failed!",
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(url=FAILED)
                await msg.edit(embed=embed)
        else:
            color = discord.Color.dark_grey()
            return await msg.edit(embed=discord.Embed(description="Incorrect Reply, menu closed.", color=color))

    # Send off an RCON command to a selected server
    @commands.command(name="rcon")
    @commands.guild_only()
    async def manual_rcon_cmd(self, ctx: commands.Context, clustername: str, servername: str, *, command: str):
        """Perform an RCON command"""
        cname = clustername.lower()
        sname = servername.lower()
        settings = await self.config.guild(ctx.guild).all()
        if not self.allowed_to_run(ctx, settings, command):
            return await ctx.send("You do not have the required permissions to run that command.")

        clusters = settings["clusters"]
        if cname != "all" and cname not in clusters:
            return await ctx.send(f"{cname} cluster not found")
        if cname != "all" and sname != "all" and sname not in clusters[cname]["servers"]:
            return await ctx.send(f"Server not found in {cname} cluster")

        serverlist = self.compile_servers(ctx.guild, cname, sname)

        if len(serverlist) == 0:
            return await ctx.send("No servers have been found")

        if command.lower() == "doexit":  # Count down, save world, exit - for clean shutdown
            await ctx.send("Beginning reboot countdown...")
            for server in serverlist:
                mapchannel = ctx.guild.get_channel(server["chatchannel"])
                msg = "Reboot starting, make sure you are in a bed to avoid your character dying!"
                await mapchannel.send(f"**{msg}**")
                await self.executor(ctx.guild, server, f'broadcast <RichColor Color="1,0,0,1">{msg.upper()}</>')
            for i in range(10, 0, -1):
                for server in serverlist:
                    mapchannel = ctx.guild.get_channel(server["chatchannel"])
                    await mapchannel.send(f"Reboot in {i}")
                    await self.executor(ctx.guild, server, f"serverchat Reboot in {i}")
                await asyncio.sleep(0.6)
            await ctx.send("Saving maps...")
            save = []
            for server in serverlist:
                mapchannel = ctx.guild.get_channel(server["chatchannel"])
                await mapchannel.send(f"Saving map...")
                save.append(self.executor(ctx.guild, server, "saveworld"))
            await asyncio.gather(*save)
            await asyncio.sleep(5)
            await ctx.send("Running DoExit...")
            exiting = []
            for server in serverlist:
                exiting.append(self.executor(ctx.guild, server, "doexit"))
            await asyncio.gather(*exiting)
        else:
            rtasks = []
            for server in serverlist:
                rtasks.append(manual_rcon(ctx.channel, server, command))
            await asyncio.gather(*rtasks)

        if command.lower().startswith("banplayer"):  # Have the host Gamertags block the user that was banned
            player_id = str(re.search(r'(\d+)', command).group(1))
            blocked = ""
            async with ctx.typing():
                async with aiohttp.ClientSession() as session:
                    for server in serverlist:
                        if "tokens" in server:
                            tokens = server["tokens"]
                            host = server["gamertag"]
                            xbl_client, token = await self.auth_manager(
                                session,
                                server["cluster"],
                                server["name"],
                                tokens,
                                ctx
                            )
                            if token:
                                try:
                                    status = await block_player(int(player_id), token)
                                except Exception as e:
                                    if "semaphore" in str(e):
                                        pass
                                if 200 <= status <= 204:
                                    blocked += f"{host} Successfully blocked XUID: {player_id}\n"
                                else:
                                    blocked += f"{host} Failed to block XUID: {player_id} - Status: {status}\n"
                    if blocked != "":
                        await ctx.send(box(blocked, lang="python"))
        if command.lower().startswith("unbanplayer"):  # Have the host Gamertags unblock the user
            player_id = str(re.search(r'(\d+)', command).group(1))
            unblocked = ""
            async with ctx.typing():
                async with aiohttp.ClientSession() as session:
                    for server in serverlist:
                        if "tokens" in server:
                            tokens = server["tokens"]
                            host = server["gamertag"]
                            xbl_client, token = await self.auth_manager(
                                session,
                                server["cluster"],
                                server["name"],
                                tokens,
                                ctx
                            )
                            if token:
                                try:
                                    status = await unblock_player(int(player_id), token)
                                except Exception as e:
                                    if "semaphore" in str(e):
                                        pass
                                if 200 <= status <= 204:
                                    unblocked += f"{host} Successfully unblocked XUID: {player_id}\n"
                                else:
                                    unblocked += f"{host} Failed to unblock XUID: {player_id} - Status: {status}\n"
                    if unblocked != "":
                        await ctx.send(box(unblocked, lang="python"))

    @commands.command(name="bulksend")
    @commands.guild_only()
    async def bulk_send_item(
            self,
            ctx: commands.Context,
            clustername: str,
            servername: str,
            implant_id: str,
            count: int,
            *,
            blueprint_string: str
    ):
        """
        Bulk send an item to a player

        The `count` specifies how many times to run the command,
        this is useful for filling an inventory of an item with a small stack size
        the blueprint string should include the amount, quality, and blueprint numbers at the end too
        """
        cname = clustername.lower()
        sname = servername.lower()
        settings = await self.config.guild(ctx.guild).all()
        if not self.allowed_to_run(ctx, settings, "giveitemtoplayer"):
            return await ctx.send("You do not have the required permissions to run that command.")
        clusters = settings["clusters"]
        if cname not in clusters:
            return await ctx.send(f"{cname} cluster not found")
        if sname not in clusters[cname]["servers"]:
            return await ctx.send(f"Server not found in {cname} cluster")
        server = self.compile_servers(ctx.guild, cname, sname)
        server = dict(server[0])  # was getting incorrect type inspection idk
        await ctx.send("Sending items in bulk")
        command = f"giveitemtoplayer {implant_id} {blueprint_string}"

        def sender():
            try:
                with Client(
                        host=server['ip'],
                        port=server['port'],
                        passwd=server['password'],
                        timeout=10
                ) as client:
                    for i in range(count):
                        client.run(command)
            except socket.timeout:
                return
            except Exception as e:
                log.warning(f"Bulksend Error: {e}")

        async with ctx.typing():
            await self.bot.loop.run_in_executor(None, sender)
        await ctx.send("Bulk send complete")

    @staticmethod
    def allowed_to_run(ctx: commands.Context, settings: dict, command: str):
        allowed = False
        # Determine if user is allowed to use the command
        for role in ctx.author.roles:
            if role.id == settings["fullaccessrole"]:
                allowed = True
            for modrole in settings["modroles"]:
                if role.id == modrole:
                    modcmds = settings["modcommands"]
                    for cmd in modcmds:
                        if str(cmd.lower()) in command.lower():
                            allowed = True
        if ctx.author.id == ctx.guild.owner.id:
            allowed = True
        if allowed:
            return True

    def compile_servers(self, guild: discord.guild, cname: str, sname: str) -> list:
        serverlist = []
        for tup in self.servers:
            sguild = tup[0]
            server = tup[1]
            if sguild == guild.id:
                if cname == "all" and sname == "all":
                    serverlist.append(server)
                elif cname == "all" and sname != "all":
                    if server["name"] == sname:
                        serverlist.append(server)
                elif cname != "all" and sname == "all":
                    if server["cluster"] == cname:
                        serverlist.append(server)
                elif cname != "all" and sname != "all":
                    if server["cluster"] == cname and server["name"] == sname:
                        serverlist.append(server)
                else:
                    continue
        return serverlist

    # Re-Initialize the cache, for debug purposes
    @commands.command(name="init", hidden=True)
    @commands.is_owner()
    @commands.guild_only()
    async def init_config(self, ctx):
        await self.initialize()
        await ctx.tick()

    # STAT COMMANDS
    # Thanks Vexed#3211 for some ideas with the Matplotlib logic :)
    @commands.command(name="servergraph", hidden=False)
    @commands.guild_only()
    async def graph_player_count(self, ctx: commands.Context, hours=None):
        """View a graph of player count over a set time"""
        embed = discord.Embed(color=discord.Color.green(),
                              description=f"Gathering Data...")
        embed.set_thumbnail(url=LOADING)
        msg = await ctx.send(embed=embed)
        settings = await self.config.guild(ctx.guild).all()
        if not hours:
            hours = 1
        # Convert to float and back to int to handle if someone types a float
        hours = float(hours)
        file = await get_graph(settings, int(hours))
        await msg.delete()
        if file:
            await ctx.send(file=file)
        else:
            await ctx.send("Not enough data, give it some time")

    # Get the top 10 players in the cluster, browse pages to see them all
    @commands.command(name="playtimeoverview", aliases=["pto"])
    @commands.guild_only()
    async def ark_playtime_overview(self, ctx: commands.Context):
        """View overview of players playtimes"""
        stats = await self.config.guild(ctx.guild).players()
        tz = await self.config.guild(ctx.guild).timezone()
        pages = overview_format(stats, ctx.guild, tz)
        if len(pages) == 0:
            return await ctx.send("There are no stats available yet!")
        await menu(ctx, pages, DEFAULT_CONTROLS)

    # Get the top 10 players in the cluster, browse pages to see them all
    @commands.command(name="arklb", aliases=["arktop"])
    @commands.guild_only()
    async def ark_leaderboard(self, ctx: commands.Context):
        """View the playtime leaderboard"""
        stats = await self.config.guild(ctx.guild).players()
        tz = await self.config.guild(ctx.guild).timezone()
        pages = lb_format(stats, ctx.guild)
        if len(pages) == 0:
            return await ctx.send("There are no stats available yet!")
        await menu(ctx, pages, DEFAULT_CONTROLS)

    # Get the top 10 players in the cluster, browse pages to see them all
    @commands.command(name="tribelb")
    @commands.guild_only()
    async def tribe_leaderboard(self, ctx: commands.Context):
        """View leaderboard for all tribes"""
        tribes = await self.config.guild(ctx.guild).tribes()
        pages = tribe_lb_format(tribes, ctx.guild)
        if len(pages) == 0:
            return await ctx.send("There are no tribes available yet!")
        await menu(ctx, pages, DEFAULT_CONTROLS)

    # Displays an embed of all maps for all clusters in order of time played on each map along with top player
    @commands.command(name="clusterstats")
    @commands.guild_only()
    async def cluster_stats(self, ctx: commands.Context):
        """View playtime data for all clusters"""
        stats = await self.config.guild(ctx.guild).players()
        pages = cstats_format(stats, ctx.guild)
        if not pages:
            return await ctx.send("No data to display yet!")
        if len(pages) == 1:
            embed = pages[0]
            return await ctx.send(embed=embed)
        await menu(ctx, pages, DEFAULT_CONTROLS)

    # Get detailed info of an individual player on the server
    @commands.command(name="playerstats")
    @commands.guild_only()
    async def get_player_stats(self, ctx: commands.Context, *, gamertag: str = None):
        """View stats for yourself or another gamertag"""
        settings = await self.config.guild(ctx.guild).all()
        stats = settings["players"]
        if not gamertag:
            for xuid, data in stats.items():
                if "discord" in data:
                    if ctx.author.id == data["discord"]:
                        gamertag = data["username"]
                        break
            else:
                embed = discord.Embed(description=f"You havent registered yet!\n\n"
                                                  f"Register with the `{ctx.prefix}register` command.")
                embed.set_thumbnail(url=FAILED)
                return await ctx.send(embed=embed)
        embed = player_stats(settings, ctx.guild, gamertag)
        if not embed:
            return await ctx.send(embed=discord.Embed(description=f"No player data found for {gamertag}"))
        await ctx.send(embed=embed)

    # Find out if a user has registered their gamertag
    @commands.command(name="findplayer")
    @commands.guild_only()
    async def find_player_from_discord(self, ctx: commands.Context, *, member: discord.Member):
        """Find out if a player has registered"""
        settings = await self.config.guild(ctx.guild).all()
        stats = settings["players"]
        if not member:
            member = self.bot.get_user(member)

        if not member:
            return await ctx.send(f"Couldnt find member.")
        for xuid, stat in stats.items():
            if "discord" in stat:
                if stat["discord"] == member.id:
                    return await ctx.send(f"User is registered as **{stat['username']}**")
        await ctx.send("User never registered.")

    @commands.command(name="findcharname")
    @commands.guild_only()
    async def find_player_by_character(self, ctx: commands.Context, *, character_name: str):
        """Find any players associated with a specified character name"""
        players = await self.config.guild(ctx.guild).players()
        matches = ""
        uids = []
        for uid, data in players.items():
            ig = data["ingame"]
            for channel, details in ig.items():
                name = details["name"]
                if name:
                    if name.lower() == character_name.lower():
                        gt = data["username"]
                        if uid not in uids:
                            matches += f"`{gt}: `{uid}\n"
                            uids.append(uid)
        if matches:
            embed = discord.Embed(
                title="Found Matches",
                description=f"`Gamertag: `Player ID\n{matches}"
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("No matches found")

    # Find out if a user has registered their discord id
    @commands.command(name="findbyid")
    @commands.guild_only()
    async def find_player_from_by_id(self, ctx: commands.Context, uid: int):
        """Find out if a player has registered by their discord ID

        This is a manual method for if the member has left the discord
        """
        settings = await self.config.guild(ctx.guild).all()
        stats = settings["players"]
        for xuid, stat in stats.items():
            if "discord" in stat:
                if stat["discord"] == uid:
                    return await ctx.send(f"User is registered as **{stat['username']}**")
        await ctx.send("User never registered.")

    # Main group
    @commands.group(name="arktools")
    @commands.guild_only()
    async def arktools_main(self, ctx: commands.Context):
        """ArkTools base setting command."""
        pass

    @arktools_main.group(name="ranks")
    @commands.admin()
    async def ranks_main(self, ctx: commands.Context):
        """Base command for playtime ranks"""
        pass

    @ranks_main.command(name="link")
    async def link_level(self, ctx: commands.Context, role: discord.Role, hours_played: int):
        """
        Link a role to a certain amount of playtime(in-hours)

        DO NOT USE EMOJIS IN RANK ROLE NAMES! Ark doesnt support unicode or
        emojis, so dont use them.
        """
        async with self.config.guild(ctx.guild).ranks() as ranks:
            if hours_played in ranks:
                old = ranks[hours_played]
                old = ctx.guild.get_role(old)
                msg = f"The role {role.mention} will now be assigned when player hits {hours_played} hours " \
                      f"instead of {old.mention}"
            else:
                msg = f"The role {role.mention} will now be assigned when player hits {hours_played} hours"
            ranks[hours_played] = role.id
            await ctx.send(msg)

    @ranks_main.command(name="unlink")
    async def unlink_level(self, ctx: commands.Context, hours: int):
        """Unlink a role assigned to a level"""
        async with self.config.guild(ctx.guild).ranks() as ranks:
            if hours in ranks:
                del ranks[hours]
                await ctx.tick()
            else:
                await ctx.send("No role assigned to that time played")

    @ranks_main.command(name="view")
    async def view_ranks(self, ctx: commands.Context):
        """View current settings for the rank system"""
        config = await self.config.guild(ctx.guild).all()
        unrank = config["autoremove"]
        rename = config["autorename"]
        ranks = config["ranks"]
        settings = f"`AutoUnrank: `{unrank}\n" \
                   f"`AutoRename: `{rename}\n\n"
        rankmsg = ""
        embed = discord.Embed(
            description=settings,
            color=discord.Color.random()
        )
        for hour in ranks:
            role = ctx.guild.get_role(ranks[hour])
            if role:
                role = role.mention
            else:
                role = ranks[hour]
            if int(hour) == 1:
                hour = f"{hour} hour played"
            else:
                hour = f"{hour} hours played"
            rankmsg += f"{role} - {hour}\n"
        if rankmsg == "":
            rankmsg = "No roles set"
        embed.add_field(
            name="Ranks",
            value=rankmsg
        )
        await ctx.send(embed=embed)

    @ranks_main.command(name="autorename")
    async def auto_name(self, ctx: commands.Context):
        """(TOGGLE)Auto rename character names to their rank"""
        if await self.config.guild(ctx.guild).autorename():
            await self.config.guild(ctx.guild).autorename.set(False)
            await ctx.send("Auto rank renaming Disabled")
        else:
            await self.config.guild(ctx.guild).autorename.set(True)
            await ctx.send("Auto rank renaming Enabled")

    @ranks_main.command(name="autoremove")
    async def auto_remove(self, ctx: commands.Context):
        """(TOGGLE)Auto remove old ranks from users when they reach the next rank"""
        if await self.config.guild(ctx.guild).autoremove():
            await self.config.guild(ctx.guild).autoremove.set(False)
            await ctx.send("Auto rank removal Disabled")
        else:
            await self.config.guild(ctx.guild).autoremove.set(True)
            await ctx.send("Auto rank removal Enabled")

    @ranks_main.command(name="initialize")
    async def initialize_ranks(self, ctx: commands.Context):
        """
        Initialize created ranks to existing player database

        This adds any roles and ranks to existing players that meet playtime
        requirements
        """
        added = 0
        ad = ""
        removed = 0
        rem = ""
        async with ctx.typing():
            async with self.config.guild(ctx.guild).all() as settings:
                stats = settings["players"]
                ranks = []
                for rank in settings["ranks"].keys():
                    ranks.append(int(rank))
                if not ranks:
                    return await ctx.send("There are no ranks set!")
                a = np.array(ranks)
                unrank = settings["autoremove"]
                for uid, stat in stats.items():
                    hours = int(stat["playtime"]["total"] / 3600)
                    try:
                        top = a[a <= hours].max()  # Highest rank lower or equal to hours played
                        # await ctx.send(top)
                    except ValueError:
                        continue
                    if top:
                        to_assign = settings["ranks"][str(top)]
                        settings["players"][uid]["rank"] = to_assign
                    if "discord" in stat:
                        did = stat["discord"]
                        member = ctx.guild.get_member(did)
                        if member and top:
                            for h, r in settings["ranks"].items():
                                r = ctx.guild.get_role(r)
                                if not r:
                                    continue
                                h = str(h)
                                top = str(top)
                                if h == top and r not in member.roles:
                                    await member.add_roles(r)
                                    added += 1
                                    ad += f"{r} to {member.display_name}\n"
                                if unrank:
                                    if h != top and r in member.roles:
                                        await member.remove_roles(r)
                                        removed += 1
                                        rem += f"{r} from {member.display_name}\n"
            final = f"**Added ranks to {added} people**\n" \
                    f"{ad}\n" \
                    f"**Removed ranks from {removed} people**\n" \
                    f"{rem}"
            for p in pagify(final):
                await ctx.send(p)

    @arktools_main.command(name="fullbackup")
    @commands.is_owner()
    async def backup_all_settings(self, ctx: commands.Context):
        """Sends a full backup of the config as a JSON file to Discord."""
        settings = await self.config.all_guilds()
        settings = json.dumps(settings)
        with open(f"{ctx.guild}.json", "w") as file:
            file.write(settings)
        with open(f"{ctx.guild}.json", "rb") as file:
            await ctx.send(file=discord.File(file, f"{ctx.guild}_full_config.json"))

    @arktools_main.command(name="backup")
    @commands.guildowner()
    async def backup_settings(self, ctx: commands.Context):
        """Sends a backup of the config as a JSON file to Discord."""
        settings = await self.config.guild(ctx.guild).all()
        settings = json.dumps(settings)
        with open(f"{ctx.guild}.json", "w") as file:
            file.write(settings)
        with open(f"{ctx.guild}.json", "rb") as file:
            await ctx.send(file=discord.File(file, f"{ctx.guild}_config.json"))

    @arktools_main.command(name="backupcluster")
    @commands.guildowner()
    async def backup_cluster(self, ctx: commands.Context, clustername: str):
        """Sends a backup of a cluster config as a JSON file to Discord."""
        settings = await self.config.guild(ctx.guild).all()
        clusters = settings["clusters"]
        if clustername not in clusters:
            return await ctx.send("Cluster not found!")
        cluster = clusters[clustername]
        cluster = json.dumps(cluster)
        with open(f"{ctx.guild}.json", "w") as file:
            file.write(cluster)
        with open(f"{ctx.guild}.json", "rb") as file:
            await ctx.send(file=discord.File(file, f"{ctx.guild}_{clustername}_config.json"))

    @arktools_main.command(name="backupstats")
    @commands.guildowner()
    async def backup_stat_settings(self, ctx: commands.Context):
        """Sends a backup of the player stats as a JSON file to Discord."""
        settings = await self.config.guild(ctx.guild).players()
        settings = json.dumps(settings)
        with open(f"{ctx.guild}.json", "w") as file:
            file.write(settings)
        with open(f"{ctx.guild}.json", "rb") as file:
            await ctx.send(file=discord.File(file, f"{ctx.guild}_playerstats.json"))

    @arktools_main.command(name="backupgraphdata")
    @commands.guildowner()
    async def backup_graph_data(self, ctx: commands.Context):
        """Sends a backup of the graph data for graphing as a JSON file to Discord."""
        settings = await self.config.guild(ctx.guild).serverstats()
        settings = json.dumps(settings)
        with open(f"{ctx.guild}.json", "w") as file:
            file.write(settings)
        with open(f"{ctx.guild}.json", "rb") as file:
            await ctx.send(file=discord.File(file, f"{ctx.guild}_graphdata.json"))

    @arktools_main.command(name="fullrestore")
    @commands.is_owner()
    async def restore_all_settings(self, ctx: commands.Context):
        """Upload a backup JSON file attached to this command to restore the full config."""
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            for guild in self.bot.guilds:
                async with self.config.guild(guild).all() as conf:
                    guild_id = str(guild.id)
                    if guild_id in config:
                        for k, v in config[guild_id]:
                            conf[k] = v
            await self.initialize()
            return await ctx.send("Config restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @arktools_main.command(name="restore")
    @commands.guildowner()
    async def restore_settings(self, ctx: commands.Context):
        """Upload a backup JSON file attached to this command to restore the config."""
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            await self.config.guild(ctx.guild).set(config)
            await self.initialize()
            return await ctx.send("Config restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @arktools_main.command(name="restorecluster")
    @commands.guildowner()
    async def restore_cluster(self, ctx: commands.Context, clustername: str):
        """Upload a backup JSON file attached to this command to restore the config for a specific cluster."""
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            async with self.config.guild(ctx.guild).clusters() as clusters:
                clusters[clustername] = config
            await self.initialize()
            return await ctx.send("Cluster restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @arktools_main.command(name="restorestats")
    @commands.guildowner()
    async def restore_stats(self, ctx: commands.Context):
        """Upload a backup JSON file attached to this command to restore the player stats."""
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            await self.config.guild(ctx.guild).players.set(config)
            await self.initialize()
            return await ctx.send("Player stats restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    @arktools_main.command(name="restoregraphdata")
    @commands.guildowner()
    async def restore_graph_data(self, ctx: commands.Context):
        """Upload a backup JSON file attached to this command to restore the graph data."""
        if ctx.message.attachments:
            attachment_url = ctx.message.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    config = await resp.json()
            await self.config.guild(ctx.guild).serverstats.set(config)
            await self.initialize()
            return await ctx.send("Graph data restored from backup file!")
        else:
            return await ctx.send("Attach your backup file to the message when using this command.")

    # cleanup graph and map data that no longer exist
    @arktools_main.command(name="cleanup")
    @commands.guildowner()
    @commands.guild_only()
    async def cleanup_data(self, ctx: commands.Context):
        """
        Delete old data that no longer exists

        If you have old deleted maps still showing up in clusterstats or graph data, this should remove them.
        This will also fix your config if you have player data from the Pre-V2 era of ArkTools
        """
        async with ctx.typing():
            settings = await self.config.guild(ctx.guild).all()
            new_settings, results = await cleanup_config(settings)

        if results:
            await self.config.guild(ctx.guild).set(new_settings)
            await ctx.send(results)
        else:
            await ctx.send("Nothing to clean, config looks healthy :thumbsup:")

    # Arktools-Mod subgroup
    @arktools_main.group(name="mod")
    @commands.guildowner()
    async def mod_permissions(self, ctx: commands.Context):
        """Permission settings for rcon commands."""
        pass

    @mod_permissions.command(name="view")
    async def view_permission_settings(self, ctx: commands.Context):
        """View current permission settings."""
        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        full_a = ctx.guild.get_role(settings['fullaccessrole'])
        if full_a:
            full_a = full_a.mention
        mods = "None"
        if len(settings['modroles']) > 0:
            mods = ""
            for mod in settings['modroles']:
                mod_obj = ctx.guild.get_role(mod)
                if mod_obj:
                    mod = mod_obj.mention
                mods += f"\n{mod}"
        try:
            embed = discord.Embed(
                title=f"Permission Settings",
                color=color,
                description=f"**Full Access Role:** {full_a}\n"
                            f"**Mod Roles:** {mods}\n"
                            f"**Mod Commands:** {settings['modcommands']}\n"
                            f"**Blacklisted Names:** {settings['badnames']}"
            )
            return await ctx.send(embed=embed)
        except KeyError:
            await ctx.send(f"Setup permissions first.")

    @mod_permissions.command(name="fullaccess")
    async def set_fullaccessrole(self, ctx: commands.Context, role: discord.Role = None):
        """Set a role for full RCON access."""
        if not role:
            await self.config.guild(ctx.guild).fullaccessrole.set(None)
            return await ctx.send(f"Full access role set to None")
        await self.config.guild(ctx.guild).fullaccessrole.set(role.id)
        await ctx.send(f"Full access role set to {role}")

    @mod_permissions.command(name="addmodrole")
    async def add_modrole(self, ctx: commands.Context, role: discord.Role):
        """Add a role to allow limited command access for."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                await ctx.send("That role already exists.")
            else:
                modroles.append(role.id)
                await ctx.send(f"The **{role}** role has been added.")

    @mod_permissions.command(name="delmodrole")
    async def del_modrole(self, ctx: commands.Context, role: discord.Role):
        """Delete a mod role."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                modroles.remove(role.id)
                await ctx.send(f"{role} role has been removed.")
            else:
                await ctx.send("That role isn't in the list.")

    @mod_permissions.command(name="addbadname")
    async def add_badname(self, ctx: commands.Context, *, badname: str):
        """Blacklist a player name to be auto-renamed if detected in chat."""
        async with self.config.guild(ctx.guild).badnames() as badnames:
            if badname in badnames:
                await ctx.send("That name already exists.")
            else:
                badnames.append(badname)
                await ctx.send(f"**{badname}** has been added to the blacklist.")

    @mod_permissions.command(name="delbadname")
    async def del_badname(self, ctx: commands.Context, *, badname: str):
        """Delete a blacklisted name."""
        async with self.config.guild(ctx.guild).badnames() as badnames:
            if badname in badnames:
                badnames.remove(badname)
                await ctx.send(f"{badname} has been removed from the blacklist.")
            else:
                await ctx.send("That name doesnt exist")

    @mod_permissions.command(name="addmodcommand")
    async def add_modcommand(self, ctx: commands.Context, modcommand: str):
        """Add allowable commands for the mods to use."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                await ctx.send("That command already exists!")
            else:
                modcommands.append(modcommand)
                await ctx.send(f"The command **{modcommand}** has been added to the list.")

    @mod_permissions.command(name="delmodcommand")
    async def del_modcommand(self, ctx: commands.Context, modcommand: str):
        """Delete an allowed mod command."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                modcommands.remove(modcommand)
                await ctx.send(f"The {modcommand} command has been removed.")
            else:
                await ctx.send("That command doesnt exist")

    # Arktools-Tribe subgroup
    @arktools_main.group(name="tribe")
    async def tribe_settings(self, ctx: commands.Context):
        """Tribe settings."""
        pass

    @tribe_settings.command(name="view")
    @commands.guildowner()
    async def view_tribe_settings(self, ctx: commands.Context):
        """Overview of all tribes and settings"""
        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        masterlog = settings["masterlog"] if "masterlog" in settings else None
        masterlog = ctx.guild.get_channel(masterlog)
        if masterlog:
            masterlog = masterlog.mention
        else:
            masterlog = "Not Set"
        tribes = settings["tribes"] if "tribes" in settings else None
        embed = discord.Embed(
            title="Tribe Settings Overview",
            color=color,
            description=f"**Master Tribe Log Channel**: {masterlog}"
        )
        if tribes is not None:
            for tribe in tribes:
                channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                if channel is not None:
                    channel = channel.mention
                else:
                    channel = "Channel has been deleted :("
                owner = ctx.guild.get_member(tribes[tribe]["owner"])
                if not tribes[tribe]["allowed"]:
                    allowedmembers = "None Set"
                else:
                    allowedmembers = ""
                    for member in tribes[tribe]["allowed"]:
                        allowedmembers += f"{ctx.guild.get_member(member).mention}\n"
                embed.add_field(
                    name=f"Tribe: {tribe}",
                    value=f"Owner: {owner.mention}\nChannel: {channel}\nAllowed Members: {allowedmembers}"
                )
        await ctx.send(embed=embed)

    @tribe_settings.command(name="setmasterlog")
    @commands.guildowner()
    async def set_masterlog(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set global channel for all tribe logs."""
        await self.config.guild(ctx.guild).masterlog.set(channel.id)
        await ctx.send(f"Master tribe log channel has been set to {channel.mention}")

    @tribe_settings.command(name="assign")
    @commands.guildowner()
    async def assign_tribe(self,
                           ctx: commands.Context,
                           tribe_id: str,
                           owner: discord.Member,
                           channel: discord.TextChannel):
        """Assign a tribe to an owner to be managed by ithem."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            msg = f"Tribe ID `{tribe_id}` has been assigned to {owner.mention} in {channel.mention}."
            if tribe_id in tribes:
                tribes[tribe_id]["owner"] = owner.id
                tribes[tribe_id]["channel"] = channel.id
            else:
                tribes[tribe_id] = {
                    "tribename": None,
                    "owner": owner.id,
                    "channel": channel.id,
                    "allowed": [],
                    "kills": 0
                }
            await channel.set_permissions(owner, read_messages=True)
            await ctx.send(msg)

    @tribe_settings.command(name="unassign")
    @commands.guildowner()
    async def unassign_tribe(self, ctx: commands.Context, tribe_id: str):
        """Unassign a tribe owner from a tribe."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribe_id not in tribes:
                return await ctx.send("Tribe ID doesn't exist!")
            await ctx.send(f"Tribe with ID: {tribe_id} has been unassigned.")
            del tribes[tribe_id]

    @tribe_settings.command(name="mytribe")
    async def view_my_tribe(self, ctx):
        """View your tribe(if you've been granted ownership of one."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes == {}:
                return await ctx.send(f"No tribes found.")
            for tribe in tribes:
                if str(ctx.author.id) == tribes[tribe]["owner"] or str(ctx.author.id) in tribes[tribe]["allowed"]:
                    owner = ctx.guild.get_member(tribes[tribe]['owner']).mention
                    embed = discord.Embed(
                        title=f"{ctx.author.name}'s Tribe",
                        description=f"Tribe ID: {tribe}\nOwner: {owner}"
                    )
                    members = ""
                    for member in tribes[tribe]["allowed"]:
                        members += f"{ctx.guild.get_member(member).mention}\n"
                    if members == "":
                        members = "None Added"
                    embed.add_field(
                        name=f"Tribe Members",
                        value=f"{members}"
                    )
                    if tribes[tribe]["kills"]:
                        embed.add_field(
                            name="Tribe Kills",
                            value=tribes[tribe]["kills"]
                        )
                    await ctx.send(embed=embed)
                    break
            else:
                await ctx.send("You don't have access any tribes.")

    @tribe_settings.command(name="add")
    async def add_member(self, ctx: commands.Context, member: discord.Member):
        """Add a member to your tribe log channel."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes == {}:
                return await ctx.send(f"There are no tribes set for this server.")
            for tribe in tribes:
                if str(ctx.author.id) == tribes[tribe]["owner"]:
                    tribes[tribe]["allowed"].append(member.id)
                    channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                    await channel.set_permissions(member, read_messages=True)
                    await ctx.send(f"{member.mention} has been added to the tribe logs")
                    break
            else:
                await ctx.send(f"You arent set as owner of any tribes to add people to.")

    @tribe_settings.command(name="remove")
    async def remove_member(self, ctx: commands.Context, member: discord.Member):
        """Remove a member from your tribe log channel."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes == {}:
                return await ctx.send(f"There are no tribes set for this server.")
            for tribe in tribes:
                if str(ctx.author.id) == tribes[tribe]["owner"]:
                    memberlist = tribes[tribe]["allowed"]
                    if str(member.id) in memberlist:
                        memberlist.remove(str(member.id))
                        channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                        await channel.set_permissions(member, read_messages=False)
                        await ctx.send(f"{member.mention} has been remove from tribe log access.")
                        break
                    else:
                        return await ctx.send("Member does not exist in tribe log access.")
            else:
                await ctx.send("You do not have ownership of any tribes")

    # Arktools-API subgroup
    @arktools_main.group(name="api")
    async def api_settings(self, ctx: commands.Context):
        """
        (Win10/Xbox CROSSPLAY ONLY) API tools for the host Gamertags.

        Type `[p]arktools api help` for more information.
        """
        pass

    @api_settings.command(name="help")
    @commands.is_owner()
    async def get_help(self, ctx):
        """Tutorial for getting your ClientID and Secret"""
        embed = discord.Embed(
            description="**How to get your Client ID and Secret**",
            color=discord.Color.magenta()
        )
        embed.add_field(
            name="Step 1",
            value="• Register a new application in "
                  "[Azure AD](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)",
            inline=False
        )
        embed.add_field(
            name="Step 2",
            value="• Name your app\n"
                  "• Select `Personal Microsoft accounts only` under supported account types\n"
                  "• Add http://localhost/auth/callback as a Redirect URI of type `Web`",
            inline=False
        )
        embed.add_field(
            name="Step 3",
            value="• Copy your Application (client) ID and save it for setting your tokens",
            inline=False
        )
        embed.add_field(
            name="Step 4",
            value="• On the App Page, navigate to `Certificates & secrets`\n"
                  "• Generate a new client secret and save it for setting your tokens\n"
                  "• **Importatnt:** The 'Value' for the secret is what you use, NOT the 'Secret ID'",
            inline=False
        )
        embed.add_field(
            name="Step 5",
            value=f"• Type `{ctx.prefix}arktools api tokenset` and include your Client ID and Secret\n",
            inline=False
        )
        embed.add_field(
            name="Step 6",
            value=f"• Type `{ctx.prefix}arktools api auth clustername servername` to authorize a server in a cluster\n"
                  f"• The bot will DM you instructions with a link, follow them exactly\n"
                  f"• After authorizing each host Gamertag, remember to sign out of Microsoft each time",
            inline=False
        )
        await ctx.send(embed=embed)

    @api_settings.command(name="viewhosts")
    async def view_host_gamertags(self, ctx: commands.Context):
        """
        View API information for the host Gamertags such as if they're authorized,
        friend list count, ect..
        """
        clientid = await self.config.clientid()
        if not clientid:
            return await ctx.send("Bot owner needs to set Client ID and Secret before api commands can be used!")
        clusters = await self.config.guild(ctx.guild).clusters()
        async with aiohttp.ClientSession() as session:
            for cname, cluster in clusters.items():
                description = f"**{cname.upper()} Cluster**\n"
                async with ctx.typing():
                    for sname, server in cluster["servers"].items():
                        if "tokens" in server:
                            tokens = server["tokens"]
                            xbl_client, token = await self.auth_manager(session, cname, sname, tokens, ctx)
                            if xbl_client:
                                authorized = "True"
                                friends = json.loads((await xbl_client.people.get_friends_summary_own()).json())
                                xuid = xbl_client.xuid
                                profile_data = json.loads((await xbl_client.profile.get_profile_by_xuid(xuid)).json())
                                gt, _, _, _ = profile_format(profile_data)
                                gamertag = server["gamertag"]
                                following = friends["target_following_count"]
                                followers = friends["target_follower_count"]
                                description += f"**{sname.capitalize()}**\n" \
                                               f"`Authorized: `{authorized}\n" \
                                               f"`Gamertag:   `{gt}\n" \
                                               f"`Followers:  `{followers}\n" \
                                               f"`Following:  `{following}\n\n"
                                if gt.lower() != gamertag.lower():
                                    async with self.config.guild(ctx.guild).clusters() as clusters:
                                        clusters[cname]["servers"][sname]["gamertag"] = gt
                embed = discord.Embed(
                    description=description
                )
                await ctx.send(embed=embed)

    @api_settings.command(name="view")
    async def view_api_settings(self, ctx: commands.Context):
        """View API configuration settings"""
        settings = await self.config.guild(ctx.guild).all()
        autofriend = settings["autofriend"]
        autowelcome = settings["autowelcome"]
        unfriendtime = settings["unfriendafter"]
        welcomemsg = settings["welcomemsg"]
        if welcomemsg is None:
            welcomemsg = f"Welcome to {ctx.guild.name}!\nThis is an automated message:\n" \
                         f"You appear to be a new player, " \
                         f"here is an invite to the Discord server:\n\n*Invite Link*"
        desc = f"`AutoFriend System:  `{'Enabled' if autofriend else 'Disabled'}\n" \
               f"`AutoWelcome System: `{'Enabled' if autowelcome else 'Disabled'}\n" \
               f"`AutoUnfriend Days:  `{unfriendtime}\n"

        color = discord.Color.random()
        embed = discord.Embed(
            title="API Settings",
            description=desc,
            color=color
        )
        if ctx.author.id in self.bot.owner_ids:
            client_id = await self.config.clientid()
            client_secret = await self.config.secret()
            token_info = f"`Client ID:     `{client_id}\n" \
                         f"`Client Secret: `{client_secret}"
            embed.add_field(
                name="Bot Owner Only Info",
                value=token_info,
                inline=False)
        embed.add_field(
            name="Welcome Message",
            value=box(welcomemsg),
            inline=False
        )
        await ctx.send(embed=embed)

    @api_settings.command(name="tokenset")
    @commands.is_owner()
    async def set_tokens(self,
                         ctx: commands.Context, client_id: str, client_secret: str):
        """Set Client ID and Secret for the bot to use"""
        await self.config.clientid.set(client_id)
        await self.config.secret.set(client_secret)
        await ctx.send(f"Client ID and secret have been set.✅\n"
                       f"Run `{ctx.prefix}arktools api auth <clustername> <servername>` to authorize your tokens.")

    @api_settings.command(name="deltokens")
    @commands.is_owner()
    async def remove_tokens(self, ctx: commands.Context):
        """Remove API tokens from the bot"""
        await self.config.client_id.set(None)
        await self.config.secret.set(None)
        await ctx.send(f"API keys removed.")

    @api_settings.command(name="auth")
    @commands.is_owner()
    async def authorize_tokens(self, ctx: commands.Context, clustername: str, servername: str):
        """
        Authorize your tokens for a server

        This sends you a DM with instructions and a link, you will need to sign
        in with the host Gamertag email and authorize it to be used with the API
        """
        clusters = await self.config.guild(ctx.guild).clusters()
        if clustername.lower() not in clusters:
            return await ctx.send(f"{clustername} cluster does not exist!")
        if servername.lower() not in clusters[clustername]["servers"]:
            return await ctx.send(f"{servername} server does not exist!")

        client_id = await self.config.clientid()
        if client_id is None:
            return await ctx.send(f"Bot owner needs to set their Client ID and Secret first!\n"
                                  f"Command is `{ctx.prefix}arktools api tokenset` to add them.")

        url = "https://login.live.com/oauth20_authorize.srf?"
        cid = f"client_id={client_id}"
        types = "&response_type=code&approval_prompt=auto"
        scopes = "&scope=Xboxlive.signin+Xboxlive.offline_access&"
        redirect_uri = "&redirect_uri=http://localhost/auth/callback"
        auth_url = f"{url}{cid}{types}{scopes}{redirect_uri}"
        await ctx.send("Sending you a DM to authorize your tokens.")
        await self.ask_auth(ctx, ctx.author, auth_url, clustername, servername)

    # Send user DM asking for authentication
    async def ask_auth(self,
                       ctx: commands.Context,
                       author: discord.User,
                       auth_url: str,
                       clustername: str,
                       servername: str
                       ):
        plz_auth = f"Please follow this link to authorize your tokens with Microsoft.\n" \
                   f"Sign in with the host Gamertag email the corresponds with the server you selected.\n" \
                   f"**YOU WILL GET A LOCALHOST ERROR AND A BLANK PAGE, THIS IS OKAY!**\n" \
                   f"On that blank page, copy the ENTIRE contents of the address bar after you authorize, " \
                   f"and reply to this message with what you copied.\n" \
                   f"{auth_url}"
        await author.send(plz_auth)

        def check(message):
            return message.author == ctx.author

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return await author.send("Authorization timeout.")

        # Retrieve code from url
        if "code" in reply.content:
            code = reply.content.split("code=")[-1]
        else:
            return await author.send("Invalid response")

        client_id = await self.config.clientid()
        client_secret = await self.config.secret()

        async with aiohttp.ClientSession() as session:
            auth_mgr = AuthenticationManager(session, client_id, client_secret, REDIRECT_URI)
            try:
                await auth_mgr.request_tokens(code)
                tokens = json.loads(auth_mgr.oauth.json())
            except Exception as e:
                if "Bad Request" in str(e):
                    return await author.send("Bad Request, Make sure to use a **Different** email than the one "
                                             "you used to make your Azure app to sign into.\n"
                                             "Check the following as well:\n"
                                             "• Paste the **Entire** contents of the address bar.\n"
                                             "• Make sure that the callback URI in your azure app is: "
                                             "http://localhost/auth/callback")
                return await author.send(f"Authorization failed: {e}")
            async with self.config.guild(ctx.guild).clusters() as clusters:
                clusters[clustername]["servers"][servername]["tokens"] = tokens
                xbl_client = XboxLiveClient(auth_mgr)
                xuid = xbl_client.xuid
                profile_data = json.loads((await xbl_client.profile.get_profile_by_xuid(xuid)).json())
                gt, _, _, _ = profile_format(profile_data)
                clusters[clustername]["servers"][servername]["gamertag"] = gt

            await author.send(f"Tokens have been Authorized for **{servername.capitalize()} {clustername.upper()}**✅")

    @api_settings.command(name="welcome")
    @commands.admin()
    async def welcome_toggle(self, ctx):
        """
        (Toggle) Automatic server welcome messages when a new player is detected on the servers

        When a new player joins the server through the list or without being in the Discord,
        the bot will send them a welcome message.
        """
        welcometoggle = await self.config.guild(ctx.guild).autowelcome()
        if welcometoggle:
            await self.config.guild(ctx.guild).autowelcome.set(False)
            await ctx.send("Auto Welcome Message **Disabled**")
        else:
            await self.config.guild(ctx.guild).autowelcome.set(True)
            await ctx.send("Auto Welcome Message **Enabled**")

    @api_settings.command(name="smartmanage")
    @commands.admin()
    async def autofriend_toggle(self, ctx: commands.Context):
        """
        (Toggle) Automatic maintenance of host Gamertag friend lists.

        This will enable automatically adding new players as a friend by the host Gamertag
        and automatically unfriending them after the set number of days of inactivity (Default is 30).
        The Gamertags will also unfriend anyone that isnt following them back
        or leaves the discord after registering.
        """
        autofriendtoggle = await self.config.guild(ctx.guild).autofriend()
        if autofriendtoggle:
            await self.config.guild(ctx.guild).autofriend.set(False)
            await ctx.send("Smart management **Disabled**")
        else:
            await self.config.guild(ctx.guild).autofriend.set(True)
            await ctx.send("Smart management **Enabled**")

    @api_settings.command(name="unfriendtime")
    @commands.admin()
    async def unfriend_time(self, ctx: commands.Context, days: int):
        """
        Set number of days of inactivity for the host Gamertags to unfriend a player.

        This keep xbox host Gamertag friends lists clean since the max you can have is 1000.
        """
        await self.config.guild(ctx.guild).unfriendafter.set(days)
        await ctx.send(f"Inactivity days till auto unfriend is {days} days.")

    @api_settings.command(name="welcomemsg")
    @commands.admin()
    async def welcome_message(self, ctx: commands.Context, *, welcome_message: str):
        """
        Set a welcome message to be used instead of the default.
        When the bot detects a new Gamertag that isn't in the database, it sends it a welcome DM with
        an invite to the server.


        Variables that can be used in the welcome message are:
        {discord} - Discord name
        {gamertag} - Persons Gamertag
        {link} - Discord link
        Put "Default" in welcome string to revert to default message.
        """
        params = {
            "discord": ctx.guild.name,
            "gamertag": "gamertag",
            "link": "channel invite"
        }
        if "default" in welcome_message.lower():
            await ctx.send("Welcome message reverted to Default!")
            return await self.config.guild(ctx.guild).welcomemsg.set(None)
        try:
            to_send = welcome_message.format(**params)
        except KeyError as e:
            return await ctx.send(f"The welcome message cannot be formatted, because it contains an "
                                  f"invalid placeholder `{e.args[0]}`. See `{ctx.prefix}arktools api setwelcome` "
                                  f"for a list of valid placeholders.")
        length = len(to_send) + 25
        if length > 256:
            return await ctx.send("Message exceeds 256 character length! Make a shorter welcome message.")
        await self.config.guild(ctx.guild).welcomemsg.set(welcome_message)
        await ctx.send(f"Welcome message set as:\n{to_send}")

    @api_settings.group(name="altdetector")
    async def alt_settings(self, ctx: commands.Context):
        """
        Alt account detection

        Get alerts in the event log when a suspicious account joins a server,
        and optionally Auto-ban them or send a warning message based on customizable settings
        """
        pass

    @alt_settings.command(name="toggle")
    @commands.admin()
    async def toggle_alt_detection(self, ctx: commands.Context):
        """Toggle the alt detection system on or off"""
        on = await self.config.guild(ctx.guild).alt.on()
        if on:
            await self.config.guild(ctx.guild).alt.on.set(False)
            await ctx.send("Alt detection system **Disabled**")
        else:
            await self.config.guild(ctx.guild).alt.on.set(True)
            await ctx.send("Alt detection system **Enabled**")

    @alt_settings.command(name="autoban")
    @commands.admin()
    async def toggle_autoban(self, ctx: commands.Context):
        """Toggle Auto-Banning of suspicious accounts on or off"""
        on = await self.config.guild(ctx.guild).alt.autoban()
        if on:
            await self.config.guild(ctx.guild).alt.autoban.set(False)
            await ctx.send("Auto-Banning **Disabled**")
        else:
            await self.config.guild(ctx.guild).alt.autoban.set(True)
            await ctx.send("Auto-Banning **Enabled**")

    @alt_settings.command(name="silver")
    @commands.admin()
    async def toggle_silver(self, ctx: commands.Context):
        """Toggle whether to include Silver accounts as suspicious"""
        on = await self.config.guild(ctx.guild).alt.silver()
        if on:
            await self.config.guild(ctx.guild).alt.silver.set(False)
            await ctx.send("Silver account detection **Disabled**")
        else:
            await self.config.guild(ctx.guild).alt.silver.set(True)
            await ctx.send("Silver account detection **Enabled**")

    @alt_settings.command(name="warning")
    @commands.admin()
    async def toggle_warning(self, ctx: commands.Context):
        """
        Toggle whether to send a warning message to the user

        Warning message must also be configured before this can work!
        """
        on = await self.config.guild(ctx.guild).alt.msgtoggle()
        if on:
            await self.config.guild(ctx.guild).alt.msgtoggle.set(False)
            await ctx.send("Warning message **Disabled**")
        else:
            await self.config.guild(ctx.guild).alt.msgtoggle.set(True)
            await ctx.send("Warning message **Enabled**")

    @alt_settings.command(name="mingamerscore")
    @commands.admin()
    async def set_min_gamerscore(self, ctx: commands.Context, minimum_gamerscore: int):
        """
        Set the minimum Gamerscore a user must have to be considered not suspicious

        If the user has a Gamerscore below the threshold, they will be flagged as sus
        """
        await self.config.guild(ctx.guild).alt.mings.set(minimum_gamerscore)
        await ctx.send(f"Minimum Gamerscore theshold has been set to `{minimum_gamerscore}`")

    @alt_settings.command(name="minfollowers")
    @commands.admin()
    async def set_min_followers(self, ctx: commands.Context, minimum_followers: int):
        """
        Set the minimum followers a user must have to be considered not sus

        If the user has less followers than the threshold, they will be flagged as sus
        """
        await self.config.guild(ctx.guild).alt.minfollowers.set(minimum_followers)
        await ctx.send(f"Minimum followers threshold has been set to `{minimum_followers}`")

    @alt_settings.command(name="minfollowing")
    @commands.admin()
    async def set_min_following(self, ctx: commands.Context, minimum_following: int):
        """
        Set the minimum accounts a user is following for them to be considered not sus

        If the user is following less users than the threshold, they will be flagged as sus
        """
        await self.config.guild(ctx.guild).alt.minfollowing.set(minimum_following)
        await ctx.send(f"Minimum following threshold has been set to `{minimum_following}`")

    @alt_settings.command(name="warningmsg")
    @commands.admin()
    async def set_warning_msg(self, ctx: commands.Context, *, warning_message: str):
        """
        Set the warning message a user would receive upon being flagged as an alt

        You can include the reasons with the warning by including the {reasons}
        placeholder in your warning message
        """
        if "{reasons}" in warning_message and len(warning_message) + 80 > 256:
            return await ctx.send("Warning message might exceed 256 characters with the reasons included, "
                                  "please make a shorter one.")

        if len(warning_message) > 256:
            return await ctx.send("Warning message exceeds 256 characters, please make a shorter one.")

        await self.config.guild(ctx.guild).alt.msg.set(warning_message)
        await ctx.send("Warning message has been set!")

    @alt_settings.command(name="ignore")
    @commands.mod()
    async def ingore_player(self, ctx: commands.Context, xuid: int):
        """Add a player to the alt detection whitelist, they will be ignored by the alt detection"""
        async with self.config.guild(ctx.guild).alt.whitelist() as whitelist:
            if xuid not in whitelist:
                whitelist.append(xuid)
                await ctx.send("User has been added to the alt detection ignore list")
                on = await self.config.guild(ctx.guild).alt.autoban()
                if on:
                    unban = True
            else:
                await ctx.send("User is already in the whitelist")
                unban = False
            if unban:
                async with ctx.typing():
                    serverlist = []
                    for tup in self.servers:
                        guild = tup[0]
                        server = tup[1]
                        if guild == ctx.guild.id:
                            serverlist.append(server)
                    unignore_tasks = []
                    if len(unignore_tasks) > 0:
                        for server in serverlist:
                            unignore_tasks.append(self.executor(guild, server, f"unbanplayer {xuid}"))
                        await asyncio.gather(*unignore_tasks)
                        await ctx.send("User has been unbanned from all servers")

    @alt_settings.command(name="unignore")
    @commands.mod()
    async def unignore_player(self, ctx: commands.Context, xuid: int):
        """Remove a player's XUID from the alt detection whitelist"""
        async with self.config.guild(ctx.guild).alt.whitelist() as whitelist:
            if xuid not in whitelist:
                await ctx.send("User is not in the ignore list")
            else:
                whitelist.remove(xuid)
                await ctx.send("User has been removed from the alt detection ignore list")

    @alt_settings.command(name="view")
    async def view_alt_settings(self, ctx: commands.Context):
        """View the current Alt Detection settings"""
        alt = await self.config.guild(ctx.guild).alt()
        on = alt["on"]
        if on:
            system = "On"
        else:
            system = "Off"
        autoban = alt["autoban"]
        silver = alt["silver"]
        warning = alt["msgtoggle"]
        min_gs = alt["mings"]
        min_followers = alt["minfollowers"]
        min_following = alt["minfollowing"]
        msg = alt["msg"]
        ignore = alt["whitelist"]
        whitelist = ""
        for xuid in ignore:
            whitelist += f"{xuid}\n"
        embed = discord.Embed(
            title="Alt Detection Settings",
            description=f"`Detection System:   `{system}\n"
                        f"`Auto Ban User:      `{autoban}\n"
                        f"`Flag Silver Users:  `{silver}\n"
                        f"`Minimum Gamerscore: `{min_gs}\n"
                        f"`Minimum Followers:  `{min_followers}\n"
                        f"`Minimum Following:  `{min_following}\n"
                        f"`Send Warning Msg:   `{warning}\n"
        )
        if msg:
            embed.add_field(name="Warning Message", value=box(msg), inline=False)
        else:
            embed.add_field(name="Warning Message", value="None Set", inline=False)
        if whitelist:
            embed.add_field(name="Ignore List", value=whitelist, inline=False)
        else:
            embed.add_field(name="Ignore List", value="No one added", inline=False)
        await ctx.send(embed=embed)

    # Arktools-Server subgroup
    @arktools_main.group(name="server")
    @commands.guildowner()
    async def server_settings(self, ctx: commands.Context):
        """Server settings."""
        pass

    @server_settings.command(name="view")
    async def view_server_settings(self, ctx: commands.Context):
        """View current server settings"""
        settings = await self.config.guild(ctx.guild).all()
        tz = settings["timezone"]
        statuschannel = "Not Set"
        eventlog = "Not Set"
        if settings["eventlog"]:
            eventlog = ctx.guild.get_channel(settings["eventlog"])
            if eventlog:
                eventlog = eventlog.mention
        if settings["status"]["channel"]:
            statuschannel = ctx.guild.get_channel(settings["status"]["channel"])
            try:
                statuschannel = statuschannel.mention
            except AttributeError:
                statuschannel = "#deleted-channel"
        stats = settings["serverstats"]["counts"]
        exp = settings["serverstats"]["expiration"]
        days = int(len(stats) / 1440)
        clustertype = settings["clustertypes"]
        embed = discord.Embed(
            description=f"`Status Channel: `{statuschannel}\n"
                        f"`Event Log:      `{eventlog}\n"
                        f"`Timezone:       `{tz}\n"
                        f"`GraphHistory:   `{days} days\n"
                        f"`GraphStorage:   `{exp} days\n"
                        f"`ClusterType:    `{clustertype.capitalize()}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        clusters = settings["clusters"]
        if clusters == {}:
            return await ctx.send("No clusters have been created!")
        for cluster in clusters:
            settings = f"**{cluster.upper()} Cluster**\n"
            cluster = clusters[cluster]
            interchat = cluster["servertoserver"]
            if interchat:
                settings += "`Interchat:  `Enabled\n"
            else:
                settings += "`Interchat:  `Disabled\n"

            if "extrcon" in cluster.keys():
                extrcon = cluster["extrcon"]
                if extrcon:
                    settings += "`Ext RCON:   `Enabled\n"
                else:
                    settings += "`Ext RCON:   `Disabled\n"
            chat = ctx.guild.get_channel(cluster['globalchatchannel'])
            adminlog = ctx.guild.get_channel(cluster['adminlogchannel'])
            join = ctx.guild.get_channel(cluster['joinchannel'])
            leave = ctx.guild.get_channel(cluster['leavechannel'])
            if all([chat, adminlog, join, leave]):
                settings += f"`GlobalChat: `{chat.mention}\n" \
                            f"`AdminLog:   `{adminlog.mention}\n" \
                            f"`JoinLog:    `{join.mention}\n" \
                            f"`LeaveLog:   `{leave.mention}\n\n"
            else:
                settings += f"`GlobalChat: `{cluster['globalchatchannel']}\n" \
                            f"`AdminLog:   `{cluster['adminlogchannel']}\n" \
                            f"`JoinLog:    `{cluster['joinchannel']}\n" \
                            f"`LeaveLog:   `{cluster['leavechannel']}\n\n"

            for server in cluster["servers"]:
                name = server
                server = cluster["servers"][server]
                channel = ctx.guild.get_channel(server['chatchannel'])
                if channel:
                    channel = channel.mention
                else:
                    channel = server['chatchannel']
                settings += f"{channel}\n" \
                            f"`Map:  `{name}\n" \
                            f"`ip:   `{server['ip']}\n" \
                            f"`Port: `{server['port']}\n" \
                            f"`Pass: `{server['password']}\n"
                if "tokens" in server.keys():
                    gt = server["gamertag"]
                    settings += f"`Gamertag: `{gt}\n"
                settings += "\n"
            for p in pagify(settings):
                embed = discord.Embed(
                    description=p,
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)

    @server_settings.command(name="graphdata")
    async def graph_data_expiration(self, ctx: commands.Context, days: int):
        """
        Set how many days worth of graph data to keep saved
        """
        await self.config.guild(ctx.guild).serverstats.expiration.set(days)
        await ctx.tick()

    @server_settings.command(name="timezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """
        Set your timezone to display in the Server Status footer.

        You can type "[p]arktools server showtimezones" for a list of all available timezones
        """

        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            return await ctx.send(
                f"Invalid Timezone, type `{ctx.prefix}arktools server timezones` for all available timezones."
            )
        time = datetime.datetime.now(tz)
        time = time.strftime('%I:%M %p')  # Convert to 12 hour format

        embed = discord.Embed(
            description=f"Timezone set as **{timezone}**\nCurrent time is displayed below\n"
                        f"`{time}`",
            color=discord.Color.green()
        )
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.send(embed=embed)

    @server_settings.command(name="timezones")
    async def display_timezones(self, ctx: commands.Context):
        """Display all available timezones for your server status embed"""
        tzlist = ""
        content = []
        pages = []
        timezones = pytz.all_timezones
        for tz in timezones:
            tz = pytz.timezone(tz)
            time = datetime.datetime.now(tz)
            time = time.strftime('%I:%M %p')
            tzlist += f"`{time}: `{tz}\n"

        cur_page = 1
        for p in pagify(tzlist):
            content.append(p)
        for c in content:
            embed = discord.Embed(
                description=c
            )
            embed.set_footer(text=f"Pages: {cur_page}/{len(content)}")
            pages.append(embed)
            cur_page += 1
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @server_settings.command(name="eventlog")
    async def set_event_log(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """
        Set a channel for server events to be logged to.
        The logs include the following events:
        1. New players that are added to the database
        2. Welcome messages sent to new players(if enabled)
        3. Old players that are unfriended for inactivity(if enabled)
        4. Players that are unfriended for leaving the Discord(if enabled)
        5. Players that are unfriended due to unfriending a host Gamertag
        """
        if channel:
            await self.config.guild(ctx.guild).eventlog.set(channel.id)
            await ctx.send(f"Event log has been set to {channel.mention}")
        else:
            await self.config.guild(ctx.guild).eventlog.set(None)
            await ctx.send(f"Event log has been set to **None**")

    @server_settings.command(name="addcluster")
    async def add_cluster(self,
                          ctx: commands.Context,
                          clustername: str,
                          joinchannel: discord.TextChannel,
                          leavechannel: discord.TextChannel,
                          adminlogchannel: discord.TextChannel,
                          globalchatchannel: discord.TextChannel):
        """
        Add a cluster with specified log channels.

        Make sure cluster name does NOT have any spaces
        """
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                return await ctx.send(f"**{clustername}** cluster already exists!")
            else:
                await ctx.send(f"**{clustername}** has been added to the list of clusters.")
                clusters[clustername.lower()] = {
                    "joinchannel": joinchannel.id,
                    "leavechannel": leavechannel.id,
                    "adminlogchannel": adminlogchannel.id,
                    "globalchatchannel": globalchatchannel.id,
                    "servertoserver": False,
                    "servers": {}
                }
                await self.initialize()

    @server_settings.command(name="clustertype")
    async def set_cluster_type(self, ctx: commands.Context, cluster_type: str):
        """
        Set the type of clusters you have available on your discord.
        This is a global setting for all your servers that will affect the wording of
        the register command prompts

        Available options are:
        `xbox` - Register command will only prompt user to enter their Gamertag
        `steam` - Register command will only prompt user to enter their Steam ID
        `both` - Register message will prompt user to enter either their gamertag or steam ID
        """
        if cluster_type.lower() not in ["xbox", "steam", "both"]:
            return await ctx.send(f"{cluster_type} is not a valid cluster type")
        await self.config.guild(ctx.guild).clustertypes.set(cluster_type)
        await ctx.send(f"Cluster type has been set to {cluster_type}")

    @server_settings.command(name="extendedrcon")
    async def toggle_extendedrcon(self, ctx: commands.Context, cluster_name: str):
        """
        Toggle ExtendedRCON for a cluster(STEAM ONLY)

        This toggle is ONLY compatible for steam servers with the extendedRCON plugin,
        view the link below for more info.
        https://arkserverapi.com/index.php?resources/extended-rcon.5/
        """
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if cluster_name.lower() not in clusters.keys():
                return await ctx.send("Cluster name does not exist!")
            else:
                cluster = cluster_name.lower()
                if "extrcon" not in clusters[cluster].keys():
                    clusters[cluster]["extrcon"] = True
                else:
                    extrcon = clusters[cluster]["extrcon"]
                    if extrcon:
                        clusters[cluster]["extrcon"] = False
                    else:
                        clusters[cluster]["extrcon"] = True

    @server_settings.command(name="renamecluster")
    async def rename_cluster(self, ctx: commands.Context, oldclustername: str, newname: str):
        """Rename a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if oldclustername.lower() not in clusters.keys():
                await ctx.send("Original cluster name not found")
            else:
                clusters[newname.lower()] = clusters.pop(oldclustername.lower())
                await ctx.send("Cluster has been renamed")
                await self.initialize()

    @server_settings.command(name="delcluster")
    async def del_cluster(self, ctx: commands.Context, clustername: str):
        """Delete a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername.lower() not in clusters.keys():
                await ctx.send("Cluster name not found")
            else:
                del clusters[clustername.lower()]
                await ctx.send(f"**{clustername}** cluster has been deleted")
                await self.initialize()

    @server_settings.command(name="addserver")
    async def add_server(self, ctx: commands.Context,
                         clustername: str,
                         servername: str,
                         ip: str,
                         port: int,
                         password: str,
                         chatchannel: discord.TextChannel):
        """Add a server to a cluster."""
        if port > 65535 or port < 0:
            return await ctx.send("Invalid port, must be between 0-65535")
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername.lower() not in clusters:
                return await ctx.send(f"The cluster {clustername} does not exist!")
            elif servername.lower() in clusters[clustername]["servers"]:
                await ctx.send(f"The **{servername}** server was **overwritten** in the **{clustername}** cluster!")
            else:
                clusters[clustername.lower()]["servers"][servername.lower()] = {
                    "ip": ip,
                    "port": port,
                    "password": password,
                    "chatchannel": chatchannel.id
                }
                await ctx.send(f"The **{servername}** server has been added to the **{clustername}** cluster!")
        await self.initialize()

    @server_settings.command(name="delserver")
    async def del_server(self, ctx: commands.Context, clustername: str, servername: str):
        """Remove a server from a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername.lower() not in clusters:
                return await ctx.send(f"{clustername} cluster not found.")
            if servername.lower() not in clusters[clustername.lower()]["servers"]:
                return await ctx.send(f"{servername} server not found.")
            del clusters[clustername.lower()]["servers"][servername.lower()]
            await ctx.send(f"**{servername}** server has been removed from **{clustername}**")
            await self.initialize()

    @server_settings.command(name="statuschannel")
    async def set_statuschannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set a channel for the server status monitor.


        Server status embed will be created and updated every 60 seconds.
        """
        await self.config.guild(ctx.guild).status.channel.set(channel.id)
        await ctx.send(f"Status channel has been set to {channel.mention}")

    @server_settings.command(name="statuschannelgraph")
    async def set_statuschannel_graph(self, ctx: commands.Context, hours: int = None):
        """
        Set the length of time to display in the server status embed in hours.


        Must use hours in whole numbers. If no time is given it will default back to 1 hour.
        """
        if hours:
            await self.config.guild(ctx.guild).status.time.set(hours)
            await ctx.send(f"Status channel graph has been set to display past {hours} hours.")
        else:
            await self.config.guild(ctx.guild).status.time.set(1)
            await ctx.send(f"Status channel graph has defaulted to display the last hour.")

    @server_settings.command(name="interchat")
    async def server_to_server_toggle(self, ctx: commands.Context, clustername: str):
        """(Toggle) server to server chat for a cluster so maps can talk to eachother."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername.lower() not in clusters:
                return await ctx.send(f"{clustername} cluster does not exist!")
            if clusters[clustername.lower()]["servertoserver"] is False:
                clusters[clustername.lower()]["servertoserver"] = True
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Enabled**.")
            if clusters[clustername.lower()]["servertoserver"] is True:
                clusters[clustername.lower()]["servertoserver"] = False
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Disabled**.")

    @server_settings.group(name="ingame")
    async def in_game(self, ctx: commands.Context):
        """Configure the in-game payday command"""

    @in_game.command(name="toggle")
    async def toggle_payday(self, ctx: commands.Context):
        """Toggle the in-game payday command on or off"""
        toggled = await self.config.guild(ctx.guild).payday.enabled()
        if toggled:
            await self.config.guild(ctx.guild).payday.enabled.set(False)
            await ctx.send("In-game payday command has been **Disabled**")
        else:
            await self.config.guild(ctx.guild).payday.enabled.set(True)
            await ctx.send("In-game payday command has been **Enabled**")

    @in_game.command(name="random")
    async def toggle_random(self, ctx: commands.Context):
        """
        Toggle whether the in-game payday command chooses a random item from the list of blueprint paths
        or if it sends all items in the list.

        Enabled = Sends 1 random item from that list
        Disabled = Sends all items in the list
        """
        toggled = await self.config.guild(ctx.guild).payday.random()
        if toggled:
            await self.config.guild(ctx.guild).payday.random.set(False)
            await ctx.send("In-game payday is no longer random")
        else:
            await self.config.guild(ctx.guild).payday.random.set(True)
            await ctx.send("In-game payday will now give a random item from the list")

    @in_game.group(name="cooldowns")
    async def cooldown_group(self, ctx: commands.Context):
        """In-Game cooldown settings"""
        pass

    @cooldown_group.command(name="payday")
    async def payday_cooldown(self, ctx: commands.Context, hours: int):
        """
        Set the payday cooldown (in hours)
        """
        await self.config.guild(ctx.guild).payday.cooldown.set(hours)
        await ctx.send(f"Cooldown set for {hours} hours!")

    @cooldown_group.command(name="voting")
    async def vote_cooldowns(self, ctx: commands.Context, minutes: int):
        """
        Set the cooldown for in-game votes (In minutes)
        """
        cooldown = minutes * 60
        cooldown = int(cooldown)
        await self.config.guild(ctx.guild).votecooldown.set(cooldown)
        await ctx.send(f"Cooldown set for {minutes} minutes!")

    @in_game.command(name="togglekit")
    async def toggle_starter_kit(self, ctx: commands.Context):
        """Toggle the in-game starter kit command on or off"""
        toggled = await self.config.guild(ctx.guild).kit.enabled()
        if toggled:
            await self.config.guild(ctx.guild).kit.enabled.set(False)
            await ctx.send("In-game starter kit command has been **Disabled**")
        else:
            await self.config.guild(ctx.guild).kit.enabled.set(True)
            await ctx.send("In-game starter kit command has been **Enabled**")

    @in_game.command(name="setpayday")
    async def set_payday_blueprint_paths(self, ctx: commands.Context):
        """
        Set the full blueprint paths for the in-game payday rewards to send
        The paths must be the FULL blueprint paths WITH the quantity, quality, and blueprint identifier
        separated by a line break

        Do NOT include "cheat" or "admincheat" or "senditemtoplayer" in front of the strings
        """
        msg = await ctx.send(
            "Type the full blueprint paths including quantity/quality/blueprint numbers below.\n"
            "Separate each full path with a new line for setting multiple items.\n"
            "Type `cancel` to cancel.")

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=240, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        if reply.content.lower() == "cancel":
            return await ctx.send("Payday path set canceled.")
        if reply.attachments:
            attachment_url = reply.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    paths = await resp.text()
                    paths = paths.split("\r\n")
        else:
            paths = reply.content.split("\n")
        await self.config.guild(ctx.guild).payday.paths.set(paths)
        await ctx.send("Paths for the in-game payday command have been set!")

    @in_game.command(name="setkit")
    async def set_kit_paths(self, ctx: commands.Context):
        """
        Set the full blueprint paths for the in-game starter kit
        The paths must be the FULL blueprint paths WITH the quantity, quality, and blueprint identifier
        separated by a line break

        Do NOT include "cheat" or "admincheat" or "senditemtoplayer" in front of the strings
        """
        msg = await ctx.send(
            "Type the full blueprint paths including quantity/quality/blueprint numbers below.\n"
            "Separate each full path with a new line for setting multiple items.\n"
            "Type `cancel` to cancel.")

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=240, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        if reply.content.lower() == "cancel":
            return await ctx.send("Starter kit path set canceled.")
        if reply.attachments:
            attachment_url = reply.attachments[0].url
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as resp:
                    paths = await resp.text()
                    paths = paths.split("\r\n")
        else:
            paths = reply.content.split("\n")
        await self.config.guild(ctx.guild).kit.paths.set(paths)
        await ctx.send("Paths for the in-game starter kit command have been set!")

    @in_game.command(name="resetkit")
    async def reset_player_kit(self, ctx: commands.Context, xuid: str):
        """
        Reset a player XUID's claim status for their starter kit,
        just in case they used the wrong implant ID
        """
        async with self.config.guild(ctx.guild).kit.claimed() as claimed:
            if xuid not in claimed:
                return await ctx.send("I could not find that person's XUID.")
            claimed.remove(xuid)
            await ctx.send(f"Claim status for XUID: `{xuid}` has been reset.")

    @in_game.command(name="resetclusterkits")
    async def reset_kit_cluster_wide(self, ctx: commands.Context, clustername: str):
        """
        Reset all kit claim statuses for a specific cluster

        Useful for periodic server wipes
        """
        settings = await self.config.guild(ctx.guild).all()
        kits = settings["kit"]["claimed"]
        wipelist = []
        clusters = settings["clusters"]
        if clustername not in clusters:
            return await ctx.send("Cluster not found!")
        stats = settings["players"]
        for xuid, data in stats.items():
            if xuid in kits:
                for mapn in data["playtime"].keys():
                    if clustername in mapn:
                        if xuid not in wipelist:
                            wipelist.append(xuid)
        await ctx.send(f"{len(wipelist)} xuids to reset")
        async with self.config.guild(ctx.guild).kit.claimed() as claimed:
            for xuid in wipelist:
                claimed.remove(xuid)
        await ctx.send(f"kit claim statuses have been reset for the {clustername} cluster")

    @in_game.command(name="view")
    async def view_ingame_settings(self, ctx: commands.Context):
        """View configuration settings for in-game payday options"""
        payday = await self.config.guild(ctx.guild).payday()
        kit = await self.config.guild(ctx.guild).kit()
        starter = "Disabled"
        if kit["enabled"]:
            starter = "Enabled"
        status = "Disabled"
        if payday["enabled"]:
            status = "Enabled"
        rand = "Off"
        if payday["random"]:
            rand = "On"
        cooldown = payday["cooldown"]
        embed = discord.Embed(
            title="In-Game Command Settings",
            description=f"`Payday Status:       `{status}\n"
                        f"`Payday Randomness:   `{rand}\n"
                        f"`Payday Cooldown:     `{cooldown}\n"
                        f"`Starter Kit:         `{starter}\n",
            color=discord.Color.random()
        )
        await ctx.send(embed=embed)
        paths = payday["paths"]
        p = ""
        for path in paths:
            p += f"{path}\n"
        if p == "":
            p = "None Set!"
        count = 1
        for page in pagify(p):
            embed = discord.Embed(
                title=f"Payday Paths Page {count}",
                description=page
            )
            await ctx.send(embed=embed)
            count += 1
        kits = kit["paths"]
        k = ""
        for path in kits:
            k += f"{path}\n"
        if k == "":
            k = "None Set!"
        count = 1
        for page in pagify(k):
            embed = discord.Embed(
                title=f"Starter Kit Paths Page {count}",
                description=page
            )
            await ctx.send(embed=embed)
            count += 1

    # Cache server data
    async def initialize(self):
        self.activeguilds = []
        self.servercount = 0
        self.servers = []
        self.channels = []
        config = await self.config.all_guilds()
        for guild_id in config:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            log.info(f"Checking {guild} config")
            newsettings, results = await cleanup_config(settings)
            if results:
                log.info(results)
                await self.config.guild(guild).set(newsettings)
            else:
                log.info("Config health: Good")
            clusters = settings["clusters"]
            if not clusters:
                continue
            servers_present = False
            for clusterdata in clusters.values():
                if clusterdata["servers"]:
                    servers_present = True
            if not servers_present:
                continue
            if guild_id not in self.activeguilds:
                self.activeguilds.append(guild_id)
            for cluster in clusters:
                if clusters[cluster] == {}:
                    continue
                globalchannel = clusters[cluster]["globalchatchannel"]
                self.channels.append(globalchannel)
                adminlog = clusters[cluster]["adminlogchannel"]
                joinchannel = clusters[cluster]["joinchannel"]
                leavechannel = clusters[cluster]["leavechannel"]
                for server in clusters[cluster]["servers"]:
                    name = server
                    server = clusters[cluster]["servers"][server]
                    server["globalchatchannel"] = globalchannel
                    server["adminlogchannel"] = adminlog
                    server["joinchannel"] = joinchannel
                    server["leavechannel"] = leavechannel
                    server["cluster"] = cluster
                    server["name"] = name
                    server["guild"] = guild
                    server["eventlog"] = settings["eventlog"]
                    if "extrcon" in clusters[cluster]:
                        server["extrcon"] = clusters[cluster]["extrcon"]
                    self.servers.append((guild.id, server))
                    self.servercount += 1
                    self.channels.append(server["chatchannel"])
                    if server["chatchannel"] not in self.playerlist:
                        self.playerlist[server["chatchannel"]] = "offline"
        log.info("Config initialized.")

    # Sends ServerChat command to designated server if message is in the server chat channel
    @commands.Cog.listener("on_message")
    async def to_server_chat(self, message: discord.Message):
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasnt sent in a guild
        if not message.guild:
            return
        # If message has no content for some reason?
        if not message:
            return
        # Can i send messages in that channel
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return
        # Check if guild id is initialized
        if message.channel.guild.id not in self.activeguilds:
            return
        # Check if any servers have been initialized
        if not self.servers:
            return
        # Reformat messages if containing mentions
        if message.mentions:
            for mention in message.mentions:
                message.content = message.content.replace(f"<@!{mention.id}>", f"@{mention.name}")
        if message.channel_mentions:
            # noinspection PyTypeChecker
            for mention in message.channel_mentions:
                message.content = message.content.replace(f"<#{mention.id}>", f"#{mention.name}")
        if message.role_mentions:
            for mention in message.role_mentions:
                message.content = message.content.replace(f"<@&{mention.id}>", f"@{mention.name}")

        # Run checks for what channel the message was sent in to see if its a map channel
        clusterchannels, allservers = self.globalchannelchecker(message.channel)
        chatchannel, servermap = self.mapchannelchecker(message.channel)

        if not allservers and not servermap:
            return
        try:
            name, msg = await decode(message)
        except TypeError:
            log.info(f"TypeError, Message to server failed from {message.author}: {message.content}")
            return
        if not msg:
            return
        if msg == " ":
            return
        guild = message.guild
        rtasks = []
        if message.channel.id in clusterchannels:
            for server in allservers:
                rtasks.append(self.executor(guild, server, f"serverchat {name}: {msg}"))
            await asyncio.gather(*rtasks)
        elif int(message.channel.id) == int(chatchannel):
            await self.executor(guild, servermap, f"serverchat {name}: {msg}")
        else:
            return

    # Returns all channels and servers related to the message
    def globalchannelchecker(self, channel: discord.TextChannel):
        clusterchannels = []
        allservers = []
        for tup in self.servers:
            server = tup[1]
            if server["globalchatchannel"] == channel.id:
                clusterchannels.append(server["globalchatchannel"])
                allservers.append(server)
        return clusterchannels, allservers

    # Returns the channel and server related to the message
    def mapchannelchecker(self, channel: discord.TextChannel):
        for tup in self.servers:
            server = tup[1]
            if server["chatchannel"] == channel.id:
                return channel.id, server
        return None, None

    # Initiates the Listplayers loop
    @tasks.loop(seconds=30)
    async def listplayers(self):
        listplayertasks = []
        for data in self.servers:
            guild = self.bot.get_guild(data[0])
            server = data[1]
            listplayertasks.append(self.executor(guild, server, "listplayers"))
        await asyncio.gather(*listplayertasks)

    # Initiates the GetChat loop
    @tasks.loop(seconds=5)
    async def getchat(self):
        chat_tasks = []
        for data in self.servers:
            guild = self.bot.get_guild(data[0])
            server = data[1]
            chat_tasks.append(self.executor(guild, server, "getchat"))
        await asyncio.gather(*chat_tasks)

    # Non-blocking sync executor for rcon task loops
    async def executor(self, guild: discord.guild, server: dict, command: str):
        if not server:
            return
        if not guild:
            return
        priority_commands = ["listplayers", "banplayer", "unbanplayer", "doexit", "saveworld"]
        for cmd in priority_commands:
            if cmd in command:
                priority = True
                break
        else:
            priority = False
        if not priority and self.in_queue(server["chatchannel"]):
            skip = True
        else:
            skip = False
        if server["port"] > 65535 or server["port"] < 0:
            eventlog = guild.get_channel(server["eventlog"])
            if eventlog:
                embed = discord.Embed(
                    description=f"Server {server['name']} {server['cluster']} has an out of range port 0-65535",
                    color=discord.Color.from_rgb(140, 7, 0)  # dark red
                )
                if eventlog.permissions_for(guild.me).send_messages:
                    await eventlog.send(embed=embed)
            return
        if command == "getchat" or "serverchat" in command:
            timeout = 2
        elif command == "listplayers":
            timeout = 5
        else:
            timeout = 3

        if "serverchat" in command and "extrcon" in server:
            if server["extrcon"]:
                msg = command.split(" ", 1)[1]
                command = f"clientchat {msg}"

        def exe():
            try:
                with Client(
                        host=server['ip'],
                        port=server['port'],
                        passwd=server['password'],
                        timeout=timeout
                ) as client:
                    result = client.run(command)
                    client.close()
                    return result
            except socket.timeout:
                return
            except Exception as e:
                if "WinError 10054" in str(e):
                    log.info(f"Server {server['name']} {server['cluster']} timed out too quickly")
                else:
                    log.warning(f"Executor Error: {e}")
                return

        if skip:
            res = None
        else:
            res = await self.bot.loop.run_in_executor(None, exe)
        if not res and not skip:
            channel = server["chatchannel"]
            if channel not in self.queue:
                # Put server in queue, loops will ignore that server for 2 minutes and then try again
                self.queue[channel] = datetime.datetime.now()
        if command == "getchat":
            if res:
                if "Server received, But no response!!" not in res:
                    await self.message_handler(guild, server, res)
        if command == "listplayers":
            # If server is online create list of player tuples
            if res:
                if "No Players Connected" in res:
                    await self.player_join_leave(guild, server, "empty")
                else:
                    regex = r"(?:[0-9]+\. )(.+), ([0-9]+)"
                    res = re.findall(regex, res)
                    await self.player_join_leave(guild, server, res)
            else:  # If server is offline return None
                await self.player_join_leave(guild, server, "offline")

    @getchat.before_loop
    async def before_getchat(self):
        await self.bot.wait_until_red_ready()
        await self.initialize()
        await asyncio.sleep(5)
        log.info("GetChat loop ready")

    @listplayers.before_loop
    async def before_listplayers(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)
        log.info("Listplayers loop ready")

    # Detect player joins/leaves and log to respective channels
    async def player_join_leave(self, guild: discord.guild, server: dict, newplayerlist: typing.Union[str, list]):
        channel = server["chatchannel"]
        joinlog = guild.get_channel(server["joinchannel"])
        leavelog = guild.get_channel(server["leavechannel"])
        mapname = server["name"].capitalize()
        clustername = server["cluster"].upper()

        can_send = False
        if joinlog and leavelog:
            jperms = joinlog.permissions_for(guild.me).send_messages
            lperms = leavelog.permissions_for(guild.me).send_messages
        else:
            jperms = None
            lperms = None
        if jperms and lperms:
            can_send = True

        lastplayerlist = self.playerlist[channel]

        # If new and last are both strings then just update them, nothing to log
        if isinstance(newplayerlist, str) and isinstance(lastplayerlist, str):
            self.playerlist[channel] = newplayerlist
        else:  # Either new playerlist, last playerlist, or neither is a string so now we narrow it down
            # If both are lists then detect change in population
            if isinstance(newplayerlist, list) and isinstance(lastplayerlist, list):
                if can_send:
                    for player in newplayerlist:
                        if player not in lastplayerlist:
                            await joinlog.send(
                                f":green_circle: `{player[0]}, {player[1]}` joined {mapname} {clustername}")
                    for player in lastplayerlist:
                        if player not in newplayerlist:
                            await leavelog.send(f":red_circle: `{player[0]}, {player[1]}` left {mapname} {clustername}")
                self.playerlist[channel] = newplayerlist
            # Went from online and populated to either offline or empty, so just dump the users into leave log
            elif isinstance(newplayerlist, str) and isinstance(lastplayerlist, list):
                for player in lastplayerlist:
                    if can_send:
                        await leavelog.send(f":red_circle: `{player[0]}, {player[1]}` left {mapname} {clustername}")
                self.playerlist[channel] = newplayerlist
            # Went from empty to populated so add everyone in the server to the join log
            elif isinstance(newplayerlist, list) and isinstance(lastplayerlist, str):
                if lastplayerlist == "empty":
                    for player in newplayerlist:
                        await joinlog.send(
                            f":green_circle: `{player[0]}, {player[1]}` joined {mapname} {clustername}")
                self.playerlist[channel] = newplayerlist
            else:
                # If a server goes from offline to populated its probably cause the cog was reloaded, so ignore
                self.playerlist[channel] = newplayerlist

    # Sends messages from in-game chat to their designated channels
    async def message_handler(self, guild: discord.guild, server: dict, res: str):
        adminlog = guild.get_channel(server["adminlogchannel"])
        globalchat = guild.get_channel(server["globalchatchannel"])
        chatchannel = guild.get_channel(server["chatchannel"])
        perms = chatchannel.permissions_for(guild.me).send_messages
        msgs = res.split("\n")
        settings = await self.config.guild(guild).all()
        badnames = settings["badnames"]
        admin_commands = ""
        globalmessages = ""
        messages = ""
        tribe_logs = []
        chats = []
        servername = server["name"].capitalize()
        clustername = server["cluster"].upper()
        # Filter messages for feedback loops and invalid strings
        for msg in msgs:
            if not msg:
                continue
            if msg == " ":
                continue
            if msg.startswith("SERVER:"):
                continue
            if msg.startswith("AdminCmd:"):  # Admin command
                admin_commands += f"**{servername} {clustername}**\n{box(msg, lang='python')}\n"
                continue
            elif "Tribe" and ", ID" in msg:  # Tribe log
                tribe_logs.append(msg)
            else:
                if "):" not in msg:
                    continue
                else:
                    chats.append(msg)
        for msg in chats:
            # Append messages to be sent to discord
            globalmessages += f"{chatchannel.mention}: {msg}\n"
            messages += f"{msg}\n"
            # Sends Discord invite to in-game chat if the word Discord is mentioned
            if "discord" in msg.lower() or "discordia" in msg.lower():
                inv = None
                try:
                    inv = await guild.vanity_invite()
                except discord.Forbidden:
                    try:
                        inv = await chatchannel.create_invite(unique=False, max_age=3600, reason="Ark Auto Response")
                    except Exception as e:
                        log.exception(f"INVITE CREATION FAILED: {e}")
                if inv:
                    await self.executor(guild, server, f"serverchat {inv}")

            # If interchat is enabled, relay message to other servers
            clustername = server["cluster"]
            if settings["clusters"][clustername]["servertoserver"]:  # Maps can talk to each other if true
                for data in self.servers:
                    s = data[1]
                    g = self.bot.get_guild(data[0])
                    if s["cluster"] == server["cluster"] and s["name"] != server["name"] and g == guild:
                        await self.executor(guild, s, f"serverchat {server['name'].capitalize()}: {msg}")

            # Break message into groups for interpretation
            reg = r'(.+)\s\((.+)\): (.+)'
            msg = re.findall(reg, msg)
            if len(msg) == 0:  # Weird this shouldnt happen but
                continue
            msg = msg[0]
            gamertag = msg[0]
            character_name = msg[1]
            message = msg[2]
            # Check if any character has a blacklisted name and rename the character to their Gamertag if so
            for badname in badnames:
                if badname.lower() == character_name.lower():
                    await self.executor(guild, server, f'renameplayer "{badname}" {gamertag}')
                    cmd = f"serverchat {gamertag}, the name {badname} has been blacklisted, you have been renamed"
                    await self.executor(guild, server, cmd)
                    if perms:
                        await chatchannel.send(f"A player named `{badname}` has been renamed to `{gamertag}`.")
            try:
                xuid, stats = await self.get_player(gamertag, settings["players"])
            except TypeError:
                stats = None
                xuid = None
            # In game player name sync
            if stats:
                server_id = str(server["chatchannel"])
                async with self.config.guild(guild).players() as playerconf:
                    if server_id not in playerconf[xuid]["ingame"]:
                        playerconf[xuid]["ingame"][server_id] = {
                            "implant": None,
                            "name": character_name,
                            "previous_names": [],
                            "stats": {
                                "pvpkills": 0,
                                "pvpdeaths": 0,
                                "pvedeaths": 0,
                                "tamed": 0
                            }
                        }
                    else:
                        saved_name = playerconf[xuid]["ingame"][server_id]["name"]
                        if not saved_name:
                            playerconf[xuid]["ingame"][server_id]["name"] = character_name
                        else:
                            if saved_name != character_name:
                                if saved_name not in playerconf[xuid]["ingame"][server_id]["previous_names"]:
                                    playerconf[xuid]["ingame"][server_id]["previous_names"].append(saved_name)
                                playerconf[xuid]["ingame"][server_id]["name"] = character_name

            # Check or apply ranks
            if settings["autorename"]:
                rank = None
                if stats:
                    if "rank" in stats:
                        rank = stats["rank"]
                        rank = guild.get_role(rank)
                if rank:
                    if str(rank) not in character_name:
                        if "[" not in character_name and "]" not in character_name:
                            cmd = f'renameplayer "{character_name}" [{str(rank)}] {character_name}'
                            await self.executor(guild, server, cmd)
                        else:  # Update their rank
                            raw_name = character_name.split("]")[-1]
                            raw_name = raw_name.strip()
                            cmd = f'renameplayer "{character_name}" [{str(rank)}] {raw_name}'
                            await self.executor(guild, server, cmd)
                        cmd = f"serverchat Congrats {gamertag}, you have reached the rank of {str(rank)}"
                        await self.executor(guild, server, cmd)
                        if perms:
                            await chatchannel.send(f"`Congrats {gamertag}, you have reached the rank of {str(rank)}`")

            # In-game command interpretation
            prefixes = await self.bot.get_valid_prefixes(guild)
            for p in prefixes:
                if message.startswith(p):
                    message = message.replace(p, "", 1)
                    resp = await self.ingame_cmd(guild, p, server, gamertag, character_name, message)
                    if resp:
                        messages += f"`{resp}`\n"
                    break
        # Send off messages to discord channels
        if perms:
            if messages:
                for p in pagify(messages):
                    await chatchannel.send(p)
            if globalmessages:
                for p in pagify(globalmessages):
                    await globalchat.send(p)
            if admin_commands:
                for p in pagify(admin_commands):
                    await adminlog.send(p)
        if tribe_logs:
            await self.tribelog_sendoff(guild, settings, server, tribe_logs)

    # In game command handler
    async def ingame_cmd(self, guild: discord.guild, prefix: str, server: dict, gamertag: str, char_name: str,
                         cmd: str) -> str:
        settings = await self.config.guild(guild).all()
        colors = [
            '<RichColor Color="1,0,0,1">',  # Red
            '<RichColor Color="0,1,0,1">',  # Green
            '<RichColor Color="1,0.65,0,1">',  # Orange
            '<RichColor Color="0,0,0,1">',  # Black
            '<RichColor Color "1,1,0,1">',  # Yellow
            '<RichColor Color="1,0,1,1">',  # Fuchsia
            '<RichColor Color="0.5,0,0.5,1">',  # Purple
            '<RichColor Color="0,0.5,0.5,1">'  # Blue
        ]
        color = random.choice(colors)
        available_cmd = f"{color}IN GAME COMMANDS</>\n" \
                        f"{prefix}register <ID> - Register your implantID to use commands without it\n" \
                        f"{prefix}imstuck - Send yourself a care package if youre stuck\n" \
                        f"{prefix}voteday - Start a vote for daytime\n" \
                        f"{prefix}votenight - Start a vote for night\n" \
                        f"{prefix}votedinowipe - Start a vote to wipe wild dinos\n" \
                        f"{prefix}votecleanup - Start a vote to wipe beaver dams and spoiled eggs\n"
        h = settings["payday"]["cooldown"]
        duration = h * 3600
        extras = 0
        if settings["payday"]["enabled"]:
            available_cmd += f"{prefix}payday - Earn in-game rewards every {h} hours!\n"
            extras += 1
        if settings["kit"]["enabled"]:
            available_cmd += f"{prefix}kit - New players can claim a one-time starter kit!\n"
            extras += 1
        players = settings["players"]
        cid = server["chatchannel"]
        playerlist = self.playerlist[cid]
        server_id = str(cid)
        time = datetime.datetime.now()
        com, arg = self.parse_cmd(cmd)
        if not com:
            return ""
        xuid, stats = await self.get_player(gamertag, players)
        if not xuid or not stats:
            resp = "In-game command failed! This can happen if you recently changed your Gamertag"
            com = f"serverchat {resp}"
            await self.executor(guild, server, com)
            log.info(f"In-Game command failed for: {gamertag}, {com}")
            return resp
        # Help command
        elif com == "help":
            if extras == 0:
                available_cmd += f"{prefix}rename NewName - Rename your character\n" \
                                 f"{prefix}players - returns current player count"
                extra_commands = None
            elif extras == 1:
                available_cmd += f"{prefix}rename NewName - Rename your character"
                extra_commands = f"{prefix}players"
            else:
                extra_commands = f"'{prefix}players' and '{prefix}rename'"
            await self.executor(guild, server, f"broadcast {available_cmd}")
            if extra_commands:
                com = f"serverchat Other commands too long to fit in the broadcast include {extra_commands}"
                await self.executor(guild, server, com)
            resp = "Sending list of in-game commands!"
            return resp
        # Register command
        elif com == "register":
            if not arg:
                resp = "You must include your implant ID in the command!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            else:
                async with self.config.guild(guild).players() as players:
                    resp = await self.check_implant(guild, server, arg)
                    if resp:
                        return resp
                    if server_id not in players[xuid]["ingame"]:
                        players[xuid]["ingame"][server_id] = {
                            "implant": arg,
                            "name": char_name,
                            "previous_names": [],
                            "stats": {
                                "pvpkills": 0,
                                "pvpdeaths": 0,
                                "pvedeaths": 0,
                                "tamed": 0
                            }
                        }
                    else:
                        players[xuid]["ingame"][server_id]["implant"] = arg
                    resp = f"{gamertag}, Your implant was registered as {arg}"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
        # Rename command
        elif com == "rename":
            if not arg:
                resp = "You need to include the new name you want in the command"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            if settings["autorename"]:
                if "rank" in players[xuid]:
                    rank = players[xuid]["rank"]
                    rank = guild.get_role(rank)
                    arg = f"[{rank}] {arg}"
            com = f'renameplayer "{char_name}" {arg}'
            await self.executor(guild, server, com)
            resp = f"{gamertag}, Your name has been changed to {arg}"
            com = f"serverchat {resp}"
            await self.executor(guild, server, com)
            return resp
        # Vote day command
        elif com == "voteday":
            remaining = await self.vote_handler(guild, cid, server, gamertag, "voteday")
            if isinstance(remaining, str):
                resp = remaining
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            elif remaining > 0:
                resp = f"Need {remaining} more In-game votes to make it day!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            else:
                resp = "Vote successful, let there be light!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                com = "settimeofday 07:00"
                await self.executor(guild, server, com)
                del self.votes[cid]
                return resp
        # Vote night command
        elif com == "votenight":
            remaining = await self.vote_handler(guild, cid, server, gamertag, "votenight")
            if isinstance(remaining, str):
                resp = remaining
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            elif remaining > 0:
                resp = f"Need {remaining} more In-game votes to make it night!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            else:
                resp = "Vote successful, turning off the sun!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                com = "settimeofday 22:00"
                await self.executor(guild, server, com)
                del self.votes[cid]
                return resp
        # Dino wipe command
        elif com == "votedinowipe":
            remaining = await self.vote_handler(guild, cid, server, gamertag, "votedinowipe")
            if isinstance(remaining, str):
                resp = remaining
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            elif remaining > 0:
                resp = f"Need {remaining} more votes to wipe wild dinos!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            else:
                resp = "Vote successful, asteroids inbound! All wild dinos will be wiped."
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                com = "destroywilddinos"
                await self.executor(guild, server, com)
                del self.votes[cid]
                return resp
        # Vote server cleanup command, wipes beaver dams and spoiled eggs
        elif com == "votecleanup":
            remaining = await self.vote_handler(guild, cid, server, gamertag, "votecleanup")
            if isinstance(remaining, str):
                resp = remaining
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            elif remaining > 0:
                resp = f"Need {remaining} more In-game votes to wipe beaver dams and spoiled eggs!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            else:
                resp = "Vote successful, wiping dams and spoiled eggs!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                cleanup_commands = [
                    "destroyall BeaverDam_C",
                    "destroyall DroppedItemGeneric_FertilizedEgg_RockDrake_NoPhysics_C",
                    "destroyall DroppedItemGeneric_FertilizedEgg_NoPhysicsWyvern_C",
                    "destroyall DroppedItemGeneric_FertilizedEgg_NoPhysicsDeinonychus_C",
                    "destroyall DroppedItemGeneric_FertilizedEgg_NoPhysicsCherufe_C"
                ]
                for cleanup_command in cleanup_commands:
                    await self.executor(guild, server, cleanup_command)
                del self.votes[cid]
                return resp
        # Player count command
        elif com == "players":
            if len(playerlist) == 1:
                resp = "You're the only person on this server :p"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            else:
                resp = f"There are {len(playerlist)} people on this server"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
        # Im stuck command
        elif com == "imstuck":
            canuse = False
            if arg:
                resp = await self.check_implant(guild, server, arg)
                if resp:
                    return resp
            else:
                implant = self.get_implant(stats, str(server["chatchannel"]))
                if not implant:
                    resp = "Include your Implant ID in the command or use the .register command to save it"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
                else:
                    arg = implant
            async with self.config.guild(guild).cooldowns() as cooldowns:
                if gamertag not in cooldowns:
                    cooldowns[gamertag] = {"imstuck": time.isoformat()}
                    canuse = True
                elif "imstuck" not in cooldowns[gamertag]:
                    cooldowns[gamertag]["imstuck"] = time.isoformat()
                    canuse = True
                else:
                    lastused = cooldowns[gamertag]["imstuck"]
                    lastused = datetime.datetime.fromisoformat(lastused)
                    td = time - lastused
                    if td.total_seconds() > 1800:
                        canuse = True
                if canuse:
                    cooldowns[gamertag]["imstuck"] = time.isoformat()
                    stasks = []
                    for path in IMSTUCK_BLUEPRINTS:
                        stasks.append(self.executor(guild, server, f"giveitemtoplayer {arg} {path}"))
                    await asyncio.gather(*stasks)
                    resp = f"{gamertag}, your care package is on the way!"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
                else:
                    lastused = cooldowns[gamertag]["imstuck"]
                    lastused = datetime.datetime.fromisoformat(lastused)
                    td = time - lastused
                    tleft = td.total_seconds()
                    tleft = time_formatter(int(tleft))
                    resp = f"{gamertag}, You need to wait {tleft} before using that command again"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
        # Payday command
        elif com == "payday":
            if not settings["payday"]["enabled"]:
                resp = f"{gamertag}, That command is disabled on this server at the moment"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            canuse = False
            if arg:
                resp = await self.check_implant(guild, server, arg)
                if resp:
                    return resp
            else:
                implant = self.get_implant(stats, str(server["chatchannel"]))
                if not implant:
                    resp = "Include your Implant ID in the command or use the .register command to save it"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
                else:
                    arg = implant
            async with self.config.guild(guild).cooldowns() as cooldowns:
                if gamertag not in cooldowns:
                    cooldowns[gamertag] = {"payday": time.isoformat()}
                    canuse = True
                elif "payday" not in cooldowns[gamertag]:
                    cooldowns[gamertag]["payday"] = time.isoformat()
                    canuse = True
                else:
                    lastused = cooldowns[gamertag]["payday"]
                    lastused = datetime.datetime.fromisoformat(lastused)
                    td = time - lastused
                    if td.total_seconds() > duration:
                        canuse = True
                if canuse:
                    cooldowns[gamertag]["payday"] = time.isoformat()
                    paths = await self.config.guild(guild).payday.paths()
                    rand = await self.config.guild(guild).payday.random()
                    if rand:
                        path = random.choice(paths)
                        await self.executor(guild, server, f"giveitemtoplayer {arg} {path}")
                    else:
                        ptasks = []
                        for path in paths:
                            ptasks.append(self.executor(guild, server, f"giveitemtoplayer {arg} {path}"))
                        await asyncio.gather(*ptasks)
                    resp = f"{gamertag}, your payday rewards have been sent!"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
                else:
                    lastused = cooldowns[gamertag]["payday"]
                    lastused = datetime.datetime.fromisoformat(lastused)
                    td = time - lastused
                    td = td.total_seconds()
                    tleft = duration - td
                    time_left = time_formatter(tleft)
                    resp = f"{gamertag}, You need to wait {time_left} before using that command again"
                    com = f"serverchat  {resp}"
                    await self.executor(guild, server, com)
                    return resp
        # Starter kit command
        elif com == "kit":
            kit = await self.config.guild(guild).kit()
            if not kit["enabled"]:
                resp = f"{gamertag}, That command is disabled on this server at the moment"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            if len(kit["paths"]) == 0:
                resp = "The Kit command has not been fully setup yet!"
                com = f"serverchat {resp}"
                await self.executor(guild, server, com)
                return resp
            if arg:
                resp = await self.check_implant(guild, server, arg)
                if resp:
                    return resp
            else:
                implant = self.get_implant(stats, str(server["chatchannel"]))
                if not implant:
                    resp = f"Use the {prefix}register command to register your ID first " \
                           f"or include your implant ID in the command"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
                else:
                    arg = implant
            async with self.config.guild(guild).kit() as kit:
                if xuid in kit["claimed"]:
                    resp = f"{gamertag}, You have already claimed your starter kit!"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
                else:
                    kit["claimed"].append(xuid)
                    ktasks = []
                    for path in kit["paths"]:
                        ktasks.append(self.executor(guild, server, f"giveitemtoplayer {arg} {path}"))
                    await asyncio.gather(*ktasks)
                    resp = f"{gamertag}, you have successfully claimed your starter kit!"
                    com = f"serverchat {resp}"
                    await self.executor(guild, server, com)
                    return resp
        # If a player tries a command that doesnt exist
        else:
            return ""

    async def check_implant(self, guild: discord.guild, server: dict, arg: str):
        if not arg.isdigit():
            resp = "That is not a number. Include your implant ID NUMBER in the command, " \
                   "your Implant is in the top left of your inventory, look for the 'specimen' number"
            com = f"serverchat {resp}"
            await self.executor(guild, server, com)
            return resp
        elif len(arg) > 9 or len(arg) < 7:
            resp = "Incorrect ID, Implant ID's are 7 or 9 digits long, " \
                   "your Implant is in the top left of your inventory, look for the 'specimen' number"
            com = f"serverchat {resp}"
            await self.executor(guild, server, com)
            return resp
        else:
            return None

    async def vote_handler(self, guild, channel_id, server, gamertag, vote_type):
        can_run = False
        time = datetime.datetime.now()
        if channel_id not in self.lastran:
            self.lastran[channel_id] = {}
            can_run = True
        if vote_type not in self.lastran[channel_id]:
            self.lastran[channel_id][vote_type] = time
            can_run = True
        if channel_id in self.votes:
            can_run = True
        last_ran = self.lastran[channel_id][vote_type]
        td = time - last_ran
        td = td.total_seconds()
        td = int(td)
        cooldown = await self.config.guild(guild).votecooldown()
        cooldown = int(cooldown)
        if td > cooldown:
            can_run = True
        if can_run:
            time_till_expired = time + datetime.timedelta(minutes=2)
            playerlist = self.playerlist[channel_id]
            if playerlist:
                count = len(playerlist)
            else:
                count = 1
            min_votes = math.ceil(count / 2)
            if count == 1:
                min_votes = 1
            if count > 10:
                min_votes = math.ceil(math.sqrt(2 * count))
            if channel_id not in self.votes:
                self.votes[channel_id] = {}
            if vote_type not in self.votes[channel_id]:
                self.votes[channel_id][vote_type] = {
                    "expires": time_till_expired,
                    "votes": [],
                    "minvotes": min_votes,
                    "server": server
                }
            if gamertag not in self.votes[channel_id][vote_type]["votes"]:
                self.votes[channel_id][vote_type]["votes"].append(gamertag)
            min_votes = self.votes[channel_id][vote_type]["minvotes"]
            current = len(self.votes[channel_id][vote_type]["votes"])
            remaining = min_votes - current
            return int(remaining)
        else:
            tleft = cooldown - td
            tleft = time_formatter(tleft)
            msg = f"Command is in cooldown, wait {tleft}"
            return msg

    @tasks.loop(seconds=10)
    async def vote_sessions(self):
        expired = []
        for cid in self.votes:
            for votetype, session in self.votes[cid].items():
                time = datetime.datetime.now()
                if time > session["expires"]:
                    if len(session["votes"]) < session["minvotes"]:
                        guild = session["server"]["guild"]
                        await self.executor(guild, session["server"], f"serverchat {votetype} session expired")
                        expired.append(cid)
        for cid in expired:
            del self.votes[cid]

    @vote_sessions.before_loop
    async def before_vote_sessions(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)
        log.info("Vote session manager ready")

    @tasks.loop(seconds=60)
    async def status_channel(self):
        for guild in self.activeguilds:
            guild = self.bot.get_guild(guild)
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            thumbnail = LIVE
            status = ""
            totalplayers = 0
            dest_channel = settings["status"]["channel"]
            if not dest_channel:
                continue
            dest_channel = guild.get_channel(dest_channel)
            if not dest_channel:
                continue
            view_perms = dest_channel.permissions_for(guild.me).view_channel
            if not view_perms:
                continue
            send_perms = dest_channel.permissions_for(guild.me).send_messages
            if not send_perms:
                continue

            for cluster in settings["clusters"]:
                cname = cluster
                clustertotal = 0
                status += f"**{cluster.upper()}**\n"
                servers = settings["clusters"][cluster]["servers"]
                clustersettngs = settings["clusters"][cluster]
                for server in servers:
                    sname = server
                    server = servers[server]
                    channel = server["chatchannel"]

                    # Get cached player count data
                    playerlist = self.playerlist[channel]

                    if channel not in self.downtime:
                        self.downtime[channel] = 0

                    count = self.downtime[channel]
                    if playerlist == "offline":
                        thumbnail = FAILED
                        inc = "Minutes."
                        if count >= 60:
                            count = count / 60
                            inc = "Hours."
                            count = int(count)
                        schannel = guild.get_channel(channel)
                        if schannel:
                            schannel = schannel.mention
                        else:
                            schannel = channel
                        status += f"{schannel}: Offline for {count} {inc}\n"
                        if self.downtime[channel] == 5:
                            mentions = discord.AllowedMentions(roles=True)
                            pingrole = guild.get_role(settings["fullaccessrole"])
                            if pingrole:
                                pingrole = pingrole.mention
                            else:
                                pingrole = "Failed to Ping admin role... BUT,"
                            alertchannel = guild.get_channel(clustersettngs["adminlogchannel"])
                            perms = None
                            if alertchannel:
                                perms = alertchannel.permissions_for(guild.me).send_messages
                            if perms:
                                await alertchannel.send(
                                    f"{pingrole}\n"
                                    f"The **{sname} {cname}** server has been offline for 5 minutes now!",
                                    allowed_mentions=mentions
                                )
                        self.downtime[channel] += 1

                    elif playerlist == "empty":
                        status += f"{guild.get_channel(channel).mention}: 0 Players\n"
                        self.downtime[channel] = 0

                    else:
                        playercount = len(playerlist)
                        clustertotal += playercount
                        totalplayers += playercount
                        if playercount == 1:
                            status += f"{guild.get_channel(channel).mention}: {playercount} player\n"
                        else:
                            status += f"{guild.get_channel(channel).mention}: {playercount} players\n"

                if clustertotal == 1:
                    status += f"`{clustertotal}` player cluster wide\n\n"
                else:
                    status += f"`{clustertotal}` players cluster wide\n\n"

                # Log player counts per cluster
                async with self.config.guild(guild).serverstats() as serverstats:
                    if cname not in serverstats:
                        serverstats[cname] = []
                    serverstats[cname].append(int(clustertotal))

            # Log total player counts
            now = datetime.datetime.now(pytz.timezone("UTC"))
            async with self.config.guild(guild).serverstats() as serverstats:
                serverstats["dates"].append(now.isoformat())
                serverstats["counts"].append(int(totalplayers))

            # Embed setup
            tz = settings["timezone"]
            tz = pytz.timezone(tz)
            hours = settings["status"]["time"]
            file = await get_graph(settings, int(hours))
            img = "attachment://plot.png"
            await self.status_cleaner(settings["status"], dest_channel)
            if len(status) <= 4096:
                embed = discord.Embed(
                    description=status,
                    color=discord.Color.random(),
                    timestamp=now.astimezone(tz)
                )
                embed.set_author(name="Server Status", icon_url=guild.icon_url)
                embed.add_field(name="Total Players", value=f"`{totalplayers}`")
                embed.set_thumbnail(url=thumbnail)
                embed.set_image(url=img)
                if file:
                    message = await dest_channel.send(embed=embed, file=file)
                else:
                    message = await dest_channel.send(embed=embed)
                await self.config.guild(guild).status.multi.set([])
                await self.config.guild(guild).status.message.set(message.id)

            else:  # Person must have a fuck ton of servers for the bot to have use this ugh
                # Embed is too dummy thicc and needs multiple embeds
                pages = 0
                for _ in pagify(status):
                    pages += 1
                new_message_list = []
                count = 1
                color = discord.Color.random()
                for p in pagify(status):
                    if count == pages:
                        embed = discord.Embed(
                            description=p,
                            color=color,
                            timestamp=now.astimezone(tz)
                        )
                    else:
                        embed = discord.Embed(
                            description=p,
                            color=color
                        )
                    if count == 1:
                        embed.set_author(name="Server Status", icon_url=guild.icon_url)
                        embed.set_thumbnail(url=thumbnail)
                    if count == pages:
                        embed.set_image(url=img)
                        message = await dest_channel.send(embed=embed, file=file)
                    else:
                        message = await dest_channel.send(embed=embed)
                    count += 1
                    new_message_list.append(message.id)
                await self.config.guild(guild).status.message.set(None)
                await self.config.guild(guild).status.multi.set(new_message_list)

    @status_channel.before_loop
    async def before_status_channel(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(15)
        log.info("Status Channel loop ready")

    # Player stat handler
    @tasks.loop(minutes=2)
    async def player_stats(self):
        current_time = datetime.datetime.now(pytz.timezone("UTC"))
        if self.time == "":
            self.time = current_time.isoformat()
        last = datetime.datetime.fromisoformat(str(self.time))
        timedifference = current_time - last
        timedifference = int(timedifference.total_seconds())
        config = await self.config.all_guilds()
        for guild_id in config:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            autofriend = settings["autofriend"]
            autowelcome = settings["autowelcome"]
            eventlog = settings["eventlog"]
            if eventlog:
                eventlog = guild.get_channel(eventlog)
            for data in self.servers:
                sguild = data[0]
                sguild = self.bot.get_guild(sguild)
                if guild != sguild:
                    continue
                server = data[1]
                channel = server["chatchannel"]
                channel_obj = guild.get_channel(channel)
                sname = server["name"]
                cname = server["cluster"]
                mapstring = f"{sname} {cname}"
                async with self.config.guild(guild).players() as stats:
                    if channel not in self.playerlist:
                        log.warning(f"Player_Stats: {sname} {cname} not found in playerlist!")
                        continue
                    if not self.playerlist[channel]:
                        continue
                    if self.playerlist[channel] == "offline":
                        continue
                    if self.playerlist[channel] == "empty":
                        continue
                    for player in self.playerlist[channel]:
                        xuid = player[1]
                        gamertag = player[0]
                        newplayermessage = ""
                        if xuid not in stats:  # New player found
                            if autowelcome:
                                prefixes = await self.bot.get_valid_prefixes(guild)
                                for p in prefixes:
                                    if str(p) != "":
                                        break
                                cmd = f"broadcast A new player has been detected on the server!\n" \
                                      f"Everyone say hi to {gamertag}!!!\n" \
                                      f"Be sure to type {p}help in global chat to see a list of help commands " \
                                      f"you can use\n" \
                                      f"If the kit command is enabled, you can use it to get your starter pack\n" \
                                      f"Enjoy your stay on {guild.name}!"
                                await self.executor(guild, server, cmd)
                                welc = f"```py\nA new player has been detected on the server!\n" \
                                       f"Everyone say hi to {gamertag}!!!\n```"
                                await channel_obj.send(welc)
                            newplayermessage += f"**{gamertag}** added to the database.\n"
                            stats[xuid] = {
                                "playtime": {"total": 0},
                                "username": gamertag,
                                "lastseen": {"time": current_time.isoformat(), "map": mapstring},
                                "ingame": {}
                            }
                            if "tokens" in server and (autowelcome or autofriend):
                                async with aiohttp.ClientSession() as session:
                                    host = server["gamertag"]
                                    tokens = server["tokens"]
                                    xbl_client, token = await self.auth_manager(
                                        session,
                                        cname,
                                        sname,
                                        tokens,
                                        ctx=None,
                                        guild=guild
                                    )
                                    if autowelcome and xbl_client:
                                        link = await channel_obj.create_invite(unique=False, reason="New Player")
                                        if settings["welcomemsg"]:
                                            params = {
                                                "discord": guild.name,
                                                "gamertag": gamertag,
                                                "link": link
                                            }
                                            welcome = settings["welcomemsg"]
                                            welcome = welcome.format(**params)
                                        else:
                                            welcome = f"Welcome to {guild.name}!\nThis is an automated message:\n" \
                                                      f"You appear to be a new player, " \
                                                      f"here is an invite to the Discord server:\n\n{link}"
                                        try:
                                            await xbl_client.message.send_message(str(xuid), welcome)
                                            newplayermessage += f"DM sent: ✅\n"
                                        except Exception as e:
                                            log.warning(f"{gamertag} Failed to DM New Player in guild {guild}: {e}")
                                            newplayermessage += f"DM sent: ❌ {e}\n"

                                    if autofriend and xbl_client:
                                        status = await add_friend(str(xuid), token)
                                        if 200 <= status <= 204:
                                            newplayermessage += f"Added by {host}: ✅\n"
                                        else:
                                            log.warning(f"{host} FAILED to add {gamertag} in guild {guild}")
                                            newplayermessage += f"Added by {host}: ❌\n"

                                    alt = settings["alt"]
                                    if alt["on"] and xbl_client:  # If alt detection is on
                                        try:
                                            profile = json.loads(
                                                (
                                                    await xbl_client.profile.get_profile_by_gamertag(gamertag)
                                                ).json()
                                            )
                                            friends = json.loads(
                                                (
                                                    await xbl_client.people.get_friends_summary_by_gamertag(gamertag)
                                                ).json()
                                            )
                                        except aiohttp.ClientResponseError:
                                            profile = None
                                            friends = None
                                        if profile and friends:
                                            sus, reasons = detect_sus(alt, profile, friends)
                                            if sus:
                                                yes = "✅"
                                                no = "❌"
                                                if alt["autoban"] and xuid not in alt["whitelist"]:
                                                    banned = yes
                                                    command = f"banplayer {xuid}"
                                                    bantasks = []
                                                    for tup in self.servers:
                                                        sguild = tup[0]
                                                        server = tup[1]
                                                        if sguild == guild.id:
                                                            bantasks.append(self.executor(guild, server, command))
                                                    log.info(f"Banning {gamertag} - {xuid} from all servers")
                                                    await asyncio.gather(*bantasks)
                                                else:
                                                    banned = no
                                                if alt["msgtoggle"] and alt["msg"]:
                                                    warning = yes
                                                    params = {"reasons": reasons}
                                                    msg = alt["msg"].format(**params)
                                                    await xbl_client.message.send_message(str(xuid), msg)
                                                else:
                                                    warning = no
                                                if eventlog:
                                                    embed = discord.Embed(
                                                        description=f"**Suspicious account detected!**\n"
                                                                    f"**{gamertag}** - `{xuid}`\n"
                                                                    f"`Auto-Banned:  `{banned}\n"
                                                                    f"`Sent Warning: `{warning}\n"
                                                                    f"**Reasons**\n"
                                                                    f"{box(reasons)}",
                                                        color=discord.Color.orange()
                                                    )
                                                    try:
                                                        await eventlog.send(embed=embed)
                                                    except discord.HTTPException:
                                                        log.warning("Sus account message failed.")
                                                        pass

                            if eventlog:
                                embed = discord.Embed(
                                    description=newplayermessage,
                                    color=discord.Color.green()
                                )
                                try:
                                    await eventlog.send(embed=embed)
                                except discord.HTTPException:
                                    log.warning("New Player Message Failed.")
                                    pass

                        last_seen = stats[xuid]["lastseen"]["map"]
                        if not last_seen:
                            if "tokens" in server and autofriend:
                                async with aiohttp.ClientSession() as session:
                                    host = server["gamertag"]
                                    tokens = server["tokens"]
                                    xbl_client, token = await self.auth_manager(
                                        session,
                                        cname,
                                        sname,
                                        tokens,
                                        ctx=None,
                                        guild=guild
                                    )
                                    if autofriend and xbl_client:
                                        status = await add_friend(str(xuid), token)
                                        if 200 <= status <= 204:
                                            newplayermessage += f"Added by {host}: ✅\n"
                                        else:
                                            newplayermessage += f"Added by {host}: ❌\n"
                        if str(channel) not in stats[xuid]["ingame"]:
                            stats[xuid]["ingame"][str(channel)] = {
                                "implant": None,
                                "name": None,
                                "previous_names": [],
                                "stats": {
                                    "pvpkills": 0,
                                    "pvpdeaths": 0,
                                    "pvedeaths": 0,
                                    "tamed": 0
                                }
                            }
                        if mapstring not in stats[xuid]["playtime"]:
                            stats[xuid]["playtime"][mapstring] = 0
                        else:
                            stats[xuid]["playtime"][mapstring] += timedifference
                            stats[xuid]["playtime"]["total"] += timedifference
                            stats[xuid]["lastseen"] = {
                                "time": current_time.isoformat(),
                                "map": mapstring
                            }
                            stats[xuid]["username"] = gamertag
                            # Rank system
                            ranks = settings["ranks"]
                            hours = int(stats[xuid]["playtime"]["total"] / 3600)
                            if str(hours) in ranks:
                                role = ranks[str(hours)]
                                role = guild.get_role(role)
                                if role:
                                    stats[xuid]["rank"] = role.id
                            if "rank" in stats[xuid] and "discord" in stats[xuid]:
                                user = stats[xuid]["discord"]
                                user = guild.get_member(user)
                                if user:
                                    rank = stats[xuid]["rank"]
                                    rank = guild.get_role(rank)
                                    if rank not in user.roles:
                                        try:
                                            await user.add_roles(rank)
                                        except Exception as e:
                                            log.warning(f"Failed to add rank role to user: {e}")
                                    if settings["autoremove"]:
                                        ranks = settings["ranks"]
                                        for role in ranks:
                                            role = ranks[role]
                                            role = guild.get_role(role)
                                            if role in user.roles:
                                                if role.id != rank.id:
                                                    try:
                                                        await user.remove_roles(role)
                                                    except Exception as e:
                                                        log.warning(f"Failed to remove rank role to user: {e}")
        self.time = current_time.isoformat()

    @player_stats.before_loop
    async def before_player_stats(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(7)
        log.info("Playerstats loop ready")

    # have the gamertags unfriend a member when they leave the server
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        settings = await self.config.guild(member.guild).all()
        tz = settings["timezone"]
        tz = pytz.timezone(tz)
        time = datetime.datetime.now(tz)
        autofriend = settings["autofriend"]
        if not autofriend:
            return
        eventlog = settings["eventlog"]
        tokendata = []
        for xuid, data in settings["players"].items():
            if "discord" in data:
                if int(member.id) == int(data["discord"]):
                    async with self.config.guild(member.guild).players() as stats:
                        stats[xuid]["leftdiscordon"] = time.isoformat()
                    for cname, cluster in settings["clusters"].items():
                        for sname, server in cluster["servers"].items():
                            if "tokens" in server:
                                tokendata.append((xuid, cname, sname, server["tokens"]))
        if len(tokendata) == 0:
            return
        async with aiohttp.ClientSession() as session:
            utasks = []
            for item in tokendata:
                xbl_client, token = await self.auth_manager(
                    session,
                    item[1],
                    item[2],
                    item[3],
                    ctx=None,
                    guild=member.guild
                )
                if token:
                    utasks.append(remove_friend(item[0], token))
            await asyncio.gather(*utasks)
            if eventlog:
                eventlog = member.guild.get_channel(eventlog)
                embed = discord.Embed(
                    description=f"**{member.display_name}** - `{member.id}` was unfriended by the host Gamertags "
                                f"for leaving the Discord.",
                    color=discord.Color.red()
                )
                await eventlog.send(embed=embed)

    # Unfriends players if they havent been seen on any server for the set amount of time
    @tasks.loop(hours=2)
    async def maintenance(self):
        cid = await self.config.clientid()
        if not cid:
            return
        for guild in self.activeguilds:
            guild = self.bot.get_guild(guild)
            settings = await self.config.guild(guild).all()
            autofriend = settings["autofriend"]
            if not autofriend:
                continue
            eventlog = settings["eventlog"]
            eventlog = guild.get_channel(eventlog)
            stats = settings["players"]
            unfriendtime = int(settings["unfriendafter"])
            # List of users who havent been detected on the servers in X amount of time
            expired = await expired_players(stats, unfriendtime)
            if len(expired) == 0:
                continue

            tokendata = []
            for cname, cluster in settings["clusters"].items():
                for sname, server in cluster["servers"].items():
                    if "tokens" in server:
                        tokendata.append((cname, sname, server["tokens"]))
            if len(tokendata) == 0:
                continue

            # Remove players from host Gamertags' friends list
            async with aiohttp.ClientSession() as session:
                for item in tokendata:
                    xbl_client, token = await self.auth_manager(
                        session,
                        item[0],
                        item[1],
                        item[2],
                        ctx=None,
                        guild=guild
                    )
                    if token:
                        host = f"{item[1].capitalize()} {item[0].upper()}"
                        # Adding expired players to unfriend queue
                        async with self.config.guild(guild).players() as playerstats:
                            for user in expired:
                                xuid = user[0]
                                playerstats[xuid]["lastseen"]["map"] = None
                                player = user[1]
                                status = await remove_friend(xuid, token)
                                if 200 <= status <= 204:
                                    # Set last seen to None
                                    msg = "This is an automated message:\n\n" \
                                          "You have been unfriended by this Gamertag.\n" \
                                          f"Reason: No activity in any server over the last {unfriendtime} days\n" \
                                          f"To play this map again simply friend the account and join session."
                                    await xbl_client.message.send_message(str(xuid), msg)
                                else:
                                    log.info(f"Failed to unfriend {player} - {xuid} by the host {host} "
                                             f"for exceeding {unfriendtime} days of inactivity.")

            if eventlog:
                for user in expired:
                    player = user[1]
                    xuid = user[0]
                    embed = discord.Embed(
                        description=f"**{player}** - `{xuid}` was unfriended by the "
                                    f"host Gamertags for exceeding {unfriendtime} days of inactivity.",
                        color=discord.Color.red()
                    )
                    await eventlog.send(embed=embed)

    @maintenance.before_loop
    async def before_maintenance(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)
        log.info("Maintenance loop ready")

    @tasks.loop(seconds=20)
    async def autofriend(self):
        cid = await self.config.clientid()
        if not cid:
            return
        for guild in self.activeguilds:
            guild = self.bot.get_guild(guild)
            settings = await self.config.guild(guild).all()
            autofriend = settings["autofriend"]
            if not autofriend:
                continue
            eventlog = settings["eventlog"]
            eventlog = guild.get_channel(eventlog)
            tokendata = []
            for cname, cluster in settings["clusters"].items():
                for sname, server in cluster["servers"].items():
                    if "tokens" in server:
                        tokendata.append((cname, sname, server["tokens"]))
            if len(tokendata) == 0:
                continue

            async with aiohttp.ClientSession() as session:
                for item in tokendata:
                    cname = item[0]
                    sname = item[1]
                    tokens = item[2]
                    await self.autofriend_session(session, guild, cname, sname, tokens, eventlog)

    async def autofriend_session(self, session, guild: discord.guild, cname, sname, tokens, eventlog):
        xbl_client, token = await self.auth_manager(
            session,
            cname,
            sname,
            tokens,
            ctx=None,
            guild=guild
        )
        if token:
            try:
                friends = json.loads((await xbl_client.people.get_friends_own()).json())
            except Exception as e:
                if "Too Many Requests" in str(e):
                    return
                elif "validation error" in str(e):
                    return
                else:
                    log.warning(f"Autofriend Session Error: {e}")
                    return
            friends = friends["people"]
            followers = await get_followers(token)
            if "people" not in followers:
                return
            followers = followers["people"]

            # Detecting friend requests
            people_to_add = await detect_friends(friends, followers)
            sname = sname.capitalize()
            cname = cname.upper()
            if len(people_to_add) > 0:
                for xuid, username in people_to_add:
                    status = await add_friend(xuid, token)
                    if 200 <= status <= 204 and eventlog:
                        embed = discord.Embed(
                            description=f"**{sname} {cname}** accepted **{username}**'s friend request.",
                            color=discord.Color.green()
                        )
                        if eventlog:
                            try:
                                await eventlog.send(embed=embed)
                            except discord.NotFound:
                                pass
                        welcome = f"Friend request accepted! " \
                                  f"{username}, you can now join session from this account's profile page"
                        await xbl_client.message.send_message(str(xuid), welcome)
                    else:
                        embed = discord.Embed(
                            description=f"**{sname} {cname}** failed to accept **{username}**'s friend request.",
                            color=discord.Color.red()
                        )
                        log.info(f"{sname} {cname} failed to accept {username}'s friend request.")
                        if eventlog:
                            try:
                                await eventlog.send(embed=embed)
                            except discord.NotFound:
                                pass

            # Detecting non-following players
            for person in friends:
                xuid = person["xuid"]
                username = person["gamertag"]
                following = person["is_following_caller"]
                added = person["added_date_time_utc"]
                added = fix_timestamp(str(added))
                tz = pytz.timezone("UTC")
                added = added.astimezone(tz)
                time = datetime.datetime.now(tz)
                timedifference = time - added
                if not following and timedifference.days > 0:
                    status = await remove_friend(xuid, token)
                    if 200 <= status <= 204:
                        ustatus = "successfully"
                        msg = f"Hi {username}, you have been unfollowed by this account for not following back.\n" \
                              "To play this map again simply add the account again and join session."
                        await xbl_client.message.send_message(str(xuid), msg)
                    else:
                        ustatus = "unsuccessfully"
                    if eventlog:
                        embed = discord.Embed(
                            description=f"**{username}** - `{xuid}` was {ustatus} removed by **{sname} {cname}**"
                                        f" for unfollowing.",
                            color=discord.Color.red()
                        )
                        await eventlog.send(embed=embed)

    @autofriend.before_loop
    async def before_autofriend(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)
        log.info("Autofriend loop ready")

    @tasks.loop(hours=5)
    async def graphdata_prune(self):
        for guild in self.activeguilds:
            guild = self.bot.get_guild(guild)
            if not guild:
                continue
            stats = {}
            data = await self.config.guild(guild).serverstats()
            exp = data["expiration"]
            curcounts = data["counts"]
            to_keep = exp * 1440
            stats["expiration"] = exp
            for item, dat in data.items():
                if item != "expiration":
                    if len(dat) > to_keep:
                        dat.reverse()
                        newdat = dat[:to_keep]
                        newdat.reverse()
                        stats[str(item)] = newdat
            if len(curcounts) > to_keep:
                await self.config.guild(guild).serverstats.set(stats)

    @graphdata_prune.before_loop
    async def before_graphdata_prune(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)
        log.info("Janitor ready")
