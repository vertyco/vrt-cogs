import logging
from pathlib import Path

from discord.ext import commands
from piccolo.engine.sqlite import SQLiteEngine
from piccolo.table import Table
from redbot.core.data_manager import cog_data_path

from .common import find_piccolo_executable, get_root, is_unc_path, run_shell
from .errors import DirectoryError, UNCPathError

log = logging.getLogger("red.vrt.appeals.engine")


async def register_cog(
    cog_instance: commands.Cog | Path,
    tables: list[type[Table]],
    *,
    trace: bool = False,
    skip_migrations: bool = False,
) -> SQLiteEngine:
    """Registers a Discord cog with a database connection and runs migrations.

    Args:
        cog_instance (commands.Cog | Path): The instance/path of the cog to register.
        tables (list[type[Table]]): List of Piccolo Table classes to associate with the database engine.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.
        skip_migrations (bool, optional): Whether to skip running migrations. Defaults to False.

    Raises:
        TypeError: If the cog instance is not a subclass of discord.ext.commands.Cog or a valid directory path.
        UNCPathError: If the cog path is a UNC path, which is not supported.
        DirectoryError: If the cog files are not in a valid directory.

    Returns:
        SQLiteEngine: The database engine associated with the registered cog.
    """
    if isinstance(cog_instance, commands.Cog):
        save_path = cog_data_path(cog_instance)
    elif cog_instance.is_dir():
        save_path = cog_instance
    else:
        # Must be a cog instance or directory
        raise TypeError(f"Invalid cog instance: {cog_instance}, must be a cog or directory path")
    if is_unc_path(save_path):
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

    log.debug("Fetching database engine")
    db = SQLiteEngine(path=str(save_path / "db.sqlite"))
    for table_class in tables:
        table_class._meta.db = db
    return db


async def run_migrations(
    cog_instance: commands.Cog | Path,
    trace: bool = False,
) -> str:
    """Runs database migrations for the cog

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to run migrations.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    commands = [
        str(find_piccolo_executable()),
        "migrations",
        "forwards",
        get_root(cog_instance).stem,
    ]
    if trace:
        commands.append("--trace")
    return await run_shell(cog_instance, commands, False)


async def reverse_migration(
    cog_instance: commands.Cog | Path,
    timestamp: str,
    trace: bool = False,
) -> str:
    """Reverses database migrations for the cog

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog for which to reverse the migration.
        timestamp (str): The timestamp of the migration to reverse to.
        trace (bool, optional): Whether to enable tracing for migrations. Defaults to False.

    Returns:
        str: The result of the migration process, including any output messages.
    """
    commands = [
        str(find_piccolo_executable()),
        "migrations",
        "backwards",
        get_root(cog_instance).stem,
        timestamp,
    ]
    if trace:
        commands.append("--trace")
    return await run_shell(cog_instance, commands, False)


async def create_migrations(
    cog_instance: commands.Cog | Path,
    trace: bool = False,
    description: str = None,
) -> str:
    """Creates new database migrations for the cog

    THIS SHOULD BE RUN MANUALLY!

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog to create migrations for.
        name (str): The name of the migration to create.

    Returns:
        str: The result of the migration process, including any output messages.
    """
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
    return await run_shell(cog_instance, commands, True)


async def diagnose_issues(cog_instance: commands.Cog | Path) -> str:
    """Diagnose issues with the cog's database connection

    Args:
        cog_instance (commands.Cog | Path): The instance of the cog to diagnose.

    Returns:
        str: The result of the diagnosis process, including any output messages.
    """
    piccolo_path = find_piccolo_executable()
    diagnoses = await run_shell(
        cog_instance,
        [str(piccolo_path), "--diagnose"],
        False,
    )
    check = await run_shell(
        cog_instance,
        [str(piccolo_path), "migrations", "check"],
        False,
    )
    return f"{diagnoses}\n{check}"
