"""Analytics tracking utilities for ticket events.

This module provides functions to record analytics events when tickets are
opened, closed, claimed, etc. The tracked data powers the analytics commands.
"""

from datetime import datetime

from .models import (
    EventType,
    GuildSettings,
    OpenedTicket,
    ServerEvent,
    StaffEvent,
    UserEvent,
)


def record_ticket_opened(
    conf: GuildSettings,
    user_id: int,
    panel_name: str,
    channel_id: int,
) -> None:
    """Record analytics when a ticket is opened.

    Args:
        conf: Guild settings
        user_id: The user who opened the ticket
        panel_name: The name of the panel used
        channel_id: The ticket channel ID
    """
    if conf.is_panel_analytics_blacklisted(panel_name):
        return

    now = datetime.now().astimezone()

    # --- User Stats ---
    user_stats = conf.get_user_stats(user_id)
    user_stats.tickets_opened += 1

    # Panel usage tracking
    if panel_name not in user_stats.panel_usage:
        user_stats.panel_usage[panel_name] = 0
    user_stats.panel_usage[panel_name] += 1

    # Track first/last ticket timestamps
    if user_stats.first_ticket is None:
        user_stats.first_ticket = now

    # Check for repeat ticket (opened within 24h of last)
    if user_stats.last_ticket:
        hours_since_last = (now - user_stats.last_ticket).total_seconds() / 3600
        if hours_since_last <= 24:
            user_stats.repeat_tickets += 1

    user_stats.last_ticket = now

    # Record user event
    user_stats.events.append(
        UserEvent(
            timestamp=now,
            event_type=EventType.TICKET_OPENED,
            panel_name=panel_name,
            ticket_channel_id=channel_id,
        )
    )

    # --- Server Stats ---
    server_stats = conf.server_stats
    server_stats.total_tickets_opened += 1

    # Time distribution
    hour = now.hour
    weekday = now.weekday()  # 0=Monday

    if hour not in server_stats.hourly_distribution:
        server_stats.hourly_distribution[hour] = 0
    server_stats.hourly_distribution[hour] += 1

    if weekday not in server_stats.daily_distribution:
        server_stats.daily_distribution[weekday] = 0
    server_stats.daily_distribution[weekday] += 1

    # Panel usage
    if panel_name not in server_stats.panel_usage:
        server_stats.panel_usage[panel_name] = 0
    server_stats.panel_usage[panel_name] += 1

    # Monthly tracking
    month_key = now.strftime("%Y-%m")
    if month_key not in server_stats.monthly_opened:
        server_stats.monthly_opened[month_key] = 0
    server_stats.monthly_opened[month_key] += 1

    # Record server event
    server_stats.events.append(
        ServerEvent(
            timestamp=now,
            event_type=EventType.TICKET_OPENED,
            panel_name=panel_name,
            hour=hour,
            weekday=weekday,
        )
    )


def record_ticket_closed(
    conf: GuildSettings,
    ticket: OpenedTicket,
    channel_id: int,
    owner_id: int,
    closed_by_id: int,
) -> None:
    """Record analytics when a ticket is closed.

    Args:
        conf: Guild settings
        ticket: The opened ticket data
        channel_id: The ticket channel ID
        owner_id: The user who owns the ticket
        closed_by_id: The user who closed the ticket
    """
    if conf.is_panel_analytics_blacklisted(ticket.panel):
        return

    now = datetime.now().astimezone()
    resolution_time = (now - ticket.opened).total_seconds()
    panel_name = ticket.panel

    # Calculate wait time (time to first response)
    wait_time: float | None = None
    if ticket.first_response:
        wait_time = (ticket.first_response - ticket.opened).total_seconds()

    # --- User Stats (for ticket owner) ---
    user_stats = conf.get_user_stats(owner_id)
    user_stats.tickets_closed += 1
    user_stats.total_resolution_time += resolution_time

    if wait_time is not None:
        user_stats.total_wait_time += wait_time

    # Record user event
    user_stats.events.append(
        UserEvent(
            timestamp=now,
            event_type=EventType.TICKET_CLOSED,
            panel_name=panel_name,
            ticket_channel_id=channel_id,
            resolution_time=resolution_time,
            wait_time=wait_time,
        )
    )

    # --- Staff Stats (only if a staff member closed it, not self-close) ---
    if closed_by_id != owner_id:
        staff_stats = conf.get_staff_stats(closed_by_id)
        staff_stats.tickets_closed += 1
        staff_stats.total_resolution_time += resolution_time
        staff_stats.resolution_count += 1
        staff_stats.last_active = now

        # Record staff event
        staff_stats.events.append(
            StaffEvent(
                timestamp=now,
                event_type=EventType.TICKET_CLOSED,
                ticket_channel_id=channel_id,
                resolution_time=resolution_time,
            )
        )

    # --- Server Stats ---
    server_stats = conf.server_stats
    server_stats.total_tickets_closed += 1
    server_stats.total_resolution_time += resolution_time
    server_stats.resolution_count += 1

    # Monthly tracking
    month_key = now.strftime("%Y-%m")
    if month_key not in server_stats.monthly_closed:
        server_stats.monthly_closed[month_key] = 0
    server_stats.monthly_closed[month_key] += 1

    # Record server event
    server_stats.events.append(
        ServerEvent(
            timestamp=now,
            event_type=EventType.TICKET_CLOSED,
            panel_name=panel_name,
            hour=now.hour,
            weekday=now.weekday(),
            resolution_time=resolution_time,
        )
    )


