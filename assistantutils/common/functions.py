import asyncio
import html as html_module
import logging
import re
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Literal, Union

import aiohttp
import discord
import resvg_py
from dateutil import parser
from redbot.core import commands, modlog
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import text_to_file

from ..abc import MixinMeta
from .utils import (
    find_category,
    find_channel,
    find_member,
    find_role,
    normalize_channel_type,
    split_permission_overwrite,
    svg_font_dirs,
)

log = logging.getLogger("red.vrt.assistantutils")


class Functions(MixinMeta):
    def get_channel_parent(self, channel: discord.abc.GuildChannel | discord.Thread):
        if isinstance(channel, discord.Thread):
            return channel.parent
        if category := getattr(channel, "category", None):
            return category
        return getattr(channel, "parent", None)

    def render_channel_overwrites(self, channel: discord.abc.GuildChannel | discord.Thread, limit: int = 10) -> str:
        overwrites = getattr(channel, "overwrites", None)
        if not overwrites:
            return "Inherited or not explicitly set."

        lines: list[str] = []
        overwrite_items = list(overwrites.items())
        for target, overwrite in overwrite_items[:limit]:
            allowed, denied = split_permission_overwrite(overwrite)
            if not allowed and not denied:
                continue
            target_name = getattr(target, "mention", None) or getattr(target, "name", str(target))
            parts: list[str] = []
            if allowed:
                parts.append(f"allow: {', '.join(allowed[:8])}")
            if denied:
                parts.append(f"deny: {', '.join(denied[:8])}")
            lines.append(f"{target_name} -> {' | '.join(parts)}")

        if not lines:
            return "Inherited or not explicitly set."
        if len(overwrite_items) > limit:
            lines.append(f"... and {len(overwrite_items) - limit} more overwrite(s)")
        return "\n".join(lines)

    def normalize_permission_names(self, permissions: list[str] | None) -> tuple[list[str], list[str]]:
        valid_flags = discord.Permissions.VALID_FLAGS
        normalized: list[str] = []
        invalid: list[str] = []
        for permission_name in permissions or []:
            cleaned = str(permission_name).strip().lower().replace("-", "_").replace(" ", "_")
            if cleaned in valid_flags:
                normalized.append(cleaned)
            else:
                invalid.append(str(permission_name))
        return sorted(set(normalized)), invalid

    def coerce_string_list(self, values: list[str] | str | None) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            return [item.strip() for item in values.split(",") if item.strip()]
        return [str(item).strip() for item in values if str(item).strip()]

    def parse_named_enum(self, enum_cls, value: str | None, field_name: str):
        if value is None:
            return None, None
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        member = enum_cls.__members__.get(normalized)
        if member is None:
            choices = ", ".join(sorted(enum_cls.__members__))
            return None, f"Invalid `{field_name}`. Valid values: {choices}"
        return member, None

    def parse_color_value(self, color: str | int | None) -> tuple[int | None, str | None]:
        if color is None:
            return None, None
        if isinstance(color, int):
            if 0 <= color <= 0xFFFFFF:
                return color, None
            return None, "Color integers must be between 0 and 16777215."

        cleaned = str(color).strip().lower()
        if cleaned in {"none", "null", "clear", "remove"}:
            return None, None
        if cleaned.startswith("#"):
            cleaned = cleaned[1:]
        if cleaned.startswith("0x"):
            cleaned = cleaned[2:]
        if len(cleaned) != 6 or any(ch not in "0123456789abcdef" for ch in cleaned):
            return None, "Colors must be a 6-digit hex value like `#5865F2`."
        return int(cleaned, 16), None

    def build_role_permissions(
        self, permissions: list[str] | str | None
    ) -> tuple[discord.Permissions | None, list[str], str | None]:
        raw_permissions = self.coerce_string_list(permissions)
        if permissions is None:
            return None, [], None
        normalized, invalid = self.normalize_permission_names(raw_permissions)
        if invalid:
            return None, [], f"Invalid permission names: {', '.join(sorted(set(invalid)))}"

        perms = discord.Permissions.none()
        for permission_name in normalized:
            setattr(perms, permission_name, True)
        return perms, normalized, None

    async def fetch_remote_asset(self, url: str, field_name: str) -> tuple[bytes | None, str | None]:
        cleaned = str(url).strip()
        if not cleaned.startswith(("http://", "https://")):
            return None, f"`{field_name}` must be an http or https URL."
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cleaned, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status not in (200, 201):
                        return None, f"Failed to fetch `{field_name}` asset: HTTP {response.status}"
                    content_type = response.headers.get("Content-Type", "")
                    if not content_type.startswith("image/"):
                        return None, f"`{field_name}` URL must point to an image."
                    data = await response.read()
                    if not data:
                        return None, f"`{field_name}` URL returned empty content."
                    return data, None
        except asyncio.TimeoutError:
            return None, f"Fetching `{field_name}` timed out."
        except Exception as e:
            return None, f"Failed to fetch `{field_name}` asset: {e}"

    async def resolve_display_icon_input(self, display_icon: str | None) -> tuple[bytes | str | None, str | None]:
        if display_icon is None:
            return None, None
        cleaned = str(display_icon).strip()
        if not cleaned or cleaned.lower() in {"none", "null", "clear", "remove"}:
            return None, None
        if cleaned.startswith(("http://", "https://")):
            return await self.fetch_remote_asset(cleaned, "display_icon")
        return cleaned, None

    async def resolve_optional_image_input(self, value: str | None, field_name: str) -> tuple[bytes | None, str | None]:
        if value is None:
            return None, None
        cleaned = str(value).strip()
        if not cleaned or cleaned.lower() in {"none", "null", "clear", "remove"}:
            return None, None
        return await self.fetch_remote_asset(cleaned, field_name)

    def parse_partial_emoji(
        self,
        guild: discord.Guild,
        emoji_input: str | None,
    ) -> tuple[discord.PartialEmoji | str | None, str | None]:
        if emoji_input is None:
            return None, None
        cleaned = str(emoji_input).strip()
        if not cleaned:
            return None, None
        if cleaned.lower() in {"none", "null", "clear", "remove"}:
            return None, None

        emoji = discord.PartialEmoji.from_str(cleaned)
        if emoji.id is not None and guild.get_emoji(emoji.id) is None:
            return None, f"Custom emoji `{emoji_input}` was not found in this server."
        if emoji.id is None and emoji.name:
            return emoji.name, None
        return emoji, None

    def build_forum_tag_objects(self, tag_names: list[str] | str | None) -> list[discord.ForumTag]:
        tags: list[discord.ForumTag] = []
        seen: set[str] = set()
        for tag_name in self.coerce_string_list(tag_names):
            normalized = tag_name[:20]
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            tags.append(discord.ForumTag(name=normalized))
        return tags

    def resolve_forum_tags(
        self,
        forum: discord.ForumChannel,
        tag_names_or_ids: list[str] | str | None,
    ) -> tuple[list[discord.ForumTag], list[str]]:
        resolved: list[discord.ForumTag] = []
        missing: list[str] = []
        for raw_value in self.coerce_string_list(tag_names_or_ids):
            tag = None
            if raw_value.isdigit():
                tag = forum.get_tag(int(raw_value))
            if tag is None:
                tag = discord.utils.find(lambda item: item.name.lower() == raw_value.lower(), forum.available_tags)
            if tag is None:
                missing.append(raw_value)
                continue
            resolved.append(tag)
        return resolved, missing

    def format_change_summary(self, heading: str, changes: dict[str, object]) -> str:
        if not changes:
            return f"{heading}\n- No changes provided."
        lines = [heading]
        for key, value in changes.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def resolve_permission_target(
        self,
        guild: discord.Guild,
        target_type: str,
        target_name_or_id: str,
    ) -> discord.Role | discord.Member | None:
        if target_type in {"member", "user"}:
            return find_member(guild, target_name_or_id)
        if target_type == "role":
            return find_role(guild, target_name_or_id)
        return None

    def get_requesting_admin(self, guild: discord.Guild, kwargs: dict) -> tuple[discord.Member | None, str | None]:
        user = kwargs.get("user")
        if not isinstance(user, discord.Member) or user.guild.id != guild.id:
            return None, "Unable to verify the requesting admin for this action."
        return user, None

    def user_has_guild_permission(self, user: discord.Member, permission_name: str) -> bool:
        if user.id == user.guild.owner_id:
            return True
        perms = user.guild_permissions
        return perms.administrator or getattr(perms, permission_name, False)

    def user_has_channel_permission(
        self,
        user: discord.Member,
        channel: discord.abc.GuildChannel | discord.Thread,
        permission_name: str,
    ) -> bool:
        if user.id == user.guild.owner_id:
            return True
        perms = channel.permissions_for(user)
        return perms.administrator or getattr(perms, permission_name, False)

    def ensure_guild_permission(self, user: discord.Member, permission_name: str, action: str) -> str | None:
        if self.user_has_guild_permission(user, permission_name):
            return None
        return f"You do not have permission to {action}. Required Discord permission: `{permission_name}`."

    def ensure_channel_permission(
        self,
        user: discord.Member,
        channel: discord.abc.GuildChannel | discord.Thread,
        permission_name: str,
        action: str,
    ) -> str | None:
        if self.user_has_channel_permission(user, channel, permission_name):
            return None
        return f"You do not have permission to {action}. Required Discord permission: `{permission_name}`."

    def ensure_permission_subset(self, user: discord.Member, permission_names: list[str], action: str) -> str | None:
        if self.user_has_guild_permission(user, "administrator"):
            return None
        missing = [
            permission_name
            for permission_name in permission_names
            if not getattr(user.guild_permissions, permission_name, False)
        ]
        if not missing:
            return None
        return (
            f"You do not have permission to {action} with these permission flags: {', '.join(missing)}. "
            "The bot will not grant permissions you do not have."
        )

    def can_manage_role(self, user: discord.Member, role: discord.Role) -> bool:
        if role.is_default() or role.managed:
            return False
        if user.id == user.guild.owner_id:
            return True
        if not self.user_has_guild_permission(user, "manage_roles"):
            return False
        return role < user.top_role

    def ensure_role_manageable(self, user: discord.Member, role: discord.Role, action: str) -> str | None:
        if self.can_manage_role(user, role):
            return None
        return f"You do not have permission to {action} for role `{role.name}`."

    def ensure_role_position(self, user: discord.Member, position: int | None, action: str) -> str | None:
        if position is None or user.id == user.guild.owner_id:
            return None
        if position >= user.top_role.position:
            return f"You do not have permission to {action} at or above your top role position."
        return None

    async def get_channel_list(
        self,
        guild: discord.Guild,
        user: discord.Member,
        *args,
        **kwargs,
    ):
        valid_channels = set(
            list(guild.channels)
            + list(guild.threads)
            + list(guild.forums)
            + list(guild.categories)
            + list(guild.voice_channels)
        )
        valid_channels = [i for i in valid_channels if i.permissions_for(user).view_channel]
        if not valid_channels:
            return "There are no channels this user can view"
        valid_channels = sorted(
            valid_channels,
            key=lambda channel: (
                channel.type.name,
                getattr(self.get_channel_parent(channel), "name", ""),
                getattr(channel, "position", 0),
                channel.name.lower(),
            ),
        )
        buffer = StringIO()
        for channel in valid_channels:
            details = [
                f"ID: {channel.id}",
                f"Mention: {channel.mention}",
                f"Type: {channel.type.name.replace('_', ' ')}",
            ]
            if parent := self.get_channel_parent(channel):
                details.append(f"Parent: {parent.name}")
            if topic := getattr(channel, "topic", None):
                details.append(f"Topic: {topic}")
            text = f"{channel.name} ({', '.join(details)})"
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
        channel = await asyncio.to_thread(find_channel, guild, channel_name_or_id)
        if not channel:
            return f"Channel not found matching the name or ID: `{channel_name_or_id}`"

        if not channel.permissions_for(user).view_channel:
            return "The user you are talking to doesn't have permission to view that channel"

        buffer = StringIO()
        buffer.write(f"Channel Name: {channel.name}\n")
        buffer.write(f"Channel ID: {channel.id}\n")
        buffer.write(f"Channel Mention: {channel.mention}\n")
        buffer.write(f"Channel Type: {channel.type.name}\n")
        buffer.write(f"Channel Position: {getattr(channel, 'position', 'n/a')}\n")
        buffer.write(f"Created At: {channel.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buffer.write(f"Created At (Discord Format): <t:{int(channel.created_at.timestamp())}:F>\n")
        if parent := self.get_channel_parent(channel):
            buffer.write(f"Parent: {parent.name} (ID: {parent.id})\n")
        permissions_synced = getattr(channel, "permissions_synced", None)
        if permissions_synced is not None:
            buffer.write(f"Permissions Synced: {permissions_synced}\n")
        if topic := getattr(channel, "topic", None):
            buffer.write(f"Channel Topic: {topic}\n")
        if isinstance(channel, discord.StageChannel):
            buffer.write(f"Bitrate: {channel.bitrate}\n")
            buffer.write(f"User Limit: {channel.user_limit}\n")
            if channel.topic:
                buffer.write(f"Stage Topic: {channel.topic}\n")
        elif isinstance(channel, discord.VoiceChannel):
            buffer.write(f"Bitrate: {channel.bitrate}\n")
            buffer.write(f"User Limit: {channel.user_limit}\n")
        elif isinstance(channel, discord.TextChannel):
            buffer.write(f"NSFW: {channel.is_nsfw()}\n")
            buffer.write(f"Slowmode Delay: {channel.slowmode_delay} seconds\n")
        elif isinstance(channel, discord.Thread):
            buffer.write(f"Archived: {channel.archived}\n")
            buffer.write(f"Locked: {channel.locked}\n")
            buffer.write(f"Message Count: {channel.message_count}\n")
        elif isinstance(channel, discord.ForumChannel):
            buffer.write(f"NSFW: {channel.is_nsfw()}\n")
            buffer.write(f"Slowmode Delay: {channel.slowmode_delay} seconds\n")
            buffer.write(f"Default Reaction Emoji: {channel.default_reaction_emoji}\n")
            buffer.write(f"Default Sort Order: {channel.default_sort_order}\n")
            if channel.available_tags:
                buffer.write(f"Available Tags: {', '.join([str(tag) for tag in channel.available_tags])}\n")
        elif isinstance(channel, discord.CategoryChannel):
            buffer.write(f"Child Channel Count: {len(channel.channels)}\n")
            buffer.write(f"NSFW: {channel.is_nsfw()}\n")
        buffer.write(f"Permission Overwrites:\n{self.render_channel_overwrites(channel)}")
        return buffer.getvalue().strip()

    async def get_user_info(
        self,
        guild: discord.Guild,
        user_name_or_id: str,
        *args,
        **kwargs,
    ):
        user = await asyncio.to_thread(find_member, guild, user_name_or_id)

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

    async def fetch_channel_history(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        channel_name_or_id: str | int = None,
        limit: int = None,
        delta: str | None = None,
        *args,
        **kwargs,
    ):
        if channel_name_or_id is not None:
            channel_override = await asyncio.to_thread(find_channel, guild, channel_name_or_id)
            if not channel_override:
                return f"No channel found matching '{channel_name_or_id}'."
            channel = channel_override
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

        if timedelta is not None and timedelta > commands.parse_timedelta("7d"):
            return "Delta cannot be greater than 7 days to prevent excessive fetching."

        if limit is None and timedelta is None:
            limit = 50

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
                    # Format embed more cleanly for AI parsing
                    embed_parts = []
                    if embed.author and embed.author.name:
                        embed_parts.append(f"Author: {embed.author.name}")
                    if embed.title:
                        embed_parts.append(f"Title: {embed.title}")
                    if embed.description:
                        embed_parts.append(f"Description: {embed.description}")
                    for field in embed.fields:
                        embed_parts.append(f"{field.name}: {field.value}")
                    if embed.footer and embed.footer.text:
                        embed_parts.append(f"Footer: {embed.footer.text}")
                    for field in embed.fields:
                        embed_parts.append(f"{field.name}: {field.value}")

                    if embed_parts:
                        embed_text = " | ".join(embed_parts)
                        buffer.write(f"{timestamp} - {message.author.name}(ID: {message.id}): [Embed] {embed_text}\n")
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
        role = await asyncio.to_thread(find_role, guild, role_name_or_id)

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
    ) -> dict:
        """
        Create a file with the provided content and send it to the Discord channel.

        Args:
            filename: Name of the file including extension
            content: Content to write to the file
            comment: Optional comment to include when sending the file
            channel: The channel where the file will be sent

        Returns:
            A dict with deferred file and result content
        """
        file = text_to_file(content, filename=filename)
        result = {"content": comment or f"File '{filename}' generated.", "defer_files": [file]}
        return result

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
            channel_override = await asyncio.to_thread(find_channel, guild, channel_name_or_id)
            if not channel_override:
                return f"No channel found matching '{channel_name_or_id}'."
            channel = channel_override

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

            # Build searchable content from message content + embeds
            searchable_parts = []
            if message.content:
                searchable_parts.append(message.content)

            # Extract text from embeds
            for embed in message.embeds:
                if embed.title:
                    searchable_parts.append(embed.title)
                if embed.description:
                    searchable_parts.append(embed.description)
                if embed.author and embed.author.name:
                    searchable_parts.append(embed.author.name)
                if embed.footer and embed.footer.text:
                    searchable_parts.append(embed.footer.text)
                for field in embed.fields:
                    if field.name:
                        searchable_parts.append(field.name)
                    if field.value:
                        searchable_parts.append(field.value)

            if not searchable_parts:
                continue

            combined_content = "\n".join(searchable_parts)

            match_found = False
            if use_regex and pattern:
                if pattern.search(combined_content):
                    match_found = True
            else:
                if query.lower() in combined_content.lower():
                    match_found = True

            if match_found:
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                jump_url = message.jump_url

                # Build full content from message content or embed
                if message.content:
                    content_text = message.content
                elif message.embeds and message.embeds[0].description:
                    content_text = f"[Embed] {message.embeds[0].description}"
                else:
                    content_text = "[Embed with no description]"

                matches.append(f"[{timestamp}]({jump_url}) **{message.author.name}**: {content_text}")

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

        # Handle Red's Alias cog
        if (
            not context.valid
            and context.prefix is not None
            and (alias_cog := bot.get_cog("Alias")) is not None
            and not await bot.cog_disabled_in_guild(alias_cog, guild)
        ):
            alias = await alias_cog._aliases.get_alias(guild, context.invoked_with)  # type: ignore
            if alias is not None:

                async def alias_callback(__, ctx: commands.Context):
                    await alias_cog.call_alias(ctx.message, ctx.prefix, alias)  # type: ignore

                context.command = commands.command(name=command)(alias_callback)
                context.command.cog = alias_cog
                context.command.params.clear()
                context.command.requires.ready_event.set()

        # Handle Red's CustomCommands cog
        if (
            not context.valid
            and context.prefix is not None
            and (cc_cog := bot.get_cog("CustomCommands")) is not None
            and not await bot.cog_disabled_in_guild(cc_cog, guild)
        ):
            try:
                raw_response, cooldowns = await cc_cog.commandobj.get(message=message, command=context.invoked_with)  # type: ignore
                if isinstance(raw_response, list):
                    import random

                    raw_response = random.choice(raw_response)

                async def cc_callback(__, ctx: commands.Context):
                    try:
                        if cooldowns:
                            cc_cog.test_cooldowns(context, context.invoked_with, cooldowns)  # type: ignore
                    except Exception:
                        return
                    del ctx.args[0]
                    await cc_cog.cc_command(*ctx.args, **ctx.kwargs, raw_response=raw_response)  # type: ignore

                context.command = commands.command(name=command)(cc_callback)
                context.command.cog = cc_cog
                context.command.requires.ready_event.set()
                context.command.params = cc_cog.prepare_args(raw_response)  # type: ignore
            except Exception:
                pass

        # Handle Phen/Lemon's Tags cog
        if (
            not context.valid
            and context.prefix is not None
            and (tags_cog := bot.get_cog("Tags")) is not None
            and not await bot.cog_disabled_in_guild(tags_cog, guild)
        ):
            tag = tags_cog.get_tag(guild, context.invoked_with, check_global=True)  # type: ignore
            if tag is not None:
                message.content = f"{context.prefix}invoketag {command}"
                context = await bot.get_context(message)
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

    async def get_modlog_cases(
        self,
        guild: discord.Guild,
        user: discord.Member,
        user_name_or_id: str,
        *args,
        **kwargs,
    ) -> str:
        """Get modlog cases (bans, kicks, mutes, etc.) for a user."""
        bot: Red = self.bot

        # Resolve the target member
        member = await asyncio.to_thread(find_member, guild, user_name_or_id)
        if member is not None:
            member_id = member.id
        else:
            user_name_or_id = str(user_name_or_id).strip()
            if not user_name_or_id.isdigit():
                return f"User not found for the name or ID: `{user_name_or_id}`"
            member_id = int(user_name_or_id)

        try:
            cases = await modlog.get_cases_for_member(guild=guild, bot=bot, member_id=member_id)
        except Exception as e:
            return f"Error retrieving modlog cases: {e}"

        if not cases:
            return f"No modlog cases found for user ID {member_id}."

        buffer = StringIO()
        buffer.write(f"Modlog cases for user ID {member_id} ({len(cases)} total):\n\n")
        for case in cases:
            # Case number and type
            buffer.write(f"Case #{case.case_number} | {case.action_type}\n")

            # User
            if isinstance(case.user, int):
                buffer.write(f"  User: ID {case.user}\n")
            else:
                buffer.write(f"  User: {case.user} (ID: {case.user.id})\n")

            # Moderator
            if case.moderator is None:
                buffer.write("  Moderator: Unknown\n")
            elif isinstance(case.moderator, int):
                buffer.write(f"  Moderator: ID {case.moderator}\n")
            else:
                buffer.write(f"  Moderator: {case.moderator} (ID: {case.moderator.id})\n")

            # Reason
            buffer.write(f"  Reason: {case.reason or 'No reason provided'}\n")

            # Timestamp
            created = datetime.fromtimestamp(case.created_at, tz=timezone.utc)
            buffer.write(f"  Date: {created.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            buffer.write(f"  Date (Discord): <t:{case.created_at}:F>\n")

            # Duration info
            if case.until:
                buffer.write(f"  Until: <t:{case.until}:F>\n")

            # Channel
            if case.channel:
                if isinstance(case.channel, int):
                    buffer.write(f"  Channel: ID {case.channel} (deleted)\n")
                else:
                    buffer.write(f"  Channel: {case.channel.name}\n")

            buffer.write("\n")

        return buffer.getvalue().strip()

    async def fetch_category_channels(
        self,
        guild: discord.Guild,
        user: discord.Member,
        category_name_or_id: str,
        *args,
        **kwargs,
    ) -> str:
        """Get a list of all channels within a specific category."""
        category = await asyncio.to_thread(find_category, guild, category_name_or_id)

        if not category:
            available = ", ".join(c.name for c in guild.categories)
            return f"No category found matching '{category_name_or_id}'. Available categories: {available}"

        channels = category.channels
        if not channels:
            return f"The category '{category.name}' has no channels."

        # Filter to channels the user can see
        visible = [ch for ch in channels if ch.permissions_for(user).view_channel]
        if not visible:
            return f"The user has no visible channels in the '{category.name}' category."

        buffer = StringIO()
        buffer.write(f"Channels in '{category.name}' (ID: {category.id}):\n")
        for ch in visible:
            ch_type = ch.type.name.replace("_", " ")
            line = f"- {ch.name} (ID: {ch.id}, Type: {ch_type}, Mention: {ch.mention})"
            if topic := getattr(ch, "topic", None):
                line += f" - Topic: {topic}"
            buffer.write(f"{line}\n")

        return buffer.getvalue().strip()

    async def send_message_to_channel(
        self,
        guild: discord.Guild,
        channel_name_or_id: str,
        message_content: str,
        *args,
        **kwargs,
    ) -> str:
        """Send a message to a specific channel as the bot."""
        target = await asyncio.to_thread(find_channel, guild, channel_name_or_id)

        if not target:
            return f"No channel found matching '{channel_name_or_id}'."

        if not hasattr(target, "send"):
            return f"'{target.name}' is not a channel you can send messages to."

        perms = target.permissions_for(guild.me)
        if not perms.send_messages:
            return f"You don't have permission to send messages in {target.mention}."

        if len(message_content) > 2000:
            return "Message content exceeds the 2000 character Discord limit. Please shorten it."

        try:
            await target.send(message_content)
            return f"Message sent to {target.mention} successfully."
        except discord.HTTPException as e:
            return f"Failed to send message: {e.text}"

    async def get_pinned_messages(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        channel_name_or_id: str = None,
        *args,
        **kwargs,
    ) -> str:
        """Fetch pinned messages from a channel."""
        if channel_name_or_id is not None:
            channel_override = await asyncio.to_thread(find_channel, guild, channel_name_or_id)
            if not channel_override:
                return f"No channel found matching '{channel_name_or_id}'."
            channel = channel_override

        if not hasattr(channel, "pins"):
            return f"'{channel.name}' does not support pinned messages."

        if not channel.permissions_for(user).view_channel:
            return "The user doesn't have permission to view that channel."
        if not channel.permissions_for(guild.me).view_channel:
            return "I don't have permission to view that channel."

        try:
            pins = await channel.pins()
        except discord.HTTPException as e:
            return f"Failed to fetch pinned messages: {e.text}"

        if not pins:
            return f"There are no pinned messages in {channel.mention}."

        buffer = StringIO()
        buffer.write(f"Pinned messages in {channel.name} ({len(pins)} total):\n\n")
        for msg in pins:
            timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            buffer.write(f"[{timestamp}] {msg.author.name} (Message ID: {msg.id}):\n")
            if msg.content:
                buffer.write(f"  {msg.content[:500]}")
                if len(msg.content) > 500:
                    buffer.write("... (truncated)")
                buffer.write("\n")
            if msg.embeds:
                for embed in msg.embeds:
                    parts = []
                    if embed.title:
                        parts.append(f"Title: {embed.title}")
                    if embed.description:
                        parts.append(f"Description: {embed.description[:300]}")
                    for field in embed.fields:
                        parts.append(f"{field.name}: {(field.value or '')[:200]}")
                    if parts:
                        buffer.write(f"  [Embed] {' | '.join(parts)}\n")
            if msg.attachments:
                for att in msg.attachments:
                    buffer.write(f"  [Attachment] {att.filename} ({att.url})\n")
            buffer.write("\n")

        return buffer.getvalue().strip()

    async def edit_bot_message(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        message_id: str,
        new_content: str,
        *args,
        **kwargs,
    ) -> str:
        """Edit a message previously sent by the bot."""
        try:
            msg_id = int(str(message_id).strip())
        except ValueError:
            return f"Invalid message ID: '{message_id}'. Must be a numeric ID."

        if len(new_content) > 2000:
            return "New content exceeds the 2000 character Discord limit. Please shorten it."

        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return f"No message found with ID `{msg_id}` in {channel.mention}."
        except discord.Forbidden:
            return f"I don't have permission to read messages in {channel.mention}."
        except discord.HTTPException as e:
            return f"Failed to fetch message: {e.text}"

        if message.author.id != guild.me.id:
            return "I can only edit messages that I sent. That message was sent by someone else."

        try:
            await message.edit(content=new_content)
            return f"Message `{msg_id}` has been edited successfully."
        except discord.HTTPException as e:
            return f"Failed to edit message: {e.text}"

    async def manage_channel(
        self,
        guild: discord.Guild,
        action: Literal["create", "edit", "move", "delete"],
        channel_name_or_id: str | None = None,
        channel_type: Literal["text", "voice", "stage", "forum", "category"] | None = None,
        name: str | None = None,
        category_name_or_id: str | None = None,
        position: int | None = None,
        topic: str | None = None,
        news: bool | None = None,
        nsfw: bool | None = None,
        slowmode_delay: int | None = None,
        default_auto_archive_duration: int | None = None,
        default_thread_slowmode_delay: int | None = None,
        user_limit: int | None = None,
        bitrate: int | None = None,
        rtc_region: str | None = None,
        video_quality_mode: Literal["auto", "full"] | None = None,
        media: bool | None = None,
        default_reaction_emoji: str | None = None,
        default_sort_order: Literal["latest_activity", "creation_date"] | None = None,
        default_layout: Literal["list_view", "gallery_view", "not_set"] | None = None,
        available_tags: list[str] | str | None = None,
        sync_permissions: bool | None = None,
        reason: str | None = None,
        dry_run: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Create, edit, move, or delete guild channels through one unified tool."""
        user, user_error = self.get_requesting_admin(guild, kwargs)
        if user_error:
            return user_error

        action = str(action).strip().lower()
        if action not in {"create", "edit", "move", "delete"}:
            return "Invalid action. Use one of: create, edit, move, delete."

        if position is not None and position < 0:
            return "Channel position must be 0 or greater."
        if slowmode_delay is not None and slowmode_delay < 0:
            return "Slowmode delay must be 0 or greater."
        if default_thread_slowmode_delay is not None and default_thread_slowmode_delay < 0:
            return "Default thread slowmode delay must be 0 or greater."
        if user_limit is not None and user_limit < 0:
            return "User limit must be 0 or greater."
        if bitrate is not None and bitrate < 8000:
            return "Bitrate must be at least 8000."

        video_quality_enum, video_quality_error = self.parse_named_enum(
            discord.VideoQualityMode,
            video_quality_mode,
            "video_quality_mode",
        )
        if video_quality_error:
            return video_quality_error

        sort_order_enum, sort_order_error = self.parse_named_enum(
            discord.ForumOrderType,
            default_sort_order,
            "default_sort_order",
        )
        if sort_order_error:
            return sort_order_error

        layout_enum, layout_error = self.parse_named_enum(
            discord.ForumLayoutType,
            default_layout,
            "default_layout",
        )
        if layout_error:
            return layout_error

        reaction_emoji, reaction_error = self.parse_partial_emoji(guild, default_reaction_emoji)
        if reaction_error:
            return reaction_error

        forum_tags = self.build_forum_tag_objects(available_tags)

        category = None
        category_explicit = category_name_or_id is not None and str(category_name_or_id).strip() != ""
        if category_explicit:
            category_query = str(category_name_or_id).strip()
            if category_query.lower() not in {"none", "null", "remove", "uncategorized", "no category"}:
                category = await asyncio.to_thread(find_category, guild, category_query)
                if not category:
                    return f"No category found matching '{category_name_or_id}'."

        error_prefix = "Channel management failed"

        try:
            if action == "create":
                normalized_type = normalize_channel_type(channel_type or "")
                if not normalized_type:
                    return "A valid `channel_type` is required: text, voice, stage, forum, or category."
                if not name:
                    return "A channel `name` is required when action is `create`."
                if normalized_type == "category" and category_explicit and category is not None:
                    return "Categories cannot be placed inside another category."

                permission_error = (
                    self.ensure_channel_permission(
                        user, category, "manage_channels", "create channels in that category"
                    )
                    if category is not None
                    else self.ensure_guild_permission(user, "manage_channels", "create channels")
                )
                if permission_error:
                    return permission_error

                create_kwargs: dict[str, object] = {"name": name, "reason": reason}
                changes: dict[str, object] = {"action": "create", "channel_type": normalized_type, "name": name}
                if position is not None:
                    create_kwargs["position"] = position
                    changes["position"] = position
                if category is not None:
                    changes["category"] = category.name

                if normalized_type == "text":
                    if news and "COMMUNITY" not in guild.features:
                        return "News channels require the server community feature."
                    if category is not None:
                        create_kwargs["category"] = category
                    if topic is not None:
                        create_kwargs["topic"] = topic
                        changes["topic"] = topic
                    if news is not None:
                        create_kwargs["news"] = news
                        changes["news"] = news
                    if nsfw is not None:
                        create_kwargs["nsfw"] = nsfw
                        changes["nsfw"] = nsfw
                    if slowmode_delay is not None:
                        create_kwargs["slowmode_delay"] = slowmode_delay
                        changes["slowmode_delay"] = slowmode_delay
                    if default_auto_archive_duration is not None:
                        create_kwargs["default_auto_archive_duration"] = default_auto_archive_duration
                        changes["default_auto_archive_duration"] = default_auto_archive_duration
                    if default_thread_slowmode_delay is not None:
                        create_kwargs["default_thread_slowmode_delay"] = default_thread_slowmode_delay
                        changes["default_thread_slowmode_delay"] = default_thread_slowmode_delay
                    if dry_run:
                        return self.format_change_summary(f"Dry run: would create text channel `{name}`.", changes)
                    created = await guild.create_text_channel(**create_kwargs)
                elif normalized_type == "voice":
                    if category is not None:
                        create_kwargs["category"] = category
                    if nsfw is not None:
                        create_kwargs["nsfw"] = nsfw
                        changes["nsfw"] = nsfw
                    if user_limit is not None:
                        create_kwargs["user_limit"] = user_limit
                        changes["user_limit"] = user_limit
                    if bitrate is not None:
                        create_kwargs["bitrate"] = min(bitrate, guild.bitrate_limit)
                        changes["bitrate"] = min(bitrate, guild.bitrate_limit)
                    if rtc_region is not None:
                        normalized_region = (
                            None
                            if str(rtc_region).strip().lower() in {"auto", "automatic", "none", "null"}
                            else rtc_region
                        )
                        create_kwargs["rtc_region"] = normalized_region
                        changes["rtc_region"] = normalized_region or "automatic"
                    if video_quality_enum is not None:
                        create_kwargs["video_quality_mode"] = video_quality_enum
                        changes["video_quality_mode"] = video_quality_enum.name
                    if dry_run:
                        return self.format_change_summary(f"Dry run: would create voice channel `{name}`.", changes)
                    created = await guild.create_voice_channel(**create_kwargs)
                elif normalized_type == "stage":
                    if category is not None:
                        create_kwargs["category"] = category
                    if nsfw is not None:
                        create_kwargs["nsfw"] = nsfw
                        changes["nsfw"] = nsfw
                    if user_limit is not None:
                        create_kwargs["user_limit"] = user_limit
                        changes["user_limit"] = user_limit
                    if bitrate is not None:
                        create_kwargs["bitrate"] = min(bitrate, guild.bitrate_limit)
                        changes["bitrate"] = min(bitrate, guild.bitrate_limit)
                    if topic is not None:
                        changes["topic"] = topic
                    if rtc_region is not None:
                        normalized_region = (
                            None
                            if str(rtc_region).strip().lower() in {"auto", "automatic", "none", "null"}
                            else rtc_region
                        )
                        create_kwargs["rtc_region"] = normalized_region
                        changes["rtc_region"] = normalized_region or "automatic"
                    if video_quality_enum is not None:
                        create_kwargs["video_quality_mode"] = video_quality_enum
                        changes["video_quality_mode"] = video_quality_enum.name
                    if dry_run:
                        return self.format_change_summary(f"Dry run: would create stage channel `{name}`.", changes)
                    created = await guild.create_stage_channel(**create_kwargs)
                    if topic is not None:
                        await created.edit(topic=topic, reason=reason)
                elif normalized_type == "forum":
                    if category is not None:
                        create_kwargs["category"] = category
                    if topic is not None:
                        create_kwargs["topic"] = topic
                        changes["topic"] = topic
                    if nsfw is not None:
                        create_kwargs["nsfw"] = nsfw
                        changes["nsfw"] = nsfw
                    if slowmode_delay is not None:
                        create_kwargs["slowmode_delay"] = slowmode_delay
                        changes["slowmode_delay"] = slowmode_delay
                    if media is not None:
                        create_kwargs["media"] = media
                        changes["media"] = media
                    if default_auto_archive_duration is not None:
                        create_kwargs["default_auto_archive_duration"] = default_auto_archive_duration
                        changes["default_auto_archive_duration"] = default_auto_archive_duration
                    if default_thread_slowmode_delay is not None:
                        create_kwargs["default_thread_slowmode_delay"] = default_thread_slowmode_delay
                        changes["default_thread_slowmode_delay"] = default_thread_slowmode_delay
                    if sort_order_enum is not None:
                        create_kwargs["default_sort_order"] = sort_order_enum
                        changes["default_sort_order"] = sort_order_enum.name
                    if layout_enum is not None:
                        create_kwargs["default_layout"] = layout_enum
                        changes["default_layout"] = layout_enum.name
                    if reaction_emoji is not None:
                        create_kwargs["default_reaction_emoji"] = reaction_emoji
                        changes["default_reaction_emoji"] = default_reaction_emoji
                    if forum_tags:
                        create_kwargs["available_tags"] = forum_tags
                        changes["available_tags"] = ", ".join(tag.name for tag in forum_tags)
                    if dry_run:
                        return self.format_change_summary(f"Dry run: would create forum channel `{name}`.", changes)
                    created = await guild.create_forum(**create_kwargs)
                else:
                    if dry_run:
                        return self.format_change_summary(f"Dry run: would create category `{name}`.", changes)
                    created = await guild.create_category(**create_kwargs)

                created_ref = getattr(created, "mention", None) or created.name
                parent_note = f" under {category.name}" if category is not None else ""
                return f"Created {normalized_type} channel {created_ref} (ID: {created.id}){parent_note}."

            if not channel_name_or_id:
                return "`channel_name_or_id` is required unless action is `create`."

            channel = await asyncio.to_thread(find_channel, guild, channel_name_or_id)
            if not channel:
                return f"No channel found matching '{channel_name_or_id}'."
            if isinstance(channel, discord.Thread):
                return "Threads are managed with `manage_thread`, not `manage_channel`."

            permission_error = self.ensure_channel_permission(
                user, channel, "manage_channels", f"{action} that channel"
            )
            if permission_error:
                return permission_error

            if action == "delete":
                channel_name = channel.name
                channel_type_name = channel.type.name.replace("_", " ")
                if dry_run:
                    return self.format_change_summary(
                        f"Dry run: would delete {channel_type_name} channel `{channel_name}`.",
                        {"channel_id": channel.id},
                    )
                await channel.delete(reason=reason)
                return f"Deleted {channel_type_name} channel `{channel_name}`."

            edit_kwargs: dict[str, object] = {}
            changes: dict[str, object] = {"action": action, "channel": channel.name}
            if name is not None:
                edit_kwargs["name"] = name
                changes["name"] = name
            if position is not None:
                edit_kwargs["position"] = position
                changes["position"] = position
            if category_explicit:
                if isinstance(channel, discord.CategoryChannel):
                    return "Categories cannot be moved into another category."
                edit_kwargs["category"] = category
                changes["category"] = category.name if category is not None else "none"
                if sync_permissions is not None:
                    edit_kwargs["sync_permissions"] = sync_permissions
                    changes["sync_permissions"] = sync_permissions
            elif sync_permissions is not None:
                if isinstance(channel, discord.CategoryChannel):
                    return "Categories do not support `sync_permissions`."
                if channel.category is None:
                    return "This channel is not inside a category, so `sync_permissions` cannot be used."
                edit_kwargs["sync_permissions"] = sync_permissions
                changes["sync_permissions"] = sync_permissions

            for field_name, value in {
                "topic": topic,
                "nsfw": nsfw,
                "slowmode_delay": slowmode_delay,
                "user_limit": user_limit,
            }.items():
                if value is None:
                    continue
                if not hasattr(channel, field_name):
                    return f"This channel type does not support `{field_name}`."
                edit_kwargs[field_name] = value
                changes[field_name] = value

            if news is not None:
                if not isinstance(channel, discord.TextChannel):
                    return "This channel type does not support `news`."
                if news and "COMMUNITY" not in guild.features:
                    return "News channels require the server community feature."
                edit_kwargs["news"] = news
                changes["news"] = news

            if bitrate is not None:
                if not hasattr(channel, "bitrate"):
                    return "This channel type does not support `bitrate`."
                edit_kwargs["bitrate"] = min(bitrate, guild.bitrate_limit)
                changes["bitrate"] = min(bitrate, guild.bitrate_limit)

            if rtc_region is not None:
                if not hasattr(channel, "rtc_region"):
                    return "This channel type does not support `rtc_region`."
                normalized_region = (
                    None if str(rtc_region).strip().lower() in {"auto", "automatic", "none", "null"} else rtc_region
                )
                edit_kwargs["rtc_region"] = normalized_region
                changes["rtc_region"] = normalized_region or "automatic"

            if video_quality_enum is not None:
                if not hasattr(channel, "video_quality_mode"):
                    return "This channel type does not support `video_quality_mode`."
                edit_kwargs["video_quality_mode"] = video_quality_enum
                changes["video_quality_mode"] = video_quality_enum.name

            if default_auto_archive_duration is not None:
                if not hasattr(channel, "default_auto_archive_duration"):
                    return "This channel type does not support `default_auto_archive_duration`."
                edit_kwargs["default_auto_archive_duration"] = default_auto_archive_duration
                changes["default_auto_archive_duration"] = default_auto_archive_duration

            if default_thread_slowmode_delay is not None:
                if not hasattr(channel, "default_thread_slowmode_delay"):
                    return "This channel type does not support `default_thread_slowmode_delay`."
                edit_kwargs["default_thread_slowmode_delay"] = default_thread_slowmode_delay
                changes["default_thread_slowmode_delay"] = default_thread_slowmode_delay

            if media is not None:
                return "`media` can only be set while creating a forum channel."

            if sort_order_enum is not None:
                if not isinstance(channel, discord.ForumChannel):
                    return "This channel type does not support `default_sort_order`."
                edit_kwargs["default_sort_order"] = sort_order_enum
                changes["default_sort_order"] = sort_order_enum.name

            if layout_enum is not None:
                if not isinstance(channel, discord.ForumChannel):
                    return "This channel type does not support `default_layout`."
                edit_kwargs["default_layout"] = layout_enum
                changes["default_layout"] = layout_enum.name

            if default_reaction_emoji is not None:
                if not isinstance(channel, discord.ForumChannel):
                    return "This channel type does not support `default_reaction_emoji`."
                edit_kwargs["default_reaction_emoji"] = reaction_emoji
                changes["default_reaction_emoji"] = default_reaction_emoji if reaction_emoji is not None else "none"

            if available_tags is not None:
                if not isinstance(channel, discord.ForumChannel):
                    return "This channel type does not support `available_tags`."
                edit_kwargs["available_tags"] = forum_tags
                changes["available_tags"] = ", ".join(tag.name for tag in forum_tags) if forum_tags else "none"

            if not edit_kwargs:
                return "No channel changes were provided."

            if dry_run:
                return self.format_change_summary(
                    f"Dry run: would {'move' if action == 'move' else 'update'} channel `{channel.name}`.",
                    changes,
                )

            await channel.edit(reason=reason, **edit_kwargs)
            result_label = "Moved" if action == "move" else "Updated"
            channel_ref = getattr(channel, "mention", None) or channel.name
            return f"{result_label} channel {channel_ref} successfully."
        except discord.Forbidden:
            return f"{error_prefix}: I do not have permission to perform that action."
        except discord.HTTPException as e:
            message = getattr(e, "text", None) or str(e)
            return f"{error_prefix}: {message}"

    async def set_channel_permissions(
        self,
        guild: discord.Guild,
        channel_name_or_id: str,
        target_type: Literal["role", "member"],
        target_name_or_id: str,
        allow_permissions: list[str] | None = None,
        deny_permissions: list[str] | None = None,
        clear_permissions: list[str] | None = None,
        reason: str | None = None,
        dry_run: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Set explicit channel permission overwrites for a role or member."""
        user, user_error = self.get_requesting_admin(guild, kwargs)
        if user_error:
            return user_error

        channel = await asyncio.to_thread(find_channel, guild, channel_name_or_id)
        if not channel:
            return f"No channel found matching '{channel_name_or_id}'."
        if isinstance(channel, discord.Thread):
            return "This tool does not currently manage thread permission overwrites. Use the parent channel instead."

        permission_error = self.ensure_channel_permission(
            user,
            channel,
            "manage_channels",
            "update channel permission overwrites",
        )
        if permission_error:
            return permission_error

        normalized_target_type = str(target_type).strip().lower()
        target = self.resolve_permission_target(guild, normalized_target_type, target_name_or_id)
        if not target:
            return f"No {normalized_target_type} found matching '{target_name_or_id}'."

        if isinstance(target, discord.Role):
            target_error = self.ensure_role_manageable(user, target, "update channel overwrites")
            if target_error:
                return target_error

        allow, invalid_allow = self.normalize_permission_names(allow_permissions)
        deny, invalid_deny = self.normalize_permission_names(deny_permissions)
        clear, invalid_clear = self.normalize_permission_names(clear_permissions)
        invalid = invalid_allow + invalid_deny + invalid_clear
        if invalid:
            return f"Invalid permission names: {', '.join(sorted(set(invalid)))}"

        allow_error = self.ensure_permission_subset(user, allow, "allow channel permissions")
        if allow_error:
            return allow_error

        overlap = (set(allow) & set(deny)) | (set(allow) & set(clear)) | (set(deny) & set(clear))
        if overlap:
            return f"Permissions must only appear in one list: {', '.join(sorted(overlap))}"
        if not allow and not deny and not clear:
            return "Provide at least one permission to allow, deny, or clear."

        overwrite = channel.overwrites_for(target)
        for permission_name in allow:
            setattr(overwrite, permission_name, True)
        for permission_name in deny:
            setattr(overwrite, permission_name, False)
        for permission_name in clear:
            setattr(overwrite, permission_name, None)

        target_label = getattr(target, "mention", None) or getattr(target, "name", str(target))
        summary_parts: list[str] = []
        if allow:
            summary_parts.append(f"allowed: {', '.join(allow)}")
        if deny:
            summary_parts.append(f"denied: {', '.join(deny)}")
        if clear:
            summary_parts.append(f"cleared: {', '.join(clear)}")
        if dry_run:
            return f"Dry run: would update overwrites for {target_label} in {channel.mention} ({'; '.join(summary_parts)})."

        try:
            if overwrite.is_empty():
                await channel.set_permissions(target, overwrite=None, reason=reason)
            else:
                await channel.set_permissions(target, overwrite=overwrite, reason=reason)
        except discord.Forbidden:
            return "I do not have permission to update channel overwrites for that target."
        except discord.HTTPException as e:
            message = getattr(e, "text", None) or str(e)
            return f"Failed to update channel overwrites: {message}"

        return f"Updated overwrites for {target_label} in {channel.mention} ({'; '.join(summary_parts)})."

    async def manage_thread(
        self,
        guild: discord.Guild,
        action: Literal["create", "edit", "delete"],
        parent_channel_name_or_id: str | None = None,
        thread_name_or_id: str | None = None,
        name: str | None = None,
        starter_message_id: str | None = None,
        private_thread: bool | None = None,
        auto_archive_duration: int | None = None,
        slowmode_delay: int | None = None,
        invitable: bool | None = None,
        archived: bool | None = None,
        locked: bool | None = None,
        pinned: bool | None = None,
        applied_tags: list[str] | str | None = None,
        message_content: str | None = None,
        reason: str | None = None,
        dry_run: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Create, edit, or delete Discord threads and forum posts."""
        user, user_error = self.get_requesting_admin(guild, kwargs)
        if user_error:
            return user_error

        action = str(action).strip().lower()
        if action not in {"create", "edit", "delete"}:
            return "Invalid action. Use one of: create, edit, delete."
        if slowmode_delay is not None and slowmode_delay < 0:
            return "Thread slowmode delay must be 0 or greater."
        if message_content is not None and len(message_content) > 2000:
            return "Thread starter content exceeds Discord's 2000 character limit."

        if action == "create":
            if not parent_channel_name_or_id:
                return "`parent_channel_name_or_id` is required when creating a thread."
            if not name:
                return "A thread `name` is required when action is `create`."

            parent = await asyncio.to_thread(find_channel, guild, parent_channel_name_or_id)
            if not isinstance(parent, (discord.TextChannel, discord.ForumChannel)):
                return "Threads can only be created inside text channels or forum channels."

            if isinstance(parent, discord.ForumChannel):
                permission_error = self.ensure_channel_permission(user, parent, "send_messages", "create forum posts")
            else:
                thread_permission = "create_private_threads" if private_thread else "create_public_threads"
                permission_error = self.ensure_channel_permission(user, parent, thread_permission, "create threads")
            if permission_error:
                return permission_error

            changes: dict[str, object] = {"action": "create", "parent": parent.name, "name": name}
            if auto_archive_duration is not None:
                changes["auto_archive_duration"] = auto_archive_duration
            if slowmode_delay is not None:
                changes["slowmode_delay"] = slowmode_delay
            if invitable is not None:
                changes["invitable"] = invitable

            if isinstance(parent, discord.ForumChannel):
                if not message_content:
                    return "`message_content` is required when creating a forum post."
                resolved_tags, missing_tags = self.resolve_forum_tags(parent, applied_tags)
                if missing_tags:
                    return f"Unknown forum tags: {', '.join(missing_tags)}"
                if resolved_tags:
                    changes["applied_tags"] = ", ".join(tag.name for tag in resolved_tags)
                if dry_run:
                    return self.format_change_summary(f"Dry run: would create forum post `{name}`.", changes)

                thread_with_message = await parent.create_thread(
                    name=name,
                    auto_archive_duration=auto_archive_duration or discord.utils.MISSING,
                    slowmode_delay=slowmode_delay,
                    content=message_content,
                    applied_tags=resolved_tags,
                    reason=reason,
                )
                return f"Created forum post {thread_with_message.thread.mention} successfully."

            if starter_message_id is not None:
                try:
                    starter_message = discord.Object(id=int(str(starter_message_id).strip()))
                except ValueError:
                    return "`starter_message_id` must be a numeric Discord message ID."
                changes["starter_message_id"] = starter_message.id
            else:
                starter_message = None

            thread_type = None
            if starter_message is None:
                thread_type = (
                    discord.ChannelType.private_thread if private_thread else discord.ChannelType.public_thread
                )
                changes["thread_type"] = thread_type.name

            if dry_run:
                return self.format_change_summary(f"Dry run: would create thread `{name}`.", changes)

            created_thread = await parent.create_thread(
                name=name,
                message=starter_message,
                auto_archive_duration=auto_archive_duration or discord.utils.MISSING,
                type=thread_type,
                reason=reason,
                invitable=True if invitable is None else invitable,
                slowmode_delay=slowmode_delay,
            )
            return f"Created thread {created_thread.mention} successfully."

        if not thread_name_or_id:
            return "`thread_name_or_id` is required unless action is `create`."

        thread = await asyncio.to_thread(find_channel, guild, thread_name_or_id)
        if not isinstance(thread, discord.Thread):
            return f"No thread found matching '{thread_name_or_id}'."

        permission_error = self.ensure_channel_permission(user, thread, "manage_threads", f"{action} that thread")
        if permission_error:
            return permission_error

        if action == "delete":
            if dry_run:
                return self.format_change_summary(
                    f"Dry run: would delete thread `{thread.name}`.",
                    {"thread_id": thread.id, "parent": getattr(thread.parent, "name", "unknown")},
                )
            await thread.delete(reason=reason)
            return f"Deleted thread `{thread.name}` successfully."

        edit_kwargs: dict[str, object] = {}
        changes: dict[str, object] = {"action": "edit", "thread": thread.name}
        if name is not None:
            edit_kwargs["name"] = name
            changes["name"] = name
        if archived is not None:
            edit_kwargs["archived"] = archived
            changes["archived"] = archived
        if locked is not None:
            edit_kwargs["locked"] = locked
            changes["locked"] = locked
        if invitable is not None:
            edit_kwargs["invitable"] = invitable
            changes["invitable"] = invitable
        if pinned is not None:
            edit_kwargs["pinned"] = pinned
            changes["pinned"] = pinned
        if slowmode_delay is not None:
            edit_kwargs["slowmode_delay"] = slowmode_delay
            changes["slowmode_delay"] = slowmode_delay
        if auto_archive_duration is not None:
            edit_kwargs["auto_archive_duration"] = auto_archive_duration
            changes["auto_archive_duration"] = auto_archive_duration
        if applied_tags is not None:
            if not isinstance(thread.parent, discord.ForumChannel):
                return "Only forum posts support `applied_tags`."
            resolved_tags, missing_tags = self.resolve_forum_tags(thread.parent, applied_tags)
            if missing_tags:
                return f"Unknown forum tags: {', '.join(missing_tags)}"
            edit_kwargs["applied_tags"] = resolved_tags
            changes["applied_tags"] = ", ".join(tag.name for tag in resolved_tags) if resolved_tags else "none"

        if not edit_kwargs:
            return "No thread changes were provided."
        if dry_run:
            return self.format_change_summary(f"Dry run: would update thread `{thread.name}`.", changes)

        await thread.edit(reason=reason, **edit_kwargs)
        return f"Updated thread {thread.mention} successfully."

    async def manage_role(
        self,
        guild: discord.Guild,
        action: Literal["create", "edit", "move", "delete"],
        role_name_or_id: str | None = None,
        name: str | None = None,
        permissions: list[str] | str | None = None,
        color: str | int | None = None,
        hoist: bool | None = None,
        mentionable: bool | None = None,
        display_icon: str | None = None,
        position: int | None = None,
        above_role_name_or_id: str | None = None,
        below_role_name_or_id: str | None = None,
        reason: str | None = None,
        dry_run: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Create, edit, move, or delete Discord roles."""
        user, user_error = self.get_requesting_admin(guild, kwargs)
        if user_error:
            return user_error

        action = str(action).strip().lower()
        if action not in {"create", "edit", "move", "delete"}:
            return "Invalid action. Use one of: create, edit, move, delete."
        if position is not None and position < 0:
            return "Role position must be 0 or greater."

        permission_error = self.ensure_guild_permission(user, "manage_roles", "manage roles")
        if permission_error:
            return permission_error

        permissions_obj, permission_names, permission_error = self.build_role_permissions(permissions)
        if permission_error:
            return permission_error
        permission_subset_error = self.ensure_permission_subset(user, permission_names, "grant role permissions")
        if permission_subset_error:
            return permission_subset_error
        color_value, color_error = self.parse_color_value(color)
        if color_error:
            return color_error
        role_icon, role_icon_error = await self.resolve_display_icon_input(display_icon)
        if role_icon_error:
            return role_icon_error
        if display_icon is not None and role_icon is not None and "ROLE_ICONS" not in guild.features:
            return "Role icons are not available in this server."

        if action == "create":
            if not name:
                return "A role `name` is required when action is `create`."
            position_error = self.ensure_role_position(user, position, "create a role")
            if position_error:
                return position_error

            create_kwargs: dict[str, object] = {"name": name, "reason": reason}
            changes: dict[str, object] = {"action": "create", "name": name}
            if permissions is not None:
                create_kwargs["permissions"] = permissions_obj or discord.Permissions.none()
                changes["permissions"] = ", ".join(permission_names) if permission_names else "none"
            if color is not None:
                create_kwargs["colour"] = color_value or 0
                changes["color"] = f"#{(color_value or 0):06x}"
            if hoist is not None:
                create_kwargs["hoist"] = hoist
                changes["hoist"] = hoist
            if mentionable is not None:
                create_kwargs["mentionable"] = mentionable
                changes["mentionable"] = mentionable
            if display_icon is not None:
                create_kwargs["display_icon"] = role_icon
                changes["display_icon"] = display_icon if role_icon is not None else "none"
            if position is not None:
                changes["position"] = position
            if dry_run:
                return self.format_change_summary(f"Dry run: would create role `{name}`.", changes)

            role = await guild.create_role(**create_kwargs)
            if position is not None:
                await role.edit(position=position, reason=reason)
            return f"Created role {role.mention} (ID: {role.id}) successfully."

        if not role_name_or_id:
            return "`role_name_or_id` is required unless action is `create`."

        role = await asyncio.to_thread(find_role, guild, role_name_or_id)
        if role is None:
            return f"No role found matching '{role_name_or_id}'."
        if role.is_default():
            return "The default @everyone role cannot be managed with this tool."

        role_error = self.ensure_role_manageable(user, role, f"{action} that role")
        if role_error:
            return role_error

        if action == "delete":
            if dry_run:
                return self.format_change_summary(
                    f"Dry run: would delete role `{role.name}`.",
                    {"role_id": role.id, "member_count": len(role.members)},
                )
            await role.delete(reason=reason)
            return f"Deleted role `{role.name}` successfully."

        if action == "move":
            if position is None and above_role_name_or_id is None and below_role_name_or_id is None:
                return "Provide `position`, `above_role_name_or_id`, or `below_role_name_or_id` to move a role."
            if position is not None and (above_role_name_or_id or below_role_name_or_id):
                return "Use either `position` or `above_role_name_or_id`/`below_role_name_or_id`, not both."
            if above_role_name_or_id and below_role_name_or_id:
                return "Use only one of `above_role_name_or_id` or `below_role_name_or_id`."

            position_error = self.ensure_role_position(user, position, "move a role")
            if position_error:
                return position_error

            changes: dict[str, object] = {"action": "move", "role": role.name}
            if position is not None:
                changes["position"] = position
                if dry_run:
                    return self.format_change_summary(f"Dry run: would move role `{role.name}`.", changes)
                await role.edit(position=position, reason=reason)
            else:
                move_kwargs: dict[str, object] = {"reason": reason}
                if above_role_name_or_id:
                    above_role = await asyncio.to_thread(find_role, guild, above_role_name_or_id)
                    if above_role is None:
                        return f"No role found matching '{above_role_name_or_id}'."
                    above_error = self.ensure_role_manageable(user, above_role, "move roles relative to that role")
                    if above_error:
                        return above_error
                    move_kwargs["above"] = above_role
                    changes["above"] = above_role.name
                if below_role_name_or_id:
                    below_role = await asyncio.to_thread(find_role, guild, below_role_name_or_id)
                    if below_role is None:
                        return f"No role found matching '{below_role_name_or_id}'."
                    below_error = self.ensure_role_manageable(user, below_role, "move roles relative to that role")
                    if below_error:
                        return below_error
                    move_kwargs["below"] = below_role
                    changes["below"] = below_role.name
                if dry_run:
                    return self.format_change_summary(f"Dry run: would move role `{role.name}`.", changes)
                await role.move(**move_kwargs)
            return f"Moved role {role.mention} successfully."

        edit_kwargs: dict[str, object] = {}
        changes: dict[str, object] = {"action": "edit", "role": role.name}
        if name is not None:
            edit_kwargs["name"] = name
            changes["name"] = name
        if permissions is not None:
            edit_kwargs["permissions"] = permissions_obj or discord.Permissions.none()
            changes["permissions"] = ", ".join(permission_names) if permission_names else "none"
        if color is not None:
            edit_kwargs["colour"] = color_value or 0
            changes["color"] = f"#{(color_value or 0):06x}"
        if hoist is not None:
            edit_kwargs["hoist"] = hoist
            changes["hoist"] = hoist
        if mentionable is not None:
            edit_kwargs["mentionable"] = mentionable
            changes["mentionable"] = mentionable
        if display_icon is not None:
            edit_kwargs["display_icon"] = role_icon
            changes["display_icon"] = display_icon if role_icon is not None else "none"
        if position is not None:
            position_error = self.ensure_role_position(user, position, "update a role")
            if position_error:
                return position_error
            edit_kwargs["position"] = position
            changes["position"] = position

        if not edit_kwargs:
            return "No role changes were provided."
        if dry_run:
            return self.format_change_summary(f"Dry run: would update role `{role.name}`.", changes)

        await role.edit(reason=reason, **edit_kwargs)
        return f"Updated role {role.mention} successfully."

    async def manage_server(
        self,
        guild: discord.Guild,
        name: str | None = None,
        description: str | None = None,
        verification_level: Literal["none", "low", "medium", "high", "highest"] | None = None,
        explicit_content_filter: Literal["disabled", "no_role", "all_members"] | None = None,
        default_notifications: Literal["all_messages", "only_mentions"] | None = None,
        preferred_locale: str | None = None,
        afk_timeout: int | None = None,
        afk_channel_name_or_id: str | None = None,
        system_channel_name_or_id: str | None = None,
        rules_channel_name_or_id: str | None = None,
        public_updates_channel_name_or_id: str | None = None,
        widget_enabled: bool | None = None,
        widget_channel_name_or_id: str | None = None,
        premium_progress_bar_enabled: bool | None = None,
        community: bool | None = None,
        invites_disabled: bool | None = None,
        icon_url: str | None = None,
        banner_url: str | None = None,
        splash_url: str | None = None,
        discovery_splash_url: str | None = None,
        reason: str | None = None,
        dry_run: bool = False,
        *args,
        **kwargs,
    ) -> str:
        """Update supported Discord server settings."""
        user, user_error = self.get_requesting_admin(guild, kwargs)
        if user_error:
            return user_error

        permission_error = self.ensure_guild_permission(user, "manage_guild", "manage server settings")
        if permission_error:
            return permission_error

        verification_enum, verification_error = self.parse_named_enum(
            discord.VerificationLevel,
            verification_level,
            "verification_level",
        )
        if verification_error:
            return verification_error

        content_filter_enum, content_filter_error = self.parse_named_enum(
            discord.ContentFilter,
            explicit_content_filter,
            "explicit_content_filter",
        )
        if content_filter_error:
            return content_filter_error

        notification_enum, notification_error = self.parse_named_enum(
            discord.NotificationLevel,
            default_notifications,
            "default_notifications",
        )
        if notification_error:
            return notification_error

        locale_enum, locale_error = self.parse_named_enum(discord.Locale, preferred_locale, "preferred_locale")
        if locale_error:
            return locale_error

        server_icon, icon_error = await self.resolve_optional_image_input(icon_url, "icon_url")
        if icon_error:
            return icon_error
        banner, banner_error = await self.resolve_optional_image_input(banner_url, "banner_url")
        if banner_error:
            return banner_error
        splash, splash_error = await self.resolve_optional_image_input(splash_url, "splash_url")
        if splash_error:
            return splash_error
        discovery_splash, discovery_splash_error = await self.resolve_optional_image_input(
            discovery_splash_url,
            "discovery_splash_url",
        )
        if discovery_splash_error:
            return discovery_splash_error

        if afk_timeout is not None and afk_timeout < 0:
            return "`afk_timeout` must be 0 or greater."

        edit_kwargs: dict[str, object] = {"reason": reason}
        changes: dict[str, object] = {}
        if name is not None:
            edit_kwargs["name"] = name
            changes["name"] = name
        if description is not None:
            edit_kwargs["description"] = description
            changes["description"] = description
        if icon_url is not None:
            edit_kwargs["icon"] = server_icon
            changes["icon"] = icon_url if server_icon is not None else "none"
        if banner_url is not None:
            edit_kwargs["banner"] = banner
            changes["banner"] = banner_url if banner is not None else "none"
        if splash_url is not None:
            edit_kwargs["splash"] = splash
            changes["splash"] = splash_url if splash is not None else "none"
        if discovery_splash_url is not None:
            edit_kwargs["discovery_splash"] = discovery_splash
            changes["discovery_splash"] = discovery_splash_url if discovery_splash is not None else "none"
        if verification_enum is not None:
            edit_kwargs["verification_level"] = verification_enum
            changes["verification_level"] = verification_enum.name
        if content_filter_enum is not None:
            edit_kwargs["explicit_content_filter"] = content_filter_enum
            changes["explicit_content_filter"] = content_filter_enum.name
        if notification_enum is not None:
            edit_kwargs["default_notifications"] = notification_enum
            changes["default_notifications"] = notification_enum.name
        if locale_enum is not None:
            edit_kwargs["preferred_locale"] = locale_enum
            changes["preferred_locale"] = locale_enum.name
        if afk_timeout is not None:
            edit_kwargs["afk_timeout"] = afk_timeout
            changes["afk_timeout"] = afk_timeout
        if widget_enabled is not None:
            edit_kwargs["widget_enabled"] = widget_enabled
            changes["widget_enabled"] = widget_enabled
        if premium_progress_bar_enabled is not None:
            edit_kwargs["premium_progress_bar_enabled"] = premium_progress_bar_enabled
            changes["premium_progress_bar_enabled"] = premium_progress_bar_enabled
        if community is not None:
            edit_kwargs["community"] = community
            changes["community"] = community
        if invites_disabled is not None:
            edit_kwargs["invites_disabled"] = invites_disabled
            changes["invites_disabled"] = invites_disabled

        invalid_for_community = [
            verification_enum is not None and verification_enum == discord.VerificationLevel.none,
            content_filter_enum is not None and content_filter_enum == discord.ContentFilter.disabled,
        ]
        if community is True and any(invalid_for_community):
            return "Community cannot stay enabled when verification level is `none` or content filter is `disabled`."
        if any(invalid_for_community) and "community" not in edit_kwargs:
            edit_kwargs["community"] = False
            changes["community"] = False

        channel_fields = {
            "afk_channel": (afk_channel_name_or_id, (discord.VoiceChannel,), "voice channel"),
            "system_channel": (system_channel_name_or_id, (discord.TextChannel,), "text channel"),
            "rules_channel": (rules_channel_name_or_id, (discord.TextChannel,), "text channel"),
            "public_updates_channel": (public_updates_channel_name_or_id, (discord.TextChannel,), "text channel"),
            "widget_channel": (widget_channel_name_or_id, (discord.TextChannel,), "text channel"),
        }
        for field_name, (reference, expected_types, expected_label) in channel_fields.items():
            if reference is None:
                continue
            lowered = str(reference).strip().lower()
            if lowered in {"none", "null", "clear", "remove"}:
                edit_kwargs[field_name] = None
                changes[field_name] = "none"
                continue

            resolved = await asyncio.to_thread(find_channel, guild, reference)
            if resolved is None:
                return f"No channel found matching '{reference}'."
            if not isinstance(resolved, expected_types):
                return f"`{field_name}` must reference a {expected_label}."
            edit_kwargs[field_name] = resolved
            changes[field_name] = resolved.name

        if len(edit_kwargs) == 1:
            return "No server changes were provided."
        if dry_run:
            return self.format_change_summary("Dry run: would update server settings.", changes)

        await guild.edit(**edit_kwargs)
        return "Updated server settings successfully."

    async def render_svg(
        self,
        svg_content: str,
        channel: discord.TextChannel,
        filename: str = "rendering.png",
        background: str = "",
        *args,
        **kwargs,
    ) -> Union[str, dict]:
        """
        Render an SVG string to a PNG image and send it to the Discord channel.

        Args:
            svg_content: Complete SVG markup to render
            channel: The channel to send the image to
            filename: Name for the output PNG file
            background: Optional CSS background color (e.g. '#ffffff')

        Returns:
            Confirmation message or error description
        """
        if not filename.lower().endswith(".png"):
            filename = filename.rsplit(".", 1)[0] + ".png"

        kwargs_render = {
            "svg_string": svg_content,
            "zoom": 2,
            "font_dirs": svg_font_dirs(),
        }
        if background:
            kwargs_render["background"] = background

        try:
            raw = await asyncio.to_thread(resvg_py.svg_to_bytes, **kwargs_render)
        except Exception as e:
            log.warning("render_svg failed to rasterize SVG", exc_info=e)
            return f"Failed to render SVG: {e}"

        png_bytes = bytes(raw)
        if not png_bytes:
            return "SVG rendered to an empty image. Check that the SVG has valid width/height attributes and visible content."

        buf = BytesIO(png_bytes)
        buf.seek(0)
        file = discord.File(buf, filename=filename)
        return {"content": "Image rendered successfully.", "defer_files": [file]}
