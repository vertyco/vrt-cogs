import unicodedata
import re
import aiohttp
import discord
import json

from rcon.asyncio import rcon

from redbot.core.utils.chat_formatting import box

import logging
log = logging.getLogger("red.vrt.arktools")


# Manual RCON commands
async def manual_rcon(channel: discord.TextChannel, server: dict, command: str):
    try:
        res = await rcon(
            command=command,
            host=server["ip"],
            port=server["port"],
            passwd=server["password"]
        )
        res = res.rstrip()
        name = server["name"]
        cluster = server["cluster"]
        if command.lower() == "listplayers":
            await channel.send(f"**{name} {cluster}**\n{box(res, lang='python')}")
        else:
            await channel.send(box(f"{name} {cluster}\n{res}", lang="python"))
    except Exception as e:
        if "121" in str(e).lower():
            cname = server["cluster"]
            sname = server["name"]
            await channel.send(f"The **{sname}** **{cname}** server has timed out and is probably down.")
        else:
            log.warning(f"Manual RCON Error: {e}")


# API call for adding a user as a friend
async def add_friend(xuid: str, token: str):
    url = f"https://social.xboxlive.com/users/me/people/xuid({xuid})"
    headers = {
        'x-xbl-contract-version': '2',
        'Authorization': token
    }
    payload = {}
    async with aiohttp.ClientSession() as session:
        async with session.put(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for removing a user as a friend
async def remove_friend(xuid: str, token: str):
    url = f"https://social.xboxlive.com/users/me/people/xuid({xuid})"
    headers = {
        'x-xbl-contract-version': '2',
        'Authorization': token
    }
    payload = {}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for blocking a gamertaga
async def block_player(xuid: int, token: str):
    url = f"https://privacy.xboxlive.com/users/me/people/never"
    headers = {
        'x-xbl-contract-version': '2',
        'Authorization': token
    }
    payload = {"xuid": xuid}
    payload = json.dumps(payload)
    async with aiohttp.ClientSession() as session:
        async with session.put(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for blocking a gamertaga
async def unblock_player(xuid: int, token: str):
    url = f"https://privacy.xboxlive.com/users/me/people/never"
    headers = {
        'x-xbl-contract-version': '2',
        'Authorization': token
    }
    payload = {"xuid": xuid}
    payload = json.dumps(payload)
    async with aiohttp.ClientSession() as session:
        async with session.delete(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for retrieving followers
async def get_followers(token: str):
    url = "https://peoplehub.xboxlive.com/users/me/people/followers/decoration/details"
    headers = {
        'x-xbl-contract-version': '2',
        'Authorization': token,
        "Accept-Language": "en-US",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url=url, headers=headers) as res:
            return await res.json()





