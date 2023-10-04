from abc import ABC, ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor

from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red
from redbot.core.config import Config


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    bot: Red
    config: Config
    executor: ThreadPoolExecutor

    # Cog cache
    data: dict
    cache_seconds: int
    render_gifs: bool
    bgdata: dict
    fdata: dict
    stars: dict
    profiles: dict

    @abstractmethod
    def generate_profile(
        self,
        bg_image: str = None,
        profile_image: str = "https://i.imgur.com/sUYWCve.png",
        level: int = 1,
        user_xp: int = 0,
        next_xp: int = 100,
        user_position: str = "1",
        user_name: str = "Unknown#0117",
        user_status: str = "online",
        colors: dict = None,
        messages: str = "0",
        voice: str = "None",
        prestige: int = 0,
        emoji: str = None,
        stars: str = "0",
        balance: int = 0,
        currency: str = "credits",
        role_icon: str = None,
        font_name: str = None,
        render_gifs: bool = False,
        blur: bool = False,
    ):
        raise NotImplementedError

    @abstractmethod
    def generate_slim_profile(
        self,
        bg_image: str = None,
        profile_image: str = "https://i.imgur.com/sUYWCve.png",
        level: int = 1,
        user_xp: int = 0,
        next_xp: int = 100,
        user_position: str = "1",
        user_name: str = "Unknown#0117",
        user_status: str = "online",
        colors: dict = None,
        messages: str = "0",
        voice: str = "None",
        prestige: int = 0,
        emoji: str = None,
        stars: str = "0",
        balance: int = 0,
        currency: str = "credits",
        role_icon: str = None,
        font_name: str = None,
        render_gifs: bool = False,
        blur: bool = False,
    ):
        raise NotImplementedError

    @abstractmethod
    def generate_levelup(
        self,
        bg_image: str = None,
        profile_image: str = None,
        level: int = 1,
        color: tuple = (0, 0, 0),
        font_name: str = None,
    ):
        raise NotImplementedError

    @abstractmethod
    def get_all_fonts(self):
        raise NotImplementedError

    @abstractmethod
    def get_all_backgrounds(self):
        raise NotImplementedError
