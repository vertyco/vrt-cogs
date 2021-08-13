from redbot.core.utils.chat_formatting import box, pagify
from redbot.core import commands, Config
from discord.ext import tasks
from rcon import Client
import rcon
import discord
import datetime
import pytz
import unicodedata
import asyncio
import os
import json
import re


class ArkTools(commands.Cog):
    """
    RCON tools and cross-chat for Ark: Survival Evolved!
    """
    __author__ = "Vertyco"
    __version__ = "1.3.26"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        default_guild = {
            "statuschannel": None,
            "statusmessage": None,
            "masterlog": None,
            "servertoserverchat": False,
            "tribes": {},
            "clusters": {},
            "servers": {},
            "servername": {},
            "ip": {},
            "port": {},
            "password": {},
            "chatchannel": {},
            "modroles": [],
            "modcommands": [],
            "badnames": [],
            "fullaccessrole": None,
            "tribelogchannels": {},
            "apikeys": {},
            "crosschattoggle": False,
            "joinchannel": {},
            "leavechannel": {},
            "adminlogchannel": {},
            "globalchatchannel": {}
        }
        self.config.register_guild(**default_guild)

        # Cache on cog load
        self.servercount = 0
        self.taskdata = []
        self.alerts = {}
        self.playerlist = {}

        # Loops
        self.chat_executor.start()
        self.playerlist_executor.start()
        self.status_channel.start()

    def cog_unload(self):
        self.chat_executor.cancel()
        self.playerlist_executor.cancel()
        self.status_channel.cancel()

    # GROUPS
    @commands.group(name="arktools")
    async def _setarktools(self, ctx: commands.Context):
        """Ark Tools base command."""
        pass

    @_setarktools.group(name="permissions")
    @commands.guildowner()
    async def _permissions(self, ctx: commands.Context):
        """Permission specific role settings for rcon commands."""
        pass

    @_setarktools.group(name="server")
    @commands.guildowner()
    async def _serversettings(self, ctx: commands.Context):
        """Server setup."""
        pass

    @_setarktools.group(name="tribe")
    async def _tribesettings(self, ctx: commands.Context):
        """Tribe commands."""
        pass

    # PERMISSIONS COMMANDS
    @_permissions.command(name="setfullaccessrole")
    async def _setfullaccessrole(self, ctx: commands.Context, role: discord.Role):
        """Set a full RCON access role."""
        await self.config.guild(ctx.guild).fullaccessrole.set(role.id)
        await ctx.send(f"Full rcon access role has been set to {role}")

    @_permissions.command(name="addmodrole")
    async def _addmodrole(self, ctx: commands.Context, *, role: discord.Role):
        """Add a role to allow limited command access for."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                await ctx.send("That role already exists.")
            else:
                modroles.append(role.id)
                await ctx.send(f"The **{role}** role has been added.")

    @_permissions.command(name="delmodrole")
    async def _delmodrole(self, ctx: commands.Context, role: discord.Role):
        """Delete a mod role."""
        async with self.config.guild(ctx.guild).modroles() as modroles:
            if role.id in modroles:
                modroles.remove(role.id)
                await ctx.send(f"{role} role has been removed.")
            else:
                await ctx.send("That role isn't in the list.")

    @_permissions.command(name="addbadname")
    async def _addbadname(self, ctx: commands.Context, *, badname: str):
        """Blacklisted a player name."""
        async with self.config.guild(ctx.guild).badnames() as badnames:
            if badname in badnames:
                await ctx.send("That name already exists.")
            else:
                badnames.append(badname)
                await ctx.send(f"**{badname}** has been added to the blacklist.")

    @_permissions.command(name="delbadname")
    async def _delbadname(self, ctx: commands.Context, badname: str):
        """Delete a blacklisted name."""
        async with self.config.guild(ctx.guild).badnames() as badnames:
            if badname in badnames:
                badnames.remove(badname)
                await ctx.send(f"{badname} has been removed from the blacklist.")
            else:
                await ctx.send("That name doesnt exist")

    @_permissions.command(name="addmodcommand")
    async def _addmodcommand(self, ctx: commands.Context, *, modcommand: str):
        """Add allowable commands for the mods to use."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                await ctx.send("That command already exists!")
            else:
                modcommands.append(modcommand)
                await ctx.send(f"The command **{modcommand}** has been added to the list.")

    @_permissions.command(name="delmodcommand")
    async def _delmodcommand(self, ctx: commands.Context, modcommand: str):
        """Delete an allowed mod command."""
        async with self.config.guild(ctx.guild).modcommands() as modcommands:
            if modcommand in modcommands:
                modcommands.remove(modcommand)
                await ctx.send(f"The {modcommand} command has been removed.")
            else:
                await ctx.send("That command doesnt exist")

    # SERVER SETTINGS COMMANDS
    @_serversettings.command(name="addcluster")
    async def _addcluster(self, ctx: commands.Context,
                          clustername: str,
                          joinchannel: discord.TextChannel,
                          leavechannel: discord.TextChannel,
                          adminlogchannel: discord.TextChannel,
                          globalchatchannel: discord.TextChannel):
        """Add a cluster with specified log channels."""
        """Include desired join, leave, admin log, and global chat channel."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                await ctx.send("Cluster already exists")
            else:
                clusters[clustername.lower()] = {
                    "joinchannel": joinchannel.id,
                    "leavechannel": leavechannel.id,
                    "adminlogchannel": adminlogchannel.id,
                    "globalchatchannel": globalchatchannel.id,
                    "servertoserver": False,
                    "servers": {}
                }
                await ctx.send(f"**{clustername}** has been added to the list of clusters.")

    @_serversettings.command(name="delcluster")
    async def _delcluster(self, ctx: commands.Context, clustername: str):
        """Delete a cluster."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername not in clusters.keys():
                await ctx.send("Cluster name not found")
            else:
                del clusters[clustername]
                await ctx.send(f"{clustername} cluster has been deleted")

    @_serversettings.command(name="addserver")
    async def _addserver(self, ctx: commands.Context, clustername: str, servername: str, ip: str,
                         port: int, password: str, channel: discord.TextChannel):
        """Add a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if clustername in clusters.keys():
                if servername in clusters[clustername]["servers"].keys():
                    await ctx.send(f"The **{servername}** server was **overwritten** in the **{clustername}** cluster!")
                if servername not in clusters[clustername]["servers"].keys():
                    await ctx.send(f"The **{servername}** server has been added to the **{clustername}** cluster!")
            clusters[clustername]["servers"][servername] = {
                "name": servername.lower(),
                "ip": ip,
                "port": port,
                "password": password,
                "chatchannel": channel.id
            }
            await self.initialize()
            if clustername not in clusters.keys():
                await ctx.send(f"The cluster {clustername} does not exist!")

    @_serversettings.command(name="delserver")
    async def _delserver(self, ctx: commands.Context, clustername: str, servername: str):
        """Remove a server."""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            server = clusters[clustername]["servers"]
            if servername in server.keys():
                del clusters[clustername]["servers"][servername]
                await ctx.send(f"{servername} server has been removed from {clustername}")
                await self.initialize()
            else:
                await ctx.send(f"{servername} server not found.")

    @_serversettings.command(name="setstatuschannel")
    async def _setstatuschannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set a channel for a server status embed."""
        """This embed will be created if not exists, and updated every 60 seconds."""
        await self.config.guild(ctx.guild).statuschannel.set(channel.id)
        await ctx.send(f"Status channel has been set to {channel.mention}")

    @_serversettings.command(name="toggle")
    async def _servertoservertoggle(self, ctx: commands.Context, clustername):
        """Toggle server to server chat so maps can talk to eachother"""
        async with self.config.guild(ctx.guild).clusters() as clusters:
            if "servertoserver" not in clusters[clustername].keys():
                clusters[clustername]["servertoserver"] = False
                return await ctx.send(
                    f"Server to server chat for {clustername.upper()} has been initialized as **Disabled**.")
            if clusters[clustername]["servertoserver"] is False:
                clusters[clustername]["servertoserver"] = True
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Enabled**.")
            if clusters[clustername]["servertoserver"] is True:
                clusters[clustername]["servertoserver"] = False
                return await ctx.send(f"Server to server chat for {clustername.upper()} has been **Disabled**.")

    # TRIBE COMMANDS
    @_tribesettings.command(name="setmasterlog")
    async def _setmasterlog(self, ctx, channel: discord.TextChannel):
        """Set global channel for all unassigned tribe logs."""
        await self.config.guild(ctx.guild).masterlog.set(channel.id)
        await ctx.send(f"Master tribe log channel has been set to {channel.mention}")

    @_tribesettings.command(name="addtribe")
    async def _addtribe(self, ctx, tribe_id, owner: discord.Member, channel: discord.TextChannel):
        """Add a tribe to be managed by it's owner."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribe_id in tribes.keys():
                await ctx.send("Tribe ID already exists!")
            else:
                tribes[tribe_id] = {
                    "owner": owner.id,
                    "channel": channel.id,
                    "allowed": []
                }
                await channel.set_permissions(owner, read_messages=True)
                await ctx.send(f"Tribe ID `{tribe_id}` has been set for {owner.mention} in {channel.mention}.")

    @_tribesettings.command(name="deltribe")
    async def _deltribe(self, ctx, tribe_id):
        """Delete a tribe."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribe_id in tribes.keys():
                await ctx.send(f"Tribe with ID: {tribe_id} has been deleted")
                del tribes[tribe_id]
            else:
                await ctx.send("Tribe ID doesn't exist!")

    @_tribesettings.command(name="mytribe")
    async def _viewtribe(self, ctx):
        """View your tribe(if you've been granted ownership of one"""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes != {}:
                for tribe in tribes:
                    if ctx.author.id == tribes[tribe]["owner"] or ctx.author.id in tribes[tribe]["allowed"]:
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
                    else:
                        await ctx.send("You don't have access any tribes.")
                    await ctx.send(embed=embed)
            else:
                await ctx.send(f"There are no tribes set for this server.")

    @_tribesettings.command(name="add")
    async def _addmember(self, ctx, member: discord.Member):
        """Add a member to your tribe logs."""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes:
                for tribe in tribes:
                    if ctx.author.id == tribes[tribe]["owner"]:
                        tribes[tribe]["allowed"].append(member.id)
                        channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                        await channel.set_permissions(member, read_messages=True)
                        await ctx.send(f"{member.mention} has been added to the tribe logs")
                    else:
                        await ctx.send(f"You arent set as owner of any tribes to add people on.")
            else:
                await ctx.send("No tribe data available")

    @_tribesettings.command(name="remove")
    async def _removemember(self, ctx, member: discord.Member):
        """Remove a member from your tribe logs"""
        async with self.config.guild(ctx.guild).tribes() as tribes:
            if tribes:
                for tribe in tribes:
                    if ctx.author.id == tribes[tribe]["owner"]:
                        memberlist = tribes[tribe]["allowed"]
                        if member.id in memberlist:
                            memberlist.remove(member.id)
                            channel = ctx.guild.get_channel(tribes[tribe]["channel"])
                            await channel.set_permissions(member, read_messages=False)
                            await ctx.send(f"{member.mention} has been remove from tribe log access.")
                        else:
                            await ctx.send("Member does not exist in tribe log access.")
                    else:
                        await ctx.send("You do not have ownership of any tribes")
            else:
                await ctx.send("No tribe data available")

    # VIEW SETTINGSs
    @_permissions.command(name="view")
    async def _viewperms(self, ctx: commands.Context):
        """View current permission settings."""
        settings = await self.config.guild(ctx.guild).all()
        color = discord.Color.dark_purple()
        statuschannel = ctx.guild.get_channel(settings['statuschannel'])
        if settings['statuschannel']:
            statuschannel = statuschannel.mention
        if not settings['statuschannel']:
            statuschannel = "Not Set"
        try:
            embed = discord.Embed(
                title=f"Permission Settings",
                color=color,
                description=f"**Full Access Role:** {settings['fullaccessrole']}\n"
                            f"**Mod Roles:** {settings['modroles']}\n"
                            f"**Mod Commands:** {settings['modcommands']}\n"
                            f"**Blacklisted Names:** {settings['badnames']}\n"
                            f"**Status Channel:** {statuschannel}"
            )
            return await ctx.send(embed=embed)
        except Exception:
            await ctx.send(f"Setup permissions first.")

    @_serversettings.command(name="view")
    async def _viewsettings(self, ctx: commands.Context):
        """View current server settings."""

        settings = await self.config.guild(ctx.guild).all()
        if not settings["clusters"]:
            await ctx.send("No servers have been added yet.")
            return
        for cname in settings["clusters"]:
            serversettings = ""
            serversettings += f"**{cname.upper()} Cluster**\n"
            if settings["clusters"][cname]["servertoserver"] is True:
                serversettings += f"`Map-to-Map Chat:` **Enabled**\n"
            if settings["clusters"][cname]["servertoserver"] is False:
                serversettings += f"`Map-to-Map Chat:` **Disabled**\n"
            for k, v in settings["clusters"][cname].items():
                if k == "globalchatchannel":
                    serversettings += f"`GlobalChat:` {ctx.guild.get_channel(v).mention}\n"
                if k == "adminlogchannel":
                    serversettings += f"`AdminLog:` {ctx.guild.get_channel(v).mention}\n"
                if k == "joinchannel":
                    serversettings += f"`JoinChannel:` {ctx.guild.get_channel(v).mention}\n"
                if k == "leavechannel":
                    serversettings += f"`LeaveChannel:` {ctx.guild.get_channel(v).mention}\n"
                else:
                    continue
            for server in settings["clusters"][cname]["servers"]:
                for k, v in settings["clusters"][cname]["servers"][server].items():
                    if k == "name":
                        serversettings += f"**Map:** `{v.capitalize()}`\n"
                    if k != "chatchannel":
                        if k != "name":
                            if k != "ip":
                                serversettings += f"**{k.capitalize()}:** `{v}`\n"
                            if k == "ip":
                                serversettings += f"**{k.upper()}:** `{v}`\n"
                    if k == "chatchannel":
                        serversettings += f"**Channel:** {ctx.guild.get_channel(v).mention}\n"
                serversettings += "\n"
            for p in pagify(serversettings):
                color = discord.Color.dark_purple()
                embed = discord.Embed(
                    color=color,
                    description=f"{p}"
                )
                await ctx.send(embed=embed)

    @_tribesettings.command(name="view")
    @commands.guildowner()
    async def _viewtribesettings(self, ctx):
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


    # Manual RCON commands
    @_setarktools.command(name="rcon")
    async def rcon(self, ctx: commands.Context, clustername: str, servername: str, *, command: str):
        """Perform an RCON command."""
        settings = await self.config.guild(ctx.guild).all()
        # Check whether user has perms
        userallowed = False
        for role in ctx.author.roles:
            if role.id == settings['fullaccessrole']:
                userallowed = True
            for modrole in settings['modroles']:
                if role.id == modrole:
                    modcmds = settings['modcommands']
                    for cmd in modcmds:
                        if str(cmd.lower()) in command.lower():
                            userallowed = True
        if not userallowed:
            if ctx.guild.owner != ctx.author:
                return await ctx.send("You do not have the required permissions to run that command.")

        # Pull data to send with command to task loop depending on what user designated
        serverlist = []
        clustername = clustername.lower()
        servername = servername.lower()
        if clustername != "all":
            if not settings["clusters"][clustername]:
                return await ctx.send("Cluster name not found.")
            if servername == "all":
                for server in settings["clusters"][clustername]["servers"]:
                    settings["clusters"][clustername]["servers"][server]["cluster"] = clustername
                    serverlist.append(settings["clusters"][clustername]["servers"][server])
            if servername != "all":
                settings["clusters"][clustername]["servers"][servername]["cluster"] = clustername
                if not settings["clusters"][clustername]["servers"][servername]:
                    return await ctx.send("Server name not found.")
                serverlist.append(settings["clusters"][clustername]["servers"][servername])
        if clustername == "all":
            for cluster in settings["clusters"]:
                if servername == "all":
                    for server in settings["clusters"][cluster]["servers"]:
                        settings["clusters"][cluster]["servers"][server]["cluster"] = cluster.lower()
                        serverlist.append(settings["clusters"][cluster]["servers"][server])
                if servername != "all":
                    settings["clusters"][cluster]["servers"][servername]["cluster"] = cluster.lower()
                    if not settings["clusters"][cluster]["servers"][servername]:
                        return await ctx.send("Server name not found.")
                    serverlist.append(settings["clusters"][cluster]["servers"][servername])

        # Sending manual commands off to the task loop
        tasks = []
        if command.lower() == "doexit":  # Count down, save world, exit - for clean shutdown
            for i in range(10, 0, -1):
                for server in serverlist:
                    mapchannel = ctx.guild.get_channel(server["chatchannel"])
                    await mapchannel.send(f"Reboot in {i}")
                    tasks.append(self.manual_rcon(ctx, server, f"serverchat Reboot in {i}"))
                await asyncio.gather(*tasks)
                await asyncio.sleep(1)
            for server in serverlist:
                mapchannel = ctx.guild.get_channel(server["chatchannel"])
                await mapchannel.send(f"Saving world...")
                tasks.append(self.manual_rcon(ctx, server, "saveworld"))
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)
            for server in serverlist:
                tasks.append(self.manual_rcon(ctx, server, "doexit"))
            await asyncio.gather(*tasks)

        else:
            for server in serverlist:
                tasks.append(self.manual_rcon(ctx, server, command))
            await asyncio.gather(*tasks)

        if command.lower() == "doexit":
            await ctx.send(f"Saved and rebooted `{len(serverlist)}` servers for `{clustername}` clusters.")
        else:
            await ctx.send(f"Executed `{command}` command on `{len(serverlist)}` servers for `{clustername}` clusters.")

    # RCON function for manual commands
    async def manual_rcon(self, ctx, serverlist, command):
        async with ctx.typing():
            try:
                map = serverlist['name'].capitalize()
                cluster = serverlist['cluster'].upper()
                res = await rcon.asyncio.rcon(
                    command=command,
                    host=serverlist['ip'],
                    port=serverlist['port'],
                    passwd=serverlist['password']
                )
                res = res.rstrip()
                if command.lower() == "listplayers":
                    await ctx.send(f"**{map} {cluster}**\n"
                                   f"{box(res, lang='python')}")
                else:
                    await ctx.send(box(f"{map} {cluster}\n{res}", lang="python"))
            except WindowsError as e:
                if e.winerror == 121:
                    clustername = serverlist['cluster']
                    servername = serverlist['name']
                    await ctx.send(f"The **{servername}** **{clustername}** server has timed out and is probably down.")
                    return

    # Cache the config on cog load for the task loops to use
    async def initialize(self):
        config = await self.config.all_guilds()
        for guildID in config:
            guild = self.bot.get_guild(int(guildID))
            if not guild:
                continue
            guildsettings = await self.config.guild(guild).clusters()
            if not guildsettings:
                continue
            for cluster in guildsettings:
                if not guildsettings[cluster]:
                    continue
                guildsettings[cluster]["servertoserver"] = False
                globalchatchannel = guildsettings[cluster]["globalchatchannel"]
                adminlogchannel = guildsettings[cluster]["adminlogchannel"]
                joinchannel = guildsettings[cluster]["joinchannel"]
                leavechannel = guildsettings[cluster]["leavechannel"]
                for server in guildsettings[cluster]["servers"]:
                    guildsettings[cluster]["servers"][server]["joinchannel"] = joinchannel
                    guildsettings[cluster]["servers"][server]["leavechannel"] = leavechannel
                    guildsettings[cluster]["servers"][server]["adminlogchannel"] = adminlogchannel
                    guildsettings[cluster]["servers"][server]["globalchatchannel"] = globalchatchannel
                    guildsettings[cluster]["servers"][server]["cluster"] = cluster
                    server = guildsettings[cluster]["servers"][server]
                    self.servercount += 1
                    self.alerts[server["chatchannel"]] = 0
                    self.playerlist[server["chatchannel"]] = []
                    self.taskdata.append([guild.id, server])

        print("ArkTools config initialized.")  # If this doesnt print then something is fucky...

    # Message listener to detect channel message is sent in and sends ServerChat command to designated server
    @commands.Cog.listener("on_message")
    async def chat_toserver(self, message: discord.Message):
        channels = []
        for data in self.taskdata:
            server = data[1]
            channels.append(server["globalchatchannel"])
            channels.append(server["chatchannel"])
        if message.channel.id not in channels:
            return
        if message.author.bot:
            return
        if message.mentions:
            for mention in message.mentions:
                message.content = message.content.replace(f"<@!{mention.id}>", f"@{mention.name}")
        if message.channel_mentions:
            for mention in message.channel_mentions:
                message.content = message.content.replace(f"<#{mention.id}>", f"#{mention.name}")
        if message.role_mentions:
            for mention in message.role_mentions:
                message.content = message.content.replace(f"<@&{mention.id}>", f"@{mention.name}")

        clusterchannels, allservers = await self.globalchannelchecker(message.channel)

        chatchannels, map = await self.mapchannelchecker(message.channel)

        if message.channel.id in clusterchannels:
            await self.chat_toserver_rcon(allservers, message)
        if message.channel.id in chatchannels:
            await self.chat_toserver_rcon(map, message)

    # Send chat to server(filters any unicode characters or custom discord emojis before hand)
    async def chat_toserver_rcon(self, server, message):
        author = message.author.name
        message = re.sub(r'https?:\/\/[^\s]+', '', message.content)
        message = re.sub(r'<:\w*:\d*>', '', message)
        message = re.sub(r'<a:\w*:\d*>', '', message)
        message = unicodedata.normalize('NFKD', message).encode('ascii', 'ignore').decode()
        normalizedname = unicodedata.normalize('NFKD', author).encode('ascii', 'ignore').decode()
        for data in server:
            try:
                await rcon.asyncio.rcon(
                    command=f"serverchat {normalizedname}: {message}",
                    host=data['ip'],
                    port=data['port'],
                    passwd=data['password'])
            except Exception as e:
                print(f"TO_SERVER ERROR: {e}")
                continue

    # Returns all channels and servers related to the message
    async def globalchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        clusterchannels = []
        allservers = []
        for cluster in settings["clusters"]:
            if settings["clusters"][cluster]["globalchatchannel"] == channel.id:
                clusterchannels.append(settings["clusters"][cluster]["globalchatchannel"])
                for server in settings["clusters"][cluster]["servers"]:
                    globalchat = settings["clusters"][cluster]["globalchatchannel"]
                    settings["clusters"][cluster]["servers"][server]["globalchatchannel"] = globalchat
                    clusterchannels.append(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    allservers.append(settings["clusters"][cluster]["servers"][server])
        return clusterchannels, allservers

    # Returns the channel and server related to the message
    async def mapchannelchecker(self, channel):
        settings = await self.config.guild(channel.guild).all()
        chatchannels = []
        map = []
        for cluster in settings["clusters"]:
            for server in settings["clusters"][cluster]["servers"]:
                if settings["clusters"][cluster]["servers"][server]["chatchannel"] == channel.id:
                    chatchannels.append(settings["clusters"][cluster]["servers"][server]["chatchannel"])
                    map.append(settings["clusters"][cluster]["servers"][server])
        return chatchannels, map

    # Initiates the GetChat loop
    @tasks.loop(seconds=4)
    async def chat_executor(self):
        for data in self.taskdata:
            guild = self.bot.get_guild(data[0])
            server = data[1]
            await self.process_handler(guild, server, "getchat")

    # Initiates the ListPlayers loop for both join/leave logs and status message to use
    @tasks.loop(seconds=30)
    async def playerlist_executor(self):
        for data in self.taskdata:
            guild = self.bot.get_guild(data[0])
            server = data[1]
            channel = server["chatchannel"]
            joinlog = guild.get_channel(server["joinchannel"])
            leavelog = guild.get_channel(server["leavechannel"])
            mapname = server["name"].capitalize()
            clustername = server["cluster"].upper()
            newplayerlist = await self.process_handler(guild, server, "listplayers")

            if newplayerlist is None:
                self.playerlist[channel] = newplayerlist
                continue
            if self.playerlist[channel] is None:
                self.playerlist[channel] = newplayerlist
                continue
            else:
                playerjoin = self.checkplayerjoin(channel, newplayerlist)
                if playerjoin:
                    await joinlog.send(
                        f":green_circle: `{playerjoin[0]}, {playerjoin[1]}` joined {mapname} {clustername}")
                playerleft = self.checkplayerleave(channel, newplayerlist)
                if playerleft:
                    await leavelog.send(f":red_circle: `{playerleft[0]}, {playerleft[1]}` left {mapname} {clustername}")

                self.playerlist[channel] = newplayerlist

    # For the Discord join log
    def checkplayerjoin(self, channel, newplayerlist):
        for player in newplayerlist:
            if player not in self.playerlist[channel]:
                return player

    # For the Discord leave log
    def checkplayerleave(self, channel, newplayerlist):
        if newplayerlist is None:
            return
        for player in self.playerlist[channel]:
            if newplayerlist is []:
                return player
            if player not in newplayerlist:
                return player

    # Creates and maintains an embed of all active servers and player counts
    @tasks.loop(seconds=60)
    async def status_channel(self):
        data = await self.config.all_guilds()
        for guildID in data:
            guild = self.bot.get_guild(int(guildID))
            if not guild:
                continue
            settings = await self.config.guild(guild).all()
            if not settings:
                continue
            status = ""
            totalplayers = 0
            for cluster in settings["clusters"]:
                clustertotal = 0
                clustername = cluster.upper()
                if not settings["clusters"]:
                    continue
                status += f"**{clustername}**\n"
                for server in settings["clusters"][cluster]["servers"]:
                    channel = settings["clusters"][cluster]["servers"][server]["chatchannel"]
                    if not channel:
                        continue

                    # Get cached player count data
                    playercount = self.playerlist[channel]

                    count = self.alerts[channel]
                    if playercount is None:
                        inc = "Minutes."
                        if count >= 60:
                            count = count / 60
                            inc = "Hours."
                            count = int(count)

                        status += f"{guild.get_channel(channel).mention}: Offline for {count} {inc}\n"
                        alertmsg = guild.get_channel(settings["clusters"][cluster]["adminlogchannel"])
                        pingrole = guild.get_role(settings['fullaccessrole'])
                        if count == 0:
                            await alertmsg.send(f"{pingrole.mention}, The **{server}** server has gone offline!!!")
                            self.alerts[channel] += 1
                            continue
                        else:
                            self.alerts[channel] += 1
                            continue

                    if playercount is []:
                        status += f"{guild.get_channel(channel).mention}: 0 Players\n"
                        if count > 0:
                            self.alerts[channel] = 0
                        continue

                    playercount = len(playercount)
                    clustertotal += playercount
                    totalplayers += playercount
                    if playercount == 1:
                        status += f"{guild.get_channel(channel).mention}: {playercount} player\n"
                    else:
                        status += f"{guild.get_channel(channel).mention}: {playercount} players\n"

                if clustertotal == 1:
                    status += f"`{clustertotal}` player in the cluster\n"
                else:
                    status += f"`{clustertotal}` players in the cluster\n"

            messagedata = await self.config.guild(guild).statusmessage()
            channeldata = await self.config.guild(guild).statuschannel()
            if not channeldata:
                continue

            # Embed setup
            thumbnail = guild.icon_url
            eastern = pytz.timezone('US/Eastern')  # Might make this configurable in the future
            time = datetime.datetime.now(eastern)
            embed = discord.Embed(
                timestamp=time,
                title="Server Status",
                color=discord.Color.random(),
                description=status
            )
            embed.add_field(name="Total Players", value=f"`{totalplayers}`")
            embed.set_thumbnail(url=thumbnail)
            destinationchannel = guild.get_channel(channeldata)
            msgtoedit = None

            if messagedata:
                try:
                    msgtoedit = await destinationchannel.fetch_message(messagedata)
                except discord.NotFound:
                    print(f"ArkTools Status message not found. Creating new message.")

            if not msgtoedit:
                await self.config.guild(guild).statusmessage.set(None)
                message = await destinationchannel.send(embed=embed)
                await self.config.guild(guild).statusmessage.set(message.id)
            if msgtoedit:
                await msgtoedit.edit(embed=embed)

    # Executes all task loop RCON commands synchronously in another thread
    # Process is synchronous for easing network buffer and keeping network traffic manageable
    async def process_handler(self, guild, server, command,):
        if command == "getchat":
            timeout = 1
        elif command == "listplayers":
            timeout = 10
        else:
            timeout = 3

        def rcon():
            try:
                with Client(server['ip'], server['port'], passwd=server['password'], timeout=timeout) as client:
                    result = client.run(command)
                    return result
            except WindowsError as e:
                if e.winerror == 121:
                    return None

        res = await self.bot.loop.run_in_executor(None, rcon)
        if res:
            if "getchat" in command:
                await self.message_handler(guild, server, res)
            if "listplayers" in command:
                regex = r"(?:[0-9]+\. )(.+), ([0-9]+)"
                playerlist = re.findall(regex, res)
                return playerlist

    # Sends messages to their designated channels from the in-game chat
    async def message_handler(self, guild, server, res):
        if "Server received, But no response!!" in res:  # Common response from an Online server with no new messages
            return
        adminlog = guild.get_channel(server["adminlogchannel"])
        globalchat = guild.get_channel(server["globalchatchannel"])
        chatchannel = guild.get_channel(server["chatchannel"])
        sourcename = server["name"]
        msgs = res.split("\n")
        messages = []
        settings = await self.config.guild(guild).all()
        badnames = settings["badnames"]
        for msg in msgs:
            if msg.startswith("AdminCmd:"):
                adminmsg = msg
                await adminlog.send(f"**{server['name'].capitalize()}**\n{box(adminmsg, lang='python')}")
            elif "Tribe" and ", ID" in msg:
                await self.tribelog_formatter(guild, server, msg)
            elif msg.startswith('SERVER:'):
                continue
            else:
                messages.append(msg)
                for names in badnames:
                    if f"({names.lower()}): " in msg.lower():
                        reg = r"(.+)\s\("
                        regname = re.findall(reg, msg)
                        for name in regname:
                            await self.process_handler(guild, server, f'renameplayer "{names.lower()}" {name}')
                            await chatchannel.send(f"A player named `{names}` has been renamed to `{name}`.")
        for msg in messages:
            if msg == ' ':
                continue
            else:
                await chatchannel.send(msg)
                await globalchat.send(f"{chatchannel.mention}: {msg}")
                clustername = server["cluster"]
                if settings["clusters"][clustername]["servertoserver"] is True:  # maps can talk to each other if true
                    for data in self.taskdata:
                        map = data[1]
                        if map["cluster"] == server["cluster"] and map["name"] != sourcename:
                            await self.process_handler(guild, map, f"serverchat {sourcename.capitalize()}: {msg}")

    # Handles tribe log formatting/itemizing
    async def tribelog_formatter(self, guild, server, msg):
        regex = r'(?i)Tribe (.+), ID (.+): (Day .+, ..:..:..): .+>(.+)<'
        tribe = re.findall(regex, msg)
        if not tribe:
            return
        name = tribe[0][0]
        tribe_id = tribe[0][1]
        time = tribe[0][2]
        action = tribe[0][3]
        if "was killed" in action.lower():
            color = discord.Color.dark_red()
        elif "tribe killed" in action.lower():
            color = discord.Color.magenta()
        elif "demolished" in action.lower():
            color = discord.Color.gold()
        elif "destroyed" in action.lower():
            color = discord.Color.red()
        elif "tamed" in action.lower():
            color = discord.Color.green()
        elif "froze" in action.lower():
            color = discord.Color.light_grey()
        elif "starved" in action.lower():
            color = discord.Color.orange()
        elif "claimed" in action.lower():
            color = discord.Color.teal()
        elif "unclaimed" in action.lower():
            color = discord.Color.blue()
        else:
            color = discord.Color.purple()
        embed = discord.Embed(
            title=f"{server['cluster'].upper()} {server['name'].capitalize()}: {name}",
            color=color,
            description=f"{box(action)}"
        )
        embed.set_footer(text=f"{time} | Tribe ID: {tribe_id}")
        await self.tribe_handler(guild, tribe_id, embed)

    # Handles sending off tribe logs to their designated channels
    async def tribe_handler(self, guild, tribe_id, embed):
        settings = await self.config.guild(guild).all()
        if "masterlog" in settings.keys():
            masterlog = guild.get_channel(settings["masterlog"])
            await masterlog.send(embed=embed)
        if "tribes" in settings.keys():
            for tribes in settings["tribes"]:
                if tribe_id == tribes:
                    tribechannel = guild.get_channel(settings["tribes"][tribes]["channel"])
                    await tribechannel.send(embed=embed)

    # Initialize the config before the chat loop starts
    @chat_executor.before_loop
    async def before_chat_executor(self):
        await self.bot.wait_until_red_ready()
        await self.initialize()
        print("Chat executor is ready.")

    # Nothing special before playerlist executor
    @playerlist_executor.before_loop
    async def before_playerlist_executor(self):
        await self.bot.wait_until_red_ready()
        print("Playerlist executor is ready.")

    # Sleep before starting so playerlist executor has time to gather the player list
    @status_channel.before_loop
    async def before_status_channel(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(15) # Gives playerlist executor time to gather player count
        print("Status channel monitor is ready.")

    # More of a test command to make sure a unicode discord name can be properly filtered with the unicodedata lib
    @commands.command(name="checkname")
    async def _checkname(self, ctx):
        """Check your discord name to see if it works with this cogs crosscaht unicode  filter."""
        """If there are no errors then you're good to go."""
        try:
            normalizedname = unicodedata.normalize('NFKD', ctx.message.author.name).encode('ascii', 'ignore').decode()
            await ctx.send(f"Filtered name: {normalizedname}")
            await ctx.send(f"Unfiltered name: {ctx.message.author.name}")
        except Exception as e:
            await ctx.send(f"Looks like your name broke the code, please pick a different name.\nError: {e}")

    # For debug purposes or just wanting to see your raw config easily
    @commands.command(name="test")
    @commands.guildowner()
    async def _getconf(self, ctx):
        """Pull your raw config and send to discord as a .txt file."""
        settings = await self.config.guild(ctx.guild).all()
        settings = json.dumps(settings)
        with open("config.txt", "w") as file:
            file.write(settings)
        with open("config.txt", "rb") as file:
            await ctx.send(file=discord.File(file, "config.txt"))
