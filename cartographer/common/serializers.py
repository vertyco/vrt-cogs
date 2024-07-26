from __future__ import annotations

import asyncio
import base64
import logging
import typing as t
from datetime import datetime, timezone
from io import BytesIO

import aiohttp
import discord
from pydantic import Field
from redbot.core.i18n import Translator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from . import Base

log = logging.getLogger("red.vrt.cartographer.serializers")
_ = Translator("Cartographer", __file__)


VOICE = t.Union[discord.VoiceChannel, discord.StageChannel]
GuildChannels = t.Union[VOICE, discord.ForumChannel, discord.TextChannel, discord.CategoryChannel]


class Role(Base):
    id: int
    name: str
    color: int
    hoist: bool
    position: int
    permissions: int
    mentionable: bool
    icon: str | None
    is_assignable: bool = False
    is_bot_managed: bool = False
    is_integration: bool = False
    is_premium_subscriber: bool = False
    is_default: bool = False

    def is_match(self, role: discord.Role) -> bool:
        cases = [
            self.name == role.name,
            self.color == role.color.value,
            self.hoist == role.hoist,
            self.position == role.position,
            self.permissions == role.permissions.value,
            self.mentionable == role.mentionable,
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

    @property
    def leave_alone(self) -> bool:
        skip = [
            not self.is_assignable,
            self.is_bot_managed,
            self.is_default,
            self.is_integration,
            self.is_premium_subscriber,
        ]
        return any(skip)

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild) -> discord.Role:
        supports_emojis = "ROLE_ICONS" in guild.features
        existing: discord.Role | None = guild.get_role(self.id)
        if not existing:
            for role in guild.roles:
                if self.is_match(role):
                    self.id = role.id
                    existing = role
                    log.info("Updating ID for role %s", self.name)

        if existing:
            if self.is_match(existing):
                # Role exists and has not changed
                return existing
            if self.leave_alone:
                return existing
            log.info("Updating role %s", self.name)
            role = existing
            await role.edit(
                name=self.name,
                color=self.color,
                hoist=self.hoist,
                position=self.position,
                permissions=discord.Permissions(self.permissions),
                mentionable=self.mentionable,
                display_icon=base64.b64decode(self.icon) if self.icon and supports_emojis else None,
                reason=_("Restored from backup"),
            )
        else:
            log.info("Restoring role %s", self.name)
            role = await guild.create_role(
                name=self.name,
                color=self.color,
                hoist=self.hoist,
                permissions=discord.Permissions(self.permissions),
                mentionable=self.mentionable,
                display_icon=base64.b64decode(self.icon) if self.icon and supports_emojis else None,
                reason=_("Restored from backup"),
            )
        return role


class Member(Base):
    id: int
    roles: list[Role]

    @classmethod
    async def serialize(cls, member: discord.Member) -> Member:
        return cls(id=member.id, roles=[await Role.serialize(i, False) for i in member.roles])

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild) -> bool:
        member = guild.get_member(self.id)
        if not member:
            return False

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
                if role_backup.leave_alone:
                    continue
                role = guild.get_role(role_backup.id)
                if not role:
                    continue
                if role >= guild.me.top_role:
                    continue
                if role not in member.roles:
                    to_add.append(role)
                for current_role in member.roles:
                    if current_role.id not in saved_role_ids:
                        to_remove.append(current_role)

        await asyncio.to_thread(_compute)

        if to_add:
            await member.add_roles(*to_add, reason=_("Restored from backup"))
        if to_remove:
            await member.remove_roles(*to_remove, reason=_("Restored from backup"))
        return True


class Overwrites(Base):
    id: int  # Role or member ID
    values: dict[str, bool | None] = {}

    @classmethod
    def serialize(cls, obj: GuildChannels) -> list[Overwrites]:
        overwrites: list[Overwrites] = [
            cls(id=role_mem.id, values=perms._values) for role_mem, perms in obj.overwrites.items()
        ]
        return overwrites

    def get(self, guild: discord.Guild) -> discord.Role | discord.Member | None:
        return guild.get_member(self.id) or guild.get_role(self.id)


