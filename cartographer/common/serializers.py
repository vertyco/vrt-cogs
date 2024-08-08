from __future__ import annotations

import asyncio
import base64
import logging
import typing as t
from datetime import datetime, timezone
from io import BytesIO, StringIO
from time import perf_counter

import aiohttp
import discord
from pydantic import VERSION, Field
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_timedelta
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

if VERSION > "1.10.15":
    from pydantic import field_validator
else:
    from pydantic import validator as field_validator

from . import Base

log = logging.getLogger("red.vrt.cartographer.serializers")
_ = Translator("Cartographer", __file__)


VOICE = t.Union[discord.VoiceChannel, discord.StageChannel]
GuildChannels = t.Union[VOICE, discord.ForumChannel, discord.TextChannel, discord.CategoryChannel]


class Role(Base):
    id: int
    name: str
    color: int
    hoist: bool = False
    position: int
    permissions: int
    mentionable: bool = False
    icon: str | None = None
    is_assignable: bool = False
    is_bot_managed: bool = False
    is_integration: bool = False
    is_premium_subscriber: bool = False
    is_default: bool = False

    def fuzzy_match(self, role: discord.Role) -> bool:
        cases = [
            self.name == role.name,
            self.color == role.color.value,
            self.hoist == role.hoist,
            self.mentionable == role.mentionable,
        ]
        return all(cases)

    def is_match(self, role: discord.Role) -> bool:
        cases = [
            self.name == role.name,
            self.color == role.color.value,
            self.hoist == role.hoist,
            self.permissions == role.permissions.value,
            self.mentionable == role.mentionable,
            self.position == role.position,
        ]
        return all(cases)

    @classmethod
    async def serialize(cls, role: discord.Role, load_icon: bool = True) -> Role:
        icon = await role.icon.read() if role.icon and load_icon else None
        return cls(
            id=role.id,
            name=role.name,
            color=role.color.value,
            hoist=role.hoist,
            position=role.position,
            permissions=role.permissions.value,
            mentionable=role.mentionable,
            icon=base64.b64encode(icon).decode() if icon else None,
            is_assignable=role.is_assignable(),
            is_bot_managed=role.is_bot_managed(),
            is_integration=role.is_integration(),
            is_premium_subscriber=role.is_premium_subscriber(),
            is_default=role.is_default(),
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> discord.Role:
        supports_emojis = "ROLE_ICONS" in guild.features
        existing: discord.Role | None = guild.get_role(self.id)
        position = max(1, min(self.position, guild.me.top_role.position - 1))
        if existing and existing < guild.me.top_role:
            if self.is_match(existing):
                # Role exists and has not changed
                return existing
            if existing.id == guild.default_role.id:
                log.info("Updating default role %s", self.name)
                await existing.edit(permissions=discord.Permissions(self.permissions))
                return existing

            log.info("Updating role %s", self.name)
            role = existing
            await role.edit(
                name=self.name,
                color=self.color,
                hoist=self.hoist,
                position=position,
                permissions=discord.Permissions(self.permissions),
                mentionable=self.mentionable,
                display_icon=base64.b64decode(self.icon) if self.icon and supports_emojis else None,
                reason=_("Restored from backup"),
            )
        else:
            log.info("Creating role %s", self.name)
            role = await guild.create_role(
                name=self.name,
                color=self.color,
                hoist=self.hoist,
                permissions=discord.Permissions(self.permissions),
                mentionable=self.mentionable,
                display_icon=base64.b64decode(self.icon) if self.icon and supports_emojis else None,
                reason=_("Restored from backup"),
            )
            await role.edit(position=position)
        return role


class Member(Base):
    id: int
    nick: str | None = None
    roles: list[Role] = []

    @classmethod
    async def serialize(cls, member: discord.Member) -> Member:
        return cls(
            id=member.id,
            nick=member.nick,
            roles=[await Role.serialize(i, load_icon=False) for i in member.roles],
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> bool:
        member = guild.get_member(self.id)
        if not member:
            return False

        if member.nick != self.nick:
            log.info("Updating nickname for %s", member.display_name)
            await member.edit(nick=self.nickname, reason=_("Restored from backup"))

        # Update the role IDs by closest match, becaue they should be restored by now
        for role in self.roles:
            if guild.get_role(role.id):
                continue
            for current_role in guild.roles:
                if role.is_match(current_role):
                    role.id = current_role.id
                    break

        saved_role_ids = {i.id for i in self.roles}
        to_add: list[discord.Role] = []
        to_remove: list[discord.Role] = []

        def _compute():
            for role_backup in self.roles:
                role = guild.get_role(role_backup.id)
                if not role:
                    continue
                if role >= guild.me.top_role:
                    continue
                if not role.is_assignable():
                    continue
                # We must ensure that the bot can actually assign the role
                if role_backup.is_default:
                    continue
                if role.is_bot_managed() and member.bot:
                    continue

                if role not in member.roles:
                    to_add.append(role)
                for current_role in member.roles:
                    if current_role.id not in saved_role_ids:
                        to_remove.append(current_role)

        await asyncio.to_thread(_compute)

        if to_add:
            try:
                await member.add_roles(*to_add, reason=_("Restored from backup"))
            except discord.HTTPException as e:
                buffer.write(
                    _("Failed to add the following roles to {}: {} - {}\n").format(member.display_name, e, to_add)
                )
        if to_remove:
            try:
                await member.remove_roles(*to_remove, reason=_("Restored from backup"))
            except discord.HTTPException as e:
                buffer.write(
                    _("Failed to remove the following roles from {}: {} - {}\n").format(
                        member.display_name, e, to_remove
                    )
                )
        return True


class Overwrites(Base):
    id: int  # Role or member ID
    name: str = ""  # Role or member name (for logging)
    is_role: bool = True
    values: dict[str, bool | None] = {}

    @classmethod
    def serialize(cls, obj: GuildChannels) -> list[Overwrites]:
        overwrites: list[Overwrites] = [
            cls(
                id=role_mem.id,
                name=role_mem.name,
                type=True if isinstance(role_mem, discord.Role) else False,
                values=perms._values,
            )
            for role_mem, perms in obj.overwrites.items()
            if perms._values
        ]
        return overwrites

    def get(self, guild: discord.Guild) -> discord.Role | discord.Member | None:
        if self.is_role:
            role = guild.get_role(self.id)
            if role:
                return role
            if self.name == "@everyone":
                return guild.default_role
            # Match by name
            for role in guild.roles:
                if role.name == self.name:
                    self.id = role.id
                    return role
        else:
            return guild.get_member(self.id)


class ChannelBase(Base):
    id: int
    name: str
    position: int = 0
    overwrites: list[Overwrites] = []
    nsfw: bool = False

    # v1.0.0 compatibility
    # Category used to be a string (name) instead of an object
    if VERSION > "1.10.15":

        @field_validator("category", mode="before", check_fields=False)
        def _validate_category(cls, v):
            if isinstance(v, str):
                return None
            return v
    else:

        @field_validator("category", pre=True, allow_reuse=True, check_fields=False)
        def _validate_category(cls, v):
            if isinstance(v, str):
                return None
            return v

    def get_overwrites(
        self, guild: discord.Guild, buffer: StringIO
    ) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
        overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {}
        for i in self.overwrites:
            obj = i.get(guild)
            if obj:
                overwrites[obj] = discord.PermissionOverwrite(**i.values)
            else:
                txt = _("Channel {} missing role or member overwrite: {} - {}\n").format(
                    f"{self.name} ({self.id})", f"{i.name} ({i.id})", str(i.values)
                )
                log.warning(txt)
                buffer.write(txt)
        return overwrites

    def is_match(self, channel: discord.abc.GuildChannel) -> bool:
        matches = [
            self.name == channel.name,
            getattr(self, "nsfw", False) == getattr(channel, "nsfw", False),
        ]
        return all(matches)


class CategoryChannel(ChannelBase):
    """Just base attributes"""

    def is_match(self, category: discord.CategoryChannel) -> bool:
        if not isinstance(category, discord.CategoryChannel):
            return False
        return super().is_match(category)

    @classmethod
    async def serialize(cls, category: discord.CategoryChannel) -> CategoryChannel:
        return cls(
            id=category.id,
            name=category.name,
            position=category.position,
            overwrites=Overwrites.serialize(category),
            nsfw=category.nsfw,
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> discord.CategoryChannel:
        existing: discord.CategoryChannel | None = guild.get_channel(self.id)
        if existing:
            if self.is_match(existing):
                # Channel exists and has not changed
                return existing
            log.info("Updating category %s", self.name)
            category = existing
            await category.edit(
                name=self.name,
                position=self.position,
                overwrites=self.get_overwrites(guild, buffer),
                nsfw=self.nsfw,
                reason=_("Restored from backup"),
            )
        else:
            for category in guild.categories:
                if self.is_match(category):
                    self.id = category.id
                    log.info("Updating ID for category %s", self.name)
                    break
            else:
                log.info("Restoring category %s", self.name)
                category = await guild.create_category_channel(
                    name=self.name,
                    position=self.position,
                    overwrites=self.get_overwrites(guild, buffer),
                    reason=_("Restored from backup"),
                )
                self.id = category.id
        return category


class FileBackup(Base):
    filename: str
    filebytes: str  # base64 encoded file

    @classmethod
    async def serialize(cls, attachment: discord.Attachment) -> FileBackup:
        return cls(
            filename=attachment.filename,
            filebytes=base64.b64encode(await attachment.read()).decode(),
        )

    async def restore(self) -> discord.File:
        return discord.File(BytesIO(base64.b64decode(self.filebytes)), filename=self.filename)


class MessageBackup(Base):
    channel_id: int
    channel_name: str
    content: str | None = None
    embeds: list[dict] = []
    files: list[FileBackup] = []
    username: str
    avatar_url: str

    @classmethod
    async def serialize(cls, message: discord.Message) -> MessageBackup:
        return cls(
            channel_id=message.channel.id,
            channel_name=message.channel.name,
            content=message.content,
            embeds=[i.to_dict() for i in message.embeds],
            files=[await FileBackup.serialize(i) for i in message.attachments],
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
        )

    async def embed_objects(self) -> list[discord.Embed]:
        return [discord.Embed.from_dict(i) for i in self.embeds]

    async def attachment_objects(self) -> list[discord.File]:
        return [await i.restore() for i in self.files]


class TextChannel(ChannelBase):
    topic: str | None = None
    news: bool = False
    slowmode_delay: int = 0
    default_auto_archive_duration: int | None
    default_thread_slowmode_delay: int | None
    category: CategoryChannel | None = None
    messages: list[MessageBackup] = []

    def is_match(self, channel: discord.TextChannel, check_category: bool = False) -> bool:
        if not isinstance(channel, discord.TextChannel):
            return False
        matches = [
            self.topic == channel.topic,
            self.news == channel.is_news(),
            self.slowmode_delay == channel.slowmode_delay,
            self.default_auto_archive_duration == channel.default_auto_archive_duration,
            self.default_thread_slowmode_delay == channel.default_thread_slowmode_delay,
        ]
        if check_category:
            matches.append(
                self.category.is_match(channel.category) if self.category else self.category == channel.category
            )
        return all(matches) and super().is_match(channel)

    @classmethod
    async def serialize(cls, channel: discord.TextChannel, limit: int = 0) -> TextChannel:
        messages: list[MessageBackup] = []
        if limit:
            try:
                async for message in channel.history(limit=limit):
                    msg_obj = MessageBackup(
                        channel_id=message.channel.id,
                        channel_name=message.channel.name,
                        content=message.content[:2000] if message.content else None,
                        embeds=[i.to_dict() for i in message.embeds],
                        attachments=[i.to_dict() for i in message.attachments],
                        username=message.author.name,
                        avatar_url=message.author.display_avatar.url,
                    )
                    messages.append(msg_obj)
            except discord.HTTPException:
                log.warning("Failed to fetch messages for text channel %s", channel.name)
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            overwrites=Overwrites.serialize(channel),
            nsfw=channel.nsfw,
            topic=channel.topic,
            news=channel.is_news(),
            slowmode_delay=channel.slowmode_delay,
            default_auto_archive_duration=channel.default_auto_archive_duration,
            default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
            category=await CategoryChannel.serialize(channel.category) if channel.category else None,
            messages=messages,
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> discord.TextChannel:
        existing: discord.TextChannel | None = guild.get_channel(self.id)
        if not existing:
            for channel in guild.text_channels:
                if self.is_match(channel):
                    self.id = channel.id
                    existing = channel
                    log.info("Updating ID for channel %s", self.name)
                    break
        if existing:
            if self.is_match(existing, True):
                # Channel exists and has not changed
                return existing
            # Update the channel
            log.info("Updating channel %s", self.name)
            channel = existing
            await channel.edit(
                name=self.name,
                position=self.position,
                news="COMMUNITY" in guild.features and self.news,
                topic=self.topic,
                nsfw=self.nsfw,
                slowmode_delay=self.slowmode_delay,
                overwrites=self.get_overwrites(guild, buffer),
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                category=await self.category.restore(guild, buffer) if self.category else None,
            )
        else:
            log.info("Restoring channel %s", self.name)
            channel = await guild.create_text_channel(
                name=self.name,
                position=self.position,
                news="COMMUNITY" in guild.features and self.news,
                topic=self.topic,
                nsfw=self.nsfw,
                slowmode_delay=self.slowmode_delay,
                overwrites=self.get_overwrites(guild, buffer),
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                category=await self.category.restore(guild, buffer) if self.category else None,
            )
            self.id = channel.id

            # Restore messages
            async def _restore_messages():
                hook = await channel.create_webhook(
                    name=_("Cartographer Restore"), reason=_("Restoring messages from backup")
                )
                for message in self.messages:
                    embeds = await message.embed_objects()
                    files = await message.attachment_objects()
                    if not any([embeds, files, message.content]):
                        continue
                    await hook.send(
                        content=message.content[:2000] if message.content else None,
                        username=message.username,
                        avatar_url=message.avatar_url,
                        embeds=embeds,
                        files=files,
                    )
                    await asyncio.sleep(1)

            if self.messages:
                asyncio.create_task(_restore_messages())
        return channel


class ForumTag(Base):
    id: int
    name: str
    moderated: bool = False
    emoji: dict | None

    def to_discord_tag(self) -> discord.ForumTag:
        return discord.ForumTag(
            name=self.name,
            moderated=self.moderated,
            emoji=discord.PartialEmoji.from_dict(self.emoji) if self.emoji else None,
        )

    def is_match(self, tag: discord.ForumTag) -> bool:
        cases = [
            self.name == tag.name,
            self.moderated == tag.moderated,
            self.emoji == tag.emoji.to_dict() if tag.emoji else self.emoji == tag.emoji,
        ]
        return all(cases)

    @classmethod
    async def serialize(cls, tag: discord.ForumTag):
        return cls(
            id=tag.id,
            name=tag.name,
            moderated=tag.moderated,
            emoji=tag.emoji.to_dict() if tag.emoji else None,
        )

    def restore(self, forum: discord.ForumChannel) -> discord.ForumTag:
        existing = forum.get_tag(self.id)
        if existing and self.is_match(existing):
            return existing
        # Try matching by name
        for existing in forum.available_tags:
            if self.is_match(existing):
                log.info("Updating ID for tag %s", self.name)
                self.id = existing.id
                return existing
            if self.name == existing.name:
                log.info("Updating tag %s", self.name)
                existing.moderated = self.moderated
                emoji = discord.PartialEmoji.from_dict(self.emoji) if self.emoji else None
                if forum.guild.get_emoji(emoji.id):
                    existing.emoji = emoji
                else:
                    for emoji in forum.guild.emojis:
                        if emoji.name == self.name:
                            existing.emoji = emoji
                            break
                return existing
        # If we're here, the tag doesn't exist
        log.info("Creating tag %s", self.name)
        emoji = discord.PartialEmoji.from_dict(self.emoji) if self.emoji else None
        if emoji and not forum.guild.get_emoji(emoji.id):
            for existing_emoji in forum.guild.emojis:
                if existing_emoji.name == self.name:
                    emoji.id = existing_emoji.id
                    break
            else:
                emoji = None
        return discord.ForumTag(name=self.name, moderated=self.moderated, emoji=emoji)


class ForumChannel(ChannelBase):
    topic: str | None = None
    slowmode_delay: int = 0
    default_auto_archive_duration: int | None
    default_thread_slowmode_delay: int | None
    tags: list[ForumTag] = []
    default_sort_order: int = 0
    category: CategoryChannel | None = None

    def is_match(self, channel: discord.ForumChannel, check_category: bool = False) -> bool:
        if not isinstance(channel, discord.ForumChannel):
            return False
        matches = [
            self.topic == channel.topic,
            self.slowmode_delay == channel.slowmode_delay,
            self.default_auto_archive_duration == channel.default_auto_archive_duration,
            self.default_thread_slowmode_delay == channel.default_thread_slowmode_delay,
            list(self.tags) == list(channel.available_tags),
            self.default_sort_order == channel.default_sort_order.value if channel.default_sort_order else 0,
        ]
        if check_category:
            matches.append(
                self.category.is_match(channel.category) if self.category else self.category == channel.category
            )
        return all(matches) and super().is_match(channel)

    @classmethod
    async def serialize(cls, forum: discord.ForumChannel):
        return cls(
            id=forum.id,
            name=forum.name,
            position=forum.position,
            overwrites=Overwrites.serialize(forum),
            nsfw=forum.nsfw,
            topic=forum.topic,
            default_auto_archive_duration=forum.default_auto_archive_duration,
            default_thread_slowmode_delay=forum.default_thread_slowmode_delay,
            tags=[await ForumTag.serialize(i) for i in forum.available_tags],
            default_sort_order=forum.default_sort_order.value if forum.default_sort_order else 0,
            slowmode_delay=forum.slowmode_delay,
            category=await CategoryChannel.serialize(forum.category) if forum.category else None,
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> discord.ForumChannel:
        existing: discord.ForumChannel | None = guild.get_channel(self.id)
        if not existing:
            for channel in guild.forums:
                if self.is_match(channel):
                    self.id = channel.id
                    existing = channel
                    log.info("Updating ID for forum channel %s", self.name)
                    break

        if existing:
            if self.is_match(existing, True):
                # Channel exists and has not changed
                return existing
            log.info("Updating forum %s", self.name)
            forum = existing
            await forum.edit(
                name=self.name,
                position=self.position,
                topic=self.topic,
                overwrites=self.get_overwrites(guild, buffer),
                nsfw=self.nsfw,
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                slowmode_delay=self.slowmode_delay,
                default_sort_order=discord.enums.ForumOrderType(self.default_sort_order),
                category=await self.category.restore(guild, buffer) if self.category else None,
                available_tags=[tag.restore(existing) for tag in self.tags],
            )
        else:
            # Since none of the tags exist yet, we need to make sure any of them that have emojis are still valid
            valid_tags: list[discord.ForumTag] = []
            for tag in self.tags:
                if not tag.emoji:
                    valid_tags.append(tag.to_discord_tag())
                    continue
                emoji = discord.PartialEmoji.from_dict(tag.emoji)
                if guild.get_emoji(emoji.id):
                    valid_tags.append(tag.to_discord_tag())
                    continue
                for existing_emoji in guild.emojis:
                    if existing_emoji.name == tag.name:
                        log.info("Updating emoji for tag %s", tag.name)
                        tag.emoji = {
                            "id": existing_emoji.id,
                            "name": existing_emoji.name,
                            "animated": existing_emoji.animated,
                        }
                        valid_tags.append(tag.to_discord_tag())
                        break
            log.info("Restoring forum %s", self.name)
            forum = await guild.create_forum(
                name=self.name,
                topic=self.topic,
                position=self.position,
                slowmode_delay=self.slowmode_delay,
                nsfw=self.nsfw,
                overwrites=self.get_overwrites(guild, buffer),
                reason=_("Restored from backup"),
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                default_sort_order=discord.enums.ForumOrderType(self.default_sort_order),
                category=await self.category.restore(guild, buffer) if self.category else None,
                available_tags=valid_tags,
            )
            self.id = forum.id
        return forum


class VoiceChannel(ChannelBase):
    slowmode_delay: int = 0
    user_limit: int = 0
    bitrate: int
    video_quality_mode: int = 1
    topic: str | None = None
    category: CategoryChannel | None = None
    messages: list[MessageBackup] = []

    def is_match(self, channel: discord.VoiceChannel, check_category: bool = False) -> bool:
        if not isinstance(channel, discord.VoiceChannel):
            return False
        matches = [
            self.slowmode_delay == channel.slowmode_delay,
            self.user_limit == channel.user_limit,
            min(self.bitrate, channel.guild.bitrate_limit) == min(channel.bitrate, channel.guild.bitrate_limit),
            self.video_quality_mode == channel.video_quality_mode.value,
        ]
        if check_category:
            matches.append(
                self.category.is_match(channel.category) if self.category else self.category == channel.category
            )
        return all(matches) and super().is_match(channel)

    @classmethod
    async def serialize(cls, channel: VOICE, limit: int = 0) -> VoiceChannel:
        messages: list[MessageBackup] = []
        if limit:
            try:
                async for message in channel.history(limit=limit):
                    msg_obj = MessageBackup(
                        channel_id=message.channel.id,
                        channel_name=message.channel.name,
                        content=message.content[:2000] if message.content else None,
                        embeds=[i.to_dict() for i in message.embeds],
                        attachments=[i.to_dict() for i in message.attachments],
                        username=message.author.name,
                        avatar_url=message.author.display_avatar.url,
                    )
                    messages.append(msg_obj)
            except discord.HTTPException:
                log.warning("Failed to fetch messages for voice channel %s", channel.name)
        kwargs = {
            "id": channel.id,
            "name": channel.name,
            "position": channel.position,
            "overwrites": Overwrites.serialize(channel),
            "nsfw": channel.nsfw,
            "slowmode_delay": channel.slowmode_delay,
            "user_limit": channel.user_limit,
            "bitrate": channel.bitrate,
            "video_quality_mode": channel.video_quality_mode.value,
            "category": await CategoryChannel.serialize(channel.category) if channel.category else None,
            "messages": messages,
        }
        if isinstance(channel, discord.StageChannel):
            kwargs["topic"] = channel.topic
        return cls(**kwargs)

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> discord.VoiceChannel:
        existing: discord.VoiceChannel | None = guild.get_channel(self.id)
        if not existing:
            for channel in guild.forums:
                if self.is_match(channel):
                    self.id = channel.id
                    existing = channel
                    log.info("Updating ID for voice hannel %s", self.name)
                    break

        if existing:
            if self.is_match(existing, True):
                # Channel exists and has not changed
                return existing
            log.info("Updating voice channel %s", self.name)
            channel = existing
            kwargs = {
                "name": self.name,
                "position": self.position,
                "user_limit": self.user_limit,
                "bitrate": min(self.bitrate, guild.bitrate_limit),
                "video_quality_mode": discord.enums.VideoQualityMode(self.video_quality_mode),
                "overwrites": self.get_overwrites(guild, buffer),
                "category": await self.category.restore(guild, buffer) if self.category else None,
                "reason": _("Restored from backup"),
            }
            if self.topic:
                kwargs["topic"] = self.topic

            await channel.edit(**kwargs)
        else:
            log.info("Restoring voice channel %s", self.name)

            kwargs = {
                "name": self.name,
                "position": self.position,
                "user_limit": self.user_limit,
                "bitrate": min(self.bitrate, guild.bitrate_limit),
                "video_quality_mode": discord.enums.VideoQualityMode(self.video_quality_mode),
                "overwrites": self.get_overwrites(guild, buffer),
                "category": await self.category.restore(guild, buffer) if self.category else None,
                "reason": _("Restored from backup"),
            }
            if self.topic:
                kwargs["topic"] = self.topic
            channel = await guild.create_voice_channel(**kwargs)
            self.id = channel.id

            # Restore messages
            async def _restore_messages():
                hook = await channel.create_webhook(
                    name=_("Cartographer Restore"), reason=_("Restoring messages from backup")
                )
                for message in self.messages:
                    embeds = await message.embed_objects()
                    files = await message.attachment_objects()
                    if not any([embeds, files, message.content]):
                        continue
                    await hook.send(
                        content=message.content[:2000] if message.content else None,
                        username=message.username,
                        avatar_url=message.avatar_url,
                        embeds=embeds,
                        files=files,
                    )
                    await asyncio.sleep(1)

            if self.messages:
                asyncio.create_task(_restore_messages())

        return channel


class GuildEmojiBackup(Base):
    id: int
    name: str
    image: str  # base64 encoded image
    roles: list[Role] = []

    @classmethod
    async def serialize(cls, emoji: discord.Emoji):
        return cls(
            id=emoji.id,
            name=emoji.name,
            image=base64.b64encode(await emoji.read()).decode(),
            roles=[await Role.serialize(i, load_icon=False) for i in emoji.roles],
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild, buffer: StringIO) -> discord.Emoji | None:
        existing = guild.get_emoji(self.id)
        roles = [await role.restore(guild, buffer) for role in self.roles]
        if not existing:
            for emoji in guild.emojis:
                if emoji.name == self.name:
                    self.id = emoji.id
                    existing = emoji
                    log.info("Updating ID for emoji %s", self.name)
                    break
        if existing:
            if existing.name == self.name and existing.roles == roles:
                # Emoji exists and has not changed
                return existing
            log.info("Updating emoji %s", self.name)
            await existing.edit(name=self.name, roles=roles, reason=_("Restored from backup"))
        else:
            log.info("Restoring emoji %s", self.name)
            emoji = await guild.create_custom_emoji(
                name=self.name,
                image=base64.b64decode(self.image),
                roles=roles,
                reason=_("Restored from backup"),
            )
            self.id = emoji.id
        return emoji


class GuildStickerBackup(Base):
    id: int
    name: str
    description: str
    emoji: str
    image: str  # base64 encoded image
    extension: str = "png"

    def is_match(self, sticker: discord.GuildSticker) -> bool:
        return self.name == sticker.name and self.description == sticker.description and self.emoji == sticker.emoji

    @classmethod
    async def serialize(cls, sticker: discord.GuildSticker):
        return cls(
            id=sticker.id,
            name=sticker.name,
            description=sticker.description,
            emoji=sticker.emoji,
            image=base64.b64encode(await sticker.read()).decode(),
            extension=sticker.format.name,
        )

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild) -> discord.Sticker:
        try:
            sticker = await guild.fetch_sticker(self.id)
            if sticker.name == self.name:
                # Sticker exists and has not changed
                return sticker
            await sticker.edit(
                name=self.name,
                description=self.description,
                emoji=self.emoji,
                reason=_("Restored from backup"),
            )
        except discord.HTTPException:
            image_bytes = base64.b64decode(self.image)
            sticker = await guild.create_sticker(
                name=self.name,
                description=self.description,
                emoji=self.emoji,
                file=discord.File(BytesIO(image_bytes), filename=f"{self.name}.{self.extension}"),
                reason=_("Restored from backup"),
            )
        return sticker


class BanBackup(Base):
    user_id: int
    reason: str | None = None


class GuildBackup(Base):
    created: datetime = Field(default_factory=lambda: datetime.now().astimezone(tz=timezone.utc))

    id: int
    owner_id: int
    name: str
    description: str | None = None
    afk_channel: VoiceChannel | None = None
    afk_timeout: int = 0
    verification_level: int  # Enum[0, 1, 2, 3, 4]
    default_notifications: int  # Enum[0, 1]
    icon: str | None = None  # base64 encoded image or None
    banner: str | None = None  # base64 encoded image or None
    splash: str | None = None  # base64 encoded image or None
    discovery_splash: str | None = None  # base64 encoded image or None
    preferred_locale: str = "en-US"
    community: bool = False
    system_channel: TextChannel | None = None
    rules_channel: TextChannel | None = None
    public_updates: TextChannel | None = None
    explicit_content_filter: int = 0
    invites_disabled: bool = False

    bans: list[BanBackup] = []

    emojis: list[GuildEmojiBackup] = []
    stickers: list[GuildStickerBackup] = []
    roles: list[Role] = []
    members: list[Member] = []

    categories: list[CategoryChannel] = []
    text_channels: list[TextChannel] = []
    voice_channels: list[VoiceChannel] = []
    forums: list[ForumChannel] = []
    indexes: dict[int, int] = {}

    def created_fmt(self, type: t.Literal["d", "D", "t", "T", "f", "F", "R"] = "F") -> str:
        return f"<t:{int(self.created.timestamp())}:{type}>"

    @classmethod
    async def serialize(
        cls,
        guild: discord.Guild,
        limit: int = 0,
        backup_members: bool = True,
        backup_roles: bool = True,
        backup_emojis: bool = True,
        backup_stickers: bool = True,
    ) -> GuildBackup:
        banner = await guild.banner.read() if guild.banner else None
        icon = await guild.icon.read() if guild.icon else None
        splash = await guild.splash.read() if guild.splash else None
        discovery_splash = await guild.discovery_splash.read() if guild.discovery_splash else None

        index = 0
        indexes: dict[int, int] = {}
        categories: t.List[CategoryChannel] = []
        text_channels: t.List[TextChannel] = []
        voice_channels: t.List[VoiceChannel] = []
        forums: t.List[ForumChannel] = []
        for cat, channels in guild.by_category():
            if cat is not None:
                category = await CategoryChannel.serialize(cat)
                categories.append(category)
                indexes[cat.id] = index
                index += 1
            for channel in channels:
                indexes[channel.id] = index
                index += 1
                if isinstance(channel, discord.TextChannel):
                    text_channels.append(await TextChannel.serialize(channel, limit))
                elif isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    voice_channels.append(await VoiceChannel.serialize(channel, limit))
                elif isinstance(channel, discord.ForumChannel):
                    forums.append(await ForumChannel.serialize(channel))
                else:
                    log.warning("Unknown channel type: %s", channel)

        bans: list[BanBackup] = []
        async for ban in guild.bans():
            bans.append(BanBackup(user_id=ban.user.id, reason=ban.reason))

        return cls(
            id=guild.id,
            owner_id=guild.owner_id,
            name=guild.name,
            description=guild.description,
            afk_channel=await VoiceChannel.serialize(guild.afk_channel) if guild.afk_channel else None,
            afk_timeout=guild.afk_timeout,
            verification_level=guild.verification_level.value,
            default_notifications=guild.default_notifications.value,
            icon=(await asyncio.to_thread(base64.b64encode, icon)).decode() if icon else None,
            banner=(await asyncio.to_thread(base64.b64encode, banner)).decode() if banner else None,
            splash=(await asyncio.to_thread(base64.b64encode, splash)).decode() if splash else None,
            discovery_splash=(await asyncio.to_thread(base64.b64encode, discovery_splash)).decode()
            if discovery_splash
            else None,
            emojis=[await GuildEmojiBackup.serialize(i) for i in guild.emojis] if backup_emojis else [],
            stickers=[await GuildStickerBackup.serialize(i) for i in guild.stickers] if backup_stickers else [],
            preferred_locale=guild.preferred_locale.value,
            community="COMMUNITY" in list(guild.features),
            system_channel=(await TextChannel.serialize(guild.system_channel)) if guild.system_channel else None,
            rules_channel=(await TextChannel.serialize(guild.rules_channel)) if guild.rules_channel else None,
            public_updates=(await TextChannel.serialize(guild.public_updates_channel))
            if guild.public_updates_channel
            else None,
            explicit_content_filter=guild.explicit_content_filter.value,
            invites_disabled=guild.invites_paused(),
            bans=[BanBackup(user_id=i.user.id, reason=i.reason) async for i in guild.bans()],
            roles=[await Role.serialize(i) for i in guild.roles] if backup_roles else [],
            members=[await Member.serialize(i) for i in guild.members] if backup_members else [],
            categories=categories,
            text_channels=text_channels,
            voice_channels=voice_channels,
            forums=forums,
            indexes=indexes,
        )

    async def restore(self, target_guild: discord.Guild, ctx: discord.TextChannel) -> str:
        """Restore a guild backup to a target guild."""

        start = perf_counter()

        def get_status_embed(stage: int) -> discord.Embed:
            embed = discord.Embed(title=_("Restoring backup"), color=discord.Color.blurple())
            if stage < 8:
                embed.set_thumbnail(url="https://i.imgur.com/l3p6EMX.gif")
            if stage == 0:
                embed.description = _("Restoring server settings")
                embed.set_footer(text=_("Step 1 of 9"))
            elif stage == 1:
                embed.description = _("Restoring roles")
                embed.set_footer(text=_("Step 2 of 9"))
            elif stage == 2:
                embed.description = _("Restoring emojis and stickers")
                embed.set_footer(text=_("Step 3 of 9"))
            elif stage == 3:
                embed.description = _("Restoring channels")
                embed.set_footer(text=_("Step 4 of 9"))
            elif stage == 4:
                embed.description = _("Restoring AFK settings")
                embed.set_footer(text=_("Step 5 of 9"))
            elif stage == 5:
                embed.description = _("Restoring system channels")
                embed.set_footer(text=_("Step 6 of 9"))
            elif stage == 6:
                embed.description = _("Restoring remainder of the server settings")
                embed.set_footer(text=_("Step 7 of 9"))
            elif stage == 7:
                embed.description = _("Restoring member roles")
                embed.set_footer(text=_("Step 8 of 9"))
            elif stage == 8:
                embed.description = _("Restoring bans")
                embed.set_footer(text=_("Step 9 of 9"))
            else:
                embed.description = _("Restoration complete!")
                embed.color = discord.Color.green()
                embed.timestamp = datetime.now()
                delta = humanize_timedelta(seconds=perf_counter() - start)
                embed.set_footer(text=_("Server restoration took {}").format(delta))
            return embed

        log.info("Restoring backup of %s to %s", self.name, target_guild.name)
        reason = _("Cartographer Restore")
        message = await ctx.send(embed=get_status_embed(0))
        results = StringIO()

        if self.community and self.verification_level < discord.enums.VerificationLevel.medium.value:
            verification = discord.enums.VerificationLevel.medium
        else:
            verification = discord.enums.VerificationLevel(self.verification_level)
        if self.community and self.explicit_content_filter != discord.enums.ContentFilter.all_members.value:
            explicit_content_filter = discord.enums.ContentFilter.disabled
        else:
            explicit_content_filter = discord.enums.ContentFilter(self.explicit_content_filter)

        icon: bytes = base64.b64decode(self.icon) if self.icon else None
        banner: bytes = base64.b64decode(self.banner) if self.banner else None
        splash: bytes = base64.b64decode(self.splash) if self.splash else None
        discovery_splash: bytes = base64.b64decode(self.discovery_splash) if self.discovery_splash else None
        if BytesIO(banner).__sizeof__() >= target_guild.filesize_limit:
            banner = None
            results.write(_("Banner too large to restore\n"))
        if BytesIO(icon).__sizeof__() >= target_guild.filesize_limit:
            icon = None
            results.write(_("Icon too large to restore\n"))
        if BytesIO(splash).__sizeof__() >= target_guild.filesize_limit:
            splash = None
            results.write(_("Splash too large to restore\n"))
        if BytesIO(discovery_splash).__sizeof__() >= target_guild.filesize_limit:
            discovery_splash = None
            results.write(_("Discovery splash too large to restore\n"))

        log.info("Target guild is community: %s", "COMMUNITY" in target_guild.features)

        update_kwargs = {}
        if self.name != target_guild.name:
            update_kwargs["name"] = self.name
        if self.description != target_guild.description:
            update_kwargs["description"] = self.description
        if icon:
            update_kwargs["icon"] = icon
        if banner:
            update_kwargs["banner"] = banner
        if splash:
            update_kwargs["splash"] = splash
        if discovery_splash:
            update_kwargs["discovery_splash"] = discovery_splash
        if self.verification_level != target_guild.verification_level.value:
            update_kwargs["verification_level"] = verification
        if self.default_notifications != target_guild.default_notifications.value:
            update_kwargs["default_notifications"] = discord.enums.NotificationLevel(self.default_notifications)
        if self.explicit_content_filter != target_guild.explicit_content_filter.value:
            update_kwargs["explicit_content_filter"] = explicit_content_filter
        if self.preferred_locale != target_guild.preferred_locale.value:
            update_kwargs["preferred_locale"] = discord.Locale(self.preferred_locale)
        if self.invites_disabled != target_guild.invites_paused():
            update_kwargs["invites_disabled"] = self.invites_disabled
        if self.verification_level == 0 or self.explicit_content_filter == 0:
            # We must make sure community is disabled if verification is off or explicit content filter is off otherwise it will error
            update_kwargs["community"] = False
        if update_kwargs:
            log.info("Updating server settings with kwargs: %s", update_kwargs)
            await target_guild.edit(reason=reason, **update_kwargs)

        # ---------------------------- ROLES ----------------------------
        if self.roles:
            await message.edit(embed=get_status_embed(1))
            # First things first, the bot can't put any roles equal to or above its top role
            # If restoring a backup where the bot's top role isnt the highest role, we'll have to ignore them
            top_role = target_guild.me.top_role
            # The position of the top role must be the highest position in the guild, so we'll calculate that

            # Iterate backwards through the roles to avoid index errors
            for i in range(len(self.roles) - 1, -1, -1):
                role = self.roles[i]
                if target_guild.get_role(role.id):
                    continue
                # Role doesn't exist, we'll see if we can find a close match
                for existing_role in target_guild.roles:
                    if role.fuzzy_match(existing_role):
                        self.roles[i].id = existing_role.id
                        log.info("Updating ID for role %s", role.name)
                        break

            # Delete any roles that arent in the backup and didn't have a close match
            updated_backup_ids = {i.id for i in self.roles}
            for role in target_guild.roles:
                cases = [
                    not role.is_assignable(),
                    role.is_bot_managed(),
                    role.is_default(),
                    role.is_premium_subscriber(),
                    role >= top_role,
                    role.id in updated_backup_ids,
                ]
                if any(cases):
                    continue
                log.info("Deleting role %s", role.name)
                await role.delete(reason=reason)

            # - Restore the roles
            for role in sorted(self.roles, key=lambda x: x.position):
                await role.restore(target_guild, results)

        # ---------------------------- EMOJIS ----------------------------
        if self.emojis or self.stickers:
            await message.edit(embed=get_status_embed(2))
        if self.emojis:
            # Update the ID of emojis that closely match any of the target guild's emojis
            for idx, emoji in enumerate(self.emojis):
                current_emoji = target_guild.get_emoji(emoji.id)
                if current_emoji:
                    # Exact emoji already exists
                    continue
                for existing_emoji in target_guild.emojis:
                    if emoji.name == existing_emoji.name:
                        self.emojis[idx].id = existing_emoji.id
                        log.info("Updating ID for emoji %s", emoji.name)
                        break
            # Delete the target guild's emojis that arent in the backup and didn't have a close match
            updated_emoji_ids = {i.id for i in self.emojis}
            for emoji in target_guild.emojis:
                if emoji.id in updated_emoji_ids:
                    continue
                await emoji.delete(reason=reason)
                log.info("Deleted emoji %s", emoji.name)

            if len(self.emojis) > target_guild.emoji_limit:
                results.write(
                    _("Backup has more emojis than the target server can hold. Some emojis will not be restored.\n")
                )
            for idx, emoji in enumerate(self.emojis):
                if idx >= target_guild.emoji_limit:
                    results.write(_("Emoji '{}' not restored due to limit\n").format(emoji.name))
                    continue
                try:
                    await emoji.restore(target_guild)
                except discord.HTTPException as e:
                    results.write(f"Error restoring emoji {emoji.name}: {e}\n")

        # ---------------------------- STICKERS ----------------------------
        if self.stickers:
            # Delete stickers that arent in the backup before restoring
            saved_sticker_ids = {i.id for i in self.stickers}
            for sticker in target_guild.stickers:
                if sticker.id in saved_sticker_ids:
                    continue
                for current_sticker in self.stickers:
                    if current_sticker.is_match(sticker):
                        current_sticker.id = sticker.id
                        log.info("Updating ID for sticker %s", sticker.name)
                        break
                else:
                    await sticker.delete(reason=reason)
                    log.info("Deleted sticker %s", sticker.name)
            if len(self.stickers) > target_guild.sticker_limit:
                results.write(
                    _("Backup has more stickers than the target server can hold. Some stickers will not be restored.\n")
                )
            for idx, sticker in enumerate(self.stickers):
                if idx >= target_guild.sticker_limit:
                    results.write(_("Sticker '{}' not restored due to limit\n").format(sticker.name))
                    continue
                try:
                    await sticker.restore(target_guild)
                except discord.HTTPException as e:
                    results.write(f"Error restoring sticker {sticker.name}: {e}\n")

        # ---------------------------- CHANNELS ----------------------------
        await message.edit(embed=get_status_embed(3))
        all_channels: list[CategoryChannel | TextChannel | VoiceChannel | ForumChannel] = (
            self.categories + self.text_channels + self.voice_channels + self.forums
        )
        # - Sort channels by saved index
        all_channels.sort(key=lambda x: self.indexes[x.id])
        # - Update the ID of channels that closely match any of the target guild's channels
        for idx, channel in enumerate(all_channels):
            current_channel = target_guild.get_channel(channel.id)
            if current_channel:
                # Exact channel already exists
                continue
            for existing_channel in target_guild.channels:
                if channel.is_match(existing_channel):
                    all_channels[idx].id = existing_channel.id
                    log.info("Updating ID for channel %s", channel.name)
                    break
        # - Delete the target guild's channels that arent in the backup and didn't have a close match
        updated_channel_ids = {i.id for i in all_channels}
        maybe_delete_later: list[discord.TextChannel] = []
        for channel in target_guild.channels:
            if channel.id in updated_channel_ids:
                continue
            if channel == ctx:
                continue
            if channel in [target_guild.public_updates_channel, target_guild.rules_channel]:
                maybe_delete_later.append(channel)
                continue
            await channel.delete(reason=reason)
            log.info("Deleted %s channel %s", type(channel), channel.name)
        # - If the current channel is not in the backup, we will need to offset all channel positions by 1
        if ctx.id not in updated_channel_ids:
            await ctx.send(_("This channel isn't part of the backup, it can be deleted after the restore is complete."))
            for channel in all_channels:
                channel.position += 1
        # - Channels should already be sorted by position
        for channel in all_channels:
            if isinstance(channel, ForumChannel) and "COMMUNITY" not in target_guild.features:
                continue
            await channel.restore(target_guild, results)

        # ---------------------------- REMAINING SETTINGS ----------------------------
        await message.edit(embed=get_status_embed(4))
        # Restore AFK settings
        afk_channel: discord.VoiceChannel | None = (
            target_guild.get_channel(self.afk_channel.id) if self.afk_channel else None
        )
        if self.afk_channel and not afk_channel:
            for channel in target_guild.voice_channels:
                if self.afk_channel.is_match(channel):
                    afk_channel = channel
                    break
        await message.edit(embed=get_status_embed(5))
        # Restore system channel
        system_channel: discord.TextChannel | None = (
            target_guild.get_channel(self.system_channel.id) if self.system_channel else None
        )
        if self.system_channel and not system_channel:
            for channel in target_guild.text_channels:
                if self.system_channel.is_match(channel):
                    system_channel = channel
                    break
        # Restore public updates channel
        public_updates_channel: discord.TextChannel | None = (
            target_guild.get_channel(self.public_updates.id) if self.public_updates else None
        )
        if self.public_updates and not public_updates_channel:
            for channel in target_guild.text_channels:
                if self.public_updates.is_match(channel):
                    public_updates_channel = channel
                    break

        rules_channel: discord.TextChannel | None = (
            target_guild.get_channel(self.rules_channel.id) if self.rules_channel else None
        )
        if self.rules_channel and not rules_channel:
            for channel in target_guild.text_channels:
                if self.rules_channel.is_match(channel):
                    rules_channel = channel
                    break

        await message.edit(embed=get_status_embed(6))
        update_kwargs = {}
        if afk_channel:
            update_kwargs["afk_channel"] = afk_channel
        if self.afk_timeout != target_guild.afk_timeout:
            update_kwargs["afk_timeout"] = self.afk_timeout
        if system_channel:
            update_kwargs["system_channel"] = system_channel
        if rules_channel:
            update_kwargs["rules_channel"] = rules_channel
        if public_updates_channel:
            update_kwargs["public_updates_channel"] = public_updates_channel
        if self.community and rules_channel and public_updates_channel:
            update_kwargs["community"] = self.community
        if update_kwargs:
            log.info("Updating remaining server settings %s", update_kwargs.keys())
            await target_guild.edit(reason=reason, **update_kwargs)

        if maybe_delete_later:
            for channel in maybe_delete_later:
                try:
                    await channel.delete(reason=reason)
                except discord.HTTPException as e:
                    results.write(f"Failed to delete channel {channel.name}: {e}\n")

        # Now that the system channels have been restored and community settings configured, we can restore the forum channels maybe
        if "COMMUNITY" in target_guild.features:
            forums = [i for i in all_channels if isinstance(i, ForumChannel)]
            for forum in forums:
                await forum.restore(target_guild, results)

        # ---------------------------- MEMBER ROLES ----------------------------
        if self.members:
            await message.edit(embed=get_status_embed(7))
            for member in self.members:
                await member.restore(target_guild, results)

        # ---------------------------- BANS ----------------------------
        if self.bans:
            await message.edit(embed=get_status_embed(8))
            existing_ban_ids = [entry.user.id async for entry in target_guild.bans()]
            for ban in self.bans:
                if ban.user_id in existing_ban_ids:
                    continue
                user = discord.Object(id=ban.user_id)
                log.info("Re-banning user %s", user.id)
                try:
                    await target_guild.ban(user, reason=ban.reason)
                except discord.HTTPException as e:
                    results.write(f"Failed to ban user {user.id}: {e}\n")

        await message.edit(embed=get_status_embed(9))
        return results.getvalue()
