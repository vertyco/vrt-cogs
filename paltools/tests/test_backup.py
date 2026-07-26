from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from paltools.common.backup import (
    BackupPlayer,
    BackupServer,
    BackupSettings,
    GuildBackup,
    chunked,
    decode,
    encode,
    settings_columns,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def make_backup(guild_id: int = 1) -> GuildBackup:
    return GuildBackup(
        guild_id=guild_id,
        created_at=NOW,
        settings=BackupSettings(log_channel_id=111, log_ips=True, status_channel_id=222, timezone="America/New_York"),
        servers=[BackupServer(id=5, name="PVE", host="1.2.3.4", port=8212, admin_password="hunter2")],
        players=[BackupPlayer(id=9, user_id="steam_1", name="Bob", first_seen=NOW, last_seen=NOW)],
    )


def test_chunked_splits_evenly_and_covers_remainder():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(chunked([], 2)) == []


def test_roundtrip_plain_json():
    payload, extension = encode(make_backup())
    assert extension == ".json"
    restored = decode(payload)
    assert restored.servers[0].admin_password == "hunter2"
    assert restored.players[0].first_seen == NOW


def test_roundtrip_gzipped():
    payload, extension = encode(make_backup(), compress_over=1)
    assert extension == ".json.gz"
    assert decode(payload).guild_id == 1


def test_decode_rejects_junk():
    with pytest.raises(ValidationError):
        decode(b'{"guild_id": "not an id"}')


def test_counts():
    assert make_backup().counts() == {"servers": 1, "players": 1, "IPs": 0, "sessions": 0}


def test_settings_kept_for_same_guild():
    values = settings_columns(make_backup(guild_id=1), 1)
    assert values == {
        "log_channel_id": 111,
        "log_ips": True,
        "status_channel_id": 222,
        "timezone": "America/New_York",
    }


def test_channels_dropped_for_a_different_guild():
    # The channel ids belong to the guild the dump came from; the toggle and the timezone do not
    values = settings_columns(make_backup(guild_id=1), 2)
    assert values == {
        "log_channel_id": None,
        "log_ips": True,
        "status_channel_id": None,
        "timezone": "America/New_York",
    }
