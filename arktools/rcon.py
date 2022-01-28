import logging

import discord
from rcon.asyncio import rcon
from redbot.core.utils.chat_formatting import box

log = logging.getLogger("red.vrt.arktools.rcon")


# Manual RCON commands
async def async_rcon(channel: discord.TextChannel, server: dict, command: str):
    serv = server["name"]
    cluster = server["cluster"]
    name = f"{serv} {cluster}"
    if "gamertag" in server:
        gt = server["gamertag"]
        name = f"{serv} {cluster} ({gt})"
    try:
        res = await rcon(
            command=command,
            host=server["ip"],
            port=server["port"],
            passwd=server["password"]
        )
        res = res.strip()
        resp = box(f"➣ {name}\n{res}", lang="python")
        if "Server received, But no response!!" in str(res):
            resp = box(f"✅ {name}", lang="python")
        await channel.send(resp)
    except Exception as e:
        if "121" in str(e):
            resp = box(f"- {name} has timed out and may be down", lang="diff")
            await channel.send(resp)
        elif "502 Bad Gateway" in str(e) and "Cloudflare" in str(e):
            log.warning("Async_RCON Error: Cloudflare Issue, Discord is borked not my fault.")
        else:
            resp = box(f"- {name} encountered an unknown error, see traceback for details.", lang="diff")
            await channel.send(resp)
            log.warning(f"Async_RCON Error: {e}")


