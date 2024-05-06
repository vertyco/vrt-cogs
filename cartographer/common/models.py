import asyncio
import base64
import logging
import typing as t
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import discord
import orjson
from discord.enums import ContentFilter, NotificationLevel, VerificationLevel
from pydantic import VERSION, BaseModel, Field
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify

log = logging.getLogger("red.vrt.cartographer.models")
_ = Translator("Cartographer", __file__)

VOICE = t.Union[discord.VoiceChannel, discord.StageChannel]
GuildChannels = t.Union[VOICE, discord.ForumChannel, discord.TextChannel, discord.CategoryChannel]


def get_named_channel(guild: discord.Guild, channel_name: str) -> GuildChannels | None:
    mapping: dict = {i.name: i for i in guild.channels}
    return mapping.get(channel_name)


def get_named_category(guild: discord.Guild, channel_name: str) -> discord.CategoryChannel | None:
    mapping = {i.name: i for i in guild.categories}
    return mapping.get(channel_name)


def get_named_role(guild: discord.Guild, role_name: str) -> discord.Role | None:
    mapping = {i.name: i for i in guild.roles}
    return mapping.get(role_name)


class Base(BaseModel):
    def model_dump(self, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(*args, **kwargs)
        if kwargs.pop("mode", "") == "json":
            return orjson.loads(super().json(*args, **kwargs))
        return super().dict(*args, **kwargs)

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)


class Overwrites(Base):
    type: int  # 0 for role, 1 for member
    id: int
    role_name: str | None = None
    values: dict[str, bool] = {}

    @classmethod
    def serialize(cls, obj: discord.TextChannel | discord.VoiceChannel | discord.CategoryChannel) -> list[t.Self]:
        overwrites = []
        for role_or_mem_obj, overwrite in obj.overwrites.items():
            obj_type = 0 if isinstance(role_or_mem_obj, discord.Role) else 1
            name = role_or_mem_obj.name if isinstance(role_or_mem_obj, discord.Role) else None
            overwrites.append(cls(type=obj_type, id=role_or_mem_obj.id, values=overwrite._values, role_name=name))
        return overwrites

    def get(self, guild: discord.Guild) -> discord.Member | discord.Role | None:
        if self.type == 0:
            role = guild.get_role(self.id)
            if not role:
                role = get_named_role(guild, self.role_name)
            return role
        else:
            return guild.get_member(self.id)


