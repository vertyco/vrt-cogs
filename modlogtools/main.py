import asyncio
import logging
import typing as t
from datetime import datetime, timedelta

import discord
from redbot.cogs.warnings.warnings import Warnings
from redbot.core import Config, commands, modlog
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB, GuildSettings, WarningRecord
from .common.utils import (
    extract_warn_id,
    from_snowflake,
    from_unix,
    get_user_id,
    utcnow,
)
from .listeners import Listeners
from .tasks import TaskLoops

log = logging.getLogger("red.vrt.modlogtools")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class ModLogTools(
    Commands,
    Listeners,
    TaskLoops,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """Extended tooling for Red's core modlog and warning system."""

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: DB = DB()
        self.save_lock = asyncio.Lock()
        self.initialized = False
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, requester: RequestType, user_id: int):
        return {}

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        if self.expiry_loop.is_running():
            self.expiry_loop.cancel()
        if self.initialized:
            await self.save()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        await self.register_casetypes()
        self.initialized = True
        if not self.expiry_loop.is_running():
            self.expiry_loop.start()
        asyncio.create_task(self.backfill_all_guilds())
        log.info("Config loaded")

    async def register_casetypes(self) -> None:
        casetypes_to_register = [
            {
                "name": "warning_expired",
                "default_setting": True,
                "image": "⌛",
                "case_str": "Warning Expired",
            }
        ]
        try:
            await modlog.register_casetypes(casetypes_to_register)
        except RuntimeError:
            pass

    def get_warnings_cog(self) -> Warnings | None:
        candidates: list[object] = []
        for name in ("Warnings", "warnings"):
            cog = self.bot.get_cog(name)
            if cog is not None:
                candidates.append(cog)

        if not candidates:
            candidates.extend(
                cog
                for cog in getattr(self.bot, "cogs", {}).values()
                if getattr(cog, "qualified_name", "").lower() == "warnings"
            )

        for cog in candidates:
            config = getattr(cog, "config", None)
            if callable(getattr(config, "all_members", None)) and callable(getattr(config, "member_from_ids", None)):
                return t.cast(Warnings, cog)

        return None

    def get_modlog_config(self) -> Config | None:
        config = getattr(modlog, "_config", None)
        if isinstance(config, Config):
            return config
        return None

    async def backfill_all_guilds(self) -> None:
        if self.get_warnings_cog() is None:
            log.info("Warnings cog not loaded, skipping modlogtools backfill")
            return

        changed = False
        for guild in self.bot.guilds:
            try:
                previous_full_sync = self.db.get_conf(guild).last_full_sync
                summary = await self.sync_guild_records(guild, save=False)
            except Exception:
                log.exception("Failed to backfill warning records for guild %s", guild.id)
                continue
            changed = changed or any(summary.values()) or self.db.get_conf(guild).last_full_sync != previous_full_sync
            await asyncio.sleep(0)

        if changed:
            await self.save()

    async def get_warning_case_map(self, guild: discord.Guild) -> dict[str, tuple[datetime, int]]:
        mapping: dict[str, tuple[datetime, int]] = {}
        try:
            cases = await modlog.get_all_cases(guild, self.bot)
        except Exception:
            log.exception("Failed to fetch modlog cases for guild %s", guild.id)
            return mapping

        conf = self.db.get_conf(guild)
        for case in cases:
            if case.action_type != "warning":
                continue
            warn_id = extract_warn_id(case.reason)
            if warn_id is None:
                continue
            key = conf.make_key(get_user_id(case.user), warn_id)
            mapping[key] = (from_unix(case.created_at), case.case_number)
        return mapping

    async def sync_guild_records(
        self,
        guild: discord.Guild,
        *,
        full_scan: bool = False,
        save: bool = True,
    ) -> dict[str, int]:
        summary = {"created": 0, "updated": 0, "resolved": 0, "backfilled": 0}
        warnings_cog = self.get_warnings_cog()
        if warnings_cog is None:
            return summary

        conf = self.db.get_conf(guild)
        if not full_scan and conf.last_full_sync is None:
            full_scan = True
        metadata_changed = False
        expiry = conf.get_warning_expiry()
        active_keys: set[str] = set()
        case_map = await self.get_warning_case_map(guild) if full_scan else {}
        all_members = await warnings_cog.config.all_members(guild)
        now = utcnow()

        for user_id, member_data in all_members.items():
            warnings_data = member_data.get("warnings", {})
            for warn_id, warning in warnings_data.items():
                warn_id = str(warn_id)
                key = conf.make_key(int(user_id), warn_id)
                active_keys.add(key)
                record = conf.records.get(key)
                case_data = case_map.get(key)
                snowflake_created_at = from_snowflake(warn_id)

                if record is None:
                    created_at = case_data[0] if case_data else snowflake_created_at or now
                    record = WarningRecord(
                        user_id=int(user_id),
                        warn_id=warn_id,
                        points=int(warning.get("points", 0) or 0),
                        description=str(warning.get("description", "") or ""),
                        moderator_id=int(warning.get("mod", 0) or 0),
                        created_at=created_at,
                        modlog_case_number=case_data[1] if case_data else None,
                        expires_at=(created_at + expiry) if expiry else None,
                    )
                    conf.records[key] = record
                    summary["created"] += 1
                    continue

                changed = False
                points = int(warning.get("points", record.points) or 0)
                if record.points != points:
                    record.points = points
                    changed = True

                description = str(warning.get("description", record.description) or "")
                if record.description != description:
                    record.description = description
                    changed = True

                moderator_id = int(warning.get("mod", record.moderator_id) or 0)
                if record.moderator_id != moderator_id:
                    record.moderator_id = moderator_id
                    changed = True

                if record.resolution is not None:
                    record.resolution = None
                    record.resolved_at = None
                    record.resolution_case_number = None
                    changed = True

                if case_data is not None:
                    case_created_at, case_number = case_data
                    if record.created_at > case_created_at:
                        record.created_at = case_created_at
                        changed = True
                    if record.modlog_case_number != case_number:
                        record.modlog_case_number = case_number
                        changed = True
                        summary["backfilled"] += 1
                elif record.modlog_case_number is None and snowflake_created_at is not None:
                    if record.created_at != snowflake_created_at:
                        record.created_at = snowflake_created_at
                        changed = True

                new_expires_at = (record.created_at + expiry) if expiry else None
                if record.expires_at != new_expires_at:
                    record.expires_at = new_expires_at
                    changed = True

                if changed:
                    summary["updated"] += 1

        for key, record in conf.records.items():
            if record.resolution is None and key not in active_keys:
                record.resolution = "removed"
                record.resolved_at = now
                summary["resolved"] += 1

        if full_scan:
            metadata_changed = conf.last_full_sync != now
            conf.last_full_sync = now

        if save and (metadata_changed or any(summary.values())):
            await self.save()
        return summary

    def preview_warning_expiry_update(self, guild: discord.Guild, duration: timedelta | None) -> dict[str, int]:
        conf = self.db.get_conf(guild)
        now = utcnow()
        summary = {"active": 0, "changed": 0, "overdue": 0}

        for record in conf.records.values():
            if not record.is_active:
                continue
            summary["active"] += 1
            projected_expires_at = (record.created_at + duration) if duration else None
            if record.expires_at != projected_expires_at:
                summary["changed"] += 1
            if projected_expires_at is not None and projected_expires_at <= now:
                summary["overdue"] += 1

        return summary

    async def export_guild_config(self, guild: discord.Guild) -> dict[str, t.Any]:
        warnings_cog = self.get_warnings_cog()
        if warnings_cog is None:
            raise RuntimeError("Warnings cog not loaded.")

        modlog_config = self.get_modlog_config()
        if modlog_config is None:
            raise RuntimeError("Modlog config not initialized.")

        return {
            "format_version": 1,
            "exported_at": utcnow().isoformat(),
            "source": {
                "guild_id": guild.id,
                "guild_name": guild.name,
            },
            "warnings": {
                "guild": await warnings_cog.config.guild(guild).all(),
                "members": await warnings_cog.config.all_members(guild),
            },
            "modlog": {
                "guild": await modlog_config.guild(guild).all(),
                "casetypes": await modlog_config.custom(modlog._CASETYPES).all(),
                "cases": await modlog_config.custom(modlog._CASES, str(guild.id)).all(),
            },
            "modlogtools": {
                "guild": self.db.get_conf(guild).model_dump(mode="json", exclude_defaults=False),
            },
        }

    def summarize_guild_import(self, guild: discord.Guild, payload: dict[str, t.Any]) -> dict[str, t.Any]:
        if payload.get("format_version") != 1:
            raise ValueError("unsupported format version")

        warnings_section = payload.get("warnings")
        modlog_section = payload.get("modlog")
        modlogtools_section = payload.get("modlogtools")
        source_section = payload.get("source") or {}
        if not isinstance(warnings_section, dict) or not isinstance(modlog_section, dict):
            raise ValueError("missing warnings/modlog sections")

        warning_members = warnings_section.get("members") or {}
        warning_guild = warnings_section.get("guild") or {}
        modlog_cases = modlog_section.get("cases") or {}
        modlog_casetypes = modlog_section.get("casetypes") or {}
        modlog_guild = modlog_section.get("guild") or {}
        modlogtools_guild = (modlogtools_section or {}).get("guild") or {}

        if not isinstance(warning_members, dict):
            raise ValueError("warnings.members must be a mapping")
        if not isinstance(warning_guild, dict):
            raise ValueError("warnings.guild must be a mapping")
        if not isinstance(modlog_cases, dict):
            raise ValueError("modlog.cases must be a mapping")
        if not isinstance(modlog_casetypes, dict):
            raise ValueError("modlog.casetypes must be a mapping")
        if not isinstance(modlog_guild, dict):
            raise ValueError("modlog.guild must be a mapping")
        if not isinstance(modlogtools_guild, dict):
            raise ValueError("modlogtools.guild must be a mapping")

        tracked = GuildSettings.model_validate(modlogtools_guild)
        total_warnings = sum(len((member_data or {}).get("warnings", {})) for member_data in warning_members.values())
        source_guild_id = source_section.get("guild_id")
        source_guild_name = source_section.get("guild_name") or "Unknown"

        return {
            "source_guild_id": source_guild_id,
            "source_guild_name": source_guild_name,
            "guild_mismatch": source_guild_id is not None and int(source_guild_id) != guild.id,
            "warning_members": len(warning_members),
            "warning_entries": total_warnings,
            "modlog_cases": len(modlog_cases),
            "modlog_casetypes": len(modlog_casetypes),
            "tracked_records": len(tracked.records),
            "warning_settings": len(warning_guild),
            "modlog_settings": len(modlog_guild),
        }

    async def import_guild_config(
        self,
        guild: discord.Guild,
        payload: dict[str, t.Any],
        *,
        save: bool = True,
    ) -> dict[str, int]:
        warnings_cog = self.get_warnings_cog()
        if warnings_cog is None:
            raise RuntimeError("Warnings cog not loaded.")

        modlog_config = self.get_modlog_config()
        if modlog_config is None:
            raise RuntimeError("Modlog config not initialized.")

        self.summarize_guild_import(guild, payload)
        warnings_section = t.cast(dict[str, t.Any], payload["warnings"])
        modlog_section = t.cast(dict[str, t.Any], payload["modlog"])
        modlogtools_section = t.cast(dict[str, t.Any], payload.get("modlogtools") or {})

        warning_guild = dict(t.cast(dict[str, t.Any], warnings_section.get("guild") or {}))
        warning_members = dict(t.cast(dict[str, t.Any], warnings_section.get("members") or {}))
        modlog_guild = dict(t.cast(dict[str, t.Any], modlog_section.get("guild") or {}))
        modlog_cases = dict(t.cast(dict[str, t.Any], modlog_section.get("cases") or {}))
        modlog_casetypes = dict(t.cast(dict[str, t.Any], modlog_section.get("casetypes") or {}))
        tracked = GuildSettings.model_validate(modlogtools_section.get("guild") or {})

        current_members = await warnings_cog.config.all_members(guild)
        for index, member_id in enumerate(list(current_members.keys()), start=1):
            await warnings_cog.config.member_from_ids(guild.id, int(member_id)).clear()
            if not index % 100:
                await asyncio.sleep(0)

        await warnings_cog.config.guild(guild).set(warning_guild)
        for index, (member_id, member_data) in enumerate(warning_members.items(), start=1):
            await warnings_cog.config.member_from_ids(guild.id, int(member_id)).set(member_data)
            if not index % 100:
                await asyncio.sleep(0)

        await modlog_config.guild(guild).set(modlog_guild)
        if modlog_casetypes:
            existing_casetypes = await modlog_config.custom(modlog._CASETYPES).all()
            existing_casetypes.update(modlog_casetypes)
            await modlog_config.custom(modlog._CASETYPES).set(existing_casetypes)
        await modlog_config.custom(modlog._CASES, str(guild.id)).clear()
        if modlog_cases:
            await modlog_config.custom(modlog._CASES, str(guild.id)).set(modlog_cases)

        self.db.configs[guild.id] = tracked
        if save:
            await self.save()

        return {
            "warning_members": len(warning_members),
            "warning_entries": sum(
                len((member_data or {}).get("warnings", {})) for member_data in warning_members.values()
            ),
            "modlog_cases": len(modlog_cases),
            "modlog_casetypes": len(modlog_casetypes),
            "tracked_records": len(tracked.records),
        }

    async def capture_warning_case(self, case: modlog.Case, *, save: bool = True) -> bool:
        warn_id = extract_warn_id(case.reason)
        if warn_id is None:
            return False

        warnings_cog = self.get_warnings_cog()
        if warnings_cog is None:
            return False

        user_id = get_user_id(case.user)
        warning = await warnings_cog.config.member_from_ids(case.guild.id, user_id).get_raw(
            "warnings", warn_id, default=None
        )
        if warning is None:
            return False

        conf = self.db.get_conf(case.guild)
        expiry = conf.get_warning_expiry()
        created_at = from_unix(case.created_at)
        record = conf.get_record(user_id, warn_id)

        if record is None:
            record = WarningRecord(
                user_id=user_id,
                warn_id=warn_id,
                points=int(warning.get("points", 0) or 0),
                description=str(warning.get("description", "") or ""),
                moderator_id=int(warning.get("mod", 0) or 0),
                created_at=created_at,
                modlog_case_number=case.case_number,
                expires_at=(created_at + expiry) if expiry else None,
            )
            conf.set_record(record)
        else:
            record.points = int(warning.get("points", record.points) or 0)
            record.description = str(warning.get("description", record.description) or "")
            record.moderator_id = int(warning.get("mod", record.moderator_id) or 0)
            record.created_at = created_at
            record.modlog_case_number = case.case_number
            record.expires_at = (created_at + expiry) if expiry else None
            record.resolution = None
            record.resolved_at = None
            record.resolution_case_number = None

        if save:
            await self.save()
        return True

    async def create_expired_warning_case(
        self,
        guild: discord.Guild,
        record: WarningRecord,
        *,
        save: bool = True,
    ) -> None:
        expiry = self.db.get_conf(guild).get_warning_expiry()
        duration = humanize_timedelta(timedelta=expiry) if expiry else "configured interval"
        lines = [
            f"Warning `{record.warn_id}` expired automatically after {duration}.",
            f"Points removed: {record.points}",
        ]
        if record.modlog_case_number is not None:
            lines.append(f"Original case: #{record.modlog_case_number}")
        if record.description:
            lines.append(f"Original reason: {record.description}")

        member = (
            guild.get_member(record.user_id) or self.bot.get_user(record.user_id) or discord.Object(id=record.user_id)
        )
        case = await modlog.create_case(
            self.bot,
            guild,
            utcnow(),
            "warning_expired",
            member,
            guild.me or self.bot.user,
            "\n".join(lines),
            until=None,
            channel=None,
        )
        if case is not None:
            record.resolution_case_number = case.case_number
        if save:
            await self.save()

    async def delete_original_warning_case_message(self, guild: discord.Guild, record: WarningRecord) -> bool:
        if record.modlog_case_number is None:
            return False

        try:
            case = await modlog.get_case(record.modlog_case_number, guild, self.bot)
        except Exception:
            log.exception(
                "Failed to fetch original warning case %s for guild %s",
                record.modlog_case_number,
                guild.id,
            )
            return False

        if case.message is None:
            return False

        try:
            await case.message.delete()
        except discord.NotFound:
            return False
        except discord.Forbidden:
            log.warning(
                "Missing permissions to delete original warning case message %s for guild %s",
                record.modlog_case_number,
                guild.id,
            )
            return False
        except discord.HTTPException:
            log.exception(
                "Failed to delete original warning case message %s for guild %s",
                record.modlog_case_number,
                guild.id,
            )
            return False

        try:
            await case.edit(
                {
                    "message": None,
                    "amended_by": guild.me or self.bot.user,
                    "modified_at": utcnow().timestamp(),
                }
            )
        except Exception:
            log.exception(
                "Deleted original warning case message but failed to clear case reference %s for guild %s",
                record.modlog_case_number,
                guild.id,
            )
        return True

    async def preview_guild_expiry(self, guild: discord.Guild) -> dict[str, int]:
        summary = {"expired": 0, "stale": 0, "points": 0, "members": 0, "linked_cases": 0}
        warnings_cog = self.get_warnings_cog()
        if warnings_cog is None:
            return summary

        conf = self.db.get_conf(guild)
        if conf.warning_expiry_seconds is None:
            return summary

        now = utcnow()
        pending: dict[int, list[WarningRecord]] = {}
        for record in conf.records.values():
            if not record.is_active:
                continue
            if record.expires_at is None or record.expires_at > now:
                continue
            pending.setdefault(record.user_id, []).append(record)

        summary["members"] = len(pending)
        for user_id, records in pending.items():
            warnings_data = await warnings_cog.config.member_from_ids(guild.id, user_id).get_raw("warnings", default={})
            for record in records:
                payload = warnings_data.get(record.warn_id)
                if payload is None:
                    summary["stale"] += 1
                    continue
                summary["expired"] += 1
                summary["points"] += int(payload.get("points", record.points) or 0)
                if record.modlog_case_number is not None:
                    summary["linked_cases"] += 1

        return summary

    async def expire_guild_warnings(self, guild: discord.Guild, *, save: bool = True) -> dict[str, int]:
        summary = {"expired": 0, "stale": 0, "points": 0, "members": 0, "linked_cases": 0, "messages_deleted": 0}
        warnings_cog = self.get_warnings_cog()
        if warnings_cog is None:
            return summary

        conf = self.db.get_conf(guild)
        if conf.warning_expiry_seconds is None:
            return summary

        await self.sync_guild_records(guild, save=False)
        now = utcnow()
        changed = False
        pending: dict[int, list[WarningRecord]] = {}
        for record in conf.records.values():
            if not record.is_active:
                continue
            if record.expires_at is None or record.expires_at > now:
                continue
            pending.setdefault(record.user_id, []).append(record)

        summary["members"] = len(pending)

        for user_id, records in pending.items():
            member_group = warnings_cog.config.member_from_ids(guild.id, user_id)
            expired_records: list[WarningRecord] = []
            async with member_group.all() as member_data:
                warnings_data = member_data.setdefault("warnings", {})
                total_points = int(member_data.get("total_points", 0) or 0)
                removed_points = 0
                for record in records:
                    payload = warnings_data.pop(record.warn_id, None)
                    if payload is None:
                        record.resolution = "removed"
                        record.resolved_at = now
                        summary["stale"] += 1
                        changed = True
                        continue

                    record.points = int(payload.get("points", record.points) or 0)
                    record.description = str(payload.get("description", record.description) or "")
                    record.moderator_id = int(payload.get("mod", record.moderator_id) or 0)
                    record.resolution = "expired"
                    record.resolved_at = now
                    removed_points += record.points
                    summary["points"] += record.points
                    if record.modlog_case_number is not None:
                        summary["linked_cases"] += 1
                    expired_records.append(record)
                    summary["expired"] += 1
                    changed = True

                if removed_points:
                    member_data["total_points"] = max(0, total_points - removed_points)

            for record in expired_records:
                await self.create_expired_warning_case(guild, record, save=False)
                if conf.delete_expired_modlog_messages:
                    summary["messages_deleted"] += int(await self.delete_original_warning_case_message(guild, record))
                await asyncio.sleep(0)

        if save and changed:
            await self.save()
        return summary

    async def save(self) -> None:
        if not self.initialized:
            return
        async with self.save_lock:
            try:
                dump = await asyncio.to_thread(self.db.model_dump, mode="json")
                await self.config.db.set(dump)
            except Exception as e:
                log.exception("Failed to save config", exc_info=e)
