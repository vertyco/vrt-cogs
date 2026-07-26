"""Guild-scoped backup and restore.

Serial primary keys are per-database, so the dump carries its own ids purely as join keys
between its own lists and restore remaps every one of them as it inserts. That is what lets a
backup taken on a test bot's database land on the live one, or on a different guild entirely.
"""

import gzip
import json
import typing as t
from datetime import datetime, timezone

from pydantic import BaseModel

from ..db.tables import GuildSettings, Player, PlayerIp, Server, Session
from ..db.utils import get_create_guild_settings

BACKUP_VERSION = 1
# Postgres caps a statement at 65535 parameters, and the widest row here is 10 columns
CHUNK = 500
GZIP_MAGIC = b"\x1f\x8b"


class BackupServer(BaseModel):
    id: int
    name: str
    host: str
    port: int
    admin_password: str
    enabled: bool = True
    last_online: datetime | None = None


class BackupPlayer(BaseModel):
    id: int
    user_id: str
    name: str = ""
    account_name: str = ""
    name_history: list[str] = []
    first_seen: datetime
    last_seen: datetime
    level: int = 0
    building_count: int = 0


class BackupPlayerIp(BaseModel):
    player_id: int
    ip: str
    first_seen: datetime
    last_seen: datetime


class BackupSession(BaseModel):
    player_id: int
    server_id: int
    joined_at: datetime
    left_at: datetime | None = None


class BackupSettings(BaseModel):
    # status_message_id is deliberately absent: the panel is a message owned by the bot that
    # posted it, and a restored id would point the poll loop at one it is not allowed to edit
    log_channel_id: int | None = None
    log_ips: bool = False
    status_channel_id: int | None = None
    timezone: str = "UTC"


class GuildBackup(BaseModel):
    version: int = BACKUP_VERSION
    guild_id: int
    created_at: datetime
    settings: BackupSettings = BackupSettings()
    servers: list[BackupServer] = []
    players: list[BackupPlayer] = []
    player_ips: list[BackupPlayerIp] = []
    sessions: list[BackupSession] = []

    def counts(self) -> dict[str, int]:
        return {
            "servers": len(self.servers),
            "players": len(self.players),
            "IPs": len(self.player_ips),
            "sessions": len(self.sessions),
        }


def chunked(rows: list, size: int = CHUNK) -> t.Iterator[list]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def encode(backup: GuildBackup, compress_over: int = 4_000_000) -> tuple[bytes, str]:
    """Serialized backup plus the extension it should carry.

    Small dumps stay readable JSON; a fleet with months of sessions would otherwise blow past
    Discord's upload limit, so those are gzipped.
    """
    payload = backup.model_dump_json(indent=2).encode()
    if len(payload) > compress_over:
        return gzip.compress(payload), ".json.gz"
    return payload, ".json"


def decode(raw: bytes) -> GuildBackup:
    """Parse either form. Sniffed by magic number rather than filename: Discord attachments are
    routinely renamed, and a mislabelled file should still restore."""
    if raw[:2] == GZIP_MAGIC:
        raw = gzip.decompress(raw)
    return GuildBackup.model_validate(json.loads(raw))


async def dump_guild(guild_id: int) -> GuildBackup:
    settings = await get_create_guild_settings(guild_id)
    # load_json, otherwise name_history is dumped as its raw JSON text and comes back a string
    players = await Player.objects().output(load_json=True).where(Player.guild_id == guild_id)
    servers = await Server.objects().where(Server.guild_id == guild_id)
    # Joined in SQL rather than filtered by an id list: a busy guild has thousands of players,
    # and is_in would push all of them through as query parameters
    ip_rows = await PlayerIp.raw(
        "SELECT ip.player AS player_id, ip.ip AS ip, ip.first_seen AS first_seen, ip.last_seen AS last_seen "
        "FROM player_ip ip JOIN player p ON ip.player = p.id WHERE p.guild_id = {}",
        guild_id,
    )
    session_rows = await Session.raw(
        "SELECT s.player AS player_id, s.server AS server_id, s.joined_at AS joined_at, s.left_at AS left_at "
        "FROM session s JOIN player p ON s.player = p.id WHERE p.guild_id = {}",
        guild_id,
    )
    return GuildBackup(
        guild_id=guild_id,
        created_at=datetime.now(timezone.utc),
        settings=BackupSettings(
            log_channel_id=settings.log_channel_id,
            log_ips=settings.log_ips,
            status_channel_id=settings.status_channel_id,
            timezone=settings.timezone or "UTC",
        ),
        servers=[
            BackupServer(
                id=s.id,
                name=s.name,
                host=s.host,
                port=s.port,
                admin_password=s.admin_password,
                enabled=s.enabled,
                last_online=s.last_online,
            )
            for s in servers
        ],
        players=[
            BackupPlayer(
                id=p.id,
                user_id=p.user_id,
                name=p.name,
                account_name=p.account_name,
                # Guarded rather than trusted: without load_json above this arrives as raw JSON
                # text, and a str would be dumped as a list of single characters
                name_history=p.name_history if isinstance(p.name_history, list) else [],
                first_seen=p.first_seen,
                last_seen=p.last_seen,
                level=p.level,
                building_count=p.building_count,
            )
            for p in players
        ],
        player_ips=[BackupPlayerIp(**row) for row in ip_rows],
        sessions=[BackupSession(**row) for row in session_rows],
    )


