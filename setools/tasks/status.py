import asyncio
import logging
from datetime import datetime
from io import StringIO

import discord
from discord.ext import tasks
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..vragepy import VRageClient

log = logging.getLogger("red.vrt.setools.tasks.status")


class StatusChannel(MixinMeta):
    @tasks.loop(seconds=30)
    async def status_channel(self):
        jobs = []
        guild_ids = [i for i in self.db.configs]
        for gid in guild_ids:
            guild: discord.Guild = self.bot.get_guild(gid)
            if not guild:
                continue
            jobs.append(self.server_status(guild))
        await asyncio.gather(*jobs)

    async def server_status(self, guild: discord.Guild):
        conf = self.db.get_conf(guild)
        if not conf.status_channel or not conf.servers:
            return
        channel = guild.get_channel(conf.status_channel)
        if not channel:
            return
        if not channel.permissions_for(guild.me).send_messages:
            return
        message = None
        if conf.status_message:
            try:
                message = await channel.fetch_message(conf.status_message)
            except discord.NotFound:
                pass

        all_online = True
        with StringIO() as buffer:
            for server in conf.servers:
                buffer.write(f"## {server.name}\n")

                try:
                    client = VRageClient(base_url=server.address, token=server.token)
                    info = await client.get_server_info()
                    roids = await client.get_asteroids()
                    objs = await client.get_floating_objects()
                    grids = await client.get_grids()
                    planets = await client.get_planets()
                except Exception as e:
                    log.exception(f"get_status failed for {server.name} in {guild}", exc_info=e)
                    all_online = False
                    buffer.write("❌ offline\n")
                    continue

                buffer.write(f"`Server:    `{info.data.ServerName}\n")
                buffer.write(f"`World:     `{info.data.WorldName}\n")
                buffer.write(f"`Players:   `{info.data.Players}\n")
                buffer.write(f"`SimSpeed:  `{info.data.SimSpeed}\n")
                buffer.write(f"`CPU Load:  `{info.data.SimulationCpuLoad}%\n")
                buffer.write(f"`QueryTime: `{round(info.meta.queryTime * 1000, 1)}ms\n")
                buffer.write(f"`Version:   `{info.data.Version}\n")
                buffer.write(f"`PiratePCU: `{humanize_number(info.data.PirateUsedPCU)}\n")
                buffer.write(f"`UsedPCU:   `{humanize_number(info.data.UsedPCU)}\n")
                buffer.write(f"`Asteroids: `{humanize_number(len(roids.data.Asteroids))}\n")
                buffer.write(f"`Objects:   `{humanize_number(len(objs.data.FloatingObjects))}\n")
                buffer.write(f"`Grids:     `{humanize_number(len(grids.data.Grids))}\n")
                buffer.write(f"`Planets:   `{humanize_number(len(planets.data.Planets))}\n")

            embed = discord.Embed(
                description=buffer.getvalue(),
                color=discord.Color.green() if all_online else discord.Color.red(),
                timestamp=datetime.now(),
            )
            if message:
                await message.edit(embed=embed)
            else:
                message = await channel.send(embed=embed)
                conf.status_message = message.id
                await self.save()
