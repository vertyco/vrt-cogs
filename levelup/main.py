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
import json
import logging
import os
import sys
import tempfile
import typing as t
from collections import defaultdict
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import aiohttp
import discord
import orjson
from pydantic import ValidationError
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path, cog_data_path, core_data_path
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_list

from .abc import CompositeMetaClass
from .commands import Commands
from .commands.user import view_profile_context
from .common.models import DB, VoiceTracking, run_migrations
from .dashboard.integration import DashboardIntegration
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
    __version__ = "5.2.0"
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
        self.msg_cache: t.Dict[int, t.Dict[int, t.List[str]]] = {}  # GuildID: {UserID: [normalized messages]}
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
        self.tenor: t.Optional[TenorAPI] = None

        # Temp directory for subprocess communication
        self.temp_dir = Path(tempfile.gettempdir()) / "levelup"

        # Semaphore to limit concurrent image generation subprocesses
        # Prevents resource exhaustion during burst activity (e.g., raid level-ups)
        self._subprocess_semaphore = asyncio.Semaphore(os.cpu_count() or 4)

        # Managed API process
        self._managed_api_process: t.Optional[asyncio.subprocess.Process] = None
        self._managed_api_pid_file = self.temp_dir / "managed_api.pid"
        self._api_log_handle: t.Optional[t.IO[str]] = None

    async def cog_load(self) -> None:
        self.temp_dir.mkdir(exist_ok=True)
        self.bot.tree.add_command(view_profile_context)
        # Kill any orphaned managed API process from a previous crash
        await self._cleanup_orphaned_api()
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(view_profile_context)
        self.bot.remove_before_invoke_hook(self.level_check)
        self.bot.remove_before_invoke_hook(self.cooldown_check)
        self.stop_levelup_tasks()
        # Stop managed API process
        await self._stop_managed_api()

    async def run_profile_subprocess(
        self,
        request_data: dict,
    ) -> t.Tuple[t.Optional[Path], t.Optional[dict]]:
        """
        Run profile/levelup image generation in a subprocess.

        This isolates heavy PIL processing from the bot's event loop.

        Args:
            request_data: Dictionary with generation parameters (ProfileRequest or LevelUpRequest schema)

        Returns:
            Tuple of (output_path, result_dict) or (None, None) on error
        """
        request_id = str(uuid4())[:8]
        input_file = self.temp_dir / f"request_{request_id}.json"
        output_file = self.temp_dir / f"output_{request_id}.webp"

        # Add custom fonts directory to request so subprocess can find them
        request_data["custom_fonts_dir"] = str(self.custom_fonts)

        # Write input JSON
        await asyncio.to_thread(input_file.write_text, json.dumps(request_data), encoding="utf-8")

        try:
            # Limit concurrent subprocesses to prevent resource exhaustion
            async with self._subprocess_semaphore:
                # Run subprocess
                runner_path = Path(__file__).parent / "generator" / "profile_runner.py"
                cmd = [sys.executable, str(runner_path), str(input_file), str(output_file)]

                log.debug(f"Running profile subprocess: {' '.join(cmd)}")

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await proc.communicate()
            stderr_text = stderr.decode() if stderr else ""
            stdout_text = stdout.decode() if stdout else ""

            # Log any errors from subprocess
            if stderr_text and stderr_text.strip():
                log.warning(f"Profile subprocess stderr: {stderr_text.strip()}")

            if proc.returncode != 0:
                log.error(f"Profile subprocess exited with code {proc.returncode}")
                if stdout_text:
                    log.error(f"Stdout: {stdout_text}")
                return None, None

            # Parse result from stdout
            try:
                result = json.loads(stdout_text)
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse profile result JSON: {e}")
                log.error(f"Stdout was: {stdout_text[:500]}")
                return None, None

            if not result.get("success"):
                log.error(f"Profile generation failed: {result.get('error', 'Unknown error')}")
                return None, None

            # Get output path from result
            actual_output = Path(result.get("output_path", str(output_file)))

            if actual_output.exists():
                return actual_output, result
            elif output_file.exists():
                return output_file, result
            else:
                log.error(f"Profile output file not created at {output_file}")
                return None, None

        except Exception as e:
            log.exception(f"Failed to run profile subprocess: {e}")
            return None, None
        finally:
            # Clean up input file
            if input_file.exists():
                try:
                    input_file.unlink()
                except Exception:
                    pass

    async def _kill_process_tree(self, pid: int) -> None:
        """Kill a process and all its children using psutil (cross-platform)"""
        import psutil

        def _kill_tree():
            try:
                parent = psutil.Process(pid)
            except psutil.NoSuchProcess:
                return

            # Get all children recursively BEFORE killing anything
            children = parent.children(recursive=True)

            # Kill children first (deepest first by reversing)
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass

            # Now kill the parent
            try:
                parent.kill()
                parent.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                pass

        await asyncio.to_thread(_kill_tree)

    async def _cleanup_orphaned_api(self) -> None:
        """Kill any orphaned managed API process from a previous crash"""
        if not self._managed_api_pid_file.exists():
            return

        try:
            pid = int(self._managed_api_pid_file.read_text().strip())
            log.warning(f"Found orphaned managed API process (PID {pid}), cleaning up...")
            await self._kill_process_tree(pid)
            log.info(f"Orphaned API process tree {pid} cleaned up")
        except (ValueError, OSError, FileNotFoundError) as e:
            log.debug(f"Could not clean up orphaned API: {e}")
        finally:
            with suppress(FileNotFoundError):
                self._managed_api_pid_file.unlink()

    async def _start_managed_api(self) -> bool:
        """Start the managed local API process"""
        if self._managed_api_process is not None:
            return True  # Already running

        port = self.db.managed_api_port

        # Set up environment for the subprocess
        env = os.environ.copy()
        env["LEVELUP_CUSTOM_FONTS_DIR"] = str(self.custom_fonts)

        # Add the cog's parent directory to PYTHONPATH so uvicorn can import levelup
        cog_parent = str(Path(__file__).parent.parent)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{cog_parent}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else cog_parent

        # Create log file in Red's logs directory
        logs_dir = core_data_path() / "logs"
        logs_dir.mkdir(exist_ok=True)
        api_log_file = logs_dir / "levelup_api.log"
        num_workers = self.db.managed_api_workers or max(1, (os.cpu_count() or 4) // 2)

        try:
            log.info(f"Starting managed API on port {port} with {num_workers} workers...")
            log.info(f"API logs will be written to: {api_log_file}")

            # Open log file for subprocess output
            self._api_log_handle = open(api_log_file, "a", encoding="utf-8")

            # On Unix, start in new process group so we can kill all workers together
            kwargs: dict = {
                "stdout": self._api_log_handle,
                "stderr": self._api_log_handle,
                "env": env,
            }
            if not IS_WINDOWS:
                kwargs["start_new_session"] = True

            self._managed_api_process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "uvicorn",
                "levelup.generator.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--workers",
                str(num_workers),
                "--log-level",
                "info",
                **kwargs,
            )

            # Write PID file for orphan detection
            self._managed_api_pid_file.write_text(str(self._managed_api_process.pid))

            # Wait for API to become ready by polling the health endpoint
            api_url = f"http://127.0.0.1:{port}"
            max_attempts = 30  # 30 seconds max wait
            for attempt in range(max_attempts):
                # Check if process died
                if self._managed_api_process.returncode is not None:
                    log.error(f"Managed API process died. Check {api_log_file} for details")
                    self._managed_api_process = None
                    self._close_api_log()
                    return False

                # Try to connect to health endpoint
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{api_url}/health", timeout=aiohttp.ClientTimeout(total=1)) as resp:
                            if resp.status == 200:
                                log.info(
                                    f"Managed API ready after {attempt + 1}s (PID {self._managed_api_process.pid})"
                                )
                                return True
                except (aiohttp.ClientError, asyncio.TimeoutError):
                    pass  # Not ready yet

                await asyncio.sleep(1)

            # Timed out waiting for API
            log.error(f"Managed API failed to become ready after {max_attempts}s. Check {api_log_file}")
            await self._stop_managed_api()
            return False

        except Exception as e:
            log.exception(f"Failed to start managed API: {e}")
            self._managed_api_process = None
            self._close_api_log()
            return False

    def _close_api_log(self) -> None:
        """Close the API log file handle if open"""
        if hasattr(self, "_api_log_handle") and self._api_log_handle:
            try:
                self._api_log_handle.close()
            except Exception:
                pass
            self._api_log_handle = None

    async def _stop_managed_api(self) -> None:
        """Stop the managed local API process gracefully"""
        if self._managed_api_process is None:
            # Clean up PID file anyway in case of inconsistent state
            with suppress(FileNotFoundError):
                self._managed_api_pid_file.unlink()
            self._close_api_log()
            return

        pid = self._managed_api_process.pid
        log.info(f"Stopping managed API (PID {pid})...")

        try:
            await self._kill_process_tree(pid)
            # Also wait on our process handle to clean up
            try:
                await asyncio.wait_for(self._managed_api_process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._managed_api_process.kill()
                await self._managed_api_process.wait()
            log.info("Managed API stopped")

        except Exception as e:
            log.error(f"Error stopping managed API: {e}")
        finally:
            self._managed_api_process = None
            self._close_api_log()
            with suppress(FileNotFoundError):
                self._managed_api_pid_file.unlink()

    def get_api_url(self) -> t.Optional[str]:
        """Get the active API URL (external, managed local, or None for subprocess)"""
        # External API takes priority
        if self.db.external_api_url:
            return self.db.external_api_url
        # Managed local API - check process is not None AND still running (returncode is None while alive)
        if (
            self.db.managed_api
            and self._managed_api_process is not None
            and self._managed_api_process.returncode is None
        ):
            return f"http://127.0.0.1:{self.db.managed_api_port}"
        # Fall back to subprocess (return None)
        return None

    def save(self, force: bool = True) -> None:
        async def _save():
            if self.io_lock.locked():
                # Already saving, skip this
                return
            if not force and perf_counter() - self.last_save < 30:
                # Do not save more than once every 30 seconds if not forced
                return
            if not self.initialized:
                # Do not save if not initialized, we don't want to overwrite the config with default data
                return
            try:
                log.debug("Saving config")
                async with self.io_lock:
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

        # add checks
        self.bot.before_invoke(self.level_check)
        self.bot.before_invoke(self.cooldown_check)

        self.start_levelup_tasks()
        self.custom_fonts.mkdir(exist_ok=True)
        self.custom_backgrounds.mkdir(exist_ok=True)
        logging.getLogger("PIL").setLevel(logging.WARNING)
        await self.load_tenor()

        # Start managed API if enabled
        if self.db.managed_api:
            await self._start_managed_api()

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
