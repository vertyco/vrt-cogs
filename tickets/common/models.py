"""
Pydantic models for the Tickets cog.

This module contains all data models used by the tickets system, following
the pattern established by ideaboard/levelup cogs.
"""

from __future__ import annotations

import logging
import typing as t
from datetime import datetime, timedelta
from enum import Enum

import discord
import orjson
from pydantic import VERSION, BaseModel, Field
from redbot.core import Config

log = logging.getLogger("red.vrt.tickets.models")


# =============================================================================
# Base Model
# =============================================================================


class Base(BaseModel):
    """Custom BaseModel with serialization helpers"""

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def load(cls, obj: dict[str, t.Any]) -> t.Self:
        if VERSION >= "2.0.1":
            return cls.model_validate(obj)
        return cls.parse_obj(obj)

    def dump(self, exclude_defaults: bool = True) -> dict[str, t.Any]:
        if VERSION >= "2.0.1":
            return self.model_dump(mode="json", exclude_defaults=exclude_defaults)
        return orjson.loads(self.json(exclude_defaults=exclude_defaults))


# =============================================================================
# Enums
# =============================================================================


class EventType(str, Enum):
    """Types of trackable events for analytics"""

    TICKET_OPENED = "opened"
    TICKET_CLOSED = "closed"
    TICKET_CLAIMED = "claimed"
    FIRST_RESPONSE = "first_response"
    MESSAGE_SENT = "message"


# =============================================================================
# Event Models (for timespan-based analytics queries)
# =============================================================================


class StaffEvent(Base):
    """A timestamped event for a staff member"""

    timestamp: datetime
    event_type: EventType
    ticket_channel_id: int  # For deduplication

    # Optional metrics attached to event
    response_time: float | None = None  # Seconds (for FIRST_RESPONSE)
    resolution_time: float | None = None  # Seconds (for TICKET_CLOSED)


class UserEvent(Base):
    """A timestamped event for a user who opens tickets"""

    timestamp: datetime
    event_type: EventType
    panel_name: str
    ticket_channel_id: int

    # Optional metrics attached to event
    resolution_time: float | None = None  # Seconds (for TICKET_CLOSED)
    wait_time: float | None = None  # Seconds to first response (for TICKET_CLOSED)


class ServerEvent(Base):
    """A timestamped event for server-wide stats"""

    timestamp: datetime
    event_type: EventType
    panel_name: str
    hour: int  # 0-23
    weekday: int  # 0-6 (Monday=0)

    # Optional metrics
    resolution_time: float | None = None


# =============================================================================
# Modal & Message Models
# =============================================================================


class ModalField(Base):
    """A field in a ticket panel's modal form"""

    label: str
    style: str = "short"  # "short" or "long"
    placeholder: str | None = None
    default: str | None = None
    required: bool = True
    min_length: int | None = None
    max_length: int | None = None


class TicketMessage(Base):
    """An embed message sent when a ticket is opened"""

    title: str | None = None
    desc: str
    footer: str | None = None
    color: int | None = None  # Hex color as int
    image: str | None = None  # Image URL


# =============================================================================
# Working Hours Models
# =============================================================================


class DayHours(Base):
    """Working hours for a single day"""

    start: str  # "HH:MM" format (24h)
    end: str  # "HH:MM" format (24h)


# =============================================================================
# Opened Ticket Model
# =============================================================================


class OpenedTicket(Base):
    """Data for an opened ticket"""

    panel: str
    opened: datetime
    pfp: str | None = None  # User avatar URL
    logmsg: int | None = None  # Log message ID
    answers: dict[str, str] = {}  # {question: answer}
    has_response: bool = False  # Whether ticket owner has responded
    message_id: int | None = None  # First bot message ID in ticket
    max_claims: int = 0
    overview_msg: int | None = None  # Overview message ID
    first_response: datetime | None = None
    closed_by: int | None = None  # User ID of who closed (set on close)


