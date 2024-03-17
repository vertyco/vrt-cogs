import asyncio
import logging

import discord
from discord.ext import tasks
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.models import Server
from ..vragepy import VRageClient

log = logging.getLogger("red.vrt.setools")


class CrossChat(MixinMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep track of latest message timestamp for each server
        # {guild_id-server_token: timestamp}
        self.last_timestamp: dict[str, str] = {}

    @tasks.loop(seconds=5)
    async def get_chat(self):
        jobs = []
        configs = self.db.configs.copy()
        for gid, settings in configs.items():
            guild: discord.Guild = self.bot.get_guild(gid)
            if not guild:
                continue
            for server in settings.servers:
                jobs.append(self.get_server_chat(guild, server))
        await asyncio.gather(*jobs)

    async def get_server_chat(self, guild: discord.Guild, server: Server):
        if not server.chat_channel:
            return
        channel = guild.get_channel(server.chat_channel)
        if not channel:
            return
        if not channel.permissions_for(guild.me).send_messages:
            return

        client = VRageClient(base_url=server.address, token=server.token)

        key = f"{guild.id}-{server.token}"
        date = self.last_timestamp.get(key)
        try:
            resp = await client.get_chat(date=date)
        except Exception as e:
            log.exception(f"get_chat failed for {server.name} in {guild}", exc_info=e)
            return
        messages = resp.data.Messages
        if not messages:
            return
        self.last_timestamp[key] = str(max(m.ts for m in messages) + 1)
        if date is None:
            # Set latest message and skip since we dont want to spam the whole buffer
            return

        unique_messages = set()
        for message in messages:
            if message.Timestamp < date:
                continue
            if message.DisplayName.startswith("Good.bot"):
                continue
            name = message.DisplayName
            # Replace other one with PC emoji
            name = name.replace("\ue030", "\N{DESKTOP COMPUTER}\N{VARIATION SELECTOR-16} ")
            # Replace unknown character with controller emoji
            name = name.replace("\ue032", "\N{VIDEO GAME} ")

            unique_messages.add(f"{name}: {message.Content}\n")

        joined = "".join(unique_messages)

        for p in pagify(joined):
            await channel.send(p)

        log.debug(f"Sent {len(unique_messages)} out of {len(messages)} messages from {server.name} in {guild}")
