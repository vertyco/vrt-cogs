import asyncio
import inspect
import logging
import os
import subprocess
import sys
import typing as t
from pathlib import Path

import asyncpg
from discord.ext import commands
from piccolo.engine.postgres import PostgresEngine
from piccolo.table import Table
from redbot.core.data_manager import cog_data_path

from .errors import ConnectionTimeoutError, DirectoryError, UNCPathError

log = logging.getLogger("red.vrt.miner.engine")


async def register_cog(
    cog_instance: commands.Cog | Path,
    tables: list[type[Table]],
    config: dict,
    *,
    trace: bool = False,
    max_size: int = 20,
    min_size: int = 1,
    skip_migrations: bool = False,
    extensions: list[str] = ("uuid-ossp",),
) -> PostgresEngine:
    """Registers a Discord cog with a database connection and runs migrations.

    Args:
        cog_instance (commands.Cog | Path): The instance/path of the cog to register.
        tables (list[type[Table]]): List of Piccolo Table classes to associate with the database engine.
        config (dict): Configuration dictionary containing database connection details.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.
        max_size (int, optional): Maximum size of the database connection pool. Defaults to 20.
        min_size (int, optional): Minimum size of the database connection pool. Defaults to 1.
        skip_migrations (bool, optional): Whether to skip running migrations. Defaults to False.
        extensions (list[str], optional): List of Postgres extensions to enable. Defaults to ("uuid-ossp",).

    Raises:
        UNCPathError: If the cog path is a UNC path, which is not supported.
        DirectoryError: If the cog files are not in a valid directory.

    Returns:
        PostgresEngine: The database engine associated with the registered cog.
    """
    assert isinstance(cog_instance, (commands.Cog, Path)), (
        "cog_instance must be a Cog instance or a Path to the cog directory"
    )
    cog_path = get_root(cog_instance)
    if is_unc_path(cog_path):
        raise UNCPathError(f"UNC paths are not supported, please move the cog's location: {cog_path}")
    if not cog_path.is_dir():
        raise DirectoryError(f"Cog files are not in a valid directory: {cog_path}")

    if await ensure_database_exists(cog_instance, config):
        log.info(f"New database created for {cog_path.stem}")

    if not skip_migrations:
        log.info("Running migrations, if any")
        result = await run_migrations(cog_instance, config, trace)
        if "No migrations need to be run" in result:
            log.info("No migrations needed ✓")
        else:
            log.info(f"Migration result...\n{result}")
            if "Traceback" in result:
                diagnoses = await diagnose_issues(cog_instance, config)
                log.error(diagnoses + "\nOne or more migrations failed to run!")

    temp_config = config.copy()
    temp_config["database"] = db_name(cog_instance)
    log.debug("Fetching database engine")
    engine = await acquire_db_engine(temp_config, extensions)
    log.debug("Database engine acquired, starting pool")
    await engine.start_connection_pool(min_size=min_size, max_size=max_size)
    log.info("Database connection pool started ✓")
    for table_class in tables:
        table_class._meta.db = engine
    return engine