# =============================================================================
# Panel Model
# =============================================================================


class Panel(Base):
    """Configuration for a ticket panel"""

    # Required settings (must be set for panel to function)
    category_id: int = 0
    channel_id: int = 0
    message_id: int = 0

    # Panel state
    disabled: bool = False

    # Alternative channel for opening tickets
    alt_channel: int = 0

    # Role requirements
    required_roles: list[int] = []  # Roles required to open tickets
    roles: list[tuple[int, bool]] = []  # Panel-specific support roles [(role_id, mention)]

    # Close settings
    close_reason: bool = True  # Require reason modal on close

    # Button settings
    button_text: str = "Open a Ticket"
    button_color: str = "blue"  # red, blue, green, grey
    button_emoji: str | None = None
    priority: int = 1  # Button order
    row: int | None = None  # Button row

    # Ticket settings
    ticket_messages: list[TicketMessage] = []
    ticket_name: str | None = None  # Channel name format
    log_channel: int = 0
    threads: bool = False  # Use threads instead of channels
    max_claims: int = 0  # Max staff who can claim (0 = unlimited)

    # Modal settings
    modal: dict[str, ModalField] = {}  # {field_name: ModalField}
    modal_title: str = ""

    # Ticket counter
    ticket_num: int = 1

    # Working hours
    working_hours: dict[str, DayHours] = {}  # {day_name: DayHours}
    timezone: str = "UTC"
    block_outside_hours: bool = False
    outside_hours_message: str = ""


# =============================================================================
# Analytics Models
# =============================================================================


class StaffStats(Base):
    """Analytics for a support staff member"""

    user_id: int

    # Ticket counts (cumulative, all-time)
    tickets_claimed: int = 0
    tickets_closed: int = 0
    tickets_reopened: int = 0  # Tickets reopened after they closed

    # Response time tracking (cumulative)
    total_response_time: float = 0  # Cumulative seconds
    response_count: int = 0
    fastest_response: float | None = None  # Seconds
    slowest_response: float | None = None  # Seconds

    # Resolution time tracking (cumulative)
    total_resolution_time: float = 0  # Cumulative seconds
    resolution_count: int = 0

    # Message tracking (cumulative)
    messages_sent: int = 0
    tickets_messaged_in: set[int] = set()  # Unique ticket channel IDs

    # Activity
    last_active: datetime | None = None

    # Event history for timespan queries
    events: list[StaffEvent] = []

    @property
    def avg_response_time(self) -> float | None:
        if self.response_count == 0:
            return None
        return self.total_response_time / self.response_count

    @property
    def avg_resolution_time(self) -> float | None:
        if self.resolution_count == 0:
            return None
        return self.total_resolution_time / self.resolution_count

    @property
    def avg_messages_per_ticket(self) -> float | None:
        ticket_count = len(self.tickets_messaged_in)
        if ticket_count == 0:
            return None
        return self.messages_sent / ticket_count


class UserStats(Base):
    """Analytics for a user who opens tickets"""

    user_id: int

    # Ticket counts (cumulative, all-time)
    tickets_opened: int = 0
    tickets_closed: int = 0

    # Time tracking (cumulative)
    total_resolution_time: float = 0  # Cumulative seconds
    total_wait_time: float = 0  # Time waiting for first response

    # Message tracking (cumulative)
    messages_sent: int = 0

    # Panel usage (cumulative)
    panel_usage: dict[str, int] = {}  # {panel_name: count}

    # Behavioral tracking
    repeat_tickets: int = 0  # Opened within 24h of closing another

    # Timestamps
    first_ticket: datetime | None = None
    last_ticket: datetime | None = None

    # Event history for timespan queries
    events: list[UserEvent] = []

    @property
    def avg_resolution_time(self) -> float | None:
        if self.tickets_closed == 0:
            return None
        return self.total_resolution_time / self.tickets_closed

    @property
    def avg_wait_time(self) -> float | None:
        if self.tickets_closed == 0:
            return None
        return self.total_wait_time / self.tickets_closed

    @property
    def avg_messages_per_ticket(self) -> float | None:
        if self.tickets_opened == 0:
            return None
        return self.messages_sent / self.tickets_opened


