import asyncio
import inspect
import logging
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
from discord.ext import commands
from piccolo.engine.postgres import PostgresEngine
from piccolo.table import Table

from .errors import ConnectionTimeoutError, DirectoryError, UNCPathError

log = logging.getLogger("red.vrt.whosalt.engine")
piccolo_path = Path(sys.executable).parent / "piccolo"


async def register_cog(
    cog_instance: commands.Cog | Path,
    config: dict,
    tables: list[type[Table]],
    pool_size: int = 20,
    trace: bool = False,
):
    """Registers a Discord cog with a database connection and runs migrations.

    Args:
        cog_instance (commands.Cog | Path): The instance/path of the cog to register.
        config (dict): Configuration dictionary containing database connection details.
        tables (list[type[Table]]): List of Piccolo Table classes to associate with the database engine.
        pool_size (int, optional): Maximum size of the database connection pool. Defaults to 20.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Raises:
        UNCPathError: If the cog path is a UNC path, which is not supported.
        DirectoryError: If the cog files are not in a valid directory.

    Returns:
        PostgresEngine: The database engine associated with the registered cog.
    """
    cog_path = _root(cog_instance)
    if _is_unc_path(cog_path):
        raise UNCPathError(f"UNC paths are not supported, please move the cog's location: {cog_path}")
    if not cog_path.is_dir():
        raise DirectoryError(f"Cog files are not in a valid directory: {cog_path}")

    if await ensure_database_exists(cog_instance, config):
        log.info(f"New database created for {cog_instance.qualified_name}")

    log.info("Running migrations, if any")
    result = await run_migrations(cog_instance, config, trace)
    if "No migrations need to be run" in result:
        log.info("No migrations needed ✓")
    else:
        log.info(f"Migration result...\n{result}")

    temp_config = config.copy()
    temp_config["database"] = _db_name(cog_instance)
    log.debug("Fetching database engine")
    engine = await _acquire_db_engine(temp_config)
    log.debug("Database engine acquired, starting pool")
    await engine.start_connection_pool(max_size=pool_size)
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
        config (dict): Configuration dictionary containing database connection details.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    temp_config = config.copy()
    temp_config["database"] = _db_name(cog_instance)
    commands = [str(piccolo_path), "migrations", "forwards", _root(cog_instance).stem]
    if trace:
        commands.append("--trace")

    def _exe():
        return (
            subprocess.run(
                commands,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                cwd=str(_root(cog_instance)),
                env=_get_env(temp_config),
            )
            .stdout.decode()
            .replace("👍", "✓")
        )

    return await asyncio.to_thread(_exe)


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
    temp_config["database"] = _db_name(cog_instance)
    commands = [str(piccolo_path), "migrations", "backwards", _root(cog_instance).stem, timestamp]
    if trace:
        commands.append("--trace")

    def _exe():
        return (
            subprocess.run(
                commands,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                cwd=str(_root(cog_instance)),
                env=_get_env(temp_config),
            )
            .stdout.decode()
            .replace("👍", "✓")
        )

    return await asyncio.to_thread(_exe)


async def create_migrations(
    cog_instance: commands.Cog | Path,
    config: dict,
    trace: bool = False,
) -> str:
    """Creates new database migrations for a given Discord cog.

    THIS SHOULD BE RUN MANUALLY!

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to create migrations.
        config (dict): Configuration dictionary containing database connection details.

    Returns:
        str: The result of the migration creation process, including any output messages.
    """
    temp_config = config.copy()
    temp_config["database"] = _db_name(cog_instance)
    commands = [str(piccolo_path), "migrations", "new", _root(cog_instance).stem, "--auto"]
    if trace:
        commands.append("--trace")

    def _exe():
        return (
            subprocess.run(
                commands,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                cwd=str(_root(cog_instance)),
                env=_get_env(temp_config),
            )
            .stdout.decode()
            .replace("👍", "✓")
        )

    return await asyncio.to_thread(_exe)


async def diagnose_issues(cog_instance: commands.Cog | Path, config: dict) -> str:
    """Diagnoses potential issues with the database setup for a given Discord cog.

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to diagnose issues.
        config (dict): Configuration dictionary containing database connection details.

    Returns:
        str: A report of the diagnosis and migration check results.
    """
    temp_config = config.copy()
    temp_config["database"] = _db_name(cog_instance)

    def _exe():
        diagnoses = subprocess.run(
            [str(piccolo_path), "--diagnose"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=str(_root(cog_instance)),
            env=_get_env(temp_config),
        ).stdout.decode()
        check = subprocess.run(
            [str(piccolo_path), "migrations", "check"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=str(_root(cog_instance)),
            env=_get_env(temp_config),
        ).stdout.decode()
        return f"DIAGNOSES\n{diagnoses}\nCHECK\n{check}"

    return await asyncio.to_thread(_exe)


async def ensure_database_exists(cog_instance: commands.Cog | Path, config: dict) -> bool:
    """Create a database for the cog if it doesn't exist.

    Args:
        cog_instance (commands.Cog | Path): The cog instance
        config (dict): the database connection information

    Returns:
        bool: True if a new database was created
    """
    conn = await asyncpg.connect(**config, timeout=10)
    database_name = _db_name(cog_instance)
    try:
        databases = await conn.fetch("SELECT datname FROM pg_database;")
        if database_name not in [db["datname"] for db in databases]:
            await conn.execute(f"CREATE DATABASE {database_name};")
            return True
    finally:
        await conn.close()
    return False


async def _acquire_db_engine(config: dict) -> PostgresEngine:
    """Acquire a database engine
    The PostgresEngine constructor is blocking and must be run in a separate thread.

    Args:
        config (dict): The database connection information

    Returns:
        PostgresEngine: The database engine
    """

    def _acquire(config: dict) -> PostgresEngine:
        return PostgresEngine(config=config)

    try:
        async with asyncio.timeout(10):
            engine = await asyncio.to_thread(_acquire, config)
            return engine
    except asyncio.TimeoutError:
        raise ConnectionTimeoutError("Database took longer than 10 seconds to connect!")


def _root(cog_instance: commands.Cog | Path) -> Path:
    """Get the root path of the cog"""
    if isinstance(cog_instance, Path):
        return cog_instance
    return Path(inspect.getfile(cog_instance.__class__)).parent


def _get_env(config: dict) -> dict:
    """Create mock environment for subprocess"""
    env = os.environ.copy()
    env["PICCOLO_CONF"] = "db.piccolo_conf"
    env["POSTGRES_HOST"] = config.get("host")
    env["POSTGRES_PORT"] = config.get("port")
    env["POSTGRES_USER"] = config.get("user")
    env["POSTGRES_PASSWORD"] = config.get("password")
    env["POSTGRES_DATABASE"] = config.get("database")
    if _is_windows():
        env["PYTHONIOENCODING"] = "utf-8"
    return env


def _db_name(cog_instance: commands.Cog | Path) -> str:
    """Get the name of the database for the cog"""
    if isinstance(cog_instance, Path):
        return cog_instance.stem.lower()
    return cog_instance.qualified_name.lower()


def _is_unc_path(path: Path) -> bool:
    """Check if path is a UNC path"""
    return path.is_absolute() and str(path).startswith(r"\\\\")


def _is_windows() -> bool:
    """Check if the OS is Windows"""
    return os.name == "nt"
