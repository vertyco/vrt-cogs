import unicodedata
import re
import aiohttp
import discord

from rcon.asyncio import rcon

from redbot.core.utils.chat_formatting import box

import logging
log = logging.getLogger("red.vrt.arktools")


# Send chat to servers(filters any unicode characters or custom discord emojis before hand since Ark doesnt like that)
async def serverchat(server: dict, message: discord.Message):
    author = message.author.name
    # Strip links, emojis, and unicode characters from message content before sending to server
    nolinks = re.sub(r'https?:\/\/[^\s]+', '', message.content)
    noemojis = re.sub(r'<:\w*:\d*>', '', nolinks)
    nocustomemojis = re.sub(r'<a:\w*:\d*>', '', noemojis)
    message = unicodedata.normalize('NFKD', nocustomemojis).encode('ascii', 'ignore').decode()
    if message == "":
        return
    if message == " ":
        return
    # Convert any unicode characters in member name to normal text
    normalizedname = unicodedata.normalize('NFKD', author).encode('ascii', 'ignore').decode()
    try:
        await rcon(
            command=f"serverchat {normalizedname}: {message}",
            host=server['ip'],
            port=server['port'],
            passwd=server['password'])
    except Exception as e:
        if "semaphor" in str(e):
            pass
        else:
            log.warning(f"serverchat: {e}")


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
        'x-xbl-contract-version': ' 2',
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
        'x-xbl-contract-version': ' 2',
        'Authorization': token
    }
    payload = {}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for blocking a gamertaga
async def block_player(xuid: str, token: str):
    url = f"https://privacy.xboxlive.com/users/me/people/never/xuid({xuid})"
    headers = {
        'x-xbl-contract-version': ' 2',
        'Authorization': token
    }
    payload = {}
    async with aiohttp.ClientSession() as session:
        async with session.put(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for blocking a gamertaga
async def unblock_player(xuid: str, token: str):
    url = f"https://privacy.xboxlive.com/users/me/people/never/xuid({xuid})"
    headers = {
        'x-xbl-contract-version': ' 2',
        'Authorization': token
    }
    payload = {}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url=url, headers=headers, data=payload) as res:
            return res.status


# API call for retrieving followers
async def get_followers(token: str):
    url = "https://peoplehub.xboxlive.com/users/me/people/followers/decoration/details"
    headers = {
        'x-xbl-contract-version': ' 2',
        'Authorization': token,
        "Accept-Language": "en-US",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url=url, headers=headers) as res:
            return await res.json()