def record_ticket_claimed(
    conf: GuildSettings,
    staff_id: int,
    channel_id: int,
    panel_name: str,
) -> None:
    """Record analytics when a staff member claims a ticket.

    Args:
        conf: Guild settings
        staff_id: The staff member who claimed
        channel_id: The ticket channel ID
        panel_name: The panel name (for blacklist checking)
    """
    if conf.is_panel_analytics_blacklisted(panel_name):
        return

    now = datetime.now().astimezone()

    staff_stats = conf.get_staff_stats(staff_id)
    staff_stats.tickets_claimed += 1
    staff_stats.last_active = now

    staff_stats.events.append(
        StaffEvent(
            timestamp=now,
            event_type=EventType.TICKET_CLAIMED,
            ticket_channel_id=channel_id,
        )
    )


def record_staff_first_response(
    conf: GuildSettings,
    ticket: OpenedTicket,
    staff_id: int,
    channel_id: int,
) -> None:
    """Record analytics when staff sends first response in a ticket.

    This should only be called once per ticket (when first_response is None).

    Args:
        conf: Guild settings
        ticket: The opened ticket data
        staff_id: The staff member who responded
        channel_id: The ticket channel ID
    """
    if conf.is_panel_analytics_blacklisted(ticket.panel):
        # Still record first_response timestamp on the ticket itself
        # so auto-close and other non-analytics features work correctly
        ticket.first_response = datetime.now().astimezone()
        return

    now = datetime.now().astimezone()
    response_time = (now - ticket.opened).total_seconds()

    # Record the first response time on the ticket itself
    ticket.first_response = now

    # --- Staff Stats ---
    staff_stats = conf.get_staff_stats(staff_id)
    staff_stats.total_response_time += response_time
    staff_stats.response_count += 1
    staff_stats.last_active = now

    # Track fastest/slowest
    if staff_stats.fastest_response is None or response_time < staff_stats.fastest_response:
        staff_stats.fastest_response = response_time
    if staff_stats.slowest_response is None or response_time > staff_stats.slowest_response:
        staff_stats.slowest_response = response_time

    # Record event
    staff_stats.events.append(
        StaffEvent(
            timestamp=now,
            event_type=EventType.FIRST_RESPONSE,
            ticket_channel_id=channel_id,
            response_time=response_time,
        )
    )

    # Also add to legacy response_times list for average display
    conf.response_times.append(response_time)
    # Keep only last 100 for the legacy average calculation
    if len(conf.response_times) > 100:
        conf.response_times = conf.response_times[-100:]


def record_staff_message(
    conf: GuildSettings,
    staff_id: int,
    channel_id: int,
    panel_name: str,
) -> None:
    """Record analytics when a staff member sends a message in a ticket.

    Args:
        conf: Guild settings
        staff_id: The staff member who sent the message
        channel_id: The ticket channel ID
        panel_name: The panel name (for blacklist checking)
    """
    if conf.is_panel_analytics_blacklisted(panel_name):
        return

    now = datetime.now().astimezone()

    staff_stats = conf.get_staff_stats(staff_id)
    staff_stats.messages_sent += 1
    staff_stats.tickets_messaged_in.add(channel_id)
    staff_stats.last_active = now

    # Record event
    staff_stats.events.append(
        StaffEvent(
            timestamp=now,
            event_type=EventType.MESSAGE_SENT,
            ticket_channel_id=channel_id,
        )
    )


def record_user_message(
    conf: GuildSettings,
    user_id: int,
    panel_name: str,
) -> None:
    """Record analytics when a ticket owner sends a message.

    Args:
        conf: Guild settings
        user_id: The user who sent the message
        panel_name: The panel name (for blacklist checking)
    """
    if conf.is_panel_analytics_blacklisted(panel_name):
        return

    user_stats = conf.get_user_stats(user_id)
    user_stats.messages_sent += 1