class Role(Base):
    id: int
    name: str
    color: int
    hoist: bool
    position: int
    permissions: int
    mentionable: bool
    icon: str | None
    is_assignable: bool
    is_managed: bool
    is_integration: bool
    is_premium: bool
    is_default: bool

    @classmethod
    def member_serialize(cls, role: discord.Role):
        return cls(
            id=role.id,
            name=role.name,
            color=role.color.value,
            hoist=role.hoist,
            position=role.position,
            permissions=role.permissions.value,
            mentionable=role.mentionable,
            icon=None,
            is_assignable=role.is_assignable(),
            is_managed=role.is_bot_managed(),
            is_integration=role.is_integration(),
            is_premium=role.is_premium_subscriber(),
            is_default=role.is_default(),
        )

    @classmethod
    async def serialize(cls, role: discord.Role):
        icon = await role.icon.read() if role.icon else None
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
            is_managed=role.is_bot_managed(),
            is_integration=role.is_integration(),
            is_premium=role.is_premium_subscriber(),
            is_default=role.is_default(),
        )

    def leave_alone(self) -> bool:
        skip = [
            not self.is_assignable,
            self.is_managed,
            self.is_integration,
            self.is_premium,
            self.is_default,
        ]
        return any(skip)

    async def restore(self, guild: discord.Guild) -> discord.Role | None:
        if guild.get_channel(self.id):
            # Role already exists
            return
        if self.leave_alone():
            return
        log.debug(f"Restoring role {self.name}")
        try:
            role = await guild.create_role(
                name=self.name,
                hoist=self.hoist,
                permissions=discord.Permissions(self.permissions),
                color=self.color,
                display_icon=base64.b64decode(self.icon) if self.icon else None,
                reason=_("Restored from backup"),
            )
        except Exception as e:
            if "needs more boosts" not in str(e):
                log.error(f"Failed to create role {self.name}", exc_info=e)
                return
            role = await guild.create_role(
                name=self.name,
                hoist=self.hoist,
                permissions=discord.Permissions(self.permissions),
                color=self.color,
                reason=_("Restored from backup"),
            )

        self.id = role.id
        return role

    async def update(self, guild: discord.Guild) -> None:
        role = guild.get_role(self.id)
        if not role:
            return
        skip = [
            role.name == self.name,
            str(role.color) == str(self.color),
            role.hoist == self.hoist,
            role.position == self.position,
            role.permissions.value == self.permissions,
            role.mentionable == self.mentionable,
            role.icon == self.icon,
            role >= guild.me.top_role,
            not role.is_assignable(),
            role.is_bot_managed(),
            role.is_default(),
            role.is_integration(),
            role.is_premium_subscriber(),
            self.position >= guild.me.top_role.position,
        ]
        if all(skip):
            return
        log.debug(f"Updating role {role.name}")
        reason = _("Restored from backup")
        perms = discord.Permissions(self.permissions)
        if self.leave_alone():
            await role.edit(
                reason=reason,
                permissions=perms,
                mentionable=self.mentionable,
            )
            return
        # All roles will need to be placed below the bot's top role so it can properly set the position
        # This means the saved position will need to be adjusted
        top_role = guild.me.top_role
        if self.position >= top_role.position:
            self.position -= top_role.position - 1
        try:
            await role.edit(
                reason=reason,
                name=self.name,
                color=self.color,
                hoist=self.hoist,
                position=self.position,
                permissions=perms,
                mentionable=self.mentionable,
                display_icon=base64.b64decode(self.icon) if self.icon else None,
            )
        except discord.HTTPException:
            await role.edit(
                reason=reason,
                name=self.name,
                color=self.color,
                hoist=self.hoist,
                permissions=perms,
                mentionable=self.mentionable,
                display_icon=base64.b64decode(self.icon) if self.icon else None,
            )


class Member(Base):
    id: int
    roles: list[Role]

    @classmethod
    def serialize(cls, member: discord.Member):
        return cls(id=member.id, roles=[Role.member_serialize(i) for i in member.roles])

    async def restore(self, guild: discord.Guild, remove_others: bool = False):
        member = guild.get_member(self.id)
        if not member:
            return
        member_roles = [r.name for r in member.roles]
        backup_roles = [r.name for r in self.roles]

        to_add = set()
        to_remove = set()

        for role_backup in self.roles:
            if role_backup.name in member_roles:
                # Member already has it
                continue
            if role_backup.leave_alone():
                continue
            role = guild.get_role(role_backup.id)
            if not role:
                role = get_named_role(guild, role_backup.name)
            if role:
                skip = [
                    not role.is_assignable(),
                    role.is_bot_managed(),
                    role.is_default(),
                    role.is_integration(),
                    role.is_premium_subscriber(),
                    role >= guild.me.top_role,
                ]
                if any(skip):
                    continue
                to_add.add(role)

        if remove_others:
            for role in member.roles:
                if role >= guild.me.top_role:
                    continue
                if role.name not in backup_roles and role not in to_add:
                    to_remove.add(role)

        to_remove = [i for i in to_remove if i and i not in to_add]
        to_add = [i for i in to_add if i]

        if to_remove or to_add:
            log.debug(f"Updating roles for {member.name}")
        if to_remove:
            asyncio.create_task(member.remove_roles(*to_remove))
        if to_add:
            asyncio.create_task(member.add_roles(*to_add))


