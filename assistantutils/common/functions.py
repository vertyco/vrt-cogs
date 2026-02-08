import asyncio
import html as html_module
import json
import logging
import re
from datetime import datetime, timezone
from io import StringIO
from typing import Literal

import aiohttp
import discord
from dateutil import parser
from duckduckgo_search import DDGS
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import text_to_file

from ..abc import MixinMeta
from .utils import clean_name

log = logging.getLogger("red.vrt.assistantutils")


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
                buffer.write(f"Available Tags: {', '.join([str(tag) for tag in channel.available_tags])}\n")
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
        limit: int = None,
        delta: str = "1h",
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
            timedelta = commands.parse_timedelta(delta) if delta else None
        except (ValueError, TypeError, commands.BadArgument):
            timedelta = None

        if limit is None and timedelta is None:
            timedelta = commands.parse_timedelta("1h")
        elif timedelta is not None and timedelta > commands.parse_timedelta("7d"):
            return "Delta cannot be greater than 7 days to prevent excessive fetching."

        # Start fetching the content
        buffer = StringIO()
        added = 0
        async for message in channel.history(limit=limit):
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

    async def get_role_info(
        self,
        guild: discord.Guild,
        role_name_or_id: str,
        *args,
        **kwargs,
    ):
        def _fuzzymatch() -> discord.Role | None:
            matches = []
            clean_query = clean_name(role_name_or_id.lower())
            for role in guild.roles:
                matches.append((role, fuzz.ratio(clean_name(role.name), clean_query)))
                matches.append((role, fuzz.ratio(role.name.lower(), role_name_or_id.lower())))

            if matches:
                matches.sort(key=lambda x: x[1], reverse=True)
                return matches[0][0]
            return None

        role_name_or_id = str(role_name_or_id).strip()
        if role_name_or_id.isdigit():
            role = guild.get_role(int(role_name_or_id))
        else:
            role = discord.utils.get(guild.roles, name=role_name_or_id)
            if not role:
                role = await asyncio.to_thread(_fuzzymatch)

        if not role:
            return f"Role not found for the name or ID: `{role_name_or_id}`"

        buffer = StringIO()
        buffer.write(f"Role Name: {role.name}\n")
        buffer.write(f"Role ID: {role.id}\n")
        buffer.write(f"Role Mention: {role.mention}\n")
        buffer.write(f"Color: #{role.color.value:06x}\n")
        buffer.write(f"Position: {role.position}\n")
        buffer.write(f"Hoisted: {role.hoist}\n")
        buffer.write(f"Mentionable: {role.mentionable}\n")
        buffer.write(f"Managed: {role.managed}\n")
        buffer.write(f"Created At: {role.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buffer.write(f"Created At (Discord Format): <t:{int(role.created_at.timestamp())}:F>\n")
        buffer.write(f"Member Count: {len(role.members)}\n")

        # Key permissions
        perms = role.permissions
        key_perms = []
        if perms.administrator:
            key_perms.append("Administrator")
        if perms.manage_guild:
            key_perms.append("Manage Server")
        if perms.manage_channels:
            key_perms.append("Manage Channels")
        if perms.manage_roles:
            key_perms.append("Manage Roles")
        if perms.manage_messages:
            key_perms.append("Manage Messages")
        if perms.kick_members:
            key_perms.append("Kick Members")
        if perms.ban_members:
            key_perms.append("Ban Members")
        if perms.moderate_members:
            key_perms.append("Timeout Members")
        if key_perms:
            buffer.write(f"Key Permissions: {', '.join(key_perms)}\n")

        return buffer.getvalue().strip()

    async def get_server_info(
        self,
        guild: discord.Guild,
        *args,
        **kwargs,
    ):
        buffer = StringIO()
        buffer.write(f"Server Name: {guild.name}\n")
        buffer.write(f"Server ID: {guild.id}\n")
        buffer.write(f"Owner: {guild.owner.name if guild.owner else 'Unknown'} (ID: {guild.owner_id})\n")
        buffer.write(f"Created At: {guild.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buffer.write(f"Created At (Discord Format): <t:{int(guild.created_at.timestamp())}:F>\n")
        buffer.write(f"Member Count: {guild.member_count}\n")
        buffer.write(f"Role Count: {len(guild.roles)}\n")
        buffer.write(f"Channel Count: {len(guild.channels)}\n")
        buffer.write(f"Text Channels: {len(guild.text_channels)}\n")
        buffer.write(f"Voice Channels: {len(guild.voice_channels)}\n")
        buffer.write(f"Forum Channels: {len(guild.forums)}\n")
        buffer.write(f"Categories: {len(guild.categories)}\n")
        buffer.write(f"Emoji Count: {len(guild.emojis)}\n")
        buffer.write(f"Sticker Count: {len(guild.stickers)}\n")
        buffer.write(f"Boost Level: {guild.premium_tier}\n")
        buffer.write(f"Boost Count: {guild.premium_subscription_count}\n")
        buffer.write(f"Verification Level: {guild.verification_level.name}\n")
        buffer.write(f"Explicit Content Filter: {guild.explicit_content_filter.name}\n")
        if guild.description:
            buffer.write(f"Description: {guild.description}\n")
        if guild.vanity_url:
            buffer.write(f"Vanity URL: {guild.vanity_url}\n")
        buffer.write(f"Preferred Locale: {guild.preferred_locale}\n")

        # Features
        if guild.features:
            features = [f.replace("_", " ").title() for f in guild.features[:10]]
            buffer.write(f"Features: {', '.join(features)}\n")

        return buffer.getvalue().strip()

    async def fetch_url(self, url: str, *args, **kwargs) -> str:
        """
        Fetch the content of a URL and return the text.

        Args:
            url: The URL to fetch content from

        Returns:
            The text content of the page, or an error message
        """
        log.info(f"Fetching URL: {url}")

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status not in (200, 201):
                        return f"Failed to fetch URL: HTTP {response.status}"

                    content_type = response.headers.get("Content-Type", "")

                    if "text/html" in content_type:
                        html = await response.text()
                        # Remove script and style elements
                        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
                        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
                        # Remove HTML tags
                        text = re.sub(r"<[^>]+>", " ", html)
                        # Clean up whitespace
                        text = re.sub(r"\s+", " ", text).strip()
                        # Decode HTML entities
                        text = html_module.unescape(text)
                        # Limit response size
                        if len(text) > 50000:
                            text = text[:50000] + "\n\n[Content truncated...]"
                        return text
                    elif "application/json" in content_type:
                        return await response.text()
                    elif "text/" in content_type:
                        return await response.text()
                    else:
                        return f"Unsupported content type: {content_type}"

        except asyncio.TimeoutError:
            return "Request timed out after 30 seconds"
        except Exception as e:
            log.error(f"Error fetching URL {url}", exc_info=e)
            return f"Failed to fetch URL: {str(e)}"

    async def create_and_send_file(
        self,
        filename: str,
        content: str,
        channel: discord.TextChannel,
        comment: str = None,
        *args,
        **kwargs,
    ) -> str:
        """
        Create a file with the provided content and send it to the Discord channel.

        Args:
            filename: Name of the file including extension
            content: Content to write to the file
            comment: Optional comment to include when sending the file
            channel: The channel where the file will be sent

        Returns:
            A message confirming the file was sent
        """
        file = text_to_file(content, filename=filename)
        await channel.send(content=comment, file=file)
        return "File sent successfully!"

    async def add_reaction(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        message_id: str,
        emoji: str,
        *args,
        **kwargs,
    ) -> str:
        """
        Add a reaction to a message.

        Args:
            guild: The guild context
            channel: The channel containing the message
            message_id: The ID of the message to react to
            emoji: The emoji to add (unicode or custom emoji format)

        Returns:
            Success or error message
        """
        try:
            message_id = int(str(message_id).strip())
        except ValueError:
            return "Invalid message ID. Please provide a valid integer message ID."

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            return f"Message with ID {message_id} not found in this channel."
        except discord.Forbidden:
            return "I don't have permission to access that message."

        try:
            await message.add_reaction(emoji)
            return f"Successfully added reaction {emoji} to the message!"
        except discord.HTTPException as e:
            return f"Failed to add reaction: {e}"

    async def search_messages(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        query: str,
        channel_name_or_id: str = None,
        limit: int = 50,
        use_regex: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """
        Search for messages containing specific text or matching a regex pattern.

        Args:
            guild: The guild to search in
            channel: The default channel context
            user: The user performing the search
            query: The search query (text or regex pattern)
            channel_name_or_id: Optional specific channel to search in
            limit: Maximum number of messages to search through (default: 50)
            use_regex: Whether to treat the query as a regex pattern

        Returns:
            Matching messages formatted as a string
        """
        # Resolve channel if specified
        if channel_name_or_id:
            channel_name_or_id = str(channel_name_or_id).strip()
            if channel_name_or_id.isdigit():
                search_channel = guild.get_channel(int(channel_name_or_id))
            else:
                search_channel = discord.utils.get(guild.channels, name=channel_name_or_id)
            if search_channel:
                channel = search_channel

        if not channel:
            return "Channel not found!"

        if not channel.permissions_for(user).read_message_history:
            return "You don't have permission to read message history in that channel."
        if not channel.permissions_for(guild.me).read_message_history:
            return "I don't have permission to read message history in that channel."

        if isinstance(channel, (discord.VoiceChannel, discord.ForumChannel, discord.CategoryChannel)):
            return "This function only works for text channels."

        # Compile regex if needed
        pattern = None
        if use_regex:
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as e:
                return f"Invalid regex pattern: {e}"

        matches = []
        searched = 0
        async for message in channel.history(limit=min(limit, 500)):
            searched += 1
            content = message.content
            if not content:
                continue

            match_found = False
            if use_regex and pattern:
                if pattern.search(content):
                    match_found = True
            else:
                if query.lower() in content.lower():
                    match_found = True

            if match_found:
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                jump_url = message.jump_url
                preview = content[:200] + "..." if len(content) > 200 else content
                matches.append(f"[{timestamp}]({jump_url}) **{message.author.name}**: {preview}")

                if len(matches) >= 10:  # Limit to 10 results
                    break

        if not matches:
            return f"No messages found matching '{query}' in the last {searched} messages."

        result = f"Found {len(matches)} matching message(s) in {channel.mention}:\n\n"
        result += "\n\n".join(matches)
        return result

    async def run_command(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        command: str,
        *args,
        **kwargs,
    ) -> str:
        """
        Run a bot command on behalf of the user.

        Args:
            guild: The guild context
            channel: The channel to run the command in
            user: The user to run the command as
            command: The command string (without prefix)

        Returns:
            Result of the command execution
        """
        bot: Red = self.bot

        # Get prefix
        prefixes = await bot.get_valid_prefixes(guild=guild)
        prefix = prefixes[0] if len(prefixes) < 3 else prefixes[2]

        # Build message content
        content = f"{prefix}{command}"

        # Create a fake message
        created_at = datetime.now(tz=timezone.utc)
        message_id = discord.utils.time_snowflake(created_at)

        author_dict = {
            "id": f"{user.id}",
            "username": user.display_name,
            "avatar": user.avatar,
            "avatar_decoration": None,
            "discriminator": f"{user.discriminator}",
            "public_flags": user.public_flags,
            "bot": user.bot,
        }
        data = {
            "id": message_id,
            "type": 0,
            "content": content,
            "channel_id": f"{channel.id}",
            "author": author_dict,
            "attachments": [],
            "embeds": [],
            "mentions": [],
            "mention_roles": [],
            "pinned": False,
            "mention_everyone": False,
            "tts": False,
            "timestamp": str(created_at).replace(" ", "T") + "+00:00",
            "edited_timestamp": None,
            "flags": 0,
            "components": [],
            "referenced_message": None,
        }
        message = discord.Message(channel=channel, state=bot._connection, data=data)

        # Get context
        context: commands.Context = await bot.get_context(message)
        context.author = user
        context.guild = guild
        context.channel = channel

        if not context.valid:
            return f"Invalid command: `{command}`. The command was not found or is not available."

        # Check if user can run this command
        try:
            can_run = await context.command.can_run(context)
            if not can_run:
                return f"You don't have permission to run the command: `{command}`"
        except commands.CommandError as e:
            return f"Cannot run command: {e}"

        # Execute the command
        try:
            await bot.invoke(context)
            return f"Successfully executed command: `{command}`"
        except Exception as e:
            log.error(f"Error running command {command}", exc_info=e)
            return f"Error executing command: {e}"
