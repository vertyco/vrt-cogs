import asyncio
import base64
import logging
import multiprocessing as mp
import os
import sys
import typing as t
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import psutil
import uvicorn
import uvicorn.config
from fastapi import FastAPI, Request
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter, ColourizedFormatter

try:
    # Running as separate service
    from fullprofile import generate_full_profile
    from runescape import generate_runescape_profile

    SERVICE = True
except ImportError:
    # Running from the cog
    from .fullprofile import generate_full_profile
    from .runescape import generate_runescape_profile

    SERVICE = False


datefmt = "%m/%d %I:%M:%S %p"
access = "%(asctime)s - %(levelname)s %(client_addr)s - '%(request_line)s' %(status_code)s"
default = "%(asctime)s - %(levelname)s - %(message)s"
LOGGING_CONFIG["formatters"]["access"]["fmt"] = access
LOGGING_CONFIG["formatters"]["access"]["datefmt"] = datefmt
LOGGING_CONFIG["formatters"]["default"]["fmt"] = default
LOGGING_CONFIG["formatters"]["default"]["datefmt"] = datefmt

default_formatter = ColourizedFormatter(fmt=default, datefmt=datefmt, use_colors=False)
access_formatter = AccessFormatter(fmt=access, datefmt=datefmt, use_colors=False)

IS_WINDOWS: bool = sys.platform.startswith("win")
DEFAULT_WORKERS: int = os.cpu_count() or 1
ROOT = Path(__file__).parent
LOG_DIR = Path.home() / "LevelUp_API_Logs"
PROC: t.Union[mp.Process, asyncio.subprocess.Process] = None
log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    LOG_DIR.mkdir(exist_ok=True, parents=True)
    proc_num = os.getpid()
    default_filename = LOG_DIR / f"levelup-api-{proc_num}.log"
    access_filename = LOG_DIR / f"levelup-api-access-{proc_num}.log"
    default_rotator = RotatingFileHandler(
        filename=str(default_filename),
        mode="a",
        maxBytes=1024 * 100,  # 100 KB
    )
    access_rotator = RotatingFileHandler(
        filename=str(access_filename),
        mode="a",
        maxBytes=1024 * 100,  # 100 KB
    )
    root_logger = logging.getLogger("uvicorn")
    error_logger = logging.getLogger("uvicorn.error")
    access_logger = logging.getLogger("uvicorn.access")
    # Set the formatters
    default_rotator.setFormatter(default_formatter)
    access_rotator.setFormatter(access_formatter)
    # Add the handlers
    root_logger.addHandler(default_rotator)
    error_logger.addHandler(default_rotator)
    access_logger.addHandler(access_rotator)
    # if not SERVICE:
    #     # Get rid of the console handler
    #     root_logger.removeHandler(root_logger.handlers[0])

    yield
    if PROC:
        log.info("Shutting down API")
        kill(PROC)


app = FastAPI(title="LevelUp API", version="0.0.1a")


# Utility to parse color strings to tuple
def parse_color(color_str: str) -> t.Union[None, t.Tuple[int, int, int]]:
    # Convert a string like (255, 255, 255) to a tuple
    if not color_str or not isinstance(color_str, str):
        return None
    color: t.Tuple[int, int, int] = tuple(map(int, color_str.strip("()").split(", ")))
    return color


def get_kwargs(form_data: t.Dict[str, t.Any]) -> t.Dict[str, t.Any]:
    kwargs = {}
    for k, v in form_data.items():
        if hasattr(v, "file"):
            kwargs[k] = v.file.read()
            continue
        elif isinstance(v, str) and v.isdigit():
            kwargs[k] = int(v)
        else:
            try:
                kwargs[k] = int(float(v))
            except ValueError:
                kwargs[k] = v

        # Some values have the following
        # ValueError: unknown color specifier: '(255, 255, 255)'
        # The following kwargs need to be evaluated as tuples
        kwargs["base_color"] = parse_color(kwargs.get("base_color"))
        kwargs["user_color"] = parse_color(kwargs.get("user_color"))
        kwargs["stat_color"] = parse_color(kwargs.get("stat_color"))
        kwargs["level_bar_color"] = parse_color(kwargs.get("level_bar_color"))

    return kwargs


@app.post("/fullprofile")
async def fullprofile(request: Request):
    form_data = await request.form()
    kwargs = get_kwargs(form_data)
    img_bytes, animated = await asyncio.to_thread(generate_full_profile, **kwargs)
    encoded = base64.b64encode(img_bytes).decode("utf-8")
    return {"b64": encoded, "animated": animated}


@app.post("/runescape")
async def runescape(request: Request):
    form_data = await request.form()
    kwargs = get_kwargs(form_data)
    img_bytes, animated = await asyncio.to_thread(generate_runescape_profile, **kwargs)
    encoded = base64.b64encode(img_bytes).decode("utf-8")
    return {"b64": encoded, "animated": animated}


@app.get("/health")
async def health():
    return {"status": "ok"}


async def run(
    port: t.Optional[int] = None,
    log_dir: t.Optional[t.Union[Path, str]] = None,
) -> t.Union[mp.Process, asyncio.subprocess.Process]:
    if log_dir:
        global LOG_DIR
        LOG_DIR = log_dir if isinstance(log_dir, Path) else Path(log_dir)

    APP_DIR = str(ROOT)
    log.info(f"Running API from {APP_DIR}")
    log.info(f"Log directory: {LOG_DIR} (As Service: {SERVICE})")
    log.info(f"Spinning up {DEFAULT_WORKERS} workers on port {port or 6969} in 5s...")
    await asyncio.sleep(5)

    if IS_WINDOWS:
        kwargs = {
            "workers": DEFAULT_WORKERS,
            "port": port or 6969,
            "app_dir": APP_DIR,
            "log_config": LOGGING_CONFIG,
            "use_colors": False,
            "host": "127.0.0.1",
        }
        proc = mp.Process(
            target=uvicorn.run,
            args=("api:app",),
            kwargs=kwargs,
        )
        proc.start()
        return proc

    # Linux
    exe_path = sys.executable
    cmd = [
        f"{exe_path} -m uvicorn api:app",
        f"--workers {DEFAULT_WORKERS}",
        f"--port {port or 6969}",
        f"--app-dir '{APP_DIR}'",
        f"--host {'0.0.0.0' if SERVICE else '127.0.0.1'}",  # Specify the host
    ]
    proc = await asyncio.create_subprocess_shell(" ".join(cmd))
    global PROC
    PROC = proc
    return proc


def kill(proc: t.Union[mp.Process, asyncio.subprocess.Process]) -> None:
    try:
        parent = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        return
    for child in parent.children(recursive=True):
        child.kill()
    if IS_WINDOWS:
        proc.terminate()


if __name__ == "__main__":
    """
    If running this script directly, spin up the API.

    Usage:
    python api.py [port] [log_dir]
    """
    proc = asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else None, int(sys.argv[2]) if len(sys.argv) > 2 else None))