class CategoryChannel(Base):
    id: int
    name: str
    position: int
    nsfw: bool = False
    overwrites: list[Overwrites]

    @classmethod
    def serialize(cls, channel: discord.CategoryChannel):
        return cls(
            id=channel.id,
            name=channel.name,
            position=channel.position,
            nsfw=channel.nsfw,
            overwrites=Overwrites.serialize(channel),
        )

    def get_overwrites(self, guild: discord.Guild) -> dict:
        return {i.get(guild): discord.PermissionOverwrite(**i.values) for i in self.overwrites if i.get(guild)}

    async def restore(self, guild: discord.Guild) -> discord.CategoryChannel | None:
        if guild.get_channel(self.id):
            return
        log.debug(f"Restoring category channel {self.name}")
        channel = await guild.create_category(
            name=self.name,
            overwrites=self.get_overwrites(guild),
            reason="Restored from backup",
            position=0,
        )
        self.id = channel.id
        return channel

    async def update(self, guild: discord.Guild) -> None:
        channel = guild.get_channel(self.id)
        if not channel:
            return
        if not isinstance(channel, discord.CategoryChannel):
            return
        equal = [
            channel.name == self.name,
            channel.position == self.position,
            channel.nsfw == self.nsfw,
            channel.overwrites == self.get_overwrites(guild),
        ]
        if all(equal):
            return
        log.debug(f"Updating category {channel.name}")
        await channel.edit(
            name=self.name,
            position=self.position,
            nsfw=self.nsfw,
            overwrites=self.get_overwrites(guild),
        )


class TextChannel(Base):
    id: int
    category: str | None
    name: str
    position: int
    topic: str | None
    overwrites: list[Overwrites]
    nsfw: bool
    news: bool
    slowmode_delay: int
    default_auto_archive_duration: int | None
    default_thread_slowmode_delay: int | None

    @classmethod
    def serialize(cls, channel: discord.TextChannel):
        return cls(
            id=channel.id,
            category=channel.category.name if channel.category else None,
            name=channel.name,
            position=channel.position,
            topic=channel.topic,
            nsfw=channel.nsfw,
            news=channel.is_news(),
            slowmode_delay=channel.slowmode_delay,
            overwrites=Overwrites.serialize(channel),
            default_auto_archive_duration=channel.default_auto_archive_duration,
            default_thread_slowmode_delay=channel.default_thread_slowmode_delay,
        )

    def get_overwrites(self, guild: discord.Guild) -> dict:
        return {i.get(guild): discord.PermissionOverwrite(**i.values) for i in self.overwrites if i.get(guild)}

    async def restore(self, guild: discord.Guild) -> discord.TextChannel | None:
        if guild.get_channel(self.id):
            return
        log.debug(f"Restoring text channel {self.name}")
        channel = await guild.create_text_channel(
            name=self.name,
            category=get_named_category(guild, self.category),
            news="COMMUNITY" in guild.features and self.news,
            topic=self.topic,
            nsfw=self.nsfw,
            slowmode_delay=self.slowmode_delay,
            overwrites=self.get_overwrites(guild),
            default_auto_archive_duration=self.default_auto_archive_duration,
            default_thread_slowmode_delay=self.default_thread_slowmode_delay,
            position=0,
        )
        self.id = channel.id
        return channel

    async def update(self, guild: discord.Guild) -> None:
        channel = guild.get_channel(self.id)
        if not channel:
            return
        if not isinstance(channel, discord.TextChannel):
            return
        equal = [
            channel.name == self.name,
            channel.category == get_named_category(guild, self.category),
            channel.position == self.position,
            channel.nsfw == self.nsfw,
            channel.overwrites == self.get_overwrites(guild),
            channel.topic == self.topic,
            channel.is_news() == self.news,
            channel.slowmode_delay == self.slowmode_delay,
            channel.default_auto_archive_duration == self.default_auto_archive_duration,
            channel.default_thread_slowmode_delay == self.default_thread_slowmode_delay,
        ]
        if all(equal):
            return
        log.debug(f"Updating text channel {channel.name}")
        coro = channel.edit(
            name=self.name,
            category=get_named_category(guild, self.category),
            position=self.position,
            news=self.news,
            topic=self.topic,
            nsfw=self.nsfw,
            slowmode_delay=self.slowmode_delay,
            overwrites=self.get_overwrites(guild),
            default_auto_archive_duration=self.default_auto_archive_duration,
            default_thread_slowmode_delay=self.default_thread_slowmode_delay,
        )
        if channel.position == self.position:
            asyncio.create_task(coro)
        else:
            await coro


