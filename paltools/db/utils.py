"""DB helper functions for PalTools. Populated alongside the poll loop."""

from datetime import datetime, timedelta

from ..common.models import PalPlayer
from .tables import GuildSettings, Player, PlayerIp, Server, Session


def escape_like(value: str) -> str:
    """Neutralize LIKE wildcards so a search for '%' matches a literal percent sign"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def get_target_servers(guild_id: int, server_name: str | None = None) -> list[Server]:
    query = Server.objects().where((Server.guild_id == guild_id) & (Server.enabled == True))  # noqa: E712
    if server_name:
        # ilike, so the name has to be escaped: an unescaped '%' matches every server, and
        # [p]paltools shutdown % would then take out whichever one sorts first
        query = query.where(Server.name.ilike(escape_like(server_name)))
    return await query.order_by(Server.name)


async def get_create_guild_settings(guild_id: int) -> GuildSettings:
    settings = await GuildSettings.objects().get(GuildSettings.guild_id == guild_id)
    if settings is not None:
        return settings
    # Not get_or_create: that is a bare SELECT-then-INSERT, and the first poll tick after a
    # guild's first server racing an admin command would raise a unique violation. Same
    # hardening as upsert_player, with a re-read since DO NOTHING returns no row.
    row = GuildSettings(guild_id=guild_id)
    await GuildSettings.insert(row).on_conflict(target=GuildSettings.guild_id, action="DO NOTHING")
    refetched = await GuildSettings.objects().get(GuildSettings.guild_id == guild_id)
    return refetched if refetched is not None else row


async def upsert_player(guild_id: int, pal: PalPlayer, now: datetime) -> Player:
    key = f"{guild_id}-{pal.user_id}"
    # load_json, otherwise name_history comes back as the raw JSON text rather than a list
    player = await Player.objects().output(load_json=True).get(Player.lookup_key == key)
    if player is None:
        player = Player(
            lookup_key=key,
            guild_id=guild_id,
            user_id=pal.user_id,
            name=pal.name,
            account_name=pal.account_name,
            # Guarded like the update path below: a player first seen mid-world-load can have a
            # blank name, which would otherwise pollute name_history forever
            name_history=[pal.name] if pal.name else [],
            first_seen=now,
            last_seen=now,
            level=pal.level,
            building_count=pal.building_count,
        )
        # Two servers in the same guild are polled concurrently, so the row can be inserted by the
        # other one between the read above and this write. Fold that into an update instead of
        # raising a unique violation that would abandon the rest of this server's tick.
        await Player.insert(player).on_conflict(
            target=Player.lookup_key,
            action="DO UPDATE",
            values=[Player.name, Player.account_name, Player.level, Player.building_count, Player.last_seen],
        )
        return player
    if pal.name and pal.name != player.name:
        history: list = player.name_history or []
        if pal.name not in history:
            history.append(pal.name)
        player.name_history = history
    player.name = pal.name or player.name
    player.account_name = pal.account_name or player.account_name
    player.level = pal.level
    player.building_count = pal.building_count
    player.last_seen = now
    await player.save()
    return player


async def touch_players(guild_id: int, pals: list[PalPlayer], now: datetime) -> None:
    """Bulk last_seen bump for players whose persisted fields are unchanged since the last poll"""
    if not pals:
        return
    keys = [f"{guild_id}-{pal.user_id}" for pal in pals]
    await Player.update({Player.last_seen: now}).where(Player.lookup_key.is_in(keys))


async def upsert_player_ip(player: Player, ip: str, now: datetime) -> None:
    if not ip:
        return
    key = f"{player.id}-{ip}"
    row = PlayerIp(lookup_key=key, player=player.id, ip=ip, first_seen=now, last_seen=now)
    # Same concurrent-insert race as upsert_player, and there is nothing to merge here:
    # an existing row only ever needs its last_seen bumped
    await PlayerIp.insert(row).on_conflict(
        target=PlayerIp.lookup_key,
        action="DO UPDATE",
        values=[PlayerIp.last_seen],
    )


async def open_session(player: Player, server_id: int, now: datetime) -> None:
    existing = (
        await Session.objects()
        .where((Session.player == player.id) & (Session.server == server_id) & (Session.left_at.is_null()))
        .first()
    )
    if existing is None:
        await Session(player=player.id, server=server_id, joined_at=now).save()


async def close_session(player: Player, server_id: int, now: datetime) -> int:
    session = (
        await Session.objects()
        .where((Session.player == player.id) & (Session.server == server_id) & (Session.left_at.is_null()))
        .order_by(Session.joined_at, ascending=False)
        .first()
    )
    if session is None:
        return 0
    session.left_at = now
    await session.save()
    return int((now - session.joined_at).total_seconds())


# Player.last_seen is per guild, so on a cluster it keeps moving while one server is down. Bounding
# it by that server's own last_online stops a session inheriting playtime from a sibling server.
# LEAST/GREATEST skip nulls in Postgres, so a server that has never been online falls back cleanly.
SESSION_END = "GREATEST(LEAST(p.last_seen, sv.last_online), s.joined_at)"
CLOSE_OPEN_SESSIONS = (
    f"UPDATE session s SET left_at = {SESSION_END} FROM player p, server sv "
    "WHERE s.player = p.id AND s.server = sv.id AND s.left_at IS NULL"
)


async def close_open_sessions(server_id: int | None = None) -> int:
    """Stamp left_at on open sessions: all of them at startup (orphans from before the restart),
    or one server's when it goes unreachable, gets disabled, or is repointed at another box.

    Without this the sessions stay open and playtime keeps accruing through the whole outage.
    """
    if server_id is None:
        rows = await Session.raw(CLOSE_OPEN_SESSIONS + " RETURNING s.id")
    else:
        rows = await Session.raw(CLOSE_OPEN_SESSIONS + " AND s.server = {} RETURNING s.id", server_id)
    return len(rows)


async def player_count_series(guild_id: int, start: datetime, end: datetime, step: timedelta) -> list[dict]:
    """Player count per enabled server at fixed intervals, rebuilt from the session rows.

    Sessions already record every join and leave, so the panel graph needs no snapshot table:
    a player counts toward a bucket whenever their session spans it.
    """
    rows = await Session.raw(
        "SELECT b.bucket AS bucket, sv.name AS server_name, COUNT(s.id) AS players "
        # Casts are required: generate_series is overloaded and Postgres cannot pick one from
        # untyped parameters ("function generate_series(unknown, unknown, unknown) is not unique")
        "FROM generate_series({}::timestamptz, {}::timestamptz, {}::interval) AS b(bucket) "
        "CROSS JOIN server sv "
        "LEFT JOIN session s ON s.server = sv.id AND s.joined_at <= b.bucket "
        "AND (s.left_at IS NULL OR s.left_at >= b.bucket) "
        "WHERE sv.guild_id = {} AND sv.enabled = true "
        "GROUP BY b.bucket, sv.name ORDER BY b.bucket",
        start,
        end,
        step,
        guild_id,
    )
    return [{"bucket": r["bucket"], "server_name": r["server_name"], "players": int(r["players"])} for r in rows]


async def mark_servers_online(server_ids: list[int], now: datetime) -> None:
    if not server_ids:
        return
    await Server.update({Server.last_online: now}).where(Server.id.is_in(server_ids))


async def find_players(guild_id: int, query: str) -> list[Player]:
    # load_json on both, otherwise callers rendering name_history get the raw JSON text
    exact = (
        await Player.objects().output(load_json=True).where((Player.guild_id == guild_id) & (Player.user_id == query))
    )
    if exact:
        return exact
    pattern = f"%{escape_like(query)}%"
    return (
        await Player.objects()
        .output(load_json=True)
        .where((Player.guild_id == guild_id) & (Player.name.ilike(pattern) | Player.account_name.ilike(pattern)))
        .limit(10)
    )


async def player_playtime(player: Player) -> dict[str, float]:
    """Seconds played per server name. Callers sum the values for the total: a server can be named 'total'."""
    rows = await Session.raw(
        "SELECT sv.name AS server_name, "
        "SUM(EXTRACT(EPOCH FROM (COALESCE(s.left_at, NOW()) - s.joined_at))) AS seconds "
        "FROM session s JOIN server sv ON s.server = sv.id "
        "WHERE s.player = {} GROUP BY sv.name",
        player.id,
    )
    return {r["server_name"]: float(r["seconds"]) for r in rows}


async def top_playtime(guild_id: int, limit: int = 10) -> list[dict]:
    rows = await Session.raw(
        "SELECT p.name AS name, p.user_id AS user_id, "
        "SUM(EXTRACT(EPOCH FROM (COALESCE(s.left_at, NOW()) - s.joined_at))) AS seconds "
        "FROM session s JOIN player p ON s.player = p.id "
        "WHERE p.guild_id = {} GROUP BY p.id ORDER BY seconds DESC LIMIT {}",
        guild_id,
        limit,
    )
    return [{"name": r["name"], "user_id": r["user_id"], "seconds": float(r["seconds"])} for r in rows]


async def player_ips(player: Player) -> list[PlayerIp]:
    return await PlayerIp.objects().where(PlayerIp.player == player.id).order_by(PlayerIp.last_seen, ascending=False)


async def shared_ip_players(player: Player) -> list[str]:
    rows = await PlayerIp.raw(
        "SELECT DISTINCT p2.name FROM player_ip ip1 "
        "JOIN player_ip ip2 ON ip1.ip = ip2.ip AND ip2.player != ip1.player "
        "JOIN player p2 ON ip2.player = p2.id "
        "WHERE ip1.player = {} AND p2.guild_id = {}",
        player.id,
        player.guild_id,
    )
    return [r["name"] for r in rows]
