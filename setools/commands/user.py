import logging
from io import StringIO

from redbot.core import commands

from ..abc import MixinMeta
from ..vragepy import VRageClient

log = logging.getLogger("red.vrt.setools.tasks.status")


class User(MixinMeta):
    @commands.command(name="playerlist")
    @commands.bot_has_permissions(embed_links=True)
    async def player_list(self, ctx: commands.Context, *, server_name: str):
        """List players on a server"""
        conf = self.db.get_conf(ctx.guild)
        server = conf.get_server(server_name)
        if not server:
            suggested = conf.get_server_similar(server_name)
            if suggested:
                await ctx.send(f"Server {server_name} not found. Did you mean {suggested.name}?")
            else:
                await ctx.send(f"Server {server_name} not found")
            return
        try:
            client = VRageClient(base_url=server.address, token=server.token)
            resp = await client.get_players()
        except Exception as e:
            log.error(f"Failed to get player list for {server_name}", exc_info=e)
            await ctx.send(f"Failed to get player list for {server_name}")
            return

        players = [i for i in resp.data.Players if i.DisplayName]
        if not players:
            await ctx.send("No players online")
            return

        buffer = StringIO()
        for player in players:
            txt = f"- **{player.DisplayName}**"
            if player.FactionTag:
                txt += f" [**{player.FactionTag}**]"
            txt += f" ({player.SteamID}) - {player.Ping}ms"
            buffer.write(f"{txt}\n")
        await ctx.send(buffer.getvalue())
