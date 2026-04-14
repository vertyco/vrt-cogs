import logging
import re
import typing as t
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, available_timezones

import discord

from .models import MAX_KEYWORDS_PER_RULE, RULE_NAME_PREFIX, GuildSettings, UserSchedule

log = logging.getLogger("red.vrt.noping")
PING_RE = re.compile(r"<@!?(\d+)>")


def make_keyword(user_id: int) -> str:
    """Create the automod keyword filter pattern for a user ID."""
    return f"*<@{user_id}>*"


def extract_user_ids(keyword_filter: list[str]) -> list[int]:
    """Extract user IDs from a list of automod keyword filter strings."""
    ids = []
    for kw in keyword_filter:
        match = PING_RE.search(kw)
        if match:
            ids.append(int(match.group(1)))
    return ids


def rule_name(index: int) -> str:
    """Generate a deterministic rule name for the given index (0-based)."""
    if index == 0:
        return RULE_NAME_PREFIX
    return f"{RULE_NAME_PREFIX} {index + 1}"


def is_noping_rule(rule: discord.AutoModRule) -> bool:
    """Check if an automod rule is managed by this cog."""
    name = rule.name.strip()
    if name == RULE_NAME_PREFIX:
        return True
    if name.startswith(RULE_NAME_PREFIX + " "):
        suffix = name[len(RULE_NAME_PREFIX) + 1 :]
        return suffix.isdigit()
    return False


def is_legacy_noping_rule(rule: discord.AutoModRule) -> bool:
    """Check if an automod rule is a legacy 'No Ping' rule from the old vrtutils cog."""
    return "no ping" in rule.name.strip().lower()


def get_noping_rules(rules: list[discord.AutoModRule]) -> list[discord.AutoModRule]:
    """Filter and sort NoPing rules from a list of automod rules.

    Finds rules managed by this cog first, then falls back to legacy 'No Ping' rules
    from the old vrtutils version so they can be adopted.
    """
    managed = [r for r in rules if is_noping_rule(r)]
    if managed:
        managed.sort(key=lambda r: r.name)
        return managed
    # No managed rules found, look for legacy rules to adopt
    legacy = [r for r in rules if is_legacy_noping_rule(r)]
    if legacy:
        legacy.sort(key=lambda r: r.name)
        return legacy
    return []


def resolve_timezone(user_sched: UserSchedule, guild_tz: str) -> ZoneInfo:
    """Resolve the effective timezone for a user (user override > guild default)."""
    tz_str = user_sched.timezone or guild_tz
    try:
        return ZoneInfo(tz_str)
    except (KeyError, ValueError):
        return ZoneInfo("UTC")


def get_current_time(timezone_str: str) -> datetime:
    """Get current time in the given timezone."""
    try:
        tz = ZoneInfo(timezone_str)
    except (KeyError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz)


def get_user_time(user_sched: UserSchedule, guild_tz: str) -> datetime:
    """Get current time in the user's effective timezone."""
    tz = resolve_timezone(user_sched, guild_tz)
    return datetime.now(tz)


def discord_timestamp(dt: datetime, style: str = "F") -> str:
    """Format a datetime as a Discord timestamp string.

    Styles: F (full), f (short datetime), D (date), d (short date),
            T (long time), t (short time), R (relative)
    """
    return f"<t:{int(dt.timestamp())}:{style}>"


def next_occurrence(tz: ZoneInfo, weekday: int, hour: int, minute: int) -> datetime:
    """Get the next occurrence of a specific weekday + time in the given timezone."""
    now = datetime.now(tz)
    target = time(hour, minute)
    days_ahead = weekday - now.weekday()
    if days_ahead < 0:
        days_ahead += 7
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=days_ahead)
    if days_ahead == 0 and now.time() >= target:
        candidate += timedelta(days=7)
    return candidate


def next_transition_dt(user_sched: UserSchedule, guild_tz: str) -> t.Optional[datetime]:
    """Calculate the datetime of the next schedule transition for a user.

    Returns None if no schedule is configured (permanent noping).
    """
    if not user_sched.has_schedule():
        return None

    tz = resolve_timezone(user_sched, guild_tz)
    now = datetime.now(tz)
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute

    current_active = user_sched.is_noping_active_at(weekday, hour, minute)
    current_total = hour * 60 + minute

    for day_offset in range(8):
        check_day = (weekday + day_offset) % 7
        day_sched = user_sched.days.get(check_day)

        if not day_sched or not day_sched.enabled or not day_sched.windows:
            if not current_active:
                if day_offset == 0:
                    all_ended = (
                        all((w.end_hour * 60 + w.end_minute) <= current_total for w in day_sched.windows)
                        if day_sched and day_sched.windows
                        else True
                    )
                    if all_ended:
                        continue
                minutes_away = day_offset * 1440 - current_total if day_offset > 0 else (1440 - current_total)
                return now + timedelta(minutes=minutes_away)
            continue

        sorted_windows = sorted(day_sched.windows, key=lambda w: w.start_hour * 60 + w.start_minute)
        for window in sorted_windows:
            start = window.start_hour * 60 + window.start_minute
            end = window.end_hour * 60 + window.end_minute

            if day_offset == 0:
                if current_active and start > current_total:
                    return now + timedelta(minutes=start - current_total)
                if not current_active and end > current_total:
                    return now + timedelta(minutes=end - current_total)
            else:
                offset_minutes = day_offset * 1440 - current_total
                if current_active:
                    return now + timedelta(minutes=offset_minutes + start)
                else:
                    return now + timedelta(minutes=offset_minutes + end)

    return None