async def run_migrations(
    cog_instance: commands.Cog | Path,
    config: dict,
    trace: bool = False,
) -> str:
    """Runs database migrations for a given Discord cog.

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to run migrations.
        config (dict): Database connection details.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    temp_config = config.copy()
    temp_config["database"] = db_name(cog_instance)
    commands = [
        str(find_piccolo_executable()),
        "migrations",
        "forwards",
        get_root(cog_instance).stem,
    ]
    if trace:
        commands.append("--trace")
    return await run_shell(cog_instance, commands, False, temp_config)


async def reverse_migration(
    cog_instance: commands.Cog | Path,
    config: dict,
    timestamp: str,
    trace: bool = False,
) -> str:
    """Reverses a database migration for a given Discord cog to a specific timestamp.

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to reverse the migration.
        config (dict): Configuration dictionary containing database connection details.
        timestamp (str): The timestamp to which the migration should be reversed.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the reverse migration process, including any output messages.
    """
    temp_config = config.copy()
    temp_config["database"] = db_name(cog_instance)
    commands = [
        str(find_piccolo_executable()),
        "migrations",
        "backwards",
        get_root(cog_instance).stem,
        timestamp,
    ]
    if trace:
        commands.append("--trace")
    return await run_shell(cog_instance, commands, False, temp_config)


async def create_migrations(
    cog_instance: commands.Cog | Path,
    config: dict,
    trace: bool = False,
    description: str = None,
) -> str:
    """Creates new database migrations for the cog

    THIS SHOULD BE RUN MANUALLY!

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to create migrations.
        config (dict): Configuration dictionary containing database connection details.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.
        description (str, optional): Description of the migration. Defaults to None.

    Returns:
        str: The result of the migration creation process, including any output messages.
    """
    temp_config = config.copy()
    temp_config["database"] = db_name(cog_instance)
    commands = [
        str(find_piccolo_executable()),
        "migrations",
        "new",
        get_root(cog_instance).stem,
        "--auto",
    ]
    if trace:
        commands.append("--trace")
    if description is not None:
        commands.append(f"--desc={description}")
    return await run_shell(cog_instance, commands, True, temp_config)


async def diagnose_issues(cog_instance: commands.Cog | Path, config: dict) -> str:
    """Diagnoses potential issues with the database setup for a given Discord cog.

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog to diagnose.
        config (dict): Configuration dictionary containing database connection details.

    Returns:
        str: The result of the diagnosis process, including any output messages.
    """
    piccolo_path = find_piccolo_executable()
    temp_config = config.copy()
    temp_config["database"] = db_name(cog_instance)
    diagnoses = await run_shell(
        cog_instance,
        [str(piccolo_path), "--diagnose"],
        False,
        temp_config,
    )
    check = await run_shell(
        cog_instance,
        [str(piccolo_path), "migrations", "check"],
        False,
        temp_config,
    )
    return f"{diagnoses}\n{check}"


async def ensure_database_exists(
    cog_instance: commands.Cog | Path,
    config: dict[str, t.Any],
) -> bool:
    """Create a database for the cog if it doesn't exist.

    Args:
        cog_instance (commands.Cog | Path): The cog instance
        config (dict): the database connection information

    Returns:
        bool: True if a new database was created
    """
    tmp_config = config.copy()
    tmp_config["timeout"] = 10
    conn = await asyncpg.connect(**tmp_config)
    database_name = db_name(cog_instance)
    try:
        databases = await conn.fetch("SELECT datname FROM pg_database;")
        if database_name not in [db["datname"] for db in databases]:
            escaped_name = '"' + database_name.replace('"', '""') + '"'
            await conn.execute(f"CREATE DATABASE {escaped_name};")
            return True
    finally:
        await conn.close()
    return False


async def acquire_db_engine(config: dict, extensions: list[str]) -> PostgresEngine:
    """Acquire a database engine
    The PostgresEngine constructor is blocking and must be run in a separate thread.

    Args:
        config (dict): The database connection information
        extensions (list[str]): The Postgres extensions to enable

    Returns:
        PostgresEngine: The database engine
    """

    async def get_conn():
        return await asyncio.to_thread(
            PostgresEngine,
            config=config,
            extensions=extensions,
        )

    try:
        return await asyncio.wait_for(get_conn(), timeout=10)
    except asyncio.TimeoutError:
        raise ConnectionTimeoutError("Database connection timed out")


def db_name(cog_instance: commands.Cog | Path) -> str:
    """Get the name of the database for the cog

    Args:
        cog_instance (commands.Cog | Path): The cog instance

    Returns:
        str: The database name
    """
    if isinstance(cog_instance, Path):
        return cog_instance.stem.lower()
    return cog_instance.qualified_name.lower()


def get_root(cog_instance: commands.Cog | Path) -> Path:
    """Get the root path of the cog"""
    if isinstance(cog_instance, Path):
        return cog_instance
    return Path(inspect.getfile(cog_instance.__class__)).parent


def is_unc_path(path: Path) -> bool:
    """Check if path is a UNC path"""
    return path.is_absolute() and str(path).startswith(r"\\\\")


def find_piccolo_executable() -> Path:
    """Find the piccolo executable in the system's PATH."""
    for path in os.environ["PATH"].split(os.pathsep):
        for executable_name in ["piccolo", "piccolo.exe"]:
            executable = Path(path) / executable_name
            if executable.exists():
                return executable

    # Fetch the lib path from downloader
    lib_path = cog_data_path(raw_name="Downloader") / "lib"
    if lib_path.exists():
        for folder in lib_path.iterdir():
            for executable_name in ["piccolo", "piccolo.exe"]:
                executable = folder / executable_name
                if executable.exists():
                    return executable

    # Check if lib was installed manually in the venv
    default_path = Path(sys.executable).parent / "piccolo"
    if default_path.exists():
        return default_path

    raise FileNotFoundError("Piccolo package not found!")


def get_env(
    cog_instance: commands.Cog | Path,
    postgres_config: dict[str, t.Any] | None = None,
) -> dict[str, t.Any]:
    """Create mock environment for subprocess"""
    env = os.environ.copy()
    if "PICCOLO_CONF" not in env:
        # Dont want to overwrite the user's config
        env["PICCOLO_CONF"] = "db.piccolo_conf"
    env["APP_NAME"] = get_root(cog_instance).stem
    if isinstance(cog_instance, Path):
        env["DB_PATH"] = str(cog_instance / "db.sqlite")
    else:
        env["DB_PATH"] = str(cog_data_path(cog_instance) / "db.sqlite")
    if os.name == "nt":  # Windows
        env["PYTHONIOENCODING"] = "utf-8"
    if postgres_config is not None:
        env["POSTGRES_USER"] = postgres_config.get("user", "postgres")
        env["POSTGRES_PASSWORD"] = postgres_config.get("password", "postgres")
        env["POSTGRES_DATABASE"] = postgres_config.get("database", "postgres")
        env["POSTGRES_HOST"] = postgres_config.get("host", "localhost")
        env["POSTGRES_PORT"] = postgres_config.get("port", "5432")
    return env


async def run_shell(
    cog_instance: commands.Cog | Path,
    commands: list[str],
    is_shell: bool,
    postgres_config: dict = None,
) -> str:
    """Run a shell command in a separate thread"""

    def _exe() -> str:
        res = subprocess.run(
            commands,
            stdout=sys.stdout if is_shell else subprocess.PIPE,
            stderr=sys.stdout if is_shell else subprocess.PIPE,
            shell=is_shell,
            cwd=str(get_root(cog_instance)),
            env=get_env(cog_instance, postgres_config),
        )
        if not res.stdout:
            return ""
        return res.stdout.decode(encoding="utf-8", errors="ignore").replace("👍", "!")

    return await asyncio.to_thread(_exe)