class ForumChannel(Base):
    id: int
    category: str | None
    name: str
    position: int
    topic: str | None
    overwrites: list[Overwrites]
    nsfw: bool
    default_auto_archive_duration: int | None
    default_thread_slowmode_delay: int | None

    @classmethod
    def serialize(cls, forum: discord.ForumChannel):
        return cls(
            id=forum.id,
            category=forum.category.name if forum.category else None,
            name=forum.name,
            position=forum.position,
            topic=forum.topic,
            nsfw=forum.nsfw,
            overwrites=Overwrites.serialize(forum),
            default_auto_archive_duration=forum.default_auto_archive_duration,
            default_thread_slowmode_delay=forum.default_thread_slowmode_delay,
        )

    def get_overwrites(self, guild: discord.Guild) -> dict:
        return {i.get(guild): discord.PermissionOverwrite(**i.values) for i in self.overwrites if i.get(guild)}

    async def restore(self, guild: discord.Guild) -> discord.ForumChannel | None:
        if guild.get_channel(self.id):
            return
        log.debug(f"Restoring forum {self.name}")
        channel = await guild.create_forum(name=self.name)
        self.id = channel.id
        return channel

    async def update(self, guild: discord.Guild) -> None:
        channel = guild.get_channel(self.id)
        if not channel:
            return
        if not isinstance(channel, discord.ForumChannel):
            return
        equal = [
            channel.name == self.name,
            channel.category == get_named_category(guild, self.category),
            channel.position == self.position,
            channel.nsfw == self.nsfw,
            channel.overwrites == self.get_overwrites(guild),
            channel.topic == self.topic,
        ]
        if all(equal):
            return
        log.debug(f"Updating forum {channel.name}")
        await channel.edit(
            name=self.name,
            category=get_named_category(guild, self.category),
            position=self.position,
            topic=self.topic,
            overwrites=self.get_overwrites(guild),
            nsfw=self.nsfw,
            default_auto_archive_duration=self.default_auto_archive_duration,
            default_thread_slowmode_delay=self.default_thread_slowmode_delay,
        )


class VoiceChannel(Base):
    id: int
    category: str | None
    name: str
    position: int
    user_limit: int
    bitrate: int
    overwrites: list[Overwrites]

    @classmethod
    def serialize(cls, channel: discord.VoiceChannel):
        return cls(
            id=channel.id,
            category=channel.category.name if channel.category else None,
            name=channel.name,
            position=channel.position,
            user_limit=channel.user_limit,
            bitrate=channel.bitrate,
            overwrites=Overwrites.serialize(channel),
        )

    def get_overwrites(self, guild: discord.Guild) -> dict:
        return {i.get(guild): discord.PermissionOverwrite(**i.values) for i in self.overwrites if i.get(guild)}

    async def restore(self, guild: discord.Guild) -> discord.VoiceChannel | None:
        if guild.get_channel(self.id):
            return
        log.debug(f"Restoring voice channel {self.name}")
        channel = await guild.create_voice_channel(
            name=self.name,
            category=get_named_category(guild, self.category),
            user_limit=self.user_limit,
            bitrate=self.bitrate if self.bitrate <= guild.bitrate_limit else 64000,
            overwrites=self.get_overwrites(guild),
            position=0,
        )
        self.id = channel.id
        return channel

    async def update(self, guild: discord.Guild) -> None:
        channel = guild.get_channel(self.id)
        if not channel:
            return
        if not isinstance(channel, discord.VoiceChannel):
            return
        equal = [
            channel.name == self.name,
            channel.category == get_named_category(guild, self.category),
            channel.position == self.position,
            channel.user_limit == self.user_limit,
            channel.bitrate == self.bitrate,
            channel.overwrites == self.get_overwrites(guild),
        ]
        if all(equal):
            return
        log.debug(f"Updating voice channel {channel.name}")
        channel: discord.VoiceChannel = channel
        coro = channel.edit(
            name=self.name,
            category=get_named_category(guild, self.category),
            position=self.position,
            user_limit=self.user_limit,
            bitrate=self.bitrate if self.bitrate <= guild.bitrate_limit else 64000,
            overwrites=self.get_overwrites(guild),
        )
        if channel.position == self.position:
            asyncio.create_task(coro)
        else:
            await coro


