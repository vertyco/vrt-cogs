"""
Bot Arena 3 - A Discord cog recreation of the classic robot combat game.

Build custom battle bots from modular parts and fight other players!
"""

import asyncio
import json
import logging
import sys
import tempfile
import typing as t
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.data_manager import cog_data_path

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB, Bot, PartsRegistry
from .common.telemetry import BattleTelemetry
from .constants import CHASSIS, COMPONENTS, PLATING

log = logging.getLogger("red.vrt.botarena")

__author__ = "Vertyco"
__version__ = "1.3.1a"


class BotArena(Commands, commands.Cog, metaclass=CompositeMetaClass):
    """
    Bot Arena - Build and Battle Robots!

    Create custom battle bots from chassis, plating, and weapons,
    then fight against other players in arena combat.
    """

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot

        # Database
        self.db: DB = DB()
        self.data_path: Path = cog_data_path(self)
        self.db_path: Path = self.data_path / "data.json"
        self.io_lock: asyncio.Lock = asyncio.Lock()
        self.last_save: float = 0.0
        self.initialized: bool = False
        self._pending_save_tasks: set[asyncio.Task] = set()  # Strong references to save tasks

        # Telemetry
        self.telemetry: BattleTelemetry = BattleTelemetry(self.data_path)

        # Parts registry
        self.registry: PartsRegistry = PartsRegistry()
        self._register_parts()

    def _register_parts(self):
        """Register all parts from constants"""
        for chassis in CHASSIS:
            self.registry.register_chassis(chassis)

        for plating in PLATING:
            self.registry.register_plating(plating)

        for component in COMPONENTS:
            self.registry.register_component(component)

        log.debug(f"Registered {len(CHASSIS)} chassis, {len(PLATING)} plating, {len(COMPONENTS)} components")

    async def cog_load(self):
        """Called when the cog is loaded"""
        asyncio.create_task(self.initialize())

    async def cog_unload(self):
        """Called when the cog is unloaded"""
        # Wait for any pending save tasks to complete before unloading
        if self._pending_save_tasks:
            log.info(f"Waiting for {len(self._pending_save_tasks)} pending save task(s) to complete...")
            await asyncio.gather(*self._pending_save_tasks, return_exceptions=True)
        # Final save before unload
        self.save(force=True)

    async def initialize(self):
        """Initialize the cog - load data"""
        await self.bot.wait_until_red_ready()
        if self.db_path.exists():
            log.info("Loading config")
            try:
                self.db = await asyncio.to_thread(DB.from_file, self.db_path)
                log.info(f"Loaded data for {len(self.db.players)} players")
            except Exception as e:
                log.error("Failed to load config!", exc_info=e)
                return
        else:
            log.info("No existing data found, starting fresh")

        self.initialized = True
        log.info("BotArena initialized")

    def save(self, force: bool = True) -> None:
        """Queue a save operation to disk (fire-and-forget)"""

        async def _save():
            try:
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
                        await asyncio.to_thread(self.db.to_file, self.db_path, True)
                    log.info("Config saved successfully")
                except Exception as e:
                    log.error("Failed to save config", exc_info=e)
                finally:
                    self.last_save = perf_counter()
            finally:
                # Remove from pending tasks when complete
                self._pending_save_tasks.discard(task)

        # Create task and store reference to prevent garbage collection
        task = asyncio.create_task(_save())
        self._pending_save_tasks.add(task)
        # Add error handler to log exceptions
        task.add_done_callback(
            lambda t: log.error("Save task failed", exc_info=t.exception()) if t.exception() else None
        )

    async def red_delete_data_for_user(
        self,
        *,
        requester: t.Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ):
        """Handle data deletion requests"""
        if user_id in self.db.players:
            del self.db.players[user_id]
            self.save()
            log.info(f"Deleted data for user {user_id}")

    async def run_battle_subprocess(
        self,
        team1: list[Bot],
        team2: list[Bot],
        config: t.Optional[dict] = None,
        output_format: str = "gif",
        team1_color: str = "blue",
        team2_color: str = "red",
        chapter: t.Optional[int] = None,
        mission_id: t.Optional[str] = None,
    ) -> tuple[t.Optional[Path], t.Optional[dict]]:
        """
        Run a battle in a subprocess and return the video path and results.

        Args:
            team1: List of Bot objects for team 1
            team2: List of Bot objects for team 2
            config: Optional battle config overrides
            output_format: "gif" or "mp4"
            team1_color: Color name for team 1 (player's team)
            team2_color: Color name for team 2 (enemy team)
            chapter: Campaign chapter number (1-5) for chapter-specific arena backgrounds
            mission_id: Mission ID for mission-specific arena backgrounds (e.g., "1-1")

        Returns:
            Tuple of (video_path, battle_result) or (None, None) on error
        """
        # Create temp files for input/output
        battle_id = str(uuid4())[:8]
        temp_dir = Path(tempfile.gettempdir()) / "botarena"
        temp_dir.mkdir(exist_ok=True)

        input_file = temp_dir / f"battle_{battle_id}_input.json"
        output_file = temp_dir / f"battle_{battle_id}.{output_format}"

        # Build input data
        default_config = {
            "arena_width": 1000,
            "arena_height": 1000,
            "fps": 30,
            "max_duration": 120.0,
            "scale": 0.5,
            "team1_color": team1_color,
            "team2_color": team2_color,
        }
        if chapter:
            default_config["chapter"] = chapter
        if mission_id:
            default_config["mission_id"] = mission_id
        if config:
            default_config.update(config)

        input_data = {
            "config": default_config,
            "team1": [bot.model_dump() for bot in team1],
            "team2": [bot.model_dump() for bot in team2],
        }

        # Write input file
        await asyncio.to_thread(input_file.write_text, json.dumps(input_data))

        try:
            # Run battle in subprocess
            runner_path = Path(__file__).parent / "battle_runner.py"
            cmd = [
                sys.executable,
                str(runner_path),
                str(input_file),
                str(output_file),
                f"--format={output_format}",
            ]

            log.debug(f"Running battle subprocess: {' '.join(cmd)}")

            # Run subprocess asynchronously
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()
            stderr_text = stderr.decode() if stderr else ""
            stdout_text = stdout.decode() if stdout else ""

            # Always log stderr if it contains anything substantial (helps debug on Linux)
            if stderr_text and stderr_text.strip():
                # Filter out just progress lines but keep anything else
                error_lines = [
                    line
                    for line in stderr_text.split("\n")
                    if line.strip()
                    and not line.startswith("Rendering frame")
                    and not line.startswith("Adding ")
                    and not line.startswith("Writing video")
                ]
                if error_lines:
                    log.warning(f"Battle subprocess stderr: {chr(10).join(error_lines)}")

            if proc.returncode != 0:
                log.error(f"Battle subprocess exited with code {proc.returncode}")
                if stderr_text:
                    log.error(f"Stderr: {stderr_text}")
                if stdout_text:
                    log.error(f"Stdout: {stdout_text}")
                return None, None

            # Parse result from stdout
            try:
                result = json.loads(stdout_text)
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse battle result JSON: {e}")
                log.error(f"Stdout was: {stdout_text[:500]}")
                return None, None

            if "error" in result:
                log.error(f"Battle error: {result['error']}")
                return None, None

            # Get actual output path (might differ if fallback was used)
            actual_output = Path(result.get("output_path", str(output_file)))

            if actual_output.exists():
                return actual_output, result
            elif output_file.exists():
                return output_file, result
            else:
                log.error(f"Battle output file not created at {output_file}")
                return None, None

        except Exception as e:
            log.exception(f"Failed to run battle subprocess: {e}")
            return None, None
        finally:
            # Clean up input file
            if input_file.exists():
                input_file.unlink()
