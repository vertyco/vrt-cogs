import discord
import datetime
import asyncio
import socket
import json
import re
import aiohttp
import pytz

from rcon import Client

from redbot.core.utils.chat_formatting import box, pagify
from redbot.core import commands, Config
from discord.ext import tasks

from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.authentication.models import OAuth2TokenResponse
from xbox.webapi.api.client import XboxLiveClient

from .menus import menu, DEFAULT_CONTROLS
from .calls import (serverchat,
                    add_friend,
                    remove_friend,
                    manual_rcon,
                    get_followers)
from .formatter import (tribelog_format,
                        profile_format,
                        expired_players,
                        lb_format,
                        cstats_format,
                        player_stats,
                        detect_friends,
                        fix_timestamp,
                        get_graph)

import logging

log = logging.getLogger("red.vrt.arktools")

LOADING = "https://i.imgur.com/l3p6EMX.gif"
LIVE = "https://i.imgur.com/LPzCcgU.gif"
FAILED = "https://i.imgur.com/TcnAyVO.png"
SUCCESS = "https://i.imgur.com/NrLAEpq.gif"

REDIRECT_URI = "http://localhost/auth/callback"

# Hard coded item blueprint paths for the imstuck command
IMSTUCK_BLUEPRINTS = [
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Resources/PrimalItemResource_Polymer_Organic.PrimalItemResource_Polymer_Organic'" 5 0 0""",
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItemAmmo_GrapplingHook.PrimalItemAmmo_GrapplingHook'" 1 0 0""",
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItem_WeaponCrossbow.PrimalItem_WeaponCrossbow'" 1 0 0""",
    f""""Blueprint'/Game/PrimalEarth/CoreBlueprints/Items/Structures/Thatch/PrimalItemStructure_ThatchFloor.PrimalItemStructure_ThatchFloor'" 1 0 0""",
    f""""Blueprint'/Game/Aberration/CoreBlueprints/Weapons/PrimalItem_WeaponClimbPick.PrimalItem_WeaponClimbPick'" 2 0 0"""
]


