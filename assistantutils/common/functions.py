import asyncio
import json
import string
from datetime import datetime
from io import StringIO
from typing import List, Literal, Tuple, Union

import discord
from dateutil import parser
from duckduckgo_search import DDGS
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

    async def get_id_from_username(
        self,
        guild: discord.Guild,
        username: str,
        *args,
        **kwargs,
    ) -> str:
        named_members = {i.name: i.id for i in guild.members}
        nicknamed_members = {i.display_name: i.id for i in guild.members}
        user_id = None
        if username in named_members:
            user_id = named_members[username]
        elif username in nicknamed_members:
            user_id = nicknamed_members[username]

        if user_id:
            return f"The ID of {username} is {user_id}"

        # No exact match found, try fuzzy matching
        matches = []
        for member in guild.members:
            name_score = fuzz.ratio(member.name, username)
            if name_score >= 80:
                matches.append((member.name, member.id, name_score))
            nickname_score = fuzz.ratio(member.display_name, username)
            if nickname_score >= 80:
                matches.append((member.display_name, member.id, nickname_score))
        if matches:
            matches.sort(key=lambda x: x[2], reverse=True)
            # Get best match
            name, uid, score = matches[0]
            return f"The closest match for '{username}' is '{name}' with ID {uid} (fuzzy score: {score})"
        return "No user found with that name or nickname!"

    async def search_web_duckduckgo(self, query: str, num_results: int = 5, *args, **kwargs) -> str:
        def _search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))

        res: list[dict] = await asyncio.to_thread(_search)
        return json.dumps(res)

    async def fetch_channel_history(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        channel_name_or_id: str | int = None,
        limit: int = 30,
        *args,
        **kwargs,
    ):
        if channel_name_or_id is not None:
            channel_name_or_id = str(channel_name_or_id)
            if channel_name_or_id.isdigit():
                channel = guild.get_channel(int(channel_name_or_id))
            else:
                named_channels = {c.name: c for c in guild.channels}
                channel = named_channels.get(channel_name_or_id)
                if not channel:
                    # Try fuzzy matching
                    matches = []
                    for c in guild.channels:
                        name_score = fuzz.ratio(c.name, channel_name_or_id)
                        if name_score >= 80:
                            matches.append((c.name, c.id, name_score))
                        clean_name_score = fuzz.ratio(clean_name(c.name), clean_name(channel_name_or_id))
                        if clean_name_score >= 80:
                            matches.append((c.name, c.id, clean_name_score))
                    if matches:
                        matches.sort(key=lambda x: x[2], reverse=True)
                        channel_name, channel_id, score = matches[0]
                        channel = guild.get_channel(int(channel_id))

        if not channel:
            return "No channel found with that name or ID!"
        if not channel.permissions_for(channel.guild.me).view_channel:
            return "I do not have permission to view that channel"
        if not channel.permissions_for(channel.guild.me).read_message_history:
            return "I do not have permission to read message history in that channel"

        if not channel.permissions_for(user).view_channel:
            return "The user you are chatting with doesn't have permission to view that channel"
        if not channel.permissions_for(user).read_message_history:
            return "The user you are chatting with doesn't have permission to read message history in that channel"

        if isinstance(channel, discord.VoiceChannel):
            return "This function only works for text channels, not voice channels."
        if isinstance(channel, discord.ForumChannel):
            return "This function does not work for forum channels."
        if isinstance(channel, discord.CategoryChannel):
            return "This function does not work for category channels."

        # Start fetching the content
        buffer = StringIO()
        added = 0
        async for message in channel.history():
            if added >= limit:
                break
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            if message.content:
                buffer.write(f"{timestamp} - {message.author.name}(ID: {message.id}): {message.content}\n")
                added += 1
            elif message.embeds:
                for embed in message.embeds:
                    buffer.write(f"{timestamp} - {message.author.name}(ID: {message.id}): [Embed]{embed.to_dict()}\n")
                    added += 1
        final = buffer.getvalue().strip()
        if not final:
            return "No messages found in this channel history."
        base_jump_url = f"https://discord.com/channels/{guild.id}/{channel.id}/"
        final = (
            f"Here are the last {added} messages from {channel.name} (Mention: {channel.mention})\n"
            f"To link a specific message, format as `{base_jump_url}/<message_id>`\n"
            f"# Message History\n"
            f"{final}"
        )
        return final

    async def get_date_from_timestamp(self, timestamp: str, *args, **kwargs) -> str:
        timestamp = str(timestamp).strip()
        if not timestamp.isdigit():
            return "Invalid timestamp format. Please provide a valid integer timestamp."
        return str(datetime.fromtimestamp(int(timestamp)))

    async def get_discord_timestamp_format(
        self,
        date_or_timestamp: str,
        timestamp_format: Literal["d", "D", "t", "T", "f", "F", "R"] = "F",
        *args,
        **kwargs,
    ) -> str:
        if date_or_timestamp.isdigit():
            timestamp = int(date_or_timestamp)
        else:
            try:
                date = parser.parse(date_or_timestamp)
                timestamp = int(date.timestamp())
            except ValueError:
                return "Invalid date or timestamp format. Please provide a valid date string or integer timestamp."
        if timestamp_format not in ["d", "D", "t", "T", "f", "F", "R"]:
            return "Invalid timestamp format. Please use one of the following: d, D, t, T, f, F, R."
        return f"<t:{timestamp}:{timestamp_format}>"

    async def get_user_roles(self, user: discord.Member, *args, **kwargs) -> str:
        buffer = StringIO()
        for role in user.roles:
            if role.is_default():
                continue
            buffer.write(f"{role.name} (ID: {role.id})\n")
        roles = buffer.getvalue().strip()
        if not roles:
            return "This user has no roles."
        return buffer.getvalue().strip()
