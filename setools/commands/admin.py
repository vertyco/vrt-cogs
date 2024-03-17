import asyncio
import json
import logging
import typing as t
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import text_to_file

from ..abc import MixinMeta
from ..common.imgen import generate_visualization
from ..views.editserver import EditServerMenu
from ..vragepy import VRageClient

log = logging.getLogger("red.vrt.setools.commands.admin")


class Admin(MixinMeta):
    @commands.group()
    @commands.admin_or_permissions(manage_guild=True)
    async def setools(self, ctx: commands.Context):
        """Admin commands for SETools"""
        pass

    @setools.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """View the current settings"""
        conf = self.db.get_conf(ctx.guild)
        if len(conf.servers) != len(set(conf.servers)):
            conf.servers = list(set(conf.servers))
            await self.save()

        channel = f"<#{conf.status_channel}>" if conf.status_channel else "Not set"

        buffer = StringIO()
        buffer.write(f"Status Channel: {channel}\n\n")
        buffer.write("▬▬▬▬**Servers**▬▬▬▬\n")
        for server in conf.servers:
            buffer.write(f"- {server.name}: {server.address}\n")
            if server.chat_channel:
                buffer.write(f" - chat: <#{server.chat_channel}>\n")
            if server.join_log:
                buffer.write(f" - joinlog: <#{server.join_log}>\n")

        embed = discord.Embed(
            title="Server Settings",
            description=buffer.getvalue(),
            color=ctx.author.color,
        )
        await ctx.send(embed=embed)

    @setools.command(name="addserver")
    async def add_server(self, ctx: commands.Context):
        """Add an SE server"""
        view = EditServerMenu(self, ctx)
        await view.start_menu()

    @setools.command(name="editserver")
    async def edit_server(self, ctx: commands.Context, *, server_name: str):
        """Edit an SE server"""
        view = EditServerMenu(self, ctx, server_name)
        await view.start_menu()

    @setools.command(name="removeserver")
    async def remove_server(self, ctx: commands.Context, *, server_name: str):
        """Remove an SE server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if server is None:
            return await ctx.send(f"Server {server_name} not found")

        conf.servers.remove(server)
        await ctx.send(f"Server {server_name} removed")
        await self.save()

    @setools.command(name="statuschannel")
    async def set_status_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the status channel"""
        conf = self.db.get_conf(ctx.guild)
        conf.status_channel = channel.id
        await ctx.send(f"Status channel set to {channel.mention}")
        await self.save()

    @setools.command(name="save")
    async def save_server(self, ctx: commands.Context, *, server_name: str):
        """Save the world on a server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            await client.save_server()
        except Exception as e:
            log.error(f"Failed to save server {server_name}", exc_info=e)
            await ctx.send(f"Failed to save server {server_name}")
            return

        await ctx.send(f"Server `{server_name}` saved")

    @setools.command(name="visualize")
    @commands.bot_has_permissions(attach_files=True)
    async def visualize_world(self, ctx: commands.Context, *, server_name: str):
        """
        Generate an visualization of the world

        **Note**: The HTML file needs to be opened in a browser to view the visualization
        """
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        async with ctx.typing():
            try:
                client = VRageClient(base_url=server.address, token=server.token)
                asteroids = (await client.get_asteroids()).data.Asteroids
                planets = (await client.get_planets()).data.Planets
                grids = (await client.get_grids()).data.Grids
                objects = (await client.get_floating_objects()).data.FloatingObjects
            except Exception as e:
                log.error(f"Failed to visualize world for {server_name}", exc_info=e)
                await ctx.send(f"Failed to visualize world for {server_name}")
                return

            html = await asyncio.to_thread(generate_visualization, asteroids, planets, grids, objects)
            file = text_to_file(html, filename="visualization.html")
            await ctx.send(file=file)

    @setools.command(name="delete")
    async def delete_thing(
        self,
        ctx: commands.Context,
        thing: t.Literal["asteroids", "objects", "grids", "planets", "roids", "objs"],
        entity_id: int,
        *,
        server_name: str,
    ):
        """Delete an Asteroid, Grid, FloatingObject, or Planet from a server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            if thing in ("asteroids", "roids"):
                await client.delete_asteroid(entity_id)
            elif thing in ("objects", "objs"):
                await client.delete_floating_object(entity_id)
            elif thing == "grids":
                await client.delete_grid(entity_id)
            elif thing == "planets":
                await client.delete_planet(entity_id)
            else:
                return await ctx.send("Invalid object type")
        except Exception as e:
            log.error(f"Failed to delete {thing} {entity_id} for {server_name}", exc_info=e)
            await ctx.send(f"Failed to delete {thing} {entity_id} for {server_name}")
            return
        await ctx.send(f"{thing} `{entity_id}` deleted on **{server_name}**")

    @setools.command(name="get")
    async def get_thing(
        self,
        ctx: commands.Context,
        thing: t.Literal["asteroids", "objects", "grids", "planets", "roids", "objs"],
        *,
        server_name: str,
    ):
        """Get a list of Asteroids, Grids, FloatingObjects, or Planets for a server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return

        buffer = StringIO()
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            if thing in ("asteroids", "roids"):
                resp = await client.get_asteroids()
                for i in resp.data.Asteroids:
                    buffer.write(f"- {i.DisplayName} ({i.EntityId}) [{i.pos}]\n")
            elif thing in ("objects", "objs"):
                resp = await client.get_floating_objects()
                for i in resp.data.FloatingObjects:
                    buffer.write(f"- {i.DisplayName} ({i.EntityId}) [{i.pos}]\n")
                    buffer.write(
                        f" - Kind: {i.Kind} - Mass: {i.Mass} - Speed: {i.LinearSpeed} - NearestPlayer: {i.DistanceToPlayer}\n"
                    )
            elif thing == "grids":
                resp = await client.get_grids()
                for i in resp.data.Grids:
                    buffer.write(f"- {i.DisplayName} ({i.EntityId}) [{i.pos}]\n")
                    for k, v in i.model_dump().items():
                        if k in ("DisplayName", "EntityId", "Position"):
                            continue
                        buffer.write(f" - {k}: {v}\n")
            elif thing == "planets":
                resp = await client.get_planets()
                for i in resp.data.Planets:
                    buffer.write(f"- {i.DisplayName} ({i.EntityId}) [{i.pos}]\n")
            else:
                return await ctx.send("Invalid object type")
        except Exception as e:
            log.error(f"Failed to get {thing} for {server_name}", exc_info=e)
            await ctx.send(f"Failed to get {thing} for {server_name}")
            return

        value = buffer.getvalue()
        if not value:
            return await ctx.send(f"No {thing} found")
        if len(value) > 1900:
            file = text_to_file(value, filename=f"{thing}.txt")
            return await ctx.send(file=file)
        await ctx.send(value)

    @setools.command(name="cheaters")
    async def get_cheaters(self, ctx: commands.Context, *, server_name: str):
        """Get the cheater list for a server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            resp = await client.get_cheaters()
        except Exception as e:
            log.error(f"Failed to get cheater list for {server_name}", exc_info=e)
            await ctx.send(f"Failed to get cheater list for {server_name}")
            return
        cheaters = [i for i in resp.data.Cheaters if i.Name]

        buffer = StringIO()
        for cheater in cheaters:
            buffer.write(f"- {cheater.Name} ({cheater.PlayerId}): {cheater.Explanation}\n")

        value = buffer.getvalue()
        if not value:
            return await ctx.send("There are no cheaters")

        if len(value) > 1900:
            file = text_to_file(value, filename="cheaters.txt")
            return await ctx.send(file=file)
        await ctx.send(value)

    @setools.command(name="banlist")
    async def get_banlist(self, ctx: commands.Context, *, server_name: str):
        """Get the ban list for a server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            resp = await client.get_banned_players()
        except Exception as e:
            log.error(f"Failed to get player list for {server_name}", exc_info=e)
            await ctx.send(f"Failed to get player list for {server_name}")
            return
        players = [i for i in resp.data.BannedPlayers if i.DisplayName]

        buffer = StringIO()
        for player in players:
            buffer.write(f"- {player.DisplayName} ({player.SteamID})\n")

        value = buffer.getvalue()
        if not value:
            return await ctx.send("There are no banned players")

        if len(value) > 1900:
            file = text_to_file(value, filename="banned_players.txt")
            return await ctx.send(file=file)
        await ctx.send(value)

    @commands.command(name="banengineer")
    @commands.admin_or_permissions(ban_members=True)
    async def ban_player(self, ctx: commands.Context, player_id: int, *, server_name: str):
        """Ban a player"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            await client.ban_player(player_id)
        except Exception as e:
            log.error(f"Failed to ban player {player_id} on {server_name}", exc_info=e)
            await ctx.send(f"Failed to ban player {player_id} on {server_name}")
            return
        await ctx.send(f"Player `{player_id}` banned on **{server_name}**")

    @commands.command(name="unbanengineer")
    @commands.admin_or_permissions(ban_members=True)
    async def unban_player(self, ctx: commands.Context, player_id: int, *, server_name: str):
        """Unban a player"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            await client.unban_player(player_id)
        except Exception as e:
            log.error(f"Failed to unban player {player_id} on {server_name}", exc_info=e)
            await ctx.send(f"Failed to unban player {player_id} on {server_name}")
            return
        await ctx.send(f"Player `{player_id}` unbanned on **{server_name}**")

    @setools.command(name="dumpendpoints")
    @commands.is_owner()
    async def dump_endpoints(self, ctx: commands.Context, *, server_name: str):
        """Get a json dump of the server's endpoints"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            resp = await client.get_endpoints()
        except Exception as e:
            log.error(f"Failed to get endpoints for {server_name}", exc_info=e)
            await ctx.send(f"Failed to get endpoints for {server_name}")
            return

        dump = json.dumps(resp.data.model_dump(), indent=4)
        file = text_to_file(dump, filename="endpoints.json")
        await ctx.send(file=file)

    @setools.command(name="promote")
    async def promote_player(self, ctx: commands.Context, player_id: int, *, server_name: str):
        """Promote a player"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            await client.promote_player(player_id)
        except Exception as e:
            log.error(f"Failed to promote player {player_id} on {server_name}", exc_info=e)
            await ctx.send(f"Failed to promote player {player_id} on {server_name}")
            return
        await ctx.send(f"Player `{player_id}` promoted on **{server_name}**")

    @setools.command(name="demote")
    async def demote_player(self, ctx: commands.Context, player_id: int, *, server_name: str):
        """Demote a player"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean **{suggested.name}**?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            await client.demote_player(player_id)
        except Exception as e:
            log.error(f"Failed to demote player {player_id} on {server_name}", exc_info=e)
            await ctx.send(f"Failed to demote player {player_id} on {server_name}")
            return
        await ctx.send(f"Player `{player_id}` demoted on **{server_name}**")