class ChannelBase(Base):
    id: int
    name: str
    position: int
    overwrites: list[Overwrites]
    nsfw: bool = False

    def get_overwrites(self, guild: discord.Guild) -> dict:
        return {i.get(guild): discord.PermissionOverwrite(**i.values) for i in self.overwrites if i.get(guild)}

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
    async def restore(self, guild: discord.Guild) -> discord.CategoryChannel:
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
                overwrites=self.get_overwrites(guild),
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
                    overwrites=self.get_overwrites(guild),
                    reason=_("Restored from backup"),
                )
                self.id = category.id
        return category


class MessageBackup(Base):
    channel_id: int
    channel_name: str
    content: str | None = None
    embeds: list[dict] = []
    attachments: list[dict] = []
    username: str
    avatar_url: str

    @property
    def embed_objects(self) -> list[discord.Embed]:
        return [discord.Embed.from_dict(i) for i in self.embeds]

    @property
    def attachment_objects(self) -> list[discord.Attachment]:
        return [discord.Attachment.from_dict(i) for i in self.attachments]


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
        # TODO: backup webhooks?
        messages: list[MessageBackup] = []
        if limit:
            async for message in channel.history(limit=limit):
                msg_obj = MessageBackup(
                    channel_id=message.channel.id,
                    channel_name=message.channel.name,
                    content=message.content,
                    embeds=[i.to_dict() for i in message.embeds],
                    attachments=[i.to_dict() for i in message.attachments],
                    username=message.author.name,
                    avatar_url=message.author.display_avatar.url,
                )
                messages.append(msg_obj)
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
    async def restore(self, guild: discord.Guild) -> discord.TextChannel:
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
                overwrites=self.get_overwrites(guild),
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                category=await self.category.restore(guild) if self.category else None,
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
                overwrites=self.get_overwrites(guild),
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                category=await self.category.restore(guild) if self.category else None,
            )
            self.id = channel.id
            # Restore messages
            if self.messages:
                hook = await channel.create_webhook(
                    name=_("Cartographer Restore"), reason=_("Restoring messages from backup")
                )
                for message in self.messages:
                    await hook.send(
                        content=message.content,
                        username=message.username,
                        avatar_url=message.avatar_url,
                        embeds=message.embed_objects,
                        files=message.attachment_objects,
                    )
        return channel


class ForumTag(Base):
    id: int
    name: str
    moderated: bool
    emoji: dict | None

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

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, forum: discord.ForumChannel) -> discord.ForumTag:
        existing = forum.get_tag(self.id)
        if not existing:
            for tag in forum.available_tags:
                if self.is_match(tag):
                    self.id = tag.id
                    self.moderated = tag.moderated
                    self.emoji = tag.emoji.to_dict() if tag.emoji else None
                    return tag
        return await forum.create_tag(
            name=self.name,
            emoji=discord.PartialEmoji.from_dict(self.emoji) if self.emoji else None,
            moderated=self.moderated,
        )


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
    async def restore(self, guild: discord.Guild) -> discord.ForumChannel:
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
                overwrites=self.get_overwrites(guild),
                nsfw=self.nsfw,
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                slowmode_delay=self.slowmode_delay,
                default_sort_order=discord.enums.ForumOrderType(self.default_sort_order),
                category=await self.category.restore(guild) if self.category else None,
            )
        else:
            log.info("Restoring forum %s", self.name)
            forum = await guild.create_forum(
                name=self.name,
                topic=self.topic,
                position=self.position,
                slowmode_delay=self.slowmode_delay,
                nsfw=self.nsfw,
                overwrites=self.get_overwrites(guild),
                reason=_("Restored from backup"),
                default_auto_archive_duration=self.default_auto_archive_duration,
                default_thread_slowmode_delay=self.default_thread_slowmode_delay,
                default_sort_order=discord.enums.ForumOrderType(self.default_sort_order),
                category=await self.category.restore(guild) if self.category else None,
            )

            self.id = forum.id
        for tag in self.tags:
            await tag.restore(forum)
        return forum


