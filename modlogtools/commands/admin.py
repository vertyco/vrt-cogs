from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import timedelta

import discord
from redbot.core import commands, modlog
from redbot.core.utils.chat_formatting import (
    humanize_number,
    humanize_timedelta,
    pagify,
    text_to_file,
)

from ..abc import MixinMeta
from ..common.models import WarningRecord
from ..common.utils import DELETED_USER_SENTINEL, from_unix, get_user_id, utcnow

log = logging.getLogger("red.vrt.modlogtools.commands.admin")


class Admin(MixinMeta):
    """Admin commands."""

    leaderboard_sort_aliases = {
        "active": "active",
        "activewarn": "active",
        "activewarns": "active",
        "warn": "warns",
        "warns": "warns",
        "warning": "warns",
        "warnings": "warns",
        "total": "warns",
        "points": "points",
        "point": "points",
        "pts": "points",
    }

    modlog_case_aliases = {
        "warn": "warning",
        "warns": "warning",
        "warning": "warning",
        "warnings": "warning",
        "ban": "ban",
        "bans": "ban",
        "kick": "kick",
        "kicks": "kick",
        "hackban": "hackban",
        "hackbans": "hackban",
        "tempban": "tempban",
        "tempbans": "tempban",
        "softban": "softban",
        "softbans": "softban",
        "unban": "unban",
        "unbans": "unban",
        "voiceban": "voiceban",
        "voicebans": "voiceban",
        "voiceunban": "voiceunban",
        "voiceunbans": "voiceunban",
        "vmute": "vmute",
        "voicemute": "vmute",
        "voicemutes": "vmute",
        "cmute": "cmute",
        "channelmute": "cmute",
        "channelmutes": "cmute",
        "smute": "smute",
        "servermute": "smute",
        "servermutes": "smute",
        "vunmute": "vunmute",
        "voiceunmute": "vunmute",
        "voiceunmutes": "vunmute",
        "cunmute": "cunmute",
        "channelunmute": "cunmute",
        "channelunmutes": "cunmute",
        "sunmute": "sunmute",
        "serverunmute": "sunmute",
        "serverunmutes": "sunmute",
        "vkick": "vkick",
        "voicekick": "vkick",
        "voicekicks": "vkick",
        "expired": "warning_expired",
        "warningexpired": "warning_expired",
        "warning_expired": "warning_expired",
    }

    def get_status_lines(self, guild: discord.Guild) -> list[str]:
        conf = self.db.get_conf(guild)
        expiry = conf.get_warning_expiry()
        active = sum(1 for record in conf.records.values() if record.is_active)
        expiry_text = humanize_timedelta(timedelta=expiry) if expiry else "disabled"
        decay_text = f"{conf.point_decay_per_day} points/day" if conf.point_decay_per_day else "disabled"
        return [
            f"Warning expiry: {expiry_text}",
            f"Warning point decay: {decay_text}",
            f"Delete original modlog messages on expiry: {'enabled' if conf.delete_expired_modlog_messages else 'disabled'}",
            f"DM members on expiry: {'enabled' if conf.dm_on_expiry else 'disabled'}",
            f"Tracked warnings: {humanize_number(len(conf.records))}",
            f"Active warnings: {humanize_number(active)}",
        ]

    def get_import_attachment(self, ctx: commands.Context) -> discord.Attachment | None:
        if ctx.message.attachments:
            return ctx.message.attachments[0]

        reference = ctx.message.reference
        resolved = getattr(reference, "resolved", None)
        if isinstance(resolved, discord.Message) and resolved.attachments:
            return resolved.attachments[0]

        return None

    def format_period(self, timespan: timedelta | None) -> str:
        if timespan is None:
            return "all time"
        return humanize_timedelta(timedelta=timespan)

    def normalize_modlog_case_type(self, value: str) -> str:
        return self.modlog_case_aliases.get(value.lower(), value.lower())

    def format_modlog_case_type(self, value: str) -> str:
        return value.replace("_", " ").title()

    def format_leaderboard_sort(self, sort_by: str) -> str:
        labels = {
            "active": "active warnings",
            "warns": "total warnings",
            "points": "warning points",
        }
        return labels.get(sort_by, sort_by)

    def parse_leaderboard_args(self, raw: str) -> tuple[str, timedelta | None, int]:
        sort_by = "active"
        timespan = None
        limit = 10
        limit_set = False

        for token in raw.split():
            lower = token.lower()
            if lower in self.leaderboard_sort_aliases:
                sort_by = self.leaderboard_sort_aliases[lower]
                continue

            delta = commands.parse_timedelta(token)
            if delta is not None:
                timespan = delta
                continue

            if not limit_set:
                try:
                    parsed_limit = int(token)
                except ValueError:
                    parsed_limit = None
                if parsed_limit is not None:
                    if not 1 <= parsed_limit <= 25:
                        raise commands.BadArgument("Limit must be between 1 and 25.")
                    limit = parsed_limit
                    limit_set = True
                    continue

            raise commands.BadArgument(
                "Unknown leaderboard option. Use one sort (`active`, `warns`, `points`), one timespan, and one limit."
            )

        return sort_by, timespan, limit

    async def get_modlog_cases_for_window(
        self,
        guild: discord.Guild,
        case_type: str,
        timespan: timedelta | None = None,
    ) -> list[modlog.Case]:
        try:
            cases = await modlog.get_all_cases(guild, self.bot)
        except Exception as e:
            log.error("Failed to fetch modlog cases for guild %s", guild.id, exc_info=e)
            return []

        if timespan is None:
            cutoff = None
        else:
            cutoff = utcnow() - timespan

        return [
            case
            for case in cases
            if case.action_type == case_type and (cutoff is None or from_unix(case.created_at) >= cutoff)
        ]

    def get_window_records(
        self,
        guild: discord.Guild,
        timespan: timedelta | None = None,
    ) -> list[WarningRecord]:
        records = list(self.db.get_conf(guild).records.values())
        if timespan is None:
            return records
        cutoff = utcnow() - timespan
        return [record for record in records if record.created_at >= cutoff]

    def get_resolved_records(
        self,
        guild: discord.Guild,
        timespan: timedelta | None = None,
    ) -> list[WarningRecord]:
        records = [record for record in self.db.get_conf(guild).records.values() if not record.is_active]
        if timespan is None:
            return records
        cutoff = utcnow() - timespan
        return [record for record in records if record.resolved_at and record.resolved_at >= cutoff]

    def get_label(self, guild: discord.Guild, user_id: int) -> str:
        if user_id == DELETED_USER_SENTINEL:
            return "Deleted User"
        member = guild.get_member(user_id) or self.bot.get_user(user_id)
        if member is not None:
            return f"{member} ({user_id})"
        return f"Unknown User ({user_id})"

    def shorten_reason(self, reason: str, *, limit: int = 60) -> str:
        if len(reason) <= limit:
            return reason
        return reason[: limit - 3] + "..."

    @commands.group(name="modlogtool", aliases=["mlt"])
    @commands.guild_only()
    @commands.mod_or_permissions(manage_messages=True)
    async def modlogtool(self, ctx: commands.Context):
        """Configure ModLogTools and view warning insights."""
        pass

    @modlogtool.command(name="view", aliases=["status", "settings"])
    async def mlt_view(self, ctx: commands.Context):
        """Show current expiry setting and tracked warning counts."""
        await ctx.send("\n".join(self.get_status_lines(ctx.guild)))

    @modlogtool.command(name="expiry")
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_expiry(
        self,
        ctx: commands.Context,
        duration: str | None = None,
        dry_run: bool = True,
    ):
        """Set warning expiry. Use `off` to disable. Dry run defaults to true."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")

        conf = self.db.get_conf(ctx.guild)
        if duration is None:
            expiry = conf.get_warning_expiry()
            lines = [
                "Warning expiry disabled."
                if expiry is None
                else f"Warning expiry: {humanize_timedelta(timedelta=expiry)}",
                f"Delete original modlog messages on expiry: {'enabled' if conf.delete_expired_modlog_messages else 'disabled'}",
            ]
            return await ctx.send("\n".join(lines))

        duration = duration.strip()
        if duration.lower() in {"off", "none", "disable", "disabled"}:
            delta = None
        else:
            try:
                # parse_timedelta raises BadArgument for sub-minimum values instead of returning None.
                delta = commands.parse_timedelta(duration, minimum=timedelta(hours=1))
            except commands.BadArgument:
                delta = None
            if delta is None:
                return await ctx.send("Could not parse duration. Example: `30d`, `12h`, `2w`. Minimum: `1h`.")

        preview = self.preview_warning_expiry_update(ctx.guild, delta)
        expiry_label = humanize_timedelta(timedelta=delta) if delta else "disabled"
        if dry_run:
            # Quote multi-word durations so the suggested apply command parses correctly.
            apply_arg = f'"{duration}"' if " " in duration else duration
            lines = [
                "Dry run only. No changes applied.",
                f"New warning expiry: {expiry_label}",
                f"Active tracked warnings: {humanize_number(preview['active'])}",
                f"Warnings with updated expiry: {humanize_number(preview['changed'])}",
            ]
            if delta:
                lines.append(f"Warnings already past new limit: {humanize_number(preview['overdue'])}")
            lines.append(f"Run `{ctx.clean_prefix}modlogtool expiry {apply_arg} false` to apply.")
            return await ctx.send("\n".join(lines))

        conf.update_expiry(delta)
        summary = await self.sync_guild_records(ctx.guild, save=False)
        await self.save()
        lines = ["Warning expiry disabled." if delta is None else f"Warning expiry set to {expiry_label}."]
        if delta:
            lines.append(
                f"Delete original modlog messages on expiry: {'enabled' if conf.delete_expired_modlog_messages else 'disabled'}"
            )
        lines.append(f"Warnings with updated expiry: {humanize_number(preview['changed'])}")
        if delta:
            lines.append(f"Warnings already past new limit: {humanize_number(preview['overdue'])}")
        lines.append(f"Sync updates: {humanize_number(summary['updated'])}")
        if delta:
            lines.append(f"Tracked warnings: {humanize_number(len(conf.records))}")
        await ctx.send("\n".join(lines))

    @modlogtool.command(name="deletemodlogmessages", aliases=["delmodlogmessages"])
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_deletemodlogmessages(self, ctx: commands.Context, enabled: bool | None = None):
        """Toggle deleting original warning modlog messages when warnings expire."""
        conf = self.db.get_conf(ctx.guild)
        if enabled is None:
            state = "enabled" if conf.delete_expired_modlog_messages else "disabled"
            return await ctx.send(f"Delete original modlog messages on expiry: {state}")

        conf.delete_expired_modlog_messages = enabled
        await self.save()
        state = "enabled" if enabled else "disabled"
        await ctx.send(f"Delete original modlog messages on expiry: {state}")

    @modlogtool.command(name="dmexpiry", aliases=["dmonexpiry"])
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_dmexpiry(self, ctx: commands.Context, enabled: bool | None = None):
        """Toggle DMing members when their warnings expire or fully decay."""
        conf = self.db.get_conf(ctx.guild)
        if enabled is None:
            state = "enabled" if conf.dm_on_expiry else "disabled"
            return await ctx.send(f"DM members on warning expiry: {state}")

        conf.dm_on_expiry = enabled
        await self.save()
        state = "enabled" if enabled else "disabled"
        await ctx.send(f"DM members on warning expiry: {state}")

    @modlogtool.command(name="decay")
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_decay(self, ctx: commands.Context, points_per_day: str | None = None):
        """Set warning point decay per day. Use `off` to disable.

        Each active warning gradually loses points per day since it was issued.
        A warning is removed entirely once it reaches 0 points. Works alongside
        or instead of the hard expiry duration.
        """
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        conf = self.db.get_conf(ctx.guild)
        if points_per_day is None:
            state = f"{conf.point_decay_per_day} points/day" if conf.point_decay_per_day else "disabled"
            return await ctx.send(f"Warning point decay: {state}")

        if points_per_day.lower() in {"off", "none", "disable", "disabled", "0"}:
            conf.point_decay_per_day = 0
            await self.save()
            return await ctx.send("Warning point decay disabled.")

        try:
            rate = int(points_per_day)
        except ValueError:
            return await ctx.send("Points per day must be a whole number or `off`.")
        if not 1 <= rate <= 1000:
            return await ctx.send("Points per day must be between 1 and 1000.")

        conf.point_decay_per_day = rate
        await self.save()
        await ctx.send(
            f"Warning point decay set to {rate} point{'s' if rate != 1 else ''} per day. "
            "Warnings are removed once they decay to 0 points."
        )

    @modlogtool.command(name="extend", aliases=["setexpiry"])
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_extend(
        self,
        ctx: commands.Context,
        member: discord.Member | commands.RawUserIdConverter,
        warn_id: str,
        *,
        duration: str,
    ):
        """Override one warning's expiry.

        `duration` - time from now (e.g. `30d`, `12h`, minimum `10m`),
        `never` to keep it active indefinitely, or `reset` to follow the
        guild-wide expiry again.
        """
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        await self.sync_guild_records(ctx.guild)

        user_id = member.id if isinstance(member, discord.Member) else int(member)
        conf = self.db.get_conf(ctx.guild)
        record = conf.get_record(user_id, warn_id)
        if record is None:
            return await ctx.send("No tracked warning with that ID for that member.")
        if not record.is_active:
            return await ctx.send(f"That warning is no longer active ({record.resolution}).")

        lowered = duration.strip().lower()
        if lowered in {"reset", "default"}:
            record.expiry_override = False
            expiry = conf.get_warning_expiry()
            record.expires_at = (record.created_at + expiry) if expiry else None
            await self.save()
            when = f"<t:{record.expires_ts}:F>" if record.expires_at else "never (guild expiry disabled)"
            return await ctx.send(f"Warning `{warn_id}` follows the guild expiry again. Expires: {when}")
        if lowered in {"never", "off"}:
            record.expiry_override = True
            record.expires_at = None
            await self.save()
            return await ctx.send(f"Warning `{warn_id}` will never expire automatically.")

        try:
            delta = commands.parse_timedelta(duration, minimum=timedelta(minutes=10))
        except commands.BadArgument:
            delta = None
        if delta is None:
            return await ctx.send("Could not parse duration. Example: `30d`, `12h`, `never`, `reset`. Minimum: `10m`.")

        record.expiry_override = True
        record.expires_at = utcnow() + delta
        await self.save()
        await ctx.send(f"Warning `{warn_id}` now expires <t:{record.expires_ts}:F>.")

    @modlogtool.command(name="sync")
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_sync(self, ctx: commands.Context):
        """Rescan Red warnings and modlog data."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        summary = await self.sync_guild_records(ctx.guild, full_scan=True)
        await ctx.send(
            "\n".join(
                [
                    "Sync complete.",
                    f"Created: {humanize_number(summary['created'])}",
                    f"Updated: {humanize_number(summary['updated'])}",
                    f"Resolved: {humanize_number(summary['resolved'])}",
                    f"Backfilled cases: {humanize_number(summary['backfilled'])}",
                ]
            )
        )

    @modlogtool.command(name="exportconfig", aliases=["exportcfg", "export"])
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_exportconfig(self, ctx: commands.Context):
        """Export current guild warnings/modlog/modlogtools config."""
        try:
            payload = await self.export_guild_config(ctx.guild)
        except RuntimeError as exc:
            return await ctx.send(str(exc))

        summary = self.summarize_guild_import(ctx.guild, payload)
        content = await asyncio.to_thread(json.dumps, payload, indent=2)
        if len(content.encode("utf-8")) > ctx.guild.filesize_limit:
            return await ctx.send("Export is too large to upload to this guild.")
        filename = f"modlogtools-{ctx.guild.id}-config-export.json"
        await ctx.send(
            "\n".join(
                [
                    "Export complete.",
                    f"Warning members: {humanize_number(summary['warning_members'])}",
                    f"Warning entries: {humanize_number(summary['warning_entries'])}",
                    f"Modlog cases: {humanize_number(summary['modlog_cases'])}",
                    f"Modlog casetypes: {humanize_number(summary['modlog_casetypes'])}",
                    f"Tracked records: {humanize_number(summary['tracked_records'])}",
                ]
            ),
            file=text_to_file(content, filename=filename),
        )

    @modlogtool.command(name="importconfig", aliases=["importcfg", "import"])
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_importconfig(self, ctx: commands.Context, dry_run: bool = True):
        """Import guild warnings/modlog/modlogtools config. Dry run defaults to true."""
        attachment = self.get_import_attachment(ctx)
        if attachment is None:
            return await ctx.send("Attach an export JSON file to this command or reply to one.")
        if attachment.size > 25 * 1024 * 1024:
            return await ctx.send("Import file too large (25MB max).")

        try:
            raw = (await attachment.read()).decode("utf-8")
            payload = await asyncio.to_thread(json.loads, raw)
            summary = await asyncio.to_thread(self.summarize_guild_import, ctx.guild, payload)
        except UnicodeDecodeError:
            return await ctx.send("Import file must be UTF-8 JSON.")
        except json.JSONDecodeError as exc:
            return await ctx.send(f"Invalid JSON: {exc}")
        except (TypeError, ValueError) as exc:
            return await ctx.send(f"Invalid import payload: {exc}")

        lines = [
            "Dry run only. No changes applied." if dry_run else "Import complete.",
            f"Source guild: {summary['source_guild_name']} ({summary['source_guild_id']})",
            f"Target guild: {ctx.guild.name} ({ctx.guild.id})",
            f"Warning members: {humanize_number(summary['warning_members'])}",
            f"Warning entries: {humanize_number(summary['warning_entries'])}",
            f"Modlog cases: {humanize_number(summary['modlog_cases'])}",
            f"Modlog casetypes: {humanize_number(summary['modlog_casetypes'])}",
            f"Tracked records: {humanize_number(summary['tracked_records'])}",
        ]
        if summary["guild_mismatch"]:
            lines.append("Source guild ID differs from current guild.")

        if dry_run:
            lines.append(f"Run `{ctx.clean_prefix}modlogtool importconfig false` with same attachment to apply.")
            return await ctx.send("\n".join(lines))

        try:
            result = await self.import_guild_config(ctx.guild, payload)
        except RuntimeError as exc:
            return await ctx.send(str(exc))
        except Exception as e:
            log.error("Failed to import config for guild %s", ctx.guild.id, exc_info=e)
            return await ctx.send("Import failed. Check logs.")

        lines.extend(
            [
                f"Imported warning members: {humanize_number(result['warning_members'])}",
                f"Imported warning entries: {humanize_number(result['warning_entries'])}",
                f"Imported modlog cases: {humanize_number(result['modlog_cases'])}",
                f"Imported modlog casetypes: {humanize_number(result['modlog_casetypes'])}",
                f"Imported tracked records: {humanize_number(result['tracked_records'])}",
            ]
        )
        await ctx.send("\n".join(lines))

    @modlogtool.command(name="expire")
    @commands.admin_or_permissions(manage_guild=True)
    async def mlt_expire(self, ctx: commands.Context, dry_run: bool = True):
        """Run warning expiry now. Dry run defaults to true."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        conf = self.db.get_conf(ctx.guild)
        if conf.get_warning_expiry() is None and not conf.point_decay_per_day:
            return await ctx.send("Warning expiry and point decay are both disabled.")

        async with ctx.typing():
            if dry_run:
                # Sync first so the dry run reflects the same state the real run would act on.
                await self.sync_guild_records(ctx.guild)
                summary = await self.preview_guild_expiry(ctx.guild)
                if not any(summary.values()):
                    return await ctx.send("Dry run complete. No warnings eligible for expiry.")
                lines = [
                    "Dry run only. No warnings removed.",
                    f"Would expire: {humanize_number(summary['expired'])}",
                    f"Would remove points: {humanize_number(summary['points'])}",
                    f"Would create modlog cases: {humanize_number(summary['expired'])}",
                    f"Already missing: {humanize_number(summary['stale'])}",
                    f"Affected members: {humanize_number(summary['members'])}",
                ]
                if conf.delete_expired_modlog_messages:
                    lines.append(f"Would delete original modlog messages: {humanize_number(summary['linked_cases'])}")
                else:
                    lines.append("Delete original modlog messages on expiry: disabled")
                lines.append(f"Run `{ctx.clean_prefix}modlogtool expire false` to apply.")
                return await ctx.send("\n".join(lines))

            summary = await self.expire_guild_warnings(ctx.guild)

        lines = [
            "Expiry run complete.",
            f"Expired: {humanize_number(summary['expired'])}",
            f"Points removed: {humanize_number(summary['points'])}",
            f"Already missing: {humanize_number(summary['stale'])}",
            f"Affected members: {humanize_number(summary['members'])}",
        ]
        if conf.point_decay_per_day:
            lines.append(f"Points decayed: {humanize_number(summary['decayed_points'])}")
            lines.append(f"Fully decayed warnings: {humanize_number(summary['decayed'])}")
        if conf.delete_expired_modlog_messages:
            lines.append(f"Original modlog messages deleted: {humanize_number(summary['messages_deleted'])}")
        else:
            lines.append("Delete original modlog messages on expiry: disabled")
        await ctx.send("\n".join(lines))

    @modlogtool.command(name="overview")
    async def mlt_overview(self, ctx: commands.Context, timespan: commands.TimedeltaConverter = None):
        """Show warning trends for the guild."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        await self.sync_guild_records(ctx.guild)

        conf = self.db.get_conf(ctx.guild)
        issued = self.get_window_records(ctx.guild, timespan)
        resolved = self.get_resolved_records(ctx.guild, timespan)
        active = [record for record in conf.records.values() if record.is_active]
        top_users = Counter(record.user_id for record in issued)
        top_mods = Counter(record.moderator_id for record in issued if record.moderator_id)
        top_reasons = Counter(record.description for record in issued if record.description)

        lines = [
            f"Period: {self.format_period(timespan)}",
            f"Warnings issued: {humanize_number(len(issued))}",
            f"Points issued: {humanize_number(sum(record.points for record in issued))}",
            f"Unique members warned: {humanize_number(len({record.user_id for record in issued}))}",
            f"Active warnings now: {humanize_number(len(active))}",
            f"Active warning points: {humanize_number(sum(record.points for record in active))}",
            f"Expired in period: {humanize_number(sum(1 for record in resolved if record.resolution == 'expired'))}",
            f"Manually removed in period: {humanize_number(sum(1 for record in resolved if record.resolution == 'removed'))}",
        ]

        if top_users:
            user_id, count = top_users.most_common(1)[0]
            lines.append(f"Top warned member: {self.get_label(ctx.guild, user_id)} [{count}]")
        if top_mods:
            mod_id, count = top_mods.most_common(1)[0]
            lines.append(f"Top issuing moderator: {self.get_label(ctx.guild, mod_id)} [{count}]")
        if top_reasons:
            reason, count = top_reasons.most_common(1)[0]
            lines.append(f"Most common reason: {self.shorten_reason(reason)} [{count}]")

        await ctx.send("\n".join(lines))

    @modlogtool.command(name="leaderboard", aliases=["topwarned", "lb"])
    async def mlt_leaderboard(
        self,
        ctx: commands.Context,
        *,
        options: str = "",
    ):
        """Show top warned members. Options: [active|warns|points] [timespan] [limit]."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        try:
            sort_by, timespan, limit = self.parse_leaderboard_args(options)
        except commands.BadArgument as exc:
            return await ctx.send(str(exc))
        await self.sync_guild_records(ctx.guild)

        window_records = self.get_window_records(ctx.guild, timespan)
        if not window_records:
            return await ctx.send("No warning data for that period.")

        active_keys = {
            (record.user_id, record.warn_id)
            for record in self.db.get_conf(ctx.guild).records.values()
            if record.is_active
        }
        aggregates: dict[int, dict[str, int]] = defaultdict(lambda: {"warns": 0, "points": 0, "active": 0})
        for record in window_records:
            aggregates[record.user_id]["warns"] += 1
            aggregates[record.user_id]["points"] += record.points
            if (record.user_id, record.warn_id) in active_keys:
                aggregates[record.user_id]["active"] += 1

        if sort_by == "active":
            ranked = sorted(
                aggregates.items(),
                key=lambda item: (item[1]["active"], item[1]["warns"], item[1]["points"]),
                reverse=True,
            )[:limit]
        elif sort_by == "points":
            ranked = sorted(
                aggregates.items(),
                key=lambda item: (item[1]["points"], item[1]["warns"], item[1]["active"]),
                reverse=True,
            )[:limit]
        else:
            ranked = sorted(
                aggregates.items(),
                key=lambda item: (item[1]["warns"], item[1]["active"], item[1]["points"]),
                reverse=True,
            )[:limit]

        lines = [f"Leaderboard for {self.format_period(timespan)} sorted by {self.format_leaderboard_sort(sort_by)}"]
        for index, (user_id, stats) in enumerate(ranked, start=1):
            lines.append(
                f"{index}. {self.get_label(ctx.guild, user_id)} -> {stats['warns']} warns | {stats['points']} pts | {stats['active']} active"
            )
        for page in pagify("\n".join(lines)):
            await ctx.send(page)

    @modlogtool.command(name="moderators", aliases=["topmods"])
    async def mlt_moderators(
        self,
        ctx: commands.Context,
        case_type: str = "warning",
        timespan: commands.TimedeltaConverter = None,
        limit: commands.Range[int, 1, 25] = 10,
    ):
        """Show which moderators issued the most cases.

        `case_type` - the modlog action to count. Common values:
        `warn` / `ban` / `kick` / `hackban` / `tempban` / `softban` /
        `unban` / `vmute` / `cmute` / `smute` / `vkick` / `expired`
        (default: warn)

        `timespan` - optional window, e.g. `30d`, `1w`, `12h`
        `limit` - number of results, 1-25 (default: 10)
        """
        normalized = self.normalize_modlog_case_type(case_type)

        try:
            all_casetypes = await modlog.get_all_casetypes(guild=ctx.guild)
        except Exception as e:
            log.error("Failed to fetch casetypes for guild %s", ctx.guild.id, exc_info=e)
            all_casetypes = []

        valid_names = {ct.name for ct in all_casetypes}
        if valid_names and normalized not in valid_names:
            type_list = " | ".join(ct.name for ct in sorted(all_casetypes, key=lambda c: c.name))
            return await ctx.send(f"Unknown case type `{case_type}`. Available: {type_list}")

        window_cases = await self.get_modlog_cases_for_window(ctx.guild, normalized, timespan)
        window_cases = [case for case in window_cases if case.moderator is not None]
        if not window_cases:
            label = self.format_modlog_case_type(normalized).lower()
            return await ctx.send(f"No moderator {label} data for that period.")

        aggregates: dict[int, int] = defaultdict(int)
        for case in window_cases:
            aggregates[get_user_id(case.moderator)] += 1

        ranked = sorted(
            aggregates.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:limit]

        case_label = self.format_modlog_case_type(normalized)
        lines = [f"Moderator leaderboard for {case_label} in {self.format_period(timespan)}"]
        for index, (user_id, count) in enumerate(ranked, start=1):
            lines.append(f"{index}. {self.get_label(ctx.guild, user_id)} -> {count} cases")
        for page in pagify("\n".join(lines)):
            await ctx.send(page)

    @modlogtool.command(name="member")
    async def mlt_member(
        self,
        ctx: commands.Context,
        member: discord.Member | commands.RawUserIdConverter,
        timespan: commands.TimedeltaConverter = None,
    ):
        """Show warning summary for one member."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        await self.sync_guild_records(ctx.guild)

        user_id = member.id if isinstance(member, discord.Member) else int(member)
        all_records = [record for record in self.db.get_conf(ctx.guild).records.values() if record.user_id == user_id]
        if not all_records:
            return await ctx.send("No tracked warnings for that member.")

        if timespan is None:
            window_records = all_records
        else:
            cutoff = utcnow() - timespan
            window_records = [record for record in all_records if record.created_at >= cutoff]

        active_records = [record for record in all_records if record.is_active]
        recent = sorted(window_records, key=lambda record: record.created_at, reverse=True)[:5]
        next_expiry = min((record.expires_at for record in active_records if record.expires_at), default=None)

        lines = [
            f"Member: {self.get_label(ctx.guild, user_id)}",
            f"Period: {self.format_period(timespan)}",
            f"Warnings issued: {humanize_number(len(window_records))}",
            f"Points issued: {humanize_number(sum(record.points for record in window_records))}",
            f"Active warnings now: {humanize_number(len(active_records))}",
            f"Active points now: {humanize_number(sum(record.points for record in active_records))}",
        ]
        if next_expiry is not None:
            lines.append(f"Next expiry: <t:{int(next_expiry.timestamp())}:F>")

        if recent:
            lines.append("Recent warnings:")
            for record in recent:
                reason = self.shorten_reason(record.description or "No reason provided")
                lines.append(
                    f"- <t:{record.created_ts}:d> | {record.points} pts | {reason} | {record.resolution or 'active'}"
                )
        lines.append(f"Use `{ctx.clean_prefix}modlogtool history` for the full list.")

        await ctx.send("\n".join(lines))

    @modlogtool.command(name="history")
    async def mlt_history(
        self,
        ctx: commands.Context,
        member: discord.Member | commands.RawUserIdConverter,
        timespan: commands.TimedeltaConverter = None,
    ):
        """Show a member's full warning history."""
        if self.get_warnings_cog() is None:
            return await ctx.send("Warnings cog not loaded.")
        await self.sync_guild_records(ctx.guild)

        user_id = member.id if isinstance(member, discord.Member) else int(member)
        records = [record for record in self.db.get_conf(ctx.guild).records.values() if record.user_id == user_id]
        if timespan is not None:
            cutoff = utcnow() - timespan
            records = [record for record in records if record.created_at >= cutoff]
        if not records:
            return await ctx.send("No tracked warnings for that member in that period.")

        records.sort(key=lambda record: record.created_at, reverse=True)
        lines = [
            f"Warning history for {self.get_label(ctx.guild, user_id)} "
            f"({self.format_period(timespan)}) - {humanize_number(len(records))} total"
        ]
        for record in records:
            reason = self.shorten_reason(record.description or "No reason provided")
            status = record.resolution or "active"
            case = f" | case #{record.modlog_case_number}" if record.modlog_case_number is not None else ""
            lines.append(
                f"- <t:{record.created_ts}:d> | `{record.warn_id}` | {record.points} pts | {status}{case} | {reason}"
            )
        for page in pagify("\n".join(lines)):
            await ctx.send(page)