class ServerStats(Base):
    """Server-wide analytics"""

    # Lifetime counters
    total_tickets_opened: int = 0
    total_tickets_closed: int = 0

    # Resolution tracking
    total_resolution_time: float = 0
    resolution_count: int = 0

    # Time distribution tracking (all-time cumulative)
    hourly_distribution: dict[int, int] = {}  # {0-23: count}
    daily_distribution: dict[int, int] = {}  # {0-6: count} (0=Monday)

    # Panel usage (all-time cumulative)
    panel_usage: dict[str, int] = {}  # {panel_name: count}

    # Monthly rollups (for trends)
    monthly_opened: dict[str, int] = {}  # {"2026-01": count}
    monthly_closed: dict[str, int] = {}  # {"2026-01": count}

    # Event history for timespan queries
    events: list[ServerEvent] = []

    @property
    def avg_resolution_time(self) -> float | None:
        if self.resolution_count == 0:
            return None
        return self.total_resolution_time / self.resolution_count

    @property
    def busiest_hour(self) -> int | None:
        if not self.hourly_distribution:
            return None
        return max(self.hourly_distribution, key=self.hourly_distribution.get)

    @property
    def busiest_day(self) -> int | None:
        if not self.daily_distribution:
            return None
        return max(self.daily_distribution, key=self.daily_distribution.get)


# =============================================================================
# Guild Settings Model
# =============================================================================


class GuildSettings(Base):
    """All settings and data for a guild"""

    # === Core Settings ===
    support_roles: list[tuple[int, bool]] = []  # [(role_id, mention)]
    blacklist: list[int] = []  # User/role IDs
    max_tickets: int = 1
    inactive: int = 0  # Auto-close hours (0 = disabled)

    # Overview panel
    overview_channel: int = 0
    overview_msg: int = 0
    overview_mention: bool = False

    # User permissions
    dm: bool = False  # DM user on ticket close
    user_can_rename: bool = False
    user_can_close: bool = True
    user_can_manage: bool = False  # Add users to ticket

    # Transcript settings
    transcript: bool = False
    detailed_transcript: bool = False  # HTML transcript

    # Thread settings
    auto_add: bool = False  # Auto-add support roles to thread tickets
    thread_close: bool = True  # Archive instead of delete

    # Suspension
    suspended_msg: str | None = None

    # Response time display (legacy, kept for compatibility)
    show_response_time: bool = True
    response_times: list[float] = []  # Legacy response times list

    # === Ticket Data ===
    opened: dict[int, dict[int, OpenedTicket]] = {}  # {user_id: {channel_id: ticket}}
    panels: dict[str, Panel] = {}  # {panel_name: Panel}

    # === Analytics Data ===
    staff_stats: dict[int, StaffStats] = {}  # {user_id: StaffStats}
    user_stats: dict[int, UserStats] = {}  # {user_id: UserStats}
    server_stats: ServerStats = Field(default_factory=ServerStats)

    # === Data Retention ===
    data_retention_days: int = 90  # Days to keep event data (0 = unlimited)

    # === Helper Methods ===
    def get_staff_stats(self, user_id: int) -> StaffStats:
        """Get or create stats for a staff member"""
        if user_id not in self.staff_stats:
            self.staff_stats[user_id] = StaffStats(user_id=user_id)
        return self.staff_stats[user_id]

    def get_user_stats(self, user_id: int) -> UserStats:
        """Get or create stats for a ticket-opening user"""
        if user_id not in self.user_stats:
            self.user_stats[user_id] = UserStats(user_id=user_id)
        return self.user_stats[user_id]

    def get_panel(self, name: str) -> Panel | None:
        """Get a panel by name (case-insensitive)"""
        return self.panels.get(name.lower())

    def get_opened_ticket(self, user_id: int, channel_id: int) -> OpenedTicket | None:
        """Get an opened ticket by user and channel ID"""
        user_tickets = self.opened.get(user_id, {})
        return user_tickets.get(channel_id)

    def is_blacklisted(self, member: discord.Member) -> bool:
        """Check if a member or any of their roles are blacklisted"""
        if member.id in self.blacklist:
            return True
        return any(r.id in self.blacklist for r in member.roles)

    def is_support_staff(self, member: discord.Member, panel: Panel | None = None) -> bool:
        """Check if member is support staff (global or panel-specific)"""
        member_role_ids = {r.id for r in member.roles}

        # Check global support roles
        global_role_ids = {r[0] for r in self.support_roles}
        if member_role_ids & global_role_ids:
            return True

        # Check panel-specific roles
        if panel:
            panel_role_ids = {r[0] for r in panel.roles}
            if member_role_ids & panel_role_ids:
                return True

        return False

    def get_support_role_ids(self, panel: Panel | None = None) -> set[int]:
        """Get all support role IDs (global + panel-specific)"""
        role_ids = {r[0] for r in self.support_roles}
        if panel:
            role_ids.update(r[0] for r in panel.roles)
        return role_ids


