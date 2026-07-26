import asyncio
import logging

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.views import SimpleMenu

from ..abc import MixinMeta
from ..common.api import PalApiError, PalClient, ServerUnreachable
from ..common.utils import format_player_lines, format_playtime
from ..db.tables import Server, ensure_db_connection
from ..db.utils import find_players, get_target_servers, player_playtime, top_playtime

log = logging.getLogger("red.vrt.paltools.commands.base")
_ = Translator("PalTools", __file__)

# Discord's total embed budget, with headroom for the title and the overflow notice
EMBED_LIMIT = 5800


@cog_i18n(_)
class Base(MixinMeta):
    @commands.command(name="palstats")
    @commands.guild_only()
    @ensure_db_connection()
    async def palstats(self, ctx: commands.Context, *, player_name: str):
        """View a PalWorld player's stats by in-game name or account name"""
        players = await find_players(ctx.guild.id, player_name)
        if not players:
            return await ctx.send(_("No players found matching `{}`").format(player_name))
        if len(players) > 1:
            names = ", ".join(p.name for p in players)
            return await ctx.send(_("Multiple matches, be more specific: {}").format(names))
        player = players[0]
        playtime = await player_playtime(player)
        embed = discord.Embed(title=player.name, color=discord.Color.blurple())
        embed.add_field(name=_("Level"), value=str(player.level))
        embed.add_field(name=_("Total playtime"), value=format_playtime(sum(playtime.values())))
        embed.add_field(name=_("First seen"), value=discord.utils.format_dt(player.first_seen, "R"))
        embed.add_field(name=_("Last seen"), value=discord.utils.format_dt(player.last_seen, "R"))
        for server_name, seconds in sorted(playtime.items(), key=lambda kv: kv[1], reverse=True)[:5]:
            embed.add_field(name=server_name, value=format_playtime(seconds))
        if player.name_history and len(player.name_history) > 1:
            embed.add_field(name=_("Previous names"), value=", ".join(player.name_history[-5:]), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="paltop")
    @commands.guild_only()
    @ensure_db_connection()
    async def paltop(self, ctx: commands.Context):
        """Top playtime leaderboard"""
        rows = await top_playtime(ctx.guild.id, limit=50)
        if not rows:
            return await ctx.send(_("No playtime recorded yet"))
        pages = []
        per_page = 10
        for start in range(0, len(rows), per_page):
            chunk = rows[start : start + per_page]
            lines = [f"**{start + i + 1}.** {r['name']} - {format_playtime(r['seconds'])}" for i, r in enumerate(chunk)]
            embed = discord.Embed(
                title=_("Playtime Leaderboard"),
                description="\n".join(lines),
                color=discord.Color.gold(),
            )
            embed.set_footer(text=_("Page {}/{}").format(start // per_page + 1, -(-len(rows) // per_page)))
            pages.append(embed)
        await SimpleMenu(pages, use_select_menu=len(pages) > 3).start(ctx)

    @commands.command(name="palstatus")
    @commands.guild_only()
    @commands.cooldown(2, 30, commands.BucketType.guild)
    @ensure_db_connection()
    async def palstatus(self, ctx: commands.Context, server_name: str | None = None):
        """Server status: version, FPS, uptime, player count"""
        servers = (await get_target_servers(ctx.guild.id, server_name))[:10]
        if not servers:
            return await ctx.send(_("No matching enabled servers"))
        # Concurrently: sequentially, every unreachable server costs the full request timeout
        values = await asyncio.gather(*(self.status_line(server) for server in servers))
        embed = discord.Embed(title=_("PalWorld Server Status"), color=discord.Color.blurple())
        for server, value in zip(servers, values, strict=True):
            embed.add_field(name=server.name, value=value, inline=False)
        await ctx.send(embed=embed)

    @staticmethod
    async def status_line(server: Server) -> str:
        client = PalClient(server.host, server.port, server.admin_password)
        try:
            info, metrics = await asyncio.gather(client.info(), client.metrics())
        except ServerUnreachable:
            return _("🔴 Unreachable")
        except PalApiError as e:
            log.warning("Status failed for %s", server.name, exc_info=e)
            return _("⚠️ Error: {}").format(e)
        return _("🟢 {} | {}/{} players | {} FPS | up {}").format(
            info.version,
            metrics.currentplayernum,
            metrics.maxplayernum,
            metrics.serverfps,
            format_playtime(metrics.uptime),
        )

    @commands.command(name="palplayers")
    @commands.guild_only()
    @commands.cooldown(2, 30, commands.BucketType.guild)
    @ensure_db_connection()
    async def palplayers(self, ctx: commands.Context, server_name: str | None = None):
        """Who is online right now"""
        servers = (await get_target_servers(ctx.guild.id, server_name))[:10]
        if not servers:
            return await ctx.send(_("No matching enabled servers"))
        fields = await asyncio.gather(*(self.players_field(server) for server in servers))
        embed = discord.Embed(title=_("Online Players"), color=discord.Color.green())
        for index, (name, value) in enumerate(fields):
            # A full roster runs to ~950 characters, so seven busy servers blow the 6000 char
            # embed ceiling and Discord rejects the whole message
            if len(embed) + len(name) + len(value) > EMBED_LIMIT:
                embed.add_field(
                    name="​", value=_("-# {} more servers do not fit").format(len(fields) - index), inline=False
                )
                break
            embed.add_field(name=name, value=value, inline=False)
        await ctx.send(embed=embed)

    @staticmethod
    async def players_field(server: Server) -> tuple[str, str]:
        client = PalClient(server.host, server.port, server.admin_password)
        count = "?"
        try:
            players = [p for p in await client.players() if not p.is_placeholder]
            count = str(len(players))
            value = format_player_lines(players) if players else _("Nobody online")
        except ServerUnreachable:
            value = _("🔴 Unreachable")
        except PalApiError as e:
            log.warning("Playerlist failed for %s", server.name, exc_info=e)
            value = _("⚠️ Error: {}").format(e)
        return f"{server.name} ({count})", value
