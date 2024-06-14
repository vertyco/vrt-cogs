import asyncio
import base64
import logging
import multiprocessing as mp
import os
import sys
import typing as t
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
import uvicorn
import uvicorn.config
from fastapi import FastAPI, Request
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter, ColourizedFormatter

try:
    # Running from the cog
    from .levelalert import generate_level_img
    from .styles.default import generate_default_profile
    from .styles.runescape import generate_runescape_profile

    SERVICE = False
except ImportError:
    # Running as separate service
    from levelalert import generate_level_img
    from styles.default import generate_default_profile
    from styles.runescape import generate_runescape_profile

    SERVICE = True


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
log = logging.getLogger("red.vrt.levelup.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
        elif isinstance(v, str) and v.lower() in ("true", "false"):
            kwargs[k] = v.lower() == "true"
        else:
            try:
                kwargs[k] = int(float(v))
            except ValueError:
                kwargs[k] = v

    # Some values have the following
    # ValueError: unknown color specifier: '(255, 255, 255)'
    # The following kwargs need to be evaluated as tuples
    if form_data.get("base_color") is not None:
        kwargs["base_color"] = parse_color(form_data.get("base_color"))
    if form_data.get("user_color") is not None:
        kwargs["user_color"] = parse_color(form_data.get("user_color"))
    if form_data.get("stat_color") is not None:
        kwargs["stat_color"] = parse_color(form_data.get("stat_color"))
    if form_data.get("level_bar_color") is not None:
        kwargs["level_bar_color"] = parse_color(form_data.get("level_bar_color"))

    return kwargs


@app.post("/fullprofile")
async def fullprofile(request: Request):
    form_data = await request.form()
    kwargs = get_kwargs(form_data)
    img_bytes, animated = await asyncio.to_thread(generate_default_profile, **kwargs)
    encoded = base64.b64encode(img_bytes).decode("utf-8")
    return {"b64": encoded, "animated": animated}


@app.post("/runescape")
async def runescape(request: Request):
    form_data = await request.form()
    kwargs = get_kwargs(form_data)
    img_bytes, animated = await asyncio.to_thread(generate_runescape_profile, **kwargs)
    encoded = base64.b64encode(img_bytes).decode("utf-8")
    return {"b64": encoded, "animated": animated}


@app.post("/levelup")
async def levelup(request: Request):
    form_data = await request.form()
    kwargs = get_kwargs(form_data)
    img_bytes, animated = await asyncio.to_thread(generate_level_img, **kwargs)
    encoded = base64.b64encode(img_bytes).decode("utf-8")
    return {"b64": encoded, "animated": animated}


@app.get("/health")
async def health():
    return {"status": "ok"}


def port_in_use(port: int) -> bool:
    for conn in psutil.net_connections():
        if conn.laddr.port == port:
            # Get the process name
            try:
                proc = psutil.Process(conn.pid)
                print(f"Process {proc.name()} is using port {port}")
            except psutil.NoSuchProcess:
                continue
            return True
    return False


def kill_process_on_port(port: int):
    """
    Find and kill the process that's using the specified port.
    """
    for proc in psutil.process_iter(["pid", "name"]):
        for conn in proc.connections(kind="inet"):
            if conn.laddr.port == port:
                try:
                    proc.terminate()  # Send SIGTERM signal
                    proc.wait(timeout=3)  # Wait for the process to terminate
                    log.warning(f"Killed process {proc.info['pid']} ({proc.info['name']}) using port {port}")
                    return True
                except Exception as e:
                    log.error(f"Failed to kill process {proc.info['pid']} ({proc.info['name']}): {e}")

    log.info(f"No process found using port {port}")
    return False


async def run(
    port: t.Optional[int] = 8888,
    log_dir: t.Optional[t.Union[Path, str]] = None,
) -> t.Union[mp.Process, asyncio.subprocess.Process]:
    if not port:
        port = 8888
    if log_dir:
        global LOG_DIR
        LOG_DIR = log_dir if isinstance(log_dir, Path) else Path(log_dir)

    # Check if port is being used
    if port_in_use(port):
        raise Exception("Port already in use")

    APP_DIR = str(ROOT)
    log.info(f"Running API from {APP_DIR}")
    log.info(f"Log directory: {LOG_DIR} (As Service: {SERVICE})")
    log.info(f"Spinning up {DEFAULT_WORKERS} workers on port {port} in 5s...")
    await asyncio.sleep(5)

    if IS_WINDOWS:
        kwargs = {
            "workers": DEFAULT_WORKERS,
            "port": port,
            "app_dir": APP_DIR,
            "log_config": LOGGING_CONFIG,
            "use_colors": False,
        }
        if SERVICE:
            kwargs["host"] = "0.0.0.0"
        log.info(f"Kwargs: {kwargs}")
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
        f"--port {port}",
        f"--app-dir {APP_DIR}",
    ]
    if SERVICE:
        cmd.append("--host 0.0.0.0")
    cmd = " ".join(cmd)
    log.info(f"Command: {cmd}")
    proc = await asyncio.create_subprocess_exec(*cmd.split(" "))

    global PROC
    PROC = proc
    return proc


def kill(proc: t.Union[mp.Process, asyncio.subprocess.Process]) -> None:
    try:
        parent = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        try:
            proc.terminate()
        except Exception as e:
            log.error("Failed to terminate process", exc_info=e)
        return
    for child in parent.children(recursive=True):
        child.kill()
    proc.terminate()


if __name__ == "__main__":
    """
    If running this script directly, spin up the API.

    Usage:
    python api.py [port] [log_dir]
    """

    logging.basicConfig(level=logging.INFO)
    loop = asyncio.ProactorEventLoop() if IS_WINDOWS else asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    log_dir = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        loop.create_task(run(port, log_dir))
        loop.run_forever()
    except KeyboardInterrupt:
        print("CTRL+C detected")
    except Exception as e:
        log.error("API failed to start", exc_info=e)
    finally:
        log.info("Shutting down API...")
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
