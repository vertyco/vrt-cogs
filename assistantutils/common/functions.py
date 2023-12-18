import string
from typing import List, Tuple, Union

import discord
from rapidfuzz import fuzz

from ..abc import MixinMeta
from .utils import clean_name


class Functions(MixinMeta):
    async def get_channel_name_from_id(
        self,
        guild: discord.Guild,
        channel_id: Union[str, int],
        user: discord.Member,
        *args,
        **kwargs,
    ):
        if isinstance(channel_id, str):
            if not channel_id.isdigit():
                return "channel_id must be a valid integer!"
        if channel := guild.get_channel_or_thread(int(channel_id)):
            if not channel.permissions_for(user).view_channel:
                return "The user you are chatting with doesnt have permission to view that channel"
            ctype = "voice" if isinstance(channel, discord.VoiceChannel) else "text"
            return f"the name of the {ctype} channel with ID {channel_id} is {channel.name}"
        return "a channel with that ID could not be found!"

    async def get_channel_id_from_name(
        self,
        guild: discord.Guild,
        channel_name: str,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        channels = list(guild.channels) + list(guild.threads) + list(guild.forums)
        valid_channels = [i for i in channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"

        matches = []
        for channel in valid_channels:
            if clean_name(channel.name) == channel_name:
                return channel.mention
            if channel.name == channel_name:
                return channel.mention
            name_score = fuzz.ratio(clean_name(channel.name), clean_name(channel_name.lower()))
            if name_score >= 80:
                matches.append((channel, name_score))

        if not matches:
            return "No channels found with that name or id!"

        matches.sort(key=lambda x: x[1], reverse=True)
        return str(matches[0][0].id)

    async def get_channel_mention(
        self,
        guild: discord.Guild,
        channel_name_or_id: str,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        channels = list(guild.channels) + list(guild.threads) + list(guild.forums)
        valid_channels = [i for i in channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"

        matches = []
        for channel in valid_channels:
            if clean_name(channel.name) == channel_name_or_id:
                return channel.mention
            if channel.name == channel_name_or_id:
                return channel.mention
            if str(channel.id) == channel_name_or_id:
                return channel.mention
            name_score = fuzz.ratio(clean_name(channel.name), clean_name(channel_name_or_id.lower()))
            if name_score >= 80:
                matches.append((channel, name_score))

            id_score = fuzz.ratio(str(channel.id), channel_name_or_id)
            if id_score > 90:
                matches.append((channel, id_score))

        if not matches:
            return "No channels found with that name or id!"

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0].mention

    async def get_channel_list(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        valid_channels = [i for i in guild.channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"
        txt = ""
        for channel in valid_channels:
            txt += f"{clean_name(channel.name)}\n"
        return txt

    async def get_channel_topic(
        self,
        guild: discord.Guild,
        channel_name_or_id: str,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        valid_channels = [i for i in guild.text_channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"

        notfound = "This channel does not have a topic set!"
        matches: List[Tuple[discord.TextChannel, int]] = []
        for channel in valid_channels:
            if clean_name(channel.name) == channel_name_or_id:
                return channel.topic or notfound
            if channel.name == channel_name_or_id:
                return channel.topic or notfound
            if str(channel.id) == channel_name_or_id:
                return channel.topic or notfound

            name_score = fuzz.ratio(clean_name(channel.name), clean_name(channel_name_or_id.lower()))
            if name_score >= 80:
                matches.append((channel, name_score))

            id_score = fuzz.ratio(str(channel.id), channel_name_or_id)
            if id_score > 90:
                matches.append((channel, id_score))

        if not matches:
            return "No channels found with that name or id!"

        matches = [i for i in matches if i[0].topic]
        if not matches:
            return "No channels found with a topic!"

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0].topic

    async def make_search_url(
        self,
        site: str,
        search_query: str,
        *args,
        **kwargs,
    ):
        site = site.lower()
        chars = string.ascii_letters + string.hexdigits
        for char in search_query:
            if char not in chars:
                search_query = search_query.replace(char, "")
        search_query = search_query.replace(" ", "+")
        if site == "youtube":
            return f"https://www.youtube.com/results?search_query={search_query}"
        return f"https://www.google.com/search?q={search_query}"

    async def get_user_from_id(
        self,
        guild: discord.Guild,
        discord_id: int,
        *args,
        **kwargs,
    ):
        member = guild.get_member(int(discord_id))
        if not member:
            return "A member with that ID does not exist!"
        return member.name