class VoiceChannel(ChannelBase):
    slowmode_delay: int = 0
    user_limit: int
    bitrate: int
    video_quality_mode: int = 1
    topic: str | None = None
    category: CategoryChannel | None = None

    def is_match(self, channel: discord.VoiceChannel, check_category: bool = False) -> bool:
        if not isinstance(channel, discord.VoiceChannel):
            return False
        matches = [
            self.slowmode_delay == channel.slowmode_delay,
            self.user_limit == channel.user_limit,
            self.bitrate == channel.bitrate,
            self.video_quality_mode == channel.video_quality_mode.value,
        ]
        if check_category:
            matches.append(
                self.category.is_match(channel.category) if self.category else self.category == channel.category
            )
        return all(matches) and super().is_match(channel)

    @classmethod
    async def serialize(cls, channel: VOICE):
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
    async def restore(self, guild: discord.Guild) -> discord.VoiceChannel:
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
                "bitrate": self.bitrate,
                "video_quality_mode": discord.enums.VideoQualityMode(self.video_quality_mode),
                "overwrites": self.get_overwrites(guild),
                "category": await self.category.restore(guild) if self.category else None,
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
                "bitrate": self.bitrate,
                "video_quality_mode": discord.enums.VideoQualityMode(self.video_quality_mode),
                "overwrites": self.get_overwrites(guild),
                "category": await self.category.restore(guild) if self.category else None,
                "reason": _("Restored from backup"),
            }
            if self.topic:
                kwargs["topic"] = self.topic
            channel = await guild.create_voice_channel(**kwargs)
            self.id = channel.id
        return channel


class GuildEmojiBackup(Base):
    id: int
    name: str
    image: str  # base64 encoded image
    # TODO: add 'roles' attribute for list of roles that can use the emoji

    @classmethod
    async def serialize(cls, emoji: discord.Emoji):
        return cls(id=emoji.id, name=emoji.name, image=base64.b64encode(await emoji.read()).decode())

    @retry(
        retry=retry_if_exception_type(aiohttp.ClientConnectionError | aiohttp.ClientOSError),
        wait=wait_random_exponential(min=1, max=3),
        stop=stop_after_attempt(5),
        reraise=False,
    )
    async def restore(self, guild: discord.Guild) -> discord.Emoji | None:
        existing = guild.get_emoji(self.id)
        if not existing:
            for emoji in guild.emojis:
                if emoji.name == self.name:
                    self.id = emoji.id
                    existing = emoji
                    log.info("Updating ID for emoji %s", self.name)
                    break
        if existing:
            if existing.name == self.name:
                # Emoji exists and has not changed
                return existing
            log.info("Updating emoji %s", self.name)
            await existing.edit(name=self.name)
        else:
            log.info("Restoring emoji %s", self.name)
            emoji = await guild.create_custom_emoji(name=self.name, image=base64.b64decode(self.image))
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