# =============================================================================
# Root Database Model
# =============================================================================


class DB(Base):
    """Root database model containing all guild configs"""

    configs: dict[int, GuildSettings] = {}  # {guild_id: GuildSettings}
    migrations: list[str] = []  # List of completed migration IDs

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        """Get or create settings for a guild"""
        gid = guild if isinstance(guild, int) else guild.id
        if gid not in self.configs:
            self.configs[gid] = GuildSettings()
        return self.configs[gid]


# =============================================================================
# Analytics Helpers
# =============================================================================


def prune_old_events(conf: GuildSettings) -> int:
    """
    Remove events older than retention period.

    Args:
        conf: The guild settings to prune

    Returns:
        Number of events removed
    """
    if conf.data_retention_days == 0:
        return 0  # Unlimited retention

    cutoff = datetime.now().astimezone() - timedelta(days=conf.data_retention_days)
    removed = 0

    for staff_stats in conf.staff_stats.values():
        original_len = len(staff_stats.events)
        staff_stats.events = [e for e in staff_stats.events if e.timestamp >= cutoff]
        removed += original_len - len(staff_stats.events)

    for user_stats in conf.user_stats.values():
        original_len = len(user_stats.events)
        user_stats.events = [e for e in user_stats.events if e.timestamp >= cutoff]
        removed += original_len - len(user_stats.events)

    # Prune server events
    original_len = len(conf.server_stats.events)
    conf.server_stats.events = [e for e in conf.server_stats.events if e.timestamp >= cutoff]
    removed += original_len - len(conf.server_stats.events)

    return removed


