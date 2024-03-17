import logging
from enum import Enum
from typing import Any

import orjson
from pydantic import VERSION, BaseModel

log = logging.getLogger("vragepy")


class _Base(BaseModel):
    """Cross-version compatibility for BaseModel."""

    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs):
        for key in obj.keys():
            if key not in cls.__annotations__:
                log.warning(f"Unknown key {key} in payload for {cls.__name__}")
        if VERSION >= "2.0.1":
            return super().model_validate(obj, *args, **kwargs)
        return super().parse_obj(obj, *args, **kwargs)

    def model_dump(self, *args, **kwargs):
        if VERSION >= "2.0.1":
            return super().model_dump(*args, **kwargs)
        if kwargs.pop("mode", "") == "json":
            return orjson.loads(super().json(*args, **kwargs))
        return super().dict(*args, **kwargs)


class Metadata(_Base):
    apiVersion: str
    queryTime: float


# -/-/-/-/-/-/-/-/ OBJECTS -/-/-/-/-/-/-/-/
class Route(_Base):
    APIVersion: str  # 1.0
    AuthenticationRequired: bool
    Description: str
    HttpMethod: str  # GET
    Path: str  # /vrageremote/v1/...


class Player(_Base):
    SteamID: int
    DisplayName: str
    FactionName: str
    FactionTag: str
    PromoteLevel: int
    Ping: int

    @property
    def id(self) -> int:
        return self.SteamID

    def __hash__(self) -> int:
        return self.id

    def __eq__(self, __value: object) -> bool:
        return isinstance(__value, Player) and self.id == __value.id


class Cheater(_Base):
    Explanation: str
    Id: int
    Name: str
    PlayerId: int
    ServerDateTime: str  # 1.1.2022


class BannedKickedPlayer(_Base):
    SteamID: int
    DisplayName: str
    time: int | None = None  # If None, player was banned

    @property
    def is_ban(self) -> bool:
        return self.time is None


class Position(_Base):
    X: float
    Y: float
    Z: float


class Character(_Base):
    DisplayName: str
    EntityId: int
    Mass: float
    Position: Position
    LinearSpeed: float


class Asteroid(_Base):
    DisplayName: str | None
    EntityId: int
    Position: Position

    @property
    def pos(self) -> str:
        return f"{round(self.Position.X, 2)}, {round(self.Position.Y, 2)}, {round(self.Position.Z, 2)}"


class FloatingObject(_Base):
    DisplayName: str
    EntityId: int
    Kind: str  # FloatingObject
    Mass: float
    Position: Position
    LinearSpeed: float
    DistanceToPlayer: float

    @property
    def pos(self) -> str:
        return f"{round(self.Position.X, 2)}, {round(self.Position.Y, 2)}, {round(self.Position.Z, 2)}"


class GridSize(Enum):
    Small = "Small"
    Large = "Large"


class Grid(_Base):
    DisplayName: str
    EntityId: int
    GridSize: GridSize
    BlocksCount: int
    Mass: float
    Position: Position
    LinearSpeed: float
    DistanceToPlayer: float
    OwnerSteamId: int
    IsPowered: bool
    PCU: int

    @property
    def pos(self) -> str:
        return f"{round(self.Position.X, 2)}, {round(self.Position.Y, 2)}, {round(self.Position.Z, 2)}"


class Planet(_Base):
    DisplayName: str
    EntityId: int
    Position: Position

    @property
    def pos(self) -> str:
        return f"{round(self.Position.X, 2)}, {round(self.Position.Y, 2)}, {round(self.Position.Z, 2)}"


class Message(_Base):
    SteamID: int
    DisplayName: str
    Content: str
    Timestamp: str  # "638457069188026869"

    @property
    def ts(self) -> float:
        return int(self.Timestamp)

    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs):
        # Ensure payload doenst have any keys that the Message model doesnt have
        for key in obj.keys():
            if key not in cls.__annotations__:
                log.error(f"Unknown key {key} in payload for Message")

        return super().model_validate(obj, *args, **kwargs)


# -/-/-/-/-/-/-/-/ DATA-RESPONSES -/-/-/-/-/-/-/-/
class RoutesData(_Base):
    Routes: list[Route]


class GameData(_Base):
    Game: str
    IsReady: bool
    PirateUsedPCU: int
    Players: int
    ServerId: int
    ServerName: str
    SimSpeed: float
    SimulationCpuLoad: float
    TotalTime: int
    UsedPCU: int
    Version: str
    WorldName: str


class PingData(_Base):
    Result: str  # Pong


class PlayerData(_Base):
    Players: list[Player]


class CheatersData(_Base):
    Cheaters: list[Cheater]


class BannedPlayerData(_Base):
    BannedPlayers: list[BannedKickedPlayer]


class KickedPlayerData(_Base):
    KickedPlayers: list[BannedKickedPlayer]


class CharactersData(_Base):
    Characters: list[Character]


class AsteroidsData(_Base):
    Asteroids: list[Asteroid]


class FloatingObjectsData(_Base):
    FloatingObjects: list[FloatingObject]


class GridsData(_Base):
    Grids: list[Grid]


class PlanetsData(_Base):
    Planets: list[Planet]


class MessageData(_Base):
    Messages: list[Message]


class EconomyData(_Base):
    TotalCurrency: int
    CurrencyFaucet: int
    CurrencySink: int
    PerPlayerBalance: list
    PerFactionBalance: list


# -/-/-/-/-/-/-/-/ RESPONSES -/-/-/-/-/-/-/-/
class EndpointsResponse(_Base):
    data: RoutesData
    meta: Metadata


class GenericResponse(_Base):
    meta: Metadata


class ServerResponse(_Base):
    data: GameData
    meta: Metadata


class PingResponse(_Base):
    data: PingData
    meta: Metadata


class PlayersResponse(_Base):
    data: PlayerData
    meta: Metadata


class CheatersResponse(_Base):
    data: CheatersData
    meta: Metadata


class BannedPlayersResponse(_Base):
    data: BannedPlayerData
    meta: Metadata


class KickedPlayersResponse(_Base):
    data: KickedPlayerData
    meta: Metadata


class CharactersResponse(_Base):
    data: CharactersData
    meta: Metadata


class AsteroidsResponse(_Base):
    data: AsteroidsData
    meta: Metadata


class FloatingObjectsResponse(_Base):
    data: FloatingObjectsData
    meta: Metadata


class GridsResponse(_Base):
    data: GridsData
    meta: Metadata


class PlanetsResponse(_Base):
    data: PlanetsData
    meta: Metadata


class MessagesResponse(_Base):
    data: MessageData
    meta: Metadata


class EconomyResponse(_Base):
    data: EconomyData
    meta: Metadata
