import asyncio
import inspect
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Type

from discord.ext.commands import Cog
from piccolo.engine.postgres import PostgresEngine
from piccolo.table import Table, create_db_tables

log = logging.getLogger("red.vrt.piccolotemplate")


def acquire_db_engine(config: dict) -> PostgresEngine:
    """This is ran in executor since it blocks if connection info is bad"""
    return PostgresEngine(config=config)


async def create_database_and_tables(
    cog: Cog,
    config: dict,
    tables: List[Type[Table]],
) -> PostgresEngine:
    """Connect to postgres, create database/tables and return engine

    Args:
        cog (Cog): Cog instance
        config (dict): database connection info
        tables (List[Type[Table]]): list of piccolo table subclasses

    Returns:
        PostgresEngine instance
    """
    log.info("Initializing database")
    engine = await asyncio.to_thread(acquire_db_engine, config)
    await engine.start_connection_pool()

    # Check if the database exists
    databases = await engine._run_in_pool("SELECT datname FROM pg_database;")
    cog_name = cog.__class__.__name__.lower()
    if cog_name not in [db["datname"] for db in databases]:
        # Create the database
        log.info(f"First time running {cog_name}! Creating new database!")
        await engine._run_in_pool(f"CREATE DATABASE {cog_name};")

    # Close old database connection
    await engine.close_connection_pool()

    # Connect to the new database
    config["database"] = cog_name
    engine = await asyncio.to_thread(acquire_db_engine, config)
    await engine.start_connection_pool()

    # Update table engines
    for table_class in tables:
        table_class._meta.db = engine

    # Create any tables that don't already exist
    await create_db_tables(*tables, if_not_exists=True)
    return engine


async def run_migrations(cog: Cog, config: dict):
    """
    Run any existing migrations programatically.

    There might be a better way to do this that subprocess, but haven't tested yet.

    Args:
        cog (Cog): Cog instance
        config (dict): Database connection info

    Returns:
        str: Results of the migration
    """

    def run():
        root = Path(inspect.getfile(cog.__class__)).parent
        env = os.environ.copy()
        env["PICCOLO_CONF"] = "db.piccolo_conf"
        env["POSTGRES_HOST"] = config.get("host")
        env["POSTGRES_PORT"] = config.get("port")
        env["POSTGRES_USER"] = config.get("user")
        env["POSTGRES_PASSWORD"] = config.get("password")
        env["POSTGRES_DATABASE"] = cog.__class__.__name__.lower()
        env["PYTHONIOENCODING"] = "utf-8"

        migration_result = subprocess.run(
            ["piccolo", "migrations", "forward", root.name],
            env=env,
            cwd=root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout.decode()
        log.debug(migration_result)

        diagnose_result = subprocess.run(
            ["piccolo", "--diagnose"],
            env=env,
            cwd=root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).stdout.decode()
        log.debug(diagnose_result)

        return migration_result

    return await asyncio.to_thread(run)


async def register_cog(
    cog: Cog, config: dict, tables: List[Type[Table]]
) -> Tuple[PostgresEngine, str]:
    """Registers a cog by creating a database for it and initializing any tables it has

    Args:
        cog (Cog): Cog instance
        config (dict): database connection info
        tables (List[Type[Table]]): list of piccolo table subclasses

    Returns:
        Tuple[PostgresEngine, str]: Postgres Engine instance, migration results
    """
    engine = await create_database_and_tables(cog, config, tables)
    result = await run_migrations(cog, config)
    return engine, result