async def wipe_guild(guild_id: int) -> None:
    """Drop every row belonging to a guild, children first.

    Raw joins rather than is_in over collected ids: the id lists run to thousands of rows on a
    real fleet, which is both a parameter blowup and a second round trip per table.
    """
    await Session.raw("DELETE FROM session s USING player p WHERE s.player = p.id AND p.guild_id = {}", guild_id)
    # Sessions are reachable from either parent, and a server row whose players were never
    # recorded under this guild would otherwise strand its sessions behind the Server delete
    await Session.raw("DELETE FROM session s USING server sv WHERE s.server = sv.id AND sv.guild_id = {}", guild_id)
    await PlayerIp.raw("DELETE FROM player_ip ip USING player p WHERE ip.player = p.id AND p.guild_id = {}", guild_id)
    await Player.delete().where(Player.guild_id == guild_id)
    await Server.delete().where(Server.guild_id == guild_id)


async def insert_servers(servers: list[BackupServer], guild_id: int) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for batch in chunked(servers):
        rows = [
            Server(
                guild_id=guild_id,
                name=s.name,
                host=s.host,
                port=s.port,
                admin_password=s.admin_password,
                enabled=s.enabled,
                last_online=s.last_online,
            )
            for s in batch
        ]
        # insert() writes the new primary keys back onto the instances it was handed, so the
        # old-to-new mapping comes straight off the rows rather than the RETURNING payload
        await Server.insert(*rows)
        mapping.update({old.id: new.id for old, new in zip(batch, rows, strict=True)})
    return mapping


async def insert_players(players: list[BackupPlayer], guild_id: int) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for batch in chunked(players):
        rows = [
            Player(
                # Rebuilt from the target guild, not carried over: the key is what upsert_player
                # looks players up by, and a stale guild id in it would fork every player row
                lookup_key=f"{guild_id}-{p.user_id}",
                guild_id=guild_id,
                user_id=p.user_id,
                name=p.name,
                account_name=p.account_name,
                name_history=p.name_history,
                first_seen=p.first_seen,
                last_seen=p.last_seen,
                level=p.level,
                building_count=p.building_count,
            )
            for p in batch
        ]
        await Player.insert(*rows)
        mapping.update({old.id: new.id for old, new in zip(batch, rows, strict=True)})
    return mapping


async def insert_player_ips(ips: list[BackupPlayerIp], player_map: dict[int, int]) -> int:
    rows = [
        PlayerIp(
            lookup_key=f"{player_map[ip.player_id]}-{ip.ip}",
            player=player_map[ip.player_id],
            ip=ip.ip,
            first_seen=ip.first_seen,
            last_seen=ip.last_seen,
        )
        for ip in ips
        if ip.player_id in player_map
    ]
    for batch in chunked(rows):
        await PlayerIp.insert(*batch)
    return len(rows)


async def insert_sessions(sessions: list[BackupSession], player_map: dict[int, int], server_map: dict[int, int]) -> int:
    # Both parents must have made it in: a hand-edited or truncated dump would otherwise raise a
    # foreign key violation halfway through and roll the whole restore back
    rows = [
        Session(
            player=player_map[s.player_id],
            server=server_map[s.server_id],
            joined_at=s.joined_at,
            left_at=s.left_at,
        )
        for s in sessions
        if s.player_id in player_map and s.server_id in server_map
    ]
    for batch in chunked(rows):
        await Session.insert(*batch)
    return len(rows)


def settings_columns(backup: GuildBackup, guild_id: int) -> dict[str, t.Any]:
    """Which settings survive a restore.

    Channel ids only mean anything in the guild they came from, so restoring a dump taken
    elsewhere keeps the toggles and drops the channels rather than pointing the poll loop and
    the log embeds at ids belonging to another server.
    """
    # The timezone travels either way: it describes the people reading the panel, not the
    # channels it is posted in, so it stays valid wherever the dump lands
    if backup.guild_id != guild_id:
        return {
            "log_channel_id": None,
            "log_ips": backup.settings.log_ips,
            "status_channel_id": None,
            "timezone": backup.settings.timezone,
        }
    return {
        "log_channel_id": backup.settings.log_channel_id,
        "log_ips": backup.settings.log_ips,
        "status_channel_id": backup.settings.status_channel_id,
        "timezone": backup.settings.timezone,
    }


async def restore_settings(backup: GuildBackup, guild_id: int) -> None:
    settings = await get_create_guild_settings(guild_id)
    values = settings_columns(backup, guild_id)
    columns = [
        GuildSettings.log_channel_id,
        GuildSettings.log_ips,
        GuildSettings.status_channel_id,
        GuildSettings.timezone,
    ]
    # Compared before the mutation below, otherwise it is always reading back what was just set
    panel_moved = values["status_channel_id"] != settings.status_channel_id
    for name, value in values.items():
        setattr(settings, name, value)
    if panel_moved:
        # The stored id refers to a panel in the channel this restore just walked away from
        settings.status_message_id = None
        columns.append(GuildSettings.status_message_id)
    await settings.save(columns=columns)


async def restore_guild(backup: GuildBackup, guild_id: int) -> dict[str, int]:
    """Replace a guild's data with a backup's, in one transaction.

    All or nothing on purpose: a failure partway through an incremental restore would leave the
    guild wiped, and the only copy of what was there is the file being restored.
    """
    async with Server._meta.db.transaction():
        await wipe_guild(guild_id)
        server_map = await insert_servers(backup.servers, guild_id)
        player_map = await insert_players(backup.players, guild_id)
        ips = await insert_player_ips(backup.player_ips, player_map)
        sessions = await insert_sessions(backup.sessions, player_map, server_map)
        await restore_settings(backup, guild_id)
    return {"servers": len(server_map), "players": len(player_map), "IPs": ips, "sessions": sessions}
