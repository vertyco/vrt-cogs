"""MIT License

Copyright (c) 2021-present vertyco

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

import asyncio
import logging
import multiprocessing as mp
import sys
import typing as t
from collections import defaultdict
from contextlib import suppress
from datetime import datetime
from time import perf_counter

import discord
import orjson
import psutil
from pydantic import ValidationError
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path, cog_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_list

from .abc import CompositeMetaClass
from .commands import Commands
from .commands.user import view_profile_context
from .common.models import DB, VoiceTracking, run_migrations
from .dashboard.integration import DashboardIntegration
from .generator import api
from .generator.tenor.converter import TenorAPI
from .listeners import Listeners
from .shared import SharedFunctions
from .tasks import Tasks

log = logging.getLogger("red.vrt.levelup")
_ = Translator("LevelUp", __file__)
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]
IS_WINDOWS: bool = sys.platform.startswith("win")

# Generate translations
# redgettext -D -r levelup/ --command-docstring


@cog_i18n(_)
class LevelUp(
    Commands,
    SharedFunctions,
    DashboardIntegration,
    Listeners,
    Tasks,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """
    Your friendly neighborhood leveling system

    Earn experience by chatting in text and voice channels, compare levels with your friends, customize your profile and view various leaderboards!
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "4.3.19"
    __contributors__ = [
        "[aikaterna](https://github.com/aikaterna/aikaterna-cogs)",
        "[AAA3A](https://github.com/AAA3A-AAA3A/AAA3A-cogs)",
    ]

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot: Red = bot

        # Cache
        self.db: DB = DB()
        self.lastmsg: t.Dict[int, t.Dict[int, float]] = {}  # GuildID: {UserID: LastMessageTime}
        self.profile_cache: t.Dict[int, t.Dict[int, t.Tuple[str, bytes]]] = {}  # GuildID: {UserID: (last_used, bytes)}
        self.stars: t.Dict[int, t.Dict[int, datetime]] = {}  # Guild_ID: {User_ID: {User_ID: datetime}}

        # {guild_id: {member_id: tracking_data}}
        self.voice_tracking: t.Dict[int, t.Dict[int, VoiceTracking]] = defaultdict(dict)

        # Root Paths
        self.cog_path = cog_data_path(self)
        self.bundled_path = bundled_data_path(self)
        # Settings Files
        self.settings_file = self.cog_path / "LevelUp.json"
        self.old_settings_file = self.cog_path / "settings.json"
        # Custom Paths
        self.custom_fonts = self.cog_path / "fonts"
        self.custom_backgrounds = self.cog_path / "backgrounds"
        # Bundled Paths
        self.stock = self.bundled_path / "stock"
        self.fonts = self.bundled_path / "fonts"
        self.backgrounds = self.bundled_path / "backgrounds"

        # Save State
        self.io_lock = asyncio.Lock()
        self.last_save: float = perf_counter()
        self.initialized: bool = False

        # Tenor API
        self.tenor: TenorAPI = None

        # Internal Profile Generator API
        self.api_proc: t.Union[asyncio.subprocess.Process, mp.Process, None] = None

    async def cog_load(self) -> None:
        if hasattr(self.bot, "_levelup_internal_api"):
            self.api_proc = self.bot._levelup_internal_api
        else:
            self.bot._levelup_internal_api = None
        self.bot.tree.add_command(view_profile_context)
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(view_profile_context)
        self.stop_levelup_tasks()

    async def start_api(self) -> bool:
        if not self.db.internal_api_port:
            return False
        if self.api_proc is not None:
            return False
        try:
            log_dir = self.cog_path / "APILogs"
            log_dir.mkdir(exist_ok=True, parents=True)
            proc = await api.run(port=self.db.internal_api_port, log_dir=log_dir)
            self.api_proc = proc
            self.bot._levelup_internal_api = proc
            log.debug(f"API Process started: {proc.pid}")
            return True
        except Exception as e:
            if "Port already in use" in str(e):
                log.error(
                    "Port already in use, Internal API cannot be started, either change the port or restart the bot instance."
                )
            else:
                log.error("Failed to start internal API", exc_info=e)
            return False

    async def stop_api(self) -> bool:
        proc: t.Union[asyncio.subprocess.Process, mp.Process, None] = self.api_proc
        self.api_proc = None
        self.bot._levelup_internal_api = None
        if proc is None:
            return False
        try:
            parent = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            return False
        for child in parent.children(recursive=True):
            log.info(f"Killing child process: {child.pid}")
            child.kill()
        proc.terminate()
        log.info(f"Terminated process: {proc.pid}, API is now stopped")
        return True

    def save(self) -> None:
        async def _save():
            if self.io_lock.locked():
                # Already saving, skip this
                return
            if perf_counter() - self.last_save < 2:
                # Do not save more than once every 2 seconds
                return
            if not self.initialized:
                # Do not save if not initialized, we don't want to overwrite the config with default data
                return
            try:
                log.debug("Saving config")
                async with self.io_lock:
                    self.db.to_file(self.settings_file)
                    await asyncio.to_thread(self.db.to_file, self.settings_file)
                log.debug("Config saved")
            except Exception as e:
                log.error("Failed to save config", exc_info=e)
            finally:
                self.last_save = perf_counter()

        asyncio.create_task(_save())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        if not hasattr(self, "__author__"):
            return
        migrated = False
        if self.settings_file.exists():
            log.info("Loading config")
            try:
                self.db = await asyncio.to_thread(DB.from_file, self.settings_file)
            except Exception as e:
                log.error("Failed to load config!", exc_info=e)
                return
        elif self.old_settings_file.exists():
            raw_settings = self.old_settings_file.read_text()
            settings = orjson.loads(raw_settings)
            if settings:
                log.warning("Migrating old settings.json")
                try:
                    self.db = await asyncio.to_thread(run_migrations, settings)
                    log.warning("Migration complete!")
                    migrated = True
                    with suppress(discord.HTTPException):
                        await self.bot.send_to_owners(
                            _(
                                "LevelUp has successfully migrated to v4!\n"
                                "Leveling is now disabled by default and must be toggled on in each server via `[p]lset toggle`.\n"
                                "[View the changelog](https://github.com/vertyco/vrt-cogs/blob/main/levelup/CHANGELOG.md) for more information."
                            )
                        )
                except ValidationError as e:
                    log.error("Failed to migrate old settings.json", exc_info=e)
                    with suppress(discord.HTTPException):
                        await self.bot.send_to_owners(
                            _("LevelUp has failed to migrate to v4!\nSend this to vertyco:\n{}").format(box(str(e)))
                        )
                    return
                except Exception as e:
                    log.error("Failed to migrate old settings.json", exc_info=e)
                    return

        log.info("Config initialized")
        self.initialized = True

        if migrated:
            self.save()

        if voice_initialized := await self.initialize_voice_states():
            log.info(f"Initialized {voice_initialized} voice states")

        self.start_levelup_tasks()
        self.custom_fonts.mkdir(exist_ok=True)
        self.custom_backgrounds.mkdir(exist_ok=True)
        logging.getLogger("PIL").setLevel(logging.WARNING)
        await self.load_tenor()
        if self.db.internal_api_port and not self.db.external_api_url:
            await self.start_api()

    async def load_tenor(self) -> None:
        tokens = await self.bot.get_shared_api_tokens("tenor")
        if "api_key" in tokens:
            log.debug("Tenor API key loaded")
            self.tenor = TenorAPI(tokens["api_key"], str(self.bot.user))

    async def on_red_api_tokens_update(self, service_name: str, api_tokens: t.Dict[str, str]) -> None:
        if service_name != "tenor":
            return
        if "api_key" in api_tokens:
            if self.tenor is not None:
                self.tenor._token = api_tokens["api_key"]
                return
            log.debug("Tenor API key updated")
            self.tenor = TenorAPI(api_tokens["api_key"], str(self.bot.user))

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = (
            f"{helpcmd}\n"
            f"Cog Version: {self.__version__}\n"
            f"Author: {self.__author__}\n"
            f"Contributors: {humanize_list(self.__contributors__)}\n"
        )
        return info

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        return

    async def red_get_data_for_user(self, *, user_id: int):
        return