def get_staff_stats_for_timespan(
    stats: StaffStats,
    timespan: timedelta | None,
) -> dict[str, t.Any]:
    """
    Get staff stats filtered to a timespan.

    Args:
        stats: The staff stats to filter
        timespan: Time window to filter to, or None for all-time

    Returns:
        Dictionary of computed stats for the timespan
    """
    if timespan is None:
        # Return cumulative all-time stats
        return {
            "tickets_claimed": stats.tickets_claimed,
            "tickets_closed": stats.tickets_closed,
            "messages_sent": stats.messages_sent,
            "avg_response_time": stats.avg_response_time,
            "avg_resolution_time": stats.avg_resolution_time,
            "fastest_response": stats.fastest_response,
            "slowest_response": stats.slowest_response,
            "response_count": stats.response_count,
            "resolution_count": stats.resolution_count,
        }

    # Filter events to timespan
    cutoff = datetime.now().astimezone() - timespan
    relevant_events = [e for e in stats.events if e.timestamp >= cutoff]

    # Calculate stats from filtered events
    claimed = sum(1 for e in relevant_events if e.event_type == EventType.TICKET_CLAIMED)
    closed = sum(1 for e in relevant_events if e.event_type == EventType.TICKET_CLOSED)
    messages = sum(1 for e in relevant_events if e.event_type == EventType.MESSAGE_SENT)

    response_events = [e for e in relevant_events if e.event_type == EventType.FIRST_RESPONSE]
    response_times = [e.response_time for e in response_events if e.response_time is not None]

    close_events = [e for e in relevant_events if e.event_type == EventType.TICKET_CLOSED]
    resolution_times = [e.resolution_time for e in close_events if e.resolution_time is not None]

    return {
        "tickets_claimed": claimed,
        "tickets_closed": closed,
        "messages_sent": messages,
        "avg_response_time": sum(response_times) / len(response_times) if response_times else None,
        "avg_resolution_time": sum(resolution_times) / len(resolution_times) if resolution_times else None,
        "fastest_response": min(response_times) if response_times else None,
        "slowest_response": max(response_times) if response_times else None,
        "response_count": len(response_times),
        "resolution_count": len(resolution_times),
    }


def get_user_stats_for_timespan(
    stats: UserStats,
    timespan: timedelta | None,
) -> dict[str, t.Any]:
    """
    Get user stats filtered to a timespan.

    Args:
        stats: The user stats to filter
        timespan: Time window to filter to, or None for all-time

    Returns:
        Dictionary of computed stats for the timespan
    """
    if timespan is None:
        # Return cumulative all-time stats
        return {
            "tickets_opened": stats.tickets_opened,
            "tickets_closed": stats.tickets_closed,
            "messages_sent": stats.messages_sent,
            "avg_resolution_time": stats.avg_resolution_time,
            "avg_wait_time": stats.avg_wait_time,
            "panel_usage": stats.panel_usage.copy(),
        }

    # Filter events to timespan
    cutoff = datetime.now().astimezone() - timespan
    relevant_events = [e for e in stats.events if e.timestamp >= cutoff]

    # Calculate stats from filtered events
    opened = sum(1 for e in relevant_events if e.event_type == EventType.TICKET_OPENED)
    closed = sum(1 for e in relevant_events if e.event_type == EventType.TICKET_CLOSED)
    messages = sum(1 for e in relevant_events if e.event_type == EventType.MESSAGE_SENT)

    close_events = [e for e in relevant_events if e.event_type == EventType.TICKET_CLOSED]
    resolution_times = [e.resolution_time for e in close_events if e.resolution_time is not None]
    wait_times = [e.wait_time for e in close_events if e.wait_time is not None]

    # Panel usage for timespan
    panel_usage: dict[str, int] = {}
    for e in relevant_events:
        if e.event_type == EventType.TICKET_OPENED:
            panel_usage[e.panel_name] = panel_usage.get(e.panel_name, 0) + 1

    return {
        "tickets_opened": opened,
        "tickets_closed": closed,
        "messages_sent": messages,
        "avg_resolution_time": sum(resolution_times) / len(resolution_times) if resolution_times else None,
        "avg_wait_time": sum(wait_times) / len(wait_times) if wait_times else None,
        "panel_usage": panel_usage,
    }


