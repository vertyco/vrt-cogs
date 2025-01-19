import asyncio
import inspect
import logging
import os
import subprocess
from pathlib import Path

from discord.ext import commands
from piccolo.engine.sqlite import SQLiteEngine
from piccolo.table import Table
from redbot.core.data_manager import cog_data_path

from .errors import DirectoryError, UNCPathError

log = logging.getLogger("red.vrt.appeals.engine")


async def register_cog(
    cog_instance: commands.Cog,
    tables: list[type[Table]],
    trace: bool = False,
    skip_migrations: bool = False,
) -> SQLiteEngine:
    """Registers a Discord cog with a database connection and runs migrations.

    Args:
        cog_instance (Cog): The instance of the cog to register.
        tables (list[type[Table]]): List of Piccolo Table classes to associate with the database engine.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.
        skip_migrations (bool, optional): Whether to skip running migrations. Defaults to False.

    Raises:
        UNCPathError: If the cog path is a UNC path, which is not supported.
        DirectoryError: If the cog files are not in a valid directory.

    Returns:
        SQLiteEngine: The database engine associated with the registered cog.
    """
    if not isinstance(cog_instance, commands.Cog):
        raise TypeError("cog_instance must be a class or subclass of discord.ext.commands.Cog")
    save_path = cog_data_path(cog_instance)
    if _is_unc_path(save_path):
        raise UNCPathError(f"UNC paths are not supported, please move the cog's location: {save_path}")
    if not save_path.is_dir():
        raise DirectoryError(f"Cog files are not in a valid directory: {save_path}")

    if not skip_migrations:
        log.info("Running migrations, if any")
        result = await run_migrations(cog_instance, trace)
        if "No migrations need to be run" in result:
            log.info("No migrations needed!")
        else:
            log.info(f"Migration result...\n{result}")
            if "Traceback" in result:
                diagnoses = await diagnose_issues(cog_instance)
                log.error(diagnoses + "\nOne or more migrations failed to run!")

    db = SQLiteEngine(path=str(save_path / "db.sqlite"))
    for table_class in tables:
        table_class._meta.db = db
    return db


async def run_migrations(cog_instance: commands.Cog, trace: bool = False) -> str:
    """Runs database migrations for the cog

    Args:
        cog_instance (Cog): The instance of the cog to run migrations for.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    piccolo_path = _find_piccolo_executable()
    commands = [str(piccolo_path), "migrations", "forwards", _root(cog_instance).stem]
    if trace:
        commands.append("--trace")
    return await _shell(cog_instance, commands, False)


async def reverse_migration(cog_instance: commands.Cog, timestamp: str, trace: bool = False) -> str:
    """Reverses database migrations for the cog

    Args:
        cog_instance (Cog): The instance of the cog to reverse migrations for.
        timestamp (str): The timestamp of the migration to reverse to.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    piccolo_path = _find_piccolo_executable()
    commands = [str(piccolo_path), "migrations", "backwards", _root(cog_instance).stem, timestamp]
    if trace:
        commands.append("--trace")
    return await _shell(cog_instance, commands, False)


async def create_migrations(cog_instance: commands.Cog | Path, trace: bool = False, description: str = None) -> str:
    """Creates new database migrations for the cog

    THIS SHOULD BE RUN MANUALLY!

    Args:
        cog_instance (Cog | Path): The instance of the cog to create migrations for.
        name (str): The name of the migration to create.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    piccolo_path = _find_piccolo_executable()
    commands = [str(piccolo_path), "migrations", "new", _root(cog_instance).stem, "--auto"]
    if trace:
        commands.append("--trace")
    if description is not None:
        commands.append(f"--desc={description}")
    return await _shell(cog_instance, commands, False)


async def diagnose_issues(cog_instance: commands.Cog | Path) -> str:
    """Diagnose issues with the cog's database connection

    Args:
        cog_instance (Cog | Path): The instance of the cog to diagnose.

    Returns:
        str: The result of the diagnosis process, including any output messages.
    """
    piccolo_path = _find_piccolo_executable()
    diagnoses = await _shell(cog_instance, [str(piccolo_path), "--diagnose"], False)
    check = await _shell(cog_instance, [str(piccolo_path), "migrations", "check"], False)
    return f"{diagnoses}\n{check}"


async def _shell(cog_instance: commands.Cog | Path, commands: list[str], is_shell: bool) -> str:
    """Run a shell command in a separate thread"""

    def _exe() -> str:
        res = subprocess.run(
            commands,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=is_shell,
            cwd=str(_root(cog_instance)),
            env=_get_env(cog_instance),
        )
        return res.stdout.decode(encoding="utf-8", errors="ignore").replace("👍", "!")

    return await asyncio.to_thread(_exe)


def _root(cog_instance: commands.Cog | Path) -> Path:
    """Get the root path of the cog"""
    if isinstance(cog_instance, Path):
        return cog_instance
    return Path(inspect.getfile(cog_instance.__class__)).parent


def _get_env(cog_instance: commands.Cog | Path) -> dict:
    """Create mock environment for subprocess"""
    env = os.environ.copy()
    env["PICCOLO_CONF"] = "db.piccolo_conf"
    env["APP_NAME"] = _root(cog_instance).stem
    if isinstance(cog_instance, Path):
        env["DB_PATH"] = str(cog_instance / "db.sqlite")
    else:
        env["DB_PATH"] = str(cog_data_path(cog_instance) / "db.sqlite")
    if _is_windows():
        env["PYTHONIOENCODING"] = "utf-8"
    return env


def _is_unc_path(path: Path) -> bool:
    """Check if path is a UNC path"""
    return path.is_absolute() and str(path).startswith(r"\\\\")


def _is_windows() -> bool:
    """Check if the OS is Windows"""
    return os.name == "nt"


def _find_piccolo_executable() -> Path:
    """Find the piccolo executable in the system's PATH."""
    for path in os.environ["PATH"].split(os.pathsep):
        for executable_name in ["piccolo", "piccolo.exe"]:
            executable = Path(path) / executable_name
            if executable.exists() and os.access(executable, os.X_OK):
                return executable

    # Fetch the lib path from downloader
    lib_path = cog_data_path(raw_name="Downloader") / "lib"
    if lib_path.exists():
        for folder in lib_path.iterdir():
            for executable_name in ["piccolo", "piccolo.exe"]:
                executable = folder / executable_name
                if executable.exists() and os.access(executable, os.X_OK):
                    return executable

    raise FileNotFoundError("Piccolo package not found!")
