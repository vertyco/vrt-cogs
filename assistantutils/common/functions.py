import asyncio
import json
from datetime import datetime
from io import StringIO
from typing import Literal

import discord
from dateutil import parser
from duckduckgo_search import DDGS
from rapidfuzz import fuzz
from redbot.core import commands

from ..abc import MixinMeta
from .utils import clean_name


class Functions(MixinMeta):
    async def get_channel_list(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        valid_channels = set(list(guild.channels) + list(guild.threads) + list(guild.forums))
        valid_channels = [i for i in valid_channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"
        buffer = StringIO()
        for channel in valid_channels:
            if topic := getattr(channel, "topic", None):
                text = f"{channel.name} (mention: {channel.mention}) - Topic: {topic}"
            else:
                text = f"{channel.name} (mention: {channel.mention})"
            buffer.write(f"{text}\n")
        return buffer.getvalue().strip()

    async def get_channel_info(
        self,
        guild: discord.Guild,
        user: discord.Member,
        channel_name_or_id: str,
        *args,
        **kwargs,
    ):
        def _fuzzymatch() -> discord.abc.GuildChannel | None:
            valid_channels = set(list(guild.channels) + list(guild.threads) + list(guild.forums))
            matches = []
            clean_query = clean_name(channel_name_or_id.lower())
            for c in valid_channels:
                matches.append((c, fuzz.ratio(clean_name(c.name), clean_query)))
                matches.append((c, fuzz.ratio(c.name, channel_name_or_id)))

            if matches:
                matches.sort(key=lambda x: x[1], reverse=True)
                return matches[0][0]
            return None

        channel_name_or_id = str(channel_name_or_id).strip()
        if channel_name_or_id.isdigit():
            channel = guild.get_channel(int(channel_name_or_id))
        else:
            channel = discord.utils.get(guild.channels, name=channel_name_or_id)
            if not channel:
                channel = await asyncio.to_thread(_fuzzymatch)

        if not channel:
            return f"Channel not found matching the name or ID: `{channel_name_or_id}`"

        if not channel.permissions_for(user).view_channel:
            return "The user you are talking to doesn't have permission to view that channel"
        if not channel.permissions_for(user).read_message_history:
            return "The user you are talking to doesn't have permission to read message history in that channel"

        buffer = StringIO()
        buffer.write(f"Channel Name: {channel.name}\n")
        buffer.write(f"Channel ID: {channel.id}\n")
        buffer.write(f"Channel Mention: {channel.mention}\n")
        buffer.write(f"Channel Type: {channel.type.name}\n")
        buffer.write(f"Created At: {channel.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buffer.write(f"Created At (Discord Format): <t:{int(channel.created_at.timestamp())}:F>\n")
        if topic := getattr(channel, "topic", None):
            buffer.write(f"Channel Topic: {topic}\n")
        if isinstance(channel, discord.VoiceChannel):
            buffer.write(f"Bitrate: {channel.bitrate}\n")
            buffer.write(f"User Limit: {channel.user_limit}\n")
        elif isinstance(channel, discord.TextChannel):
            buffer.write(f"NSFW: {channel.is_nsfw()}\n")
            buffer.write(f"Slowmode Delay: {channel.slowmode_delay} seconds\n")
        elif isinstance(channel, discord.ForumChannel):
            buffer.write(f"Default Reaction Emoji: {channel.default_reaction_emoji}\n")
            buffer.write(f"Default Sort Order: {channel.default_sort_order}\n")
            if channel.available_tags:
                buffer.write(f"Available Tags: {', '.join(channel.available_tags)}\n")
        return buffer.getvalue().strip()

    async def get_user_info(
        self,
        guild: discord.Guild,
        user_name_or_id: str,
        *args,
        **kwargs,
    ):
        def _fuzzymatch() -> discord.Member | None:
            matches = []
            clean_query = clean_name(user_name_or_id.lower())
            for member in guild.members:
                matches.append((member, fuzz.ratio(clean_name(member.name), clean_query)))
                matches.append((member, fuzz.ratio(member.name, user_name_or_id)))
                if member.display_name != member.name:
                    matches.append((member, fuzz.ratio(clean_name(member.display_name), clean_query)))
                    matches.append((member, fuzz.ratio(member.display_name, user_name_or_id)))

            if matches:
                matches.sort(key=lambda x: x[1], reverse=True)
                return matches[0][0]
            return None

        user_name_or_id = str(user_name_or_id).strip()
        if user_name_or_id.isdigit():
            user = guild.get_member(int(user_name_or_id))
        else:
            user = discord.utils.get(guild.members, name=user_name_or_id)
            if not user:
                user = discord.utils.get(guild.members, display_name=user_name_or_id)
                if not user:
                    user = await asyncio.to_thread(_fuzzymatch)

        if not user:
            return f"User not found for the name or ID: `{user_name_or_id}`"

        buffer = StringIO()
        buffer.write(f"Username: {user.name}\n")
        if user.display_name != user.name:
            buffer.write(f"Display Name: {user.display_name}\n")
        buffer.write(f"User ID: {user.id}\n")
        buffer.write(f"User Mention: {user.mention}\n")
        buffer.write(f"Created At: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buffer.write(f"Created At (Discord Format): <t:{int(user.created_at.timestamp())}:F>\n")
        buffer.write(f"Joined At: {user.joined_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buffer.write(f"Joined At (Discord Format): <t:{int(user.joined_at.timestamp())}:F>\n")

        for role in user.roles:
            if role.is_default():
                continue
            buffer.write(f"Role: {role.name} (Mention: {role.mention})\n")

        return buffer.getvalue().strip()

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
        delta: str = "",
        *args,
        **kwargs,
    ):
        if channel_name_or_id is not None:
            channel_name_or_id = str(channel_name_or_id)
            channel_name_or_id = channel_name_or_id.replace("#", "").replace("<", "").replace(">", "").strip()
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

        try:
            timedelta = commands.parse_timedelta(delta)
        except (ValueError, TypeError, commands.BadArgument):
            timedelta = None

        # Start fetching the content
        buffer = StringIO()
        added = 0
        async for message in channel.history():
            if added >= limit and not timedelta:
                break
            if timedelta:
                if message.created_at < (discord.utils.utcnow() - timedelta):
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
            f"# Message History (Current time: {discord.utils.utcnow()})\n"
            f"{final}"
        )
        return final

    async def convert_datetime_timestamp(
        self,
        date_or_timestamp: str,
        *args,
        **kwargs,
    ):
        date_or_timestamp = str(date_or_timestamp).strip()
        if date_or_timestamp.isdigit():
            # It's a timestamp
            try:
                timestamp = int(date_or_timestamp)
                return str(datetime.fromtimestamp(timestamp))
            except ValueError:
                return "Invalid timestamp format. Please provide a valid integer timestamp."
        else:
            # It's a date string
            try:
                date = parser.parse(date_or_timestamp)
                return str(int(date.timestamp()))
            except ValueError:
                return "Invalid date format. Please provide a valid date string in 'YYYY-MM-DD HH:MM:SS' format."

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