class ArkTools(commands.Cog):
    """
    RCON/API tools and cross-chat for Ark: Survival Evolved!
    """
    __author__ = "Vertyco"
    __version__ = "2.1.7"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117117117117, force_registration=True)
        default_guild = {
            "welcomemsg": None,
            "playerclearmessage": None,
            "status": {"channel": None, "message": None},
            "masterlog": None,
            "eventlog": None,
            "fullaccessrole": None,
            "autowelcome": False,
            "autofriend": False,
            "datalogs": False,
            "unfriendafter": 30,
            "clusters": {},
            "modroles": [],
            "modcommands": [],
            "badnames": [],
            "tribes": {},
            "players": {},
            "serverstats": {"dates": [], "counts": [], "expiration": 30},
            "timezone": "US/Eastern"
        }
        default_global = {
            "clientid": None,
            "secret": None
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        # Cache on cog load
        self.activeguilds = []
        self.servers = []
        self.channels = []
        self.servercount = 0
        self.playerlist = {}
        self.downtime = {}
        self.time = ""

        # Loops
        self.getchat.start()
        self.listplayers.start()
        self.status_channel.start()
        self.playerstats.start()
        self.maintenance.start()
        self.autofriend.start()

    def cog_unload(self):
        self.getchat.cancel()
        self.listplayers.cancel()
        self.status_channel.cancel()
        self.playerstats.cancel()
        self.maintenance.cancel()
        self.autofriend.cancel()

    # General authentication manager
    async def auth_manager(
            self,
            ctx: commands.Context,
            session: aiohttp.ClientSession,
            cname: str,
            sname: str,
            tokens: dict,
    ):
        client_id = await self.config.clientid()
        client_secret = await self.config.secret()
        if not client_id:
            await ctx.send(f"Client ID and Secret have not been set yet!\n"
                           f"Bot owner needs to run `{ctx.prefix}arktools api addtokens`")
            return None, None
        auth_mgr = AuthenticationManager(session, client_id, client_secret, REDIRECT_URI)
        try:
            auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        except Exception as e:
            if "validation error" in str(e):
                await ctx.send(f"Client ID and Secret have not been authorized yet!\n"
                               f"Bot owner needs to run `{ctx.prefix}apiset authorize`")
                return None, None
        await auth_mgr.refresh_tokens()
        async with self.config.guild(ctx.guild).clusters() as clusters:
            clusters[cname]["servers"][sname]["tokens"] = json.loads(auth_mgr.oauth.json())
        xbl_client = XboxLiveClient(auth_mgr)
        token = auth_mgr.xsts_token.authorization_header_value
        return xbl_client, token

    # Authentication handling for task loops, just same logic with no ctx yea prolly could have done it a cleaner way :p
    async def loop_auth_manager(
            self,
            guild: discord.guild,
            session: aiohttp.ClientSession,
            cname: str,
            sname: str,
            tokens: dict,
    ):
        client_id = await self.config.clientid()
        client_secret = await self.config.secret()
        if not client_id:
            return None, None
        auth_mgr = AuthenticationManager(session, client_id, client_secret, REDIRECT_URI)
        try:
            auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        except Exception as e:
            if "validation error" in str(e):
                return None, None
        await auth_mgr.refresh_tokens()
        async with self.config.guild(guild).clusters() as clusters:
            clusters[cname]["servers"][sname]["tokens"] = json.loads(auth_mgr.oauth.json())
        xbl_client = XboxLiveClient(auth_mgr)
        token = auth_mgr.xsts_token.authorization_header_value
        return xbl_client, token

    # Pull the first (authorized) token data found for non-specific api use
    @staticmethod
    def pull_key(clusters: dict):
        for cname, cluster in clusters.items():
            for sname, server in cluster["servers"].items():
                if "tokens" in server:
                    tokens = server["tokens"]
                    return tokens, cname, sname

    # Hard coded item send for those tough times
    @commands.command(name="imstuck")
    @commands.cooldown(1, 1800, commands.BucketType.user)
    async def im_stuck(self, ctx: commands.Context):
        """
        For those tough times when Ark is being Ark

        Sends you tools to get unstuck, or off yourself.
        """
        embed = discord.Embed(
            description=f"**Type your Implant ID in chat.**"
        )
        embed.set_footer(text="Hint: your implant id can be seen by hovering over it in your inventory!")
        embed.set_thumbnail(url="https://i.imgur.com/kfanq99.png")
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel
        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="Ok guess ya didn't need help then."))

        if reply.content.isdigit():
            implant_id = reply.content
            try:
                await reply.delete()
            except discord.NotFound:
                pass
            embed = discord.Embed(
                description=f"Sit tight, your care package is on the way!"
            )
            embed.set_thumbnail(url="https://i.imgur.com/8ofOx6X.png")
            await msg.edit(embed=embed)
            settings = await self.config.guild(ctx.guild).all()
            serverlist = []
            for cname, cdata in settings["clusters"].items():
                for sname, sdata in cdata["servers"].items():
                    serverlist.append(sdata)

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
    async def wipe_all_stats(self, ctx: commands.Context):
        """Wipe all player stats including last seen data and registration."""
        async with self.config.guild(ctx.guild).all() as data:
            data["players"].clear()
            await ctx.send(embed=discord.Embed(description="All player data has been wiped."))

    @commands.command(name="wipegraphdata")
    @commands.guildowner()
    async def wipe_graph_data(self, ctx: commands.Context):
        """Reset the player count graph data"""
        async with self.config.guild(ctx.guild).all() as settings:
            for sname, slist in settings["serverstats"].items():
                if sname != "expiration":
                    slist.clear()
            await ctx.tick()

    @commands.command(name="unregister")
    @commands.admin()
    async def unregister_user(self, ctx: commands.Context, member: discord.Member):
        """Unregister a user from a Gamertag"""
        async with self.config.guild(ctx.guild).players() as players:
            for data in players.values():
                if "discord" in data:
                    if data["discord"] == member.id:
                        del data["discord"]
                        return await ctx.send(f"{member.mention} has been unregistered!")
            else:
                await ctx.send(f"{member.mention} not found registered to any Gamertag!")

    @commands.command(name="register")
    @commands.guild_only()
    async def register_user(self, ctx: commands.Context):
        """Register your Gamertag or steam ID in the database."""
        timezone = await self.config.guild(ctx.guild).timezone()
        tz = pytz.timezone(timezone)
        time = datetime.datetime.now(tz)
        embed = discord.Embed(
            description=f"**Type your Xbox Gamertag or Steam ID in chat below.**"
        )
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        # Check if user entered ID instead of Gamertag and go that route instead
        if reply.content.isdigit():
            sid = reply.content
            async with self.config.guild(ctx.guild).players() as players:
                if sid not in players:
                    players[sid] = {}
                if "discord" in players[sid]:
                    if players[sid]["discord"] != ctx.author.id:
                        claimed = ctx.guild.get_member(players[sid]["discord"])
                        embed = discord.Embed(
                            description=f"{claimed.mention} has already claimed this Steam ID",
                            color=discord.Color.orange()
                        )
                        return await msg.edit(embed=embed)
                    if players[sid]["discord"] == ctx.author.id:
                        embed = discord.Embed(
                            description=f"You have already claimed this Steam ID",
                            color=discord.Color.green()
                        )
                        return await msg.edit(embed=embed)
                embed = discord.Embed(
                    description=f"**Type your Steam Username in chat below(Or Gamertag).**"
                )
                await msg.edit(embed=embed)
                try:
                    reply = await self.bot.wait_for("message", timeout=60, check=check)
                except asyncio.TimeoutError:
                    return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
                sname = reply.content
                players[sid] = {
                    "discord": ctx.author.id,
                    "username": sname,
                    "playtime": {"total": 0},
                    "lastseen": {
                        "time": time.isoformat(),
                        "map": None
                    }
                }
                players[sid]["discord"] = ctx.author.id
                players[sid]["username"] = sname
                embed = discord.Embed(
                    description=f"Your account has been registered as **{sname}**: `{sid}`"
                )
                return await msg.edit(embed=embed)

        # If user doesnt type ID then make sure there's at least one server with an active API before registering
        apipresent = False
        clusters = await self.config.guild(ctx.guild).clusters()
        for cluster in clusters.values():
            for server in cluster["servers"].values():
                if "tokens" in server:
                    apipresent = True
                    break
        if not apipresent:
            embed = discord.Embed(
                description="❌ API keys have not been set!."
            )
            embed.set_thumbnail(url=FAILED)
            return await ctx.send(embed=embed)

        gamertag = reply.content
        embed = discord.Embed(color=discord.Color.green(),
                              description=f"Searching...")
        embed.set_thumbnail(url=LOADING)
        await msg.edit(embed=embed)
        async with aiohttp.ClientSession() as session:
            tokens, cname, sname = self.pull_key(clusters)
            xbl_client, _ = await self.auth_manager(ctx, session, cname, sname, tokens)
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
                if xuid not in players:
                    players[xuid] = {}
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
                players[xuid] = {
                    "discord": ctx.author.id,
                    "username": gt,
                    "playtime": {"total": 0},
                    "lastseen": {
                        "time": time.isoformat(),
                        "map": None
                    }
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

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        if reply.content.lower() == "all":
            embed = discord.Embed(
                description="Gathering Data..."
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)

            # Iterate through server tokens and send off friend requests
            for cname, cluster in clusters.items():
                for sname, server in cluster["servers"].items():
                    if "tokens" in server:
                        tokendata = server["tokens"]
                        async with aiohttp.ClientSession() as session:
                            xbl_client, token = await self.auth_manager(ctx, session, cname, sname, tokendata)
                            if not xbl_client:
                                return
                            status = await add_friend(xuid, token)
                            if 200 <= status <= 204:
                                embed = discord.Embed(
                                    description=f"Friend request sent from... `{server['gamertag']}`",
                                    color=discord.Color.green()
                                )
                                embed.set_thumbnail(url=LOADING)
                            else:
                                embed = discord.Embed(
                                    description=f"Friend request from `{tokendata['gamertag']}` may have failed!",
                                    color=discord.Color.red()
                                )
                                embed.set_thumbnail(url=FAILED)
                            await msg.edit(embed=embed)
            embed = discord.Embed(color=discord.Color.green(),
                                  description=f"✅ Finished adding `{players[xuid]['username']}` for All Gamertags.\n"
                                              f"You should now be able to join from the Gamertags' profile page.")
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
                xbl_client, token = await self.auth_manager(ctx, session, cname, sname, tokendata)
                if not xbl_client:
                    return
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
                        description=f"Friend request from `{tokendata['gamertag']}` may have failed!",
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(url=FAILED)
                await msg.edit(embed=embed)
        else:
            color = discord.Color.dark_grey()
            return await msg.edit(embed=discord.Embed(description="Incorrect Reply, menu closed.", color=color))

    @commands.command(name="rcon")
    @commands.guild_only()
    async def manual_rcon(self, ctx: commands.Context, clustername: str, servername: str, *, command: str):
        """Perform an RCON command"""
        cname = clustername.lower()
        sname = servername.lower()
        settings = await self.config.guild(ctx.guild).all()
        if not settings["fullaccessrole"]:
            return await ctx.send("Full access role has not been set!")
        allowed = False
        for role in ctx.author.roles:
            if role.id == settings["fullaccessrole"]:
                allowed = True
            for modrole in settings["modroles"]:
                if role.id == modrole:
                    modcmds = settings["modcommands"]
                    for cmd in modcmds:
                        if str(cmd.lower()) in command.lower():
                            allowed = True
        if not allowed:
            if ctx.guild.owner != ctx.author:
                return await ctx.send("You do not have the required permissions to run that command.")

        clusters = settings["clusters"]
        if cname != "all" and cname not in clusters:
            return await ctx.send(f"{cname} cluster not found")
        if cname != "all" and sname != "all" and sname not in clusters[cname]["servers"]:
            return await ctx.send(f"Server not found in {cname} cluster")

        serverlist = []
        for tup in self.servers:
            server = tup[1]
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
        if len(serverlist) == 0:
            return await ctx.send("No servers have been found")

        if command.lower() == "doexit":  # Count down, save world, exit - for clean shutdown
            await ctx.send("Beginning reboot countdown...")
            for i in range(10, 0, -1):
                for server in serverlist:
                    mapchannel = ctx.guild.get_channel(server["chatchannel"])
                    await mapchannel.send(f"Reboot in {i}")
                    await self.executor(ctx.guild, server, f"serverchat Reboot in {i}")
                await asyncio.sleep(1)
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

        if "banplayer" in command.lower():
            player_id = str(re.search(r'(\d+)', command).group(1))
            unfriend = ""
            async with ctx.typing():
                async with aiohttp.ClientSession() as session:
                    for server in serverlist:
                        if "tokens" in server:
                            tokens = server["tokens"]
                            host = server["gamertag"]
                            xbl_client, token = await self.loop_auth_manager(
                                ctx.guild,
                                session,
                                server["cluster"],
                                server["name"],
                                tokens
                            )
                            if token:
                                status = await remove_friend(player_id, token)
                                if 200 <= status <= 204:
                                    unfriend += f"{host} Successfully unfriended XUID: {player_id}\n"
                                else:
                                    unfriend += f"{host} Failed to unfriend XUID: {player_id}\n"
                    if unfriend != "":
                        await ctx.send(box(unfriend, lang="python"))

    @commands.command(name="init", hidden=True)
    @commands.is_owner()
    async def init_config(self, ctx):
        await self.initialize()
        await ctx.tick()

    # STAT COMMANDS
    # Thanks to Vexed#3211 for help with the Matplotlib logic :)
    @commands.command(name="servergraph", hidden=False)
    async def graph_player_count(self, ctx: commands.Context, hours: int = None):
        """View a graph of player count over a set time"""
        if not hours:
            hours = 1
        settings = await self.config.guild(ctx.guild).all()
        file = await get_graph(settings, hours)
        if file:
            await ctx.send(file=file)
        else:
            await ctx.send("Not enough data, give it some time")

    # Get the top 10 players in the cluster, browse pages to see them all
    @commands.command(name="arklb")
    async def ark_leaderboard(self, ctx: commands.Context):
        """View leaderboard for time played"""
        stats = await self.config.guild(ctx.guild).players()
        tz = await self.config.guild(ctx.guild).timezone()
        pages = lb_format(stats, ctx.guild, tz)
        if len(pages) == 0:
            return await ctx.send("There are no stats available yet!")
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="clusterstats")
    async def cluster_stats(self, ctx: commands.Context):
        """View playtime data for all clusters"""
        stats = await self.config.guild(ctx.guild).players()
        pages = cstats_format(stats, ctx.guild)
        if len(pages) == 1:
            embed = pages[0]
            return await ctx.send(embed=embed)
        await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="playerstats")
    async def get_player_stats(self, ctx: commands.Context, *, gamertag: str = None):
        """View stats for yourself or another gamertag"""
        settings = await self.config.guild(ctx.guild).all()
        stats = settings["players"]
        tz = pytz.timezone(settings["timezone"])
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
        embed = player_stats(stats, tz, ctx.guild, gamertag)
        if not embed:
            return await ctx.send(embed=discord.Embed(description=f"No player data found for {gamertag}"))
        await ctx.send(embed=embed)

    @commands.command(name="findplayer")
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

    # Main group
    @commands.group(name="arktools")
    @commands.guild_only()
    async def arktools_main(self, ctx: commands.Context):
        """ArkTools base setting command."""
        pass

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
        try:
            embed = discord.Embed(
                title=f"Permission Settings",
                color=color,
                description=f"**Full Access Role:** {settings['fullaccessrole']}\n"
                            f"**Mod Roles:** {settings['modroles']}\n"
                            f"**Mod Commands:** {settings['modcommands']}\n"
                            f"**Blacklisted Names:** {settings['badnames']}"
            )
            return await ctx.send(embed=embed)
        except KeyError:
            await ctx.send(f"Setup permissions first.")

    @mod_permissions.command(name="fullaccess")
    async def set_fullaccessrole(self, ctx: commands.Context, role: discord.Role):
        """Set a role for full RCON access."""
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
        masterlog = ctx.guild.get_channel(masterlog).mention if not None else "Not Set"
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
    async def set_masterlog(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set global channel for all tribe logs."""
        await self.config.guild(ctx.guild).masterlog.set(channel.id)
        await ctx.send(f"Master tribe log channel has been set to {channel.mention}")

    @tribe_settings.command(name="assign")
    async def assign_tribe(self,
                           ctx: commands.Context,
                           tribe_id: str,
                           owner: discord.Member,
                           channel: discord.TextChannel):
        """Assign a tribe to an owner to be managed by ithem."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribe_id in tribes:
                return await ctx.send("Tribe ID already exists!")
            tribes[tribe_id] = {
                "owner": owner.id,
                "channel": channel.id,
                "allowed": []
            }
            await channel.set_permissions(owner, read_messages=True)
            await ctx.send(f"Tribe ID `{tribe_id}` has been assigned to {owner.mention} in {channel.mention}.")

    @tribe_settings.command(name="unassign")
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
                return await ctx.send(f"There are no tribes set for this server.")
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
                        authorized = "False"
                        gamertag = "N/A"
                        following = "N/A"
                        followers = "N/A"
                        if "tokens" in server:
                            tokens = server["tokens"]
                            xbl_client, token = await self.auth_manager(ctx, session, cname, sname, tokens)
                            if xbl_client:
                                authorized = "True"
                                friends = json.loads((await xbl_client.people.get_friends_summary_own()).json())
                                gamertag = server["gamertag"]
                                following = friends["target_following_count"]
                                followers = friends["target_follower_count"]
                        description += f"**{sname.capitalize()}**\n" \
                                       f"`Authorized: `{authorized}\n" \
                                       f"`Gamertag:   `{gamertag}\n" \
                                       f"`Followers:  `{followers}\n" \
                                       f"`Following:  `{following}\n\n"
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
    async def unfriend_time(self, ctx: commands.Context, days: int):
        """
        Set number of days of inactivity for the host Gamertags to unfriend a player.

        This keep xbox host Gamertag friends lists clean since the max you can have is 1000.
        """
        await self.config.guild(ctx.guild).unfriendafter.set(days)
        await ctx.send(f"Inactivity days till auto unfriend is {days} days.")

    @api_settings.command(name="welcomemsg")
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
                                  f"invalid placeholder `{{{e.args[0]}}}`. See `{ctx.prefix}arktools api setwelcome` "
                                  f"for a list of valid placeholders.")
        if len(welcome_message) > 256:
            return await ctx.send("Message exceeds 256 character length! Make a shorter welcome message.")
        await self.config.guild(ctx.guild).welcomemsg.set(welcome_message)
        await ctx.send(f"Welcome message set as:\n{to_send}")

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
            eventlog = ctx.guild.get_channel(settings["eventlog"]).mention
        if settings["status"]["channel"]:
            statuschannel = ctx.guild.get_channel(settings["status"]["channel"])
            try:
                statuschannel = statuschannel.mention
            except AttributeError:
                statuschannel = "`#deleted-channel`"
        embed = discord.Embed(
            description=f"`Server Status Channel: `{statuschannel}\n"
                        f"`Event Log: `{eventlog}\n"
                        f"`Timezone:  `{tz}",
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

            settings += f"`GlobalChat: `{ctx.guild.get_channel(cluster['globalchatchannel']).mention}\n" \
                        f"`AdminLog:   `{ctx.guild.get_channel(cluster['adminlogchannel']).mention}\n" \
                        f"`JoinLog:    `{ctx.guild.get_channel(cluster['joinchannel']).mention}\n" \
                        f"`LeaveLog:   `{ctx.guild.get_channel(cluster['leavechannel']).mention}\n\n"

            for server in cluster["servers"]:
                name = server
                server = cluster["servers"][server]
                channel = ctx.guild.get_channel(server['chatchannel'])
                settings += f"{channel.mention}\n" \
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
            tzlist += f"{tz}\n"

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
        """Add a cluster with specified log channels."""
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

    @server_settings.command(name="delcluster")
    async def del_cluster(self, ctx: commands.Context, clustername: str):
        """Delete a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters.keys():
                await ctx.send("Cluster name not found")
            else:
                del clusters[clustername]
                await ctx.send(f"**{clustername}** cluster has been deleted")

    @server_settings.command(name="addserver")
    async def add_server(self, ctx: commands.Context,
                         clustername: str,
                         servername: str,
                         ip: str,
                         port: int,
                         password: str,
                         channel: discord.TextChannel):
        """Add a server to a cluster."""
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
                    "chatchannel": channel.id
                }
                await ctx.send(f"The **{servername}** server has been added to the **{clustername}** cluster!")

    @server_settings.command(name="delserver")
    async def del_server(self, ctx: commands.Context, clustername: str, servername: str):
        """Remove a server from a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters:
                return await ctx.send(f"{clustername} cluster not found.")
            if servername not in clusters[clustername]["servers"]:
                return await ctx.send(f"{servername} server not found.")
            del clusters[clustername]["servers"][servername]
            await ctx.send(f"**{servername}** server has been removed from **{clustername}**")

    @server_settings.command(name="statuschannel")
    async def set_statuschannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """
        Set a channel for the server status monitor.


        Server status embed will be created and updated every 60 seconds.
        """
        await self.config.guild(ctx.guild).status.channel.set(channel.id)
        await ctx.send(f"Status channel has been set to {channel.mention}")

    @server_settings.command(name="interchat")
    async def server_to_server_toggle(self, ctx: commands.Context, clustername: str):
        """(Toggle) server to server chat for a cluster so maps can talk to eachother."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername.lower() not in clusters:
                return await ctx.send(f"{clustername} cluster does not exist!")
            if clusters[clustername]["servertoserver"] is False:
                clusters[clustername]["servertoserver"] = True
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Enabled**.")
            if clusters[clustername]["servertoserver"] is True:
                clusters[clustername]["servertoserver"] = False
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Disabled**.")

    # Cache server data
    async def initialize(self):
        self.servercount = 0
        self.servers = []
        self.channels = []
        self.playerlist = {}
        config = await self.config.all_guilds()
        for guild_id in config:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            clusters = await self.config.guild(guild).clusters()
            if clusters == {}:
                continue
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
                    self.servers.append((guild.id, server))
                    self.servercount += 1
                    self.channels.append(server["chatchannel"])
                    self.playerlist[server["chatchannel"]] = None

            # Rehash player stats for ArkTools version < 2.0.0 config conversion
            rehashed_stats = {}
            stats = await self.config.guild(guild).players()
            for key, value in stats.items():
                if key.isdigit():
                    rehashed_stats[key] = value
                else:
                    log.info(f"Fixing config for {key}")
                    xuid = value["xuid"]
                    last_seen = value["lastseen"]
                    if last_seen["map"] == "None":
                        last_seen["map"] = None
                    rehashed_stats[xuid] = {
                        "playtime": value["playtime"],
                        "lastseen": last_seen,
                        "username": key
                    }
                    if "discord" in value:
                        rehashed_stats[xuid]["discord"] = value["discord"]
            log.info(f"Rehashed config for {len(stats.keys())} players")
            await self.config.guild(guild).players.set(rehashed_stats)

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
        rtasks = []
        if message.channel.id in clusterchannels:
            for server in allservers:
                rtasks.append(serverchat(server, message))
            await asyncio.gather(*rtasks)
        elif int(message.channel.id) == int(chatchannel):
            await serverchat(servermap, message)
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
    @tasks.loop(seconds=3)
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
        if command == "getchat" or "serverchat" in command:
            timeout = 1
        elif command == "listplayers":
            timeout = 10
        else:
            timeout = 3

        def exe():
            try:
                with Client(
                        host=server['ip'],
                        port=server['port'],
                        passwd=server['password'],
                        timeout=timeout
                ) as client:
                    result = client.run(command)
                    return result
            except socket.timeout:
                pass
            except Exception as e:
                log.warning(f"Executor Error: {e}")
                pass

        res = await self.bot.loop.run_in_executor(None, exe)
        if command == "getchat":
            if res and "Server received, But no response!!" not in res:
                await self.message_handler(guild, server, res)
        if command == "listplayers":
            if res:  # If server is online create list of player tuples
                if "No Players Connected" in res:
                    await self.player_join_leave(guild, server, [])
                else:
                    regex = r"(?:[0-9]+\. )(.+), ([0-9]+)"
                    res = re.findall(regex, res)
                    await self.player_join_leave(guild, server, res)
            else:  # If server is offline return None
                await self.player_join_leave(guild, server, None)

    @getchat.before_loop
    async def before_getchat(self):
        await self.bot.wait_until_red_ready()
        await self.initialize()
        await asyncio.sleep(5)
        log.info("Chat loop ready.")

    @listplayers.before_loop
    async def before_listplayers(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(5)
        log.info("Listplayers loop ready")

    # Detect player joins/leaves and log to respective channels
    async def player_join_leave(self, guild: discord.guild, server: dict, newplayerlist: list = None):
        channel = server["chatchannel"]
        joinlog = guild.get_channel(server["joinchannel"])
        leavelog = guild.get_channel(server["leavechannel"])
        mapname = server["name"].capitalize()
        clustername = server["cluster"].upper()

        lastplayerlist = self.playerlist[channel]

        if newplayerlist is None and lastplayerlist is None:
            return

        elif newplayerlist is None and lastplayerlist:
            for player in lastplayerlist:
                await leavelog.send(f":red_circle: `{player[0]}, {player[1]}` left {mapname} {clustername}")
            self.playerlist[channel] = None

        # Cog was probably reloaded so dont bother spamming join log with all current members
        elif len(newplayerlist) >= 0 and lastplayerlist is None:
            self.playerlist[channel] = newplayerlist

        elif len(newplayerlist) == 0 and len(lastplayerlist) == 0:
            return

        else:
            for player in newplayerlist:
                if player not in lastplayerlist:
                    await joinlog.send(f":green_circle: `{player[0]}, {player[1]}` joined {mapname} {clustername}")
            for player in lastplayerlist:
                if player not in newplayerlist:
                    await leavelog.send(f":red_circle: `{player[0]}, {player[1]}` left {mapname} {clustername}")
            self.playerlist[channel] = newplayerlist

    # Sends messages from in-game chat to their designated channels
    async def message_handler(self, guild: discord.guild, server: dict, res: str):
        adminlog = guild.get_channel(server["adminlogchannel"])
        globalchat = guild.get_channel(server["globalchatchannel"])
        chatchannel = guild.get_channel(server["chatchannel"])
        msgs = res.split("\n")
        messages = []
        settings = await self.config.guild(guild).all()
        badnames = settings["badnames"]
        for msg in msgs:
            if msg.startswith("AdminCmd:"):  # Send off to admin log channel
                adminmsg = msg
                await adminlog.send(f"**{server['name'].capitalize()}**\n{box(adminmsg, lang='python')}")
            elif "Tribe" and ", ID" in msg:  # send off to tribe log channel
                tribe_id, embed = await tribelog_format(server, msg)
                if "masterlog" in settings:
                    masterlog = guild.get_channel(settings["masterlog"])
                    await masterlog.send(embed=embed)
                if "tribes" in settings:
                    for tribes in settings["tribes"]:
                        if tribe_id == tribes:
                            tribechannel = guild.get_channel(settings["tribes"][tribes]["channel"])
                            await tribechannel.send(embed=embed)
            # Check if message is looped
            elif msg.startswith('SERVER:'):
                continue
            # Check for any other message that might not conform
            elif ":" not in msg:
                continue
            else:
                messages.append(msg)
                # Check if any character has a blacklisted name and rename the character to their Gamertag if so
                for badname in badnames:
                    if f"({badname.lower()}): " in msg.lower():
                        reg = r"(.+)\s\("
                        regname = re.findall(reg, msg)
                        gt = regname[0]
                        await self.executor(guild, server, f'renameplayer "{badname}" {gt}')
                        await chatchannel.send(f"A player named `{badname}` has been renamed to `{gt}`.")
                        break
        for msg in messages:
            if msg == ' ':
                continue
            elif msg == '':
                continue
            elif msg is None:
                continue
            else:
                # Sends Discord invite to in-game chat if the word Discord is mentioned
                if "discord" in msg.lower() or "discordia" in msg.lower():
                    try:
                        link = await chatchannel.create_invite(unique=False, max_age=3600, reason="Ark Auto Response")
                        await self.executor(guild, server, f"serverchat {link}")
                    except Exception as e:
                        log.exception(f"INVITE CREATION FAILED: {e}")

                await chatchannel.send(msg)
                await globalchat.send(f"{chatchannel.mention}: {msg}")
                clustername = server["cluster"]
                # If interchat is enabled, relay message to other servers
                if settings["clusters"][clustername]["servertoserver"] is True:  # maps can talk to each other if true
                    for data in self.servers:
                        s = data[1]
                        if s["cluster"] == server["cluster"] and s["name"] != server["name"]:
                            await self.executor(guild, s, f"serverchat {server['name'].capitalize()}: {msg}")

    @tasks.loop(seconds=60)
    async def status_channel(self):
        for guild in self.activeguilds:
            guild = self.bot.get_guild(guild)
            settings = await self.config.guild(guild).all()
            thumbnail = LIVE
            status = ""
            totalplayers = 0
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
                    if playerlist is None:
                        thumbnail = FAILED
                        inc = "Minutes."
                        if count >= 60:
                            count = count / 60
                            inc = "Hours."
                            count = int(count)
                        status += f"{guild.get_channel(channel).mention}: Offline for {count} {inc}\n"
                        if self.downtime[channel] == 5:
                            mentions = discord.AllowedMentions(roles=True)
                            pingrole = guild.get_role(settings["fullaccessrole"])
                            alertchannel = guild.get_channel(clustersettngs["adminlogchannel"])
                            await alertchannel.send(
                                f"{pingrole.mention}\n"
                                f"The **{sname} {cname}** server has been offline for 5 minutes now!",
                                allowed_mentions=mentions
                            )
                        self.downtime[channel] += 1
                        continue

                    elif len(playerlist) == 0:
                        status += f"{guild.get_channel(channel).mention}: 0 Players\n"
                        self.downtime[channel] = 0
                        continue

                    else:
                        playercount = len(playerlist)
                        clustertotal += playercount
                        totalplayers += playercount

                    if playercount == 1:
                        status += f"{guild.get_channel(channel).mention}: {playercount} player\n"
                    else:
                        status += f"{guild.get_channel(channel).mention}: {playercount} players\n"

                if clustertotal == 1:
                    status += f"`{clustertotal}` player in the cluster\n\n"
                else:
                    status += f"`{clustertotal}` players in the cluster\n\n"

                # Log player counts per cluster
                async with self.config.guild(guild).serverstats() as serverstats:
                    if cname not in serverstats:
                        serverstats[cname] = []
                    serverstats[cname].append(int(clustertotal))

            message = settings["status"]["message"]
            channel = settings["status"]["channel"]
            if not channel:
                continue

            # Log total player counts
            tz = pytz.timezone(settings["timezone"])  # idk if it matters since timestamps use client time
            time = datetime.datetime.now(tz)
            async with self.config.guild(guild).serverstats() as serverstats:
                # times = time.strftime('%I:%M %p')
                serverstats["dates"].append(time.isoformat())
                serverstats["counts"].append(int(totalplayers))

            # Embed setup
            file = await get_graph(settings, 1)
            embed = discord.Embed(
                description=status,
                color=discord.Color.random(),
                timestamp=time
            )
            embed.set_author(name="Server Status", icon_url=guild.icon_url)
            embed.add_field(name="Total Players", value=f"`{totalplayers}`")
            embed.set_thumbnail(url=thumbnail)
            embed.set_image(url=f"attachment://plot.png")

            dest_channel = guild.get_channel(channel)
            msgtoedit = None

            if message:
                try:
                    msgtoedit = await dest_channel.fetch_message(message)
                except discord.NotFound:
                    log.info(f"Status message not found. Creating new message.")

            if not msgtoedit:
                if file:
                    message = await dest_channel.send(embed=embed, file=file)
                else:
                    message = await dest_channel.send(embed=embed)
                await self.config.guild(guild).status.message.set(message.id)
            if msgtoedit:
                try:
                    if file:
                        await msgtoedit.delete()
                        message = await dest_channel.send(embed=embed, file=file)
                    else:
                        await msgtoedit.delete()
                        message = await dest_channel.send(embed=embed)
                    await self.config.guild(guild).status.message.set(message.id)
                except discord.Forbidden:  # Probably imported config from another bot and cant edit the message
                    if file:
                        message = await dest_channel.send(embed=embed, file=file)
                    else:
                        message = await dest_channel.send(embed=embed, file=file)
                    await self.config.guild(guild).status.message.set(message.id)

    @status_channel.before_loop
    async def before_status_channel(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(10)
        log.info("Status Channel loop ready")

    # Player stat handler
    @tasks.loop(minutes=2)
    async def playerstats(self):
        for data in self.servers:
            guild = data[0]
            server = data[1]
            guild = self.bot.get_guild(guild)

            settings = await self.config.guild(guild).all()
            autofriend = settings["autofriend"]
            autowelcome = settings["autowelcome"]
            channel = server["chatchannel"]
            channel_obj = guild.get_channel(channel)
            eventlog = settings["eventlog"]
            if eventlog:
                eventlog = guild.get_channel(eventlog)

            tz = pytz.timezone(settings["timezone"])
            time = datetime.datetime.now(tz)
            if self.time == "":
                self.time = time.isoformat()
            last = datetime.datetime.fromisoformat(str(self.time))
            timedifference = time - last
            timedifference = timedifference.seconds

            sname = server["name"]
            cname = server["cluster"]
            mapstring = f"{sname} {cname}"
            async with self.config.guild(guild).players() as stats:
                if channel not in self.playerlist:
                    continue
                if not self.playerlist[channel]:
                    continue
                for player in self.playerlist[channel]:
                    xuid = player[1]
                    gamertag = player[0]
                    # New player found
                    newplayermessage = ""
                    if xuid not in stats:
                        newplayermessage += f"**{gamertag}** added to the database.\n"
                        log.info(f"New Player - {gamertag}")
                        stats[xuid] = {
                            "playtime": {"total": 0},
                            "username": gamertag,
                            "lastseen": {"time": time.isoformat(), "map": mapstring}
                        }
                        if "tokens" in server and (autowelcome or autofriend):
                            async with aiohttp.ClientSession() as session:
                                host = server["gamertag"]
                                tokens = server["tokens"]
                                xbl_client, token = await self.loop_auth_manager(
                                    guild,
                                    session,
                                    cname,
                                    sname,
                                    tokens
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
                                        log.info("New Player DM Successful")
                                        newplayermessage += f"DM sent: ✅\n"
                                    except Exception as e:
                                        log.warning(f"New Player DM FAILED: {e}")
                                        newplayermessage += f"DM sent: ❌\n"

                                if autofriend and xbl_client:
                                    status = await add_friend(str(xuid), token)
                                    if 200 <= status <= 204:
                                        log.info(f"{host} Successfully added {gamertag}")
                                        newplayermessage += f"Added by {host}: ✅\n"
                                    else:
                                        log.warning(f"{host} FAILED to add {gamertag}")
                                        newplayermessage += f"Added by {host}: ❌\n"

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
                                xbl_client, token = await self.loop_auth_manager(
                                    guild,
                                    session,
                                    cname,
                                    sname,
                                    tokens
                                )
                                if autofriend and xbl_client:
                                    status = await add_friend(str(xuid), token)
                                    if 200 <= status <= 204:
                                        log.info(f"{host} Successfully added {gamertag}")
                                        newplayermessage += f"Added by {host}: ✅\n"
                                    else:
                                        log.warning(f"{host} FAILED to add {gamertag}")
                                        newplayermessage += f"Added by {host}: ❌\n"

                    if mapstring not in stats[xuid]["playtime"]:
                        stats[xuid]["playtime"][mapstring] = 0

                    else:
                        stats[xuid]["playtime"][mapstring] += int(timedifference)
                        stats[xuid]["playtime"]["total"] += int(timedifference)
                        stats[xuid]["lastseen"] = {
                            "time": time.isoformat(),
                            "map": mapstring
                        }
            self.time = time.isoformat()

    @playerstats.before_loop
    async def before_playerstats(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(7)
        log.info("Playerstats loop ready")

    # have the gamertags unfriend a member when they leave the server
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not member:
            return
        settings = await self.config.guild(member.guild).all()
        autofriend = settings["autofriend"]
        if not autofriend:
            return
        eventlog = settings["eventlog"]
        tokendata = []
        for xuid, data in settings["players"].items():
            if "discord" in data:
                if str(member.id) == data["discord"]:
                    for cname, cluster in settings["clusters"].items():
                        for sname, server in cluster.items():
                            if "tokens" in server:
                                tokendata.append((xuid, cname, sname, server["tokens"]))
        if len(tokendata) == 0:
            return
        async with aiohttp.ClientSession() as session:
            utasks = []
            for item in tokendata:
                xbl_client, token = await self.loop_auth_manager(
                    member.guild,
                    session,
                    item[1],
                    item[2],
                    item[3]
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
            tz = pytz.timezone(settings["timezone"])
            time = datetime.datetime.now(tz)

            # List of users who havent been detected on the servers in X amount of time
            expired = await expired_players(stats, time, unfriendtime, tz)
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
                    xbl_client, token = await self.loop_auth_manager(
                        guild,
                        session,
                        item[0],
                        item[1],
                        item[2]
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
                                    ustatus = "Successfuly"
                                    # Set last seen to None
                                    msg = "AUTOMATED MESSAGE\n\nYou have been unfriended by this Gamertag.\n" \
                                          f"Reason: No activity in any server over the last {unfriendtime} days\n" \
                                          f"To play this map again simply friend the account and join session."
                                    await xbl_client.message.send_message(str(xuid), msg)
                                else:
                                    ustatus = "Unsuccessfuly"
                                log.info(f"{player} - {xuid} was {ustatus} unfriended by the host {host} "
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

    @tasks.loop(seconds=15)
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
            atasks = []
            async with aiohttp.ClientSession() as session:
                for item in tokendata:
                    cname = item[0]
                    sname = item[1]
                    tokens = item[2]
                    atasks.append(self.autofriend_session(session, guild, cname, sname, tokens, eventlog))
                await asyncio.gather(*atasks)

    async def autofriend_session(self, session, guild: discord.guild, cname, sname, tokens, eventlog):
        xbl_client, token = await self.loop_auth_manager(
            guild,
            session,
            cname,
            sname,
            tokens
        )
        if token:
            friends = json.loads((await xbl_client.people.get_friends_own()).json())
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
                        log.info(f"{sname} {cname} accepted {username}'s friend request.")
                        if eventlog:
                            await eventlog.send(embed=embed)
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
                            await eventlog.send(embed=embed)

            # Detecting non-following players
            for person in friends:
                xuid = person["xuid"]
                username = person["gamertag"]
                following = person["is_following_caller"]
                added = person["added_date_time_utc"]
                added = fix_timestamp(str(added))
                tz = pytz.timezone("UTC")
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
                    log.info(f"{username} - {xuid} was {ustatus} removed by {sname} {cname} "
                             f"for unfollowing.")
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
