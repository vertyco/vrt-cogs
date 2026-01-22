import logging
from datetime import datetime, timedelta

import discord
import pytz
from dateutil import parser
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from redbot.core.commands import parse_timedelta

from ..db.tables import GlobalSettings, GuildSettings

log = logging.getLogger("red.vrt.metrics.utils")


def chunk(obj_list: list, chunk_size: int):
    for i in range(0, len(obj_list), chunk_size):
        yield obj_list[i : i + chunk_size]


def get_window(delta: timedelta, data_points: int, snapshot_interval_minutes: int) -> int:
    if data_points <= 2:
        return max(2, data_points)

    delta_minutes = max(delta.total_seconds() / 60.0, 1.0)

    avg_interval = delta_minutes / max(data_points - 1, 1)
    effective_interval = max(float(snapshot_interval_minutes), avg_interval, 1.0)

    min_span = effective_interval * 2
    max_span = min(delta_minutes, 60.0 * 24 * 2)
    target_span = delta_minutes * 0.1

    target_span = max(target_span, min_span)
    target_span = min(target_span, max_span)

    desired_points = int(round(target_span / effective_interval))
    if desired_points < 2:
        desired_points = 2

    if desired_points > data_points:
        desired_points = data_points

    max_allowed = max(2, int(data_points * 0.4))
    if desired_points > max_allowed:
        desired_points = max_allowed

    return desired_points


def get_timespan(
    timespan: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    timezone: str = "UTC",
) -> tuple[datetime, datetime]:
    # Used by playergraph and lookback commands
    now = TimestamptzNow().python()
    user_tz = pytz.timezone(timezone)

    parsed_timespan: None | timedelta = None
    if timespan and timespan == "all":
        parsed_timespan = timedelta(weeks=10000)  # Arbitrary large number of weeks
    elif timespan:
        parsed_timespan = parse_timedelta(timespan)

    parsed_start: None | datetime = None
    if start_time:
        try:
            parsed_start = parser.parse(start_time)
        except parser.ParserError:
            pass
    parsed_end: None | datetime = None
    if end_time:
        try:
            parsed_end = parser.parse(end_time)
        except parser.ParserError:
            pass

    if start_time and end_time and not parsed_start and not parsed_end:
        log.warning(f"Failed to parse start or end time: {start_time}, {end_time} - Combining")
        # Combine the two into the start, maybe the user didnt use quotes
        start_time = start_time + " " + end_time
        try:
            parsed_start = parser.parse(start_time)
        except parser.ParserError:
            pass

    if parsed_start and parsed_start.tzinfo is None:
        # localize to UTC
        parsed_start = user_tz.localize(parsed_start)
    elif parsed_start:
        parsed_start = parsed_start.astimezone(user_tz)

    if parsed_end and parsed_end.tzinfo is None:
        parsed_end = user_tz.localize(parsed_end)
    elif parsed_end:
        parsed_end = parsed_end.astimezone(user_tz)

    if parsed_timespan and parsed_start:
        start = parsed_start
        end = parsed_start + parsed_timespan
    elif parsed_timespan and parsed_end:
        end = parsed_end
        start = parsed_end - parsed_timespan
    elif parsed_timespan:
        start = now - parsed_timespan
        end = now
    elif parsed_start and parsed_end:
        start = parsed_start
        end = parsed_end
    elif parsed_start and not parsed_end:
        end = now
        start = parsed_start
    else:
        start = now - timedelta(hours=12)
        end = now

    if start >= end:
        start = end - timedelta(hours=12)

    return start, end


class DBUtils:
    @staticmethod
    async def get_create_global_settings() -> GlobalSettings:
        settings: GlobalSettings = await GlobalSettings.objects().get_or_create(
            (GlobalSettings.key == 1), defaults={GlobalSettings.key: 1}
        )
        return settings

    @staticmethod
    async def get_create_guild_settings(guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        settings = await GuildSettings.objects().get_or_create(
            (GuildSettings.id == gid), defaults={GuildSettings.id: gid}
        )
        return settings
