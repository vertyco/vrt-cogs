import asyncio
import logging
from contextlib import suppress
from io import StringIO

import discord
from discord.ext import tasks
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..vragepy import Player, VRageClient

log = logging.getLogger("red.vrt.setools")


class JoinLog(MixinMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.playerlists: dict[str, list[Player]] = {}

    @tasks.loop(seconds=10)
    async def joinlogs(self):
        jobs = []
        guild_ids = [i for i in self.db.configs]
        for gid in guild_ids:
            guild: discord.Guild = self.bot.get_guild(gid)
            if not guild:
                continue
            jobs.append(self.process_joinlog(guild))
        await asyncio.gather(*jobs)

    async def process_joinlog(self, guild: discord.Guild):
        conf = self.db.get_conf(guild)
        if not conf.servers:
            return
        for server in conf.servers:
            if not server.join_log:
                continue
            channel = guild.get_channel(server.join_log)
            if not channel:
                continue
            if not channel.permissions_for(guild.me).send_messages:
                continue
            try:
                client = VRageClient(base_url=server.address, token=server.token)
                resp = await client.get_players()
            except Exception as e:
                log.exception(f"get_players failed for {server.name} in {guild}", exc_info=e)
                continue

            if server.id not in self.playerlists:
                # First time running
                # Initialize list instead of spamming the joinlog
                self.playerlists[server.id] = resp.data.Players
                continue

            new_playerlist = resp.data.Players
            last_playerlist = self.playerlists[server.id]

            joined = [i for i in new_playerlist if i not in last_playerlist]
            left = [i for i in last_playerlist if i not in new_playerlist]

            # With faction tag
            join1 = ":green_circle: **{} [{}]** (`{}`) has joined **{}**\n"
            leave1 = ":red_circle: **{} [{}]** (`{}`) has left **{}**\n"
            # Without faction tag
            join2 = ":green_circle: **{}** (`{}`) has joined **{}**\n"
            leave2 = ":red_circle: **{}** (`{}`) has left **{}**\n"

            buffer = StringIO()
            for i in joined:
                if not i.DisplayName:
                    continue
                if i.FactionTag:
                    buffer.write(join1.format(i.DisplayName, i.FactionTag, i.SteamID, server.name))
                else:
                    buffer.write(join2.format(i.DisplayName, i.SteamID, server.name))

            for i in left:
                if not i.DisplayName:
                    continue
                if i.FactionTag:
                    buffer.write(leave1.format(i.DisplayName, i.FactionTag, i.SteamID, server.name))
                else:
                    buffer.write(leave2.format(i.DisplayName, i.SteamID, server.name))

            if buffer.getvalue():
                for page in pagify(buffer.getvalue()):
                    with suppress(discord.HTTPException, discord.Forbidden, discord.NotFound):
                        await channel.send(page)

            self.playerlists[server.id] = new_playerlist
