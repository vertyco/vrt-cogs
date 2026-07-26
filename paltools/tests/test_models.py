from paltools.common.models import PalPlayer, PlayersResponse, ServerInfo, ServerMetrics

PLAYER_RAW = {
    "name": "викинг",
    "accountName": "viking99",
    "playerId": "A1B2C3D4E5F60718293A4B5C6D7E8F90",
    "userId": "steam_76561198000000001",
    "iP": "10.0.0.5",
    "ping": 43.2,
    "location_x": -123456.7,
    "location_y": 98765.4,
    "level": 42,
    "building_count": 128,
    "some_future_field": "ignored",
}

# Real payload shape verified live against a PalWorld 1.0.1 server /players endpoint:
# capital "iP", float ping, no building_count field at all.
REAL_PLAYER_RAW = {
    "name": "виkinger",
    "accountName": "viking99",
    "playerId": "A1B2C3D4E5F60718293A4B5C6D7E8F90",
    "userId": "steam_76561198000000001",
    "iP": "10.0.0.5",
    "ping": 61.0357,
    "location_x": -123456.7,
    "location_y": 98765.4,
    "level": 42,
}


def test_player_parses_aliases_and_ignores_extras():
    p = PalPlayer.model_validate(PLAYER_RAW)
    assert p.account_name == "viking99"
    assert p.player_id == "A1B2C3D4E5F60718293A4B5C6D7E8F90"
    assert p.user_id == "steam_76561198000000001"
    assert p.ip == "10.0.0.5"
    assert p.level == 42
    assert p.is_placeholder is False


def test_placeholder_player_detected():
    raw = dict(PLAYER_RAW, playerId="00000000000000000000000000000000", level=0)
    assert PalPlayer.model_validate(raw).is_placeholder is True
    raw = dict(PLAYER_RAW, playerId="")
    assert PalPlayer.model_validate(raw).is_placeholder is True


def test_blank_user_id_is_placeholder():
    # userId is the player's database key: a blank one would merge every such player onto one row
    raw = dict(PLAYER_RAW, userId="")
    assert PalPlayer.model_validate(raw).is_placeholder is True
    raw = dict(PLAYER_RAW)
    del raw["userId"]
    assert PalPlayer.model_validate(raw).is_placeholder is True


def test_players_response_wrapper():
    res = PlayersResponse.model_validate({"players": [PLAYER_RAW]})
    assert len(res.players) == 1


def test_missing_optional_fields_default():
    p = PalPlayer.model_validate({"name": "x", "playerId": "ABC", "userId": "steam_1"})
    assert p.ip == ""
    assert p.ping == 0.0
    assert p.building_count == 0


def test_real_players_payload_shape():
    # Locks in the capital-P "iP" alias, float ping, and missing building_count
    # against the real live /players response shape.
    p = PalPlayer.model_validate(REAL_PLAYER_RAW)
    assert p.ip == "10.0.0.5"
    assert isinstance(p.ping, float)
    assert p.ping == 61.0357
    assert p.building_count == 0
    assert p.is_placeholder is False


def test_info_and_metrics():
    info = ServerInfo.model_validate({"version": "v0.3.1.0", "servername": "Test", "description": "d", "extra": 1})
    assert info.servername == "Test"
    m = ServerMetrics.model_validate(
        {"serverfps": 58, "currentplayernum": 3, "serverframetime": 16.9, "maxplayernum": 32, "uptime": 86400}
    )
    assert m.maxplayernum == 32
