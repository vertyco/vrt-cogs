from abc import ABC, ABCMeta

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core import Config
from redbot.core.bot import Red

from .bundled.scores import ScoreBoard
from .common.games import GameRegistry
from .common.server import HubServer
from .common.sessions import LaunchMemory, SessionStore


class CompositeMetaClass(CogMeta, ABCMeta):
    """Metaclass for combining Cog and ABC functionality"""


class MixinMeta(ABC):
    """Type hinting mixin for all command classes"""

    def __init__(self, *args):
        self.bot: Red
        self.config: Config
        self.registry: GameRegistry
        self.sessions: SessionStore
        self.launches: LaunchMemory
        self.scores: ScoreBoard
        self.server: HubServer
        self.open_view: discord.ui.View

    async def start_server(self) -> None:
        raise NotImplementedError

    async def launch(self, interaction: discord.Interaction, key: str | None = None) -> None:
        raise NotImplementedError