def window_discord_times(
    user_sched: UserSchedule,
    guild_tz: str,
    weekday: int,
    window_index: int,
) -> tuple[str, str]:
    """Convert a schedule window to Discord timestamp strings for the next occurrence."""
    tz = resolve_timezone(user_sched, guild_tz)
    day_sched = user_sched.days.get(weekday)
    if not day_sched or window_index >= len(day_sched.windows):
        return ("N/A", "N/A")
    window = day_sched.windows[window_index]
    start_dt = next_occurrence(tz, weekday, window.start_hour, window.start_minute)
    end_dt = next_occurrence(tz, weekday, window.end_hour, window.end_minute)
    return (discord_timestamp(start_dt, "t"), discord_timestamp(end_dt, "t"))


def import_legacy_users(
    all_rules: list[discord.AutoModRule],
    conf: GuildSettings,
    guild_id: int,
) -> int:
    """Import users from legacy 'No Ping' automod rules into the cog's database.

    Checks the provided rules for legacy naming patterns and extracts user IDs
    from their keyword filters. Any users not already in the database are added
    with noping enabled (permanent, no schedule).

    Only runs when no managed NoPing rules exist yet (first-time adoption).
    Returns the number of newly imported users.
    """
    # Only import if we don't already have managed rules (first-time adoption)
    managed = [r for r in all_rules if is_noping_rule(r)]
    if managed:
        return 0

    legacy = [r for r in all_rules if is_legacy_noping_rule(r)]
    if not legacy:
        return 0

    imported = 0
    for rule in legacy:
        existing_ids = extract_user_ids(rule.trigger.keyword_filter)
        for uid in existing_ids:
            if uid not in conf.users:
                sched = conf.get_user(uid)
                sched.enabled = True
                imported += 1
            elif not conf.users[uid].enabled:
                conf.users[uid].enabled = True
                imported += 1

    if imported:
        log.info("Imported %d user(s) from legacy No Ping rules in guild %s", imported, guild_id)
    return imported


async def sync_rules(
    guild: discord.Guild,
    conf: GuildSettings,
    active_user_ids: list[int],
    bot_mod_roles: list[discord.Role],
    all_rules: list[discord.AutoModRule],
) -> list[int]:
    """Synchronize automod rules with the current set of active noping user IDs.

    Creates, updates, or deletes rules as needed to match the active user set.
    Returns the list of rule IDs that are currently active.
    """
    keywords = [make_keyword(uid) for uid in active_user_ids]
    chunks: list[list[str]] = []
    for i in range(0, len(keywords), MAX_KEYWORDS_PER_RULE):
        chunks.append(keywords[i : i + MAX_KEYWORDS_PER_RULE])

    existing_rules = get_noping_rules(all_rules)

    rule_ids: list[int] = []

    for idx, chunk in enumerate(chunks):
        expected_name = rule_name(idx)
        trigger = discord.AutoModTrigger(keyword_filter=chunk)

        if idx < len(existing_rules):
            rule = existing_rules[idx]
            try:
                await rule.edit(
                    name=expected_name,
                    trigger=trigger,
                    enabled=True,
                    reason="NoPing schedule sync",
                )
                rule_ids.append(rule.id)
            except discord.HTTPException:
                log.exception("Failed to edit automod rule %s in guild %s", rule.id, guild.id)
        else:
            exempt_roles = list(set(bot_mod_roles))[:20]
            try:
                new_rule = await guild.create_automod_rule(
                    name=expected_name,
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[
                        discord.AutoModRuleAction(
                            type=discord.AutoModRuleActionType.block_message,
                            custom_message="This user does not want to be pinged!",
                        ),
                    ],
                    exempt_roles=exempt_roles,
                    enabled=True,
                    reason="NoPing rule created for ping protection.",
                )
                rule_ids.append(new_rule.id)
            except discord.HTTPException:
                log.exception("Failed to create automod rule in guild %s", guild.id)

    for excess_rule in existing_rules[len(chunks) :]:
        try:
            await excess_rule.delete(reason="NoPing rule no longer needed.")
        except discord.HTTPException:
            log.exception("Failed to delete excess automod rule %s in guild %s", excess_rule.id, guild.id)

    return rule_ids


def get_noping_user_ids_at_now(conf: GuildSettings) -> list[int]:
    """Get user IDs whose noping is active right now, respecting per-user timezones."""
    active = []
    for uid, sched in conf.users.items():
        if not sched.enabled:
            continue
        now = get_user_time(sched, conf.timezone)
        if sched.is_noping_active_at(now.weekday(), now.hour, now.minute):
            active.append(uid)
    return active


def get_available_timezones() -> list[str]:
    """Get a sorted list of all available timezone names."""
    return sorted(available_timezones())
