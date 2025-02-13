import asyncio
import inspect
import os
import subprocess
from pathlib import Path

from discord.ext import commands
from redbot.core.data_manager import cog_data_path


def get_root(cog_instance: commands.Cog | Path) -> Path:
    """Get the root path of the cog"""
    if isinstance(cog_instance, Path):
        return cog_instance
    return Path(inspect.getfile(cog_instance.__class__)).parent


def is_unc_path(path: Path) -> bool:
    """Check if path is a UNC path"""
    return path.is_absolute() and str(path).startswith(r"\\\\")


def is_windows() -> bool:
    """Check if the OS is Windows"""
    return os.name == "nt"


def find_piccolo_executable() -> Path:
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


def get_env(cog_instance: commands.Cog | Path, postgres_config: dict = None) -> dict:
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
    if is_windows():
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
) -> str:
    """Run a shell command in a separate thread"""

    def _exe() -> str:
        res = subprocess.run(
            commands,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=is_shell,
            cwd=str(get_root(cog_instance)),
            env=get_env(cog_instance),
        )
        return res.stdout.decode(encoding="utf-8", errors="ignore").replace("👍", "!")

    return await asyncio.to_thread(_exe)