def get_server_stats_for_timespan(
    stats: ServerStats,
    timespan: timedelta | None,
) -> dict[str, t.Any]:
    """
    Get server stats filtered to a timespan.

    Args:
        stats: The server stats to filter
        timespan: Time window to filter to, or None for all-time

    Returns:
        Dictionary of computed stats for the timespan
    """
    if timespan is None:
        # Return cumulative all-time stats
        return {
            "total_tickets_opened": stats.total_tickets_opened,
            "total_tickets_closed": stats.total_tickets_closed,
            "avg_resolution_time": stats.avg_resolution_time,
            "hourly_distribution": stats.hourly_distribution.copy(),
            "daily_distribution": stats.daily_distribution.copy(),
            "panel_usage": stats.panel_usage.copy(),
            "busiest_hour": stats.busiest_hour,
            "busiest_day": stats.busiest_day,
        }

    # Filter events to timespan
    cutoff = datetime.now().astimezone() - timespan
    relevant_events = [e for e in stats.events if e.timestamp >= cutoff]

    # Calculate stats from filtered events
    opened = sum(1 for e in relevant_events if e.event_type == EventType.TICKET_OPENED)
    closed = sum(1 for e in relevant_events if e.event_type == EventType.TICKET_CLOSED)

    close_events = [e for e in relevant_events if e.event_type == EventType.TICKET_CLOSED]
    resolution_times = [e.resolution_time for e in close_events if e.resolution_time is not None]

    # Build distributions for timespan
    hourly: dict[int, int] = {}
    daily: dict[int, int] = {}
    panel_usage: dict[str, int] = {}

    for e in relevant_events:
        if e.event_type == EventType.TICKET_OPENED:
            hourly[e.hour] = hourly.get(e.hour, 0) + 1
            daily[e.weekday] = daily.get(e.weekday, 0) + 1
            panel_usage[e.panel_name] = panel_usage.get(e.panel_name, 0) + 1

    return {
        "total_tickets_opened": opened,
        "total_tickets_closed": closed,
        "avg_resolution_time": sum(resolution_times) / len(resolution_times) if resolution_times else None,
        "hourly_distribution": hourly,
        "daily_distribution": daily,
        "panel_usage": panel_usage,
        "busiest_hour": max(hourly, key=hourly.get) if hourly else None,
        "busiest_day": max(daily, key=daily.get) if daily else None,
    }


# =============================================================================
# Migration
# =============================================================================