class GuildBackup(Base):
    created: datetime = Field(default_factory=lambda: datetime.now().astimezone(tz=timezone.utc))

    id: int
    owner_id: int
    name: str
    description: str | None = None
    afk_channel: VoiceChannel | None = None
    afk_timeout: int
    verification_level: int  # Enum[0, 1, 2, 3, 4]
    default_notifications: int  # Enum[0, 1]
    icon: str | None = None  # base64 encoded image or None
    banner: str | None = None  # base64 encoded image or None
    splash: str | None = None  # base64 encoded image or None
    discovery_splash: str | None = None  # base64 encoded image or None
    preferred_locale: str
    community: bool = False
    system_channel: TextChannel | None = None
    rules_channel: TextChannel | None = None
    public_updates: TextChannel | None = None
    explicit_content_filter: int = 0
    invites_disabled: bool = False

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
    async def serialize(cls, guild: discord.Guild, limit: int = 0) -> GuildBackup:
        banner = await guild.banner.read() if guild.banner else None
        icon = await guild.icon.read() if guild.icon else None
        splash = await guild.splash.read() if guild.splash else None
        discovery_splash = await guild.discovery_splash.read() if guild.discovery_splash else None
        roles = [await Role.serialize(i) for i in guild.roles]

        return cls(
            id=guild.id,
            owner_id=guild.owner_id,
            name=guild.name,
            description=guild.description,
            afk_channel=await VoiceChannel.serialize(guild.afk_channel) if guild.afk_channel else None,
            afk_timeout=guild.afk_timeout,
            verification_level=guild.verification_level.value,
            default_notifications=guild.default_notifications.value,
            icon=base64.b64encode(icon).decode() if icon else None,
            banner=base64.b64encode(banner).decode() if banner else None,
            splash=base64.b64encode(splash).decode() if splash else None,
            discovery_splash=base64.b64encode(discovery_splash).decode() if discovery_splash else None,
            emojis=[await GuildEmojiBackup.serialize(i) for i in guild.emojis],
            stickers=[await GuildStickerBackup.serialize(i) for i in guild.stickers],
            preferred_locale=str(guild.preferred_locale),
            community="COMMUNITY" in list(guild.features),
            system_channel=(await TextChannel.serialize(guild.system_channel)) if guild.system_channel else None,
            rules_channel=(await TextChannel.serialize(guild.rules_channel)) if guild.rules_channel else None,
            public_updates=(await TextChannel.serialize(guild.public_updates_channel))
            if guild.public_updates_channel
            else None,
            explicit_content_filter=guild.explicit_content_filter.value,
            invites_disabled=guild.invites_paused(),
            roles=[i for i in roles if not i.leave_alone and i.id != guild.id],
            members=[await Member.serialize(i) for i in guild.members],
            categories=[await CategoryChannel.serialize(i) for i in guild.categories],
            text_channels=[await TextChannel.serialize(i, limit) for i in guild.text_channels],
            voice_channels=[await VoiceChannel.serialize(i) for i in guild.voice_channels],
            forums=[await ForumChannel.serialize(i) for i in guild.forums],
            indexes={c.id: idx for idx, c in enumerate(guild.channels)},
        )

    async def restore(self, target_guild: discord.Guild, ctx: discord.TextChannel):
        """Restore a guild backup to a target guild.

        # Guilds must be restored in the following order:
        - Restore guild settings that dont require channels
        - Restore emojis and stickers
        - Restore roles in order of position
        - ALL channels (categories, text, voice, forums) in order of position
        - AFK channel and timeout settings
        - Reassign Rules channel, Public updates channel, and Safety alerts channel
        - Restore member roles
        """

        def get_status_embed(stage: int) -> discord.Embed:
            embed = discord.Embed(title=_("Restoring backup"), color=discord.Color.blurple())
            if stage == 0:
                embed.description = _("Restoring server settings")
                embed.set_footer(text=_("Step 1 of 8"))
            elif stage == 1:
                embed.description = _("Restoring emojis and stickers")
                embed.set_footer(text=_("Step 2 of 8"))
            elif stage == 2:
                embed.description = _("Restoring roles")
                embed.set_footer(text=_("Step 3 of 8"))
            elif stage == 3:
                embed.description = _("Restoring channels")
                embed.set_footer(text=_("Step 4 of 8"))
            elif stage == 4:
                embed.description = _("Restoring AFK settings")
                embed.set_footer(text=_("Step 5 of 8"))
            elif stage == 5:
                embed.description = _("Restoring system channels")
                embed.set_footer(text=_("Step 6 of 8"))
            elif stage == 6:
                embed.description = _("Restoring remainder of the server settings")
                embed.set_footer(text=_("Step 7 of 8"))
            elif stage == 7:
                embed.description = _("Restoring member roles")
                embed.set_footer(text=_("Step 8 of 8"))
            else:
                embed.description = _("Restoration complete!")
                embed.color = discord.Color.green()
                embed.timestamp = datetime.now()
            return embed

        log.info("Restoring backup of %s to %s", self.name, target_guild.name)
        reason = _("Cartographer Restore")
        message = await ctx.send(embed=get_status_embed(0))

        if self.community and self.verification_level < discord.enums.VerificationLevel.medium.value:
            verification = discord.enums.VerificationLevel.medium
        else:
            verification = discord.enums.VerificationLevel(self.verification_level)
        if self.community and self.explicit_content_filter != discord.enums.ContentFilter.all_members.value:
            explicit_content_filter = discord.enums.ContentFilter.disabled
        else:
            explicit_content_filter = discord.enums.ContentFilter(self.explicit_content_filter)

        icon = base64.b64decode(self.icon) if self.icon else None
        banner = base64.b64decode(self.banner) if self.banner else None
        splash = base64.b64decode(self.splash) if self.splash else None
        discovery_splash = base64.b64decode(self.discovery_splash) if self.discovery_splash else None
        if BytesIO(banner).__sizeof__() >= target_guild.filesize_limit:
            banner = None
        if BytesIO(icon).__sizeof__() >= target_guild.filesize_limit:
            icon = None
        if BytesIO(splash).__sizeof__() >= target_guild.filesize_limit:
            splash = None
        if BytesIO(discovery_splash).__sizeof__() >= target_guild.filesize_limit:
            discovery_splash = None

        await target_guild.edit(
            reason=reason,
            name=self.name,
            icon=icon,
            banner=banner,
            splash=splash,
            discovery_splash=discovery_splash,
            description=self.description,
            verification_level=verification,
            default_notifications=discord.enums.NotificationLevel(self.default_notifications),
            explicit_content_filter=explicit_content_filter,
            preferred_locale=self.preferred_locale,
            invites_disabled=self.invites_disabled,
        )

        # Delete emojis that arent in the backup before restoring
        await message.edit(embed=get_status_embed(1))
        saved_emoji_names = {i.id for i in self.emojis}
        for emoji in target_guild.emojis:
            if emoji.name not in saved_emoji_names:
                await emoji.delete(reason=reason)
                log.info("Deleted emoji %s", emoji.name)
        if len(self.emojis) > target_guild.emoji_limit:
            await ctx.send(
                _("This server has more emojis than the target server can hold. Some emojis will not be restored.")
            )
        for emoji in self.emojis[: target_guild.emoji_limit]:
            asyncio.create_task(emoji.restore(target_guild))

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
            await ctx.send(
                _("This server has more stickers than the target server can hold. Some stickers will not be restored.")
            )
        for sticker in self.stickers[: target_guild.sticker_limit]:
            asyncio.create_task(sticker.restore(target_guild))

        await message.edit(embed=get_status_embed(2))
        # Sort all roles by thier position and update by best match
        for idx, role in enumerate(self.roles):
            role.position = idx
            current_role = target_guild.get_role(role.id)
            if current_role:
                continue
            for existing_role in target_guild.roles:
                if role.is_match(existing_role):
                    log.info("Updating ID for role %s", role.name)
                    role.id = existing_role.id
                    break

        backup_role_ids = [i.id for i in self.roles]
        for role in target_guild.roles:
            if role.id in backup_role_ids:
                continue
            if role >= target_guild.me.top_role:
                # We cant delete roles above the bot's top role
                continue
            skip = [
                role.id == target_guild.id,
                not role.is_assignable(),
            ]
            if any(skip):
                continue
            await role.delete(reason=reason)
            log.info("Deleted role %s", role.name)

        # Restore roles
        # Offset all positions by the bot's top role, since we cant create roles above the bot's top role
        for role in self.roles:
            try:
                await role.restore(target_guild)
            except discord.HTTPException as e:
                log.error("Failed to restore role %s: %s", role.name, e)

        await message.edit(embed=get_status_embed(3))
        # First we need to delete all channels that arent part of the backup
        all_channels: list[CategoryChannel | TextChannel | VoiceChannel | ForumChannel] = (
            self.categories + self.text_channels + self.voice_channels + self.forums
        )
        # Sort channels by the index and apply the new position
        all_channels.sort(key=lambda x: self.indexes[x.id])
        for idx, channel in enumerate(all_channels):
            channel.position = idx
            if target_guild.get_channel(channel.id):
                continue
            # Try to match the channel to an existing channel
            for existing_channel in target_guild.channels:
                if channel.is_match(existing_channel):
                    log.info("Updating ID for channel %s", channel.name)
                    channel.id = existing_channel.id
                    break

        all_channel_ids = [i.id for i in all_channels]
        # Now delete any channels that arent in the backup
        for channel in target_guild.channels:
            if channel.id in all_channel_ids + [ctx.id]:
                # Ignore existing and the current context channel
                continue
            await channel.delete(reason=reason)
            log.info("Deleted channel %s", channel.name)

        # If the current channel is not in the backup, we will need to offset all channel positions by 1
        current_channel = None
        if ctx.id not in all_channel_ids:
            # We'll need to offset all channel positions by 1
            for channel in all_channels:
                channel.position += 1
            # See if there is a closest match:
            for channel in all_channels:
                # Make sure the channel is the same type as the current channel
                if isinstance(channel, (CategoryChannel,)):
                    continue
                if channel.is_match(ctx):
                    # If we find a substitute match for the current channel, we'll need to offset all channel positions by 1
                    # After that  we'll have to restore the current channel's position
                    current_channel = channel
                    channel.id = ctx.id
                    break
            else:
                log.info("Current channel is not in backup, offsetting channel positions by 1")

        # # Restore categories first since order is weird with them
        # for category in self.categories:
        #     await category.restore(target_guild)
        for channel in all_channels:
            # category: CategoryChannel | None = getattr(channel, "category", None)
            # if category:
            #     await category.restore(target_guild)
            await channel.restore(target_guild)

        if current_channel:
            await current_channel.restore(target_guild)

        await message.edit(embed=get_status_embed(4))
        # Restore AFK settings
        afk_channel = target_guild.get_channel(self.afk_channel.id) if self.afk_channel else None
        if self.afk_channel and not afk_channel:
            for channel in target_guild.voice_channels:
                if self.afk_channel.is_match(channel):
                    afk_channel = channel
                    break
        await message.edit(embed=get_status_embed(5))
        # Restore system channel
        system_channel = target_guild.get_channel(self.system_channel.id) if self.system_channel else None
        if self.system_channel and not system_channel:
            for channel in target_guild.text_channels:
                if self.system_channel.is_match(channel):
                    system_channel = channel
                    break
        # Restore public updates channel
        public_updates_channel = target_guild.get_channel(self.public_updates.id) if self.public_updates else None
        if self.public_updates and not public_updates_channel:
            for channel in target_guild.text_channels:
                if self.public_updates.is_match(channel):
                    public_updates_channel = channel
                    break

        rules_channel = target_guild.get_channel(self.rules_channel.id) if self.rules_channel else None
        if self.rules_channel and not rules_channel:
            for channel in target_guild.text_channels:
                if self.rules_channel.is_match(channel):
                    rules_channel = channel
                    break

        await message.edit(embed=get_status_embed(6))
        await target_guild.edit(
            afk_channel=afk_channel,
            afk_timeout=self.afk_timeout,
            system_channel=system_channel,
            public_updates_channel=public_updates_channel,
            rules_channel=rules_channel,
            community=self.community if rules_channel and public_updates_channel else False,
        )

        await message.edit(embed=get_status_embed(7))
        # Finally restore member roles
        for member in self.members:
            await member.restore(target_guild)
        await message.edit(embed=get_status_embed(8))
