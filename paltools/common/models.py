from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class PalResponse(BaseModel):
    """Base for everything parsed off the wire.

    The server sends null for fields it has not filled in yet, and pydantic rejects the whole
    payload over a single one. That would mark an otherwise healthy server offline and close
    every open session on it, so nulls fall back to the field default instead.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @field_validator("*", mode="before")
    @classmethod
    def null_to_default(cls, value: object, info: ValidationInfo) -> object:
        if value is None and info.field_name in cls.model_fields:
            return cls.model_fields[info.field_name].get_default(call_default_factory=True)
        return value


class PalPlayer(PalResponse):
    name: str = ""
    account_name: str = Field(default="", alias="accountName")
    player_id: str = Field(default="", alias="playerId")
    user_id: str = Field(default="", alias="userId")
    ip: str = Field(default="", alias="iP")
    ping: float = 0.0
    location_x: float = 0.0
    location_y: float = 0.0
    level: int = 0
    building_count: int = 0

    @property
    def is_placeholder(self) -> bool:
        # Mid-login players show an all-zero (or empty) playerId and must be ignored by the poll diff.
        # An empty userId is just as unusable: it is the player's database key, and a blank one would
        # collapse every such player onto a single row.
        return not self.player_id.strip("0") or not self.user_id.strip()


class PlayersResponse(PalResponse):
    players: list[PalPlayer] = []


class ServerInfo(PalResponse):
    version: str = ""
    servername: str = ""
    description: str = ""


class ServerMetrics(PalResponse):
    serverfps: int = 0
    currentplayernum: int = 0
    serverframetime: float = 0.0
    maxplayernum: int = 0
    uptime: int = 0


class ServerStatus(BaseModel):
    """What one poll tick learned about a server, handed to the live status panel"""

    name: str
    online: bool
    players: list[PalPlayer] = []
    max_players: int = 0
    last_online: datetime | None = None