async def run_migrations(data: dict[str, t.Any], config: Config) -> tuple[DB, bool]:
    """
    Run migrations on config data and return validated DB model.

    Args:
        data: Raw config data dict from Config.db()
        config: The Red Config instance (for saving if migrations occur)

    Returns:
        Tuple of (validated DB model, whether migrations occurred)
    """
    if not data:
        data = {"configs": {}, "migrations": []}

    if "migrations" not in data:
        data["migrations"] = []

    if "configs" not in data:
        data["configs"] = {}

    migrated: bool = False

    # Day number to day name mapping for working_hours migration
    day_num_to_name: dict[str, str] = {
        "0": "sunday",
        "1": "monday",
        "2": "tuesday",
        "3": "wednesday",
        "4": "thursday",
        "5": "friday",
        "6": "saturday",
    }

    # Always check and fix data structures (idempotent migrations)
    for gid, conf in list(data["configs"].items()):
        if not conf:
            continue

        # Sanitize opened tickets - fix invalid first_response values
        opened: dict[str, t.Any] = conf.get("opened", {})
        for uid, tickets in opened.items():
            if not isinstance(tickets, dict):
                continue
            for cid, ticket in tickets.items():
                if not isinstance(ticket, dict):
                    continue
                # Fix invalid first_response values (e.g., "legacy" string)
                first_response = ticket.get("first_response")
                if first_response is not None and not isinstance(first_response, (int, float)):
                    # If it's not a valid timestamp or None, clear it
                    if isinstance(first_response, str):
                        # Try to parse as ISO datetime string, otherwise set to None
                        try:
                            datetime.fromisoformat(first_response.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            ticket["first_response"] = None
                            migrated = True

        panels: dict[str, t.Any] = conf.get("panels", {})
        for panel_name, panel in panels.items():
            # Convert modal from list to dict if needed (old schema)
            if isinstance(panel.get("modal"), list):
                panel["modal"] = {}
                migrated = True

            # Rename "description" to "desc" in ticket_messages
            messages: list[dict[str, t.Any]] = panel.get("ticket_messages", [])
            for msg in messages:
                if "desc" not in msg and "description" in msg:
                    msg["desc"] = msg.pop("description")
                    migrated = True
                elif "desc" not in msg:
                    msg["desc"] = ""

            # Migrate working_hours from old nested structure to new flat structure
            # Old format: {enabled: bool, allow_outside: bool, message: {}, days: {0: {enabled, start, end}}}
            # New format: {day_name: {start, end}}
            old_wh: dict[str, t.Any] = panel.get("working_hours", {})
            if old_wh and ("enabled" in old_wh or "days" in old_wh or "message" in old_wh):
                # Old format detected - convert to new format
                log.info(f"Migrating working_hours for panel '{panel_name}' in guild {gid}")
                new_wh: dict[str, dict[str, str]] = {}
                old_days: dict[str, t.Any] = old_wh.get("days", {})

                for day_num, day_data in old_days.items():
                    if isinstance(day_data, dict) and day_data.get("enabled"):
                        day_name: str | None = day_num_to_name.get(str(day_num))
                        if day_name:
                            new_wh[day_name] = {
                                "start": day_data.get("start", "09:00"),
                                "end": day_data.get("end", "17:00"),
                            }

                panel["working_hours"] = new_wh
                panel["block_outside_hours"] = not old_wh.get("allow_outside", True)

                # Extract message content if present
                old_msg: dict[str, t.Any] = old_wh.get("message", {})
                if old_msg and isinstance(old_msg, dict):
                    msg_parts: list[str] = []
                    if old_msg.get("title"):
                        msg_parts.append(old_msg["title"])
                    if old_msg.get("description"):
                        msg_parts.append(old_msg["description"])
                    panel["outside_hours_message"] = "\n".join(msg_parts) if msg_parts else ""

                # Preserve timezone if it existed
                if "timezone" not in panel:
                    panel["timezone"] = old_wh.get("timezone", "UTC")

                migrated = True

        # Convert support_roles from int to [int, bool] format
        support_roles: list[t.Any] = conf.get("support_roles", [])
        if support_roles and isinstance(support_roles[0], int):
            conf["support_roles"] = [[role, False] for role in support_roles]
            migrated = True

        # Convert panel roles from int to [int, bool] format
        for panel in panels.values():
            roles: list[t.Any] = panel.get("roles", [])
            if roles and isinstance(roles[0], int):
                panel["roles"] = [[role, False] for role in roles]
                migrated = True

    # Mark 3.0.0 migration as complete
    if "3.0.0" not in data["migrations"]:
        data["migrations"].append("3.0.0")
        migrated = True

    # Save if migrations were performed
    if migrated:
        await config.db.set(data)

    # Pydantic handles all default values automatically
    return DB.load(data), migrated


async def migrate_from_old_config(config: Config) -> tuple[DB, bool]:
    """
    Migrate from old per-guild Red Config format to new global Pydantic format.

    This is called when config.db() returns empty but there may be old
    per-guild data from config.all_guilds().

    Args:
        config: The Red Config instance

    Returns:
        Tuple of (validated DB model, whether migration occurred)
    """
    old_data: dict[int, dict[str, t.Any]] = await config.all_guilds()

    if not old_data:
        # No old data either, just return empty DB
        return DB(), False

    log.warning("Migrating from old per-guild Config to new Pydantic format")

    new_data: dict[str, t.Any] = {
        "configs": {},
        "migrations": [],
    }

    for gid, guild_conf in old_data.items():
        if not guild_conf:
            continue
        # Direct copy - structure is mostly the same
        new_data["configs"][int(gid)] = guild_conf

    # Clear old per-guild data after copying
    await config.clear_all_guilds()

    # Run standard migrations and return DB model
    return await run_migrations(new_data, config)