class GuildBackup(Base):
    created: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    id: int
    owner_id: int
    name: str
    description: str | None = None
    afk_channel_id: int | None = None
    afk_timeout: int
    verification_level: int  # Enum[0, 1, 2, 3, 4]
    default_notifications: int  # Enum[0, 1]
    banner: str | None = None
    icon: str | None = None
    preferred_locale: str
    community: bool
    rules_channel: str | None = None
    public_updates_channel: str | None = None
    content_filter: int

    roles: list[Role]
    members: list[Member] = []
    categories: list[CategoryChannel] = []
    text_channels: list[TextChannel] = []
    voice_channels: list[VoiceChannel] = []
    forums: list[ForumChannel] = []

    @property
    def created_f(self) -> str:
        return f"<t:{int(self.created.timestamp())}:F>"

    @property
    def created_r(self) -> str:
        return f"<t:{int(self.created.timestamp())}:R>"

    @classmethod
    def serialize(cls, guild: discord.Guild, banner: bytes | None, icon: bytes | None, roles: list[Role]):
        members = [Member.serialize(member) for member in guild.members]
        categories = [CategoryChannel.serialize(category) for category in guild.categories]
        text_channels = [TextChannel.serialize(text_channel) for text_channel in guild.text_channels]
        voice_channels = [VoiceChannel.serialize(voice_channel) for voice_channel in guild.voice_channels]
        forums = [ForumChannel.serialize(forum) for forum in guild.forums]
        return cls(
            id=guild.id,
            owner_id=guild.owner_id,
            name=guild.name,
            description=guild.description,
            afk_channel_id=guild.afk_channel.id if guild.afk_channel else None,
            afk_timeout=guild.afk_timeout,
            verification_level=guild.verification_level.value,
            default_notifications=guild.default_notifications.value,
            banner=base64.b64encode(banner).decode() if banner else None,
            icon=base64.b64encode(icon).decode() if icon else None,
            preferred_locale=str(guild.preferred_locale),
            rules_channel_id=guild.rules_channel.name if guild.rules_channel else None,
            public_updates_channel=guild.public_updates_channel.name if guild.public_updates_channel else None,
            content_filter=guild.explicit_content_filter.value,
            roles=roles,
            members=members,
            categories=categories,
            text_channels=text_channels,
            voice_channels=voice_channels,
            forums=forums,
            community="COMMUNITY" in list(guild.features),
        )

    @property
    def has_duplcate_roles(self) -> bool:
        existing = set()
        for i in self.roles:
            if i.name in existing:
                return True
            existing.add(i.name)
        return False

    @property
    def has_duplcate_text_channels(self) -> bool:
        existing = set()
        for i in self.text_channels:
            if i.name in existing:
                return True
            existing.add(i.name)
        return False

    @property
    def has_duplcate_categories(self) -> bool:
        existing = set()
        for i in self.categories:
            if i.name in existing:
                return True
            existing.add(i.name)
        return False

    @property
    def has_duplcate_voice_channels(self) -> bool:
        existing = set()
        for i in self.voice_channels:
            if i.name in existing:
                return True
            existing.add(i.name)
        return False

    @property
    def has_duplcate_forum_channels(self) -> bool:
        existing = set()
        for i in self.forums:
            if i.name in existing:
                return True
            existing.add(i.name)
        return False

    async def restore(
        self,
        guild: discord.Guild,
        current_channel: discord.TextChannel | discord.ForumChannel,
        remove_old: bool = False,
    ):
        log.info(f"Restoring backup '{self.name}' to guild '{guild.name}'")
        reason = _("Cartographer Restore")
        results = StringIO(_("Server restore has completed successfully!"))

        # Update guild before forums just in case it wasnt a community server
        log.debug("Restoring guild")
        verification = VerificationLevel(self.verification_level)
        content_filter = ContentFilter(self.content_filter)
        if self.community and self.verification_level < VerificationLevel.medium.value:
            verification = VerificationLevel.medium
        if self.community and self.content_filter != ContentFilter.all_members.value:
            content_filter = ContentFilter.all_members

        rules_channel = get_named_channel(guild, self.rules_channel) or get_named_channel(
            guild, self.public_updates_channel
        )
        if not rules_channel:
            rules_channel = await guild.create_text_channel(name="rules")

        public_updates_channel = get_named_channel(guild, self.public_updates_channel) or get_named_channel(
            guild, self.rules_channel
        )
        if not public_updates_channel:
            public_updates_channel = await guild.create_text_channel(name="public-updates")

        banner = base64.b64decode(self.banner) if self.banner else None
        icon = base64.b64decode(self.icon) if self.icon else None

        if BytesIO(banner).__sizeof__() >= guild.filesize_limit:
            banner = None
        if BytesIO(icon).__sizeof__() >= guild.filesize_limit:
            icon = None

        try:
            await guild.edit(
                reason=reason,
                name=self.name,
                description=self.description,
                afk_channel=get_named_channel(guild, self.afk_channel_id or 0),
                afk_timeout=self.afk_timeout,
                verification_level=verification,
                default_notifications=NotificationLevel(self.default_notifications),
                banner=banner,
                icon=icon,
                preferred_locale=self.preferred_locale,
                community=self.community,
                rules_channel=rules_channel,
                public_updates_channel=public_updates_channel,
                explicit_content_filter=content_filter,
            )
        except Exception as e:
            log.warning("Couldn't fully edit guild", exc_info=e)
            results.write(_("\nFailed to fully edit guild: {}").format(str(e)))
            await guild.edit(
                reason=reason,
                name=self.name,
                description=self.description,
                afk_channel=get_named_channel(guild, self.afk_channel_id or 0),
                afk_timeout=self.afk_timeout,
                verification_level=verification,
                default_notifications=NotificationLevel(self.default_notifications),
                preferred_locale=self.preferred_locale,
                community=self.community,
                rules_channel=rules_channel,
                public_updates_channel=public_updates_channel,
                explicit_content_filter=content_filter,
            )

        remove = _(" (Removal)")
        all_objs = self.categories + self.text_channels + self.voice_channels + self.forums

        if remove_old:
            log.info("Removing any roles or channels that arent in the backup")
            role_ids = [i.id for i in self.roles]
            for role in guild.roles:
                skip = [
                    not role.is_assignable(),
                    role.is_bot_managed(),
                    role.is_default(),
                    role.is_integration(),
                    role.is_premium_subscriber(),
                    role >= guild.me.top_role,
                ]
                if any(skip):
                    continue
                if role.id in role_ids:
                    continue
                try:
                    await role.delete(reason=reason + remove)
                    log.info(f"Deleted role {role.name}")
                except discord.HTTPException as e:
                    results.write(_("\nFailed to delete role {}: {}").format(role.name, str(e.text)))
            chan_ids = [i.id for i in all_objs]
            # Ensure consistency of all channels
            for chan in guild.channels:
                if chan.id in chan_ids:
                    continue
                if chan.id == current_channel.id:
                    results.write(_("\nCan't delete {} as it is the current channel").format(chan.name))
                    continue
                try:
                    await chan.delete(reason=reason + remove)
                    log.info(f"Deleted channel {chan.name}")
                except discord.HTTPException as e:
                    results.write(_("\nFailed to delete channel {}: {}").format(chan.name, str(e.text)))
            for chan in guild.categories:
                if chan.id in chan_ids:
                    continue
                try:
                    await chan.delete(reason=reason + remove)
                    log.info(f"Deleted channel {chan.name}")
                except discord.HTTPException as e:
                    results.write(_("\nFailed to delete category {}: {}").format(chan.name, str(e.text)))
            for chan in guild.forums:
                if chan.id in chan_ids:
                    continue
                try:
                    await chan.delete(reason=reason + remove)
                    log.info(f"Deleted channel {chan.name}")
                except discord.HTTPException as e:
                    results.write(_("\nFailed to delete forum {}: {}").format(chan.name, str(e.text)))

        log.info("Recreating roles")
        for role_backup in self.roles:
            try:
                await role_backup.restore(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to restore role {}: {}").format(role_backup.name, str(e.text)))
        log.info("Updating roles")
        for role_backup in self.roles:
            try:
                await role_backup.update(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to update role {}: {}").format(role_backup.name, str(e.text)))
        log.info("Syncing member roles")
        for member in self.members:
            await member.restore(guild, remove_old)

        log.info("Restoring categories")
        for obj in self.categories:
            try:
                await obj.restore(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to restore category {}: {}").format(obj.name, str(e.text)))
        log.info("Restoring text channels")
        for obj in self.text_channels:
            try:
                await obj.restore(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to restore text channel {}: {}").format(obj.name, str(e.text)))
        log.info("Restoring voice channels")
        for obj in self.voice_channels:
            try:
                await obj.restore(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to restore voice channel {}: {}").format(obj.name, str(e.text)))
        log.info("Restoring forum channels")
        for obj in self.forums:
            try:
                await obj.restore(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to restore forum {}: {}").format(obj.name, str(e.text)))

        # Ensure all channel consistency
        log.info("Syncing categories")
        for obj in self.categories:
            try:
                await obj.update(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to update category {}: {}").format(obj.name, str(e.text)))
        log.info("Syncing text channels")
        for obj in self.text_channels:
            try:
                await obj.update(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to update text channel {}: {}").format(obj.name, str(e.text)))
        log.info("Syncing voice channels")
        for obj in self.voice_channels:
            try:
                await obj.update(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to update voice channel {}: {}").format(obj.name, str(e.text)))
        log.info("Syncing forum channels")
        for obj in self.forums:
            try:
                await obj.update(guild)
            except discord.HTTPException as e:
                results.write(_("\nFailed to update forum {}: {}").format(obj.name, str(e.text)))

        for p in pagify(results.getvalue(), page_length=1900):
            await current_channel.send(p)


class GuildSettings(Base):
    backups: list[GuildBackup] = []
    auto_backup_interval_hours: int = 0
    last_backup: datetime = Field(default_factory=lambda: datetime.now().astimezone() - timedelta(days=999))

    @property
    def last_backup_f(self) -> str:
        return f"<t:{int(self.last_backup.timestamp())}:F>"

    @property
    def last_backup_r(self) -> str:
        return f"<t:{int(self.last_backup.timestamp())}:R>"

    async def backup(self, guild: discord.Guild) -> None:
        banner = await guild.banner.read() if guild.banner else None
        icon = await guild.icon.read() if guild.icon else None
        roles = [await Role.serialize(i) for i in guild.roles]

        def _backup():
            return GuildBackup.serialize(guild, banner, icon, roles)

        guild_backup = await asyncio.to_thread(_backup)
        self.backups.append(guild_backup)
        self.last_backup = datetime.now().astimezone()


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    max_backups_per_guild: int = 5
    allow_auto_backups: bool = False
    ignored_guilds: list[int] = []
    allowed_guilds: list[int] = []

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())

    def cleanup(self, guild: discord.Guild | int):
        conf = self.get_conf(guild)
        conf.backups = conf.backups[-self.max_backups_per_guild :]
