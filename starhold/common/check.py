"""
Checking a Starhold run's score without running the game in the bot.

A check starts common/replay.py as its own short-lived Python program, hands it the run on stdin and reads the result
it prints. The bot's process only waits on it, like waiting on a web request, and never loads V8 itself. Checks run
one at a time, each with a time limit, so a busy evening can't pile up programs on the bot's machine.

The program runs in isolated mode (-I): the current folder and the user's own packages stay off its path, so a file
planted there can't take part. Red installs the cogs' requirements, mini-racer among them, into a folder of its own
outside site-packages, which isolated mode also hides, so the boot line adds that folder back after the standard
library, where Red puts it too, so nothing in it can shadow a standard module.
"""

import asyncio
import importlib.util
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("red.vrt.starhold.check")

REPLAY = Path(__file__).with_name("replay.py")
# Covers starting the program and replaying the run together
TIME_LIMIT = 20
# Run as python -I -c BOOT <folder> <program>: adds the folder holding mini-racer to the end of the path, then runs the
# program as if it had been started directly
BOOT = (
    'import runpy, sys; sys.argv[1] and sys.path.append(sys.argv[1]); runpy.run_path(sys.argv[2], run_name="__main__")'
)
CHECK_FAILED = "Couldn't check this run, so it can't be cashed in."
# The bot can't check any run (mini-racer isn't installed): no fault of the run's, so it is checked again when next
# asked, once the bot's owner has installed it
UNAVAILABLE = {"error": CHECK_FAILED, "retry": True}
# What the rules' summary() prints, and nothing else
RESULT_KEYS = {"score", "wave", "lives", "step", "over"}


def requirement_folder() -> str | None:
    """The folder that holds mini-racer, found without importing it, or None when it isn't installed"""
    spec = importlib.util.find_spec("py_mini_racer")
    if spec is None or not spec.submodule_search_locations:
        return None
    return str(Path(list(spec.submodule_search_locations)[0]).parent)


def right_types(result: dict) -> bool:
    """Whole numbers for score, wave, lives and step, and a real true/false for over (bool counts as int otherwise)"""
    numbers = all(type(result[key]) is int for key in ("score", "wave", "lives", "step"))
    return numbers and type(result["over"]) is bool


def read_result(out: bytes) -> dict:
    """The program's printed result, or an error when it isn't exactly the shape the rules print"""
    try:
        result = json.loads(out.decode())
    except ValueError as e:
        log.error("A Starhold check printed something that isn't JSON", exc_info=e)
        return {"error": CHECK_FAILED}
    if not isinstance(result, dict) or set(result) != RESULT_KEYS or not right_types(result):
        log.error("A Starhold check printed an unexpected result: %r", result)
        return {"error": CHECK_FAILED}
    return result


class Checker:
    """Runs checks one at a time, each in its own program with a time limit"""

    def __init__(self, program: Path = REPLAY, limit: float = TIME_LIMIT):
        self.program = program
        self.limit = limit
        self.lock = asyncio.Lock()
        # The program running now, so unloading the cog can stop it
        self.proc: asyncio.subprocess.Process | None = None

    async def check(self, seed: int, moves: list, end: int) -> dict:
        """The replay's {score, wave, lives, step, over}, or {"error": text} when the run couldn't be checked"""
        folder = requirement_folder()
        if folder is None:
            log.error("Can't check Starhold runs: mini-racer isn't installed. Install it with [p]pipinstall mini-racer")
            return dict(UNAVAILABLE)
        data = json.dumps({"seed": seed, "moves": moves, "end": end}).encode()
        # Later checks wait their turn here
        async with self.lock:
            try:
                return await self.run(folder, data)
            except OSError as e:
                log.error("Couldn't start a Starhold check", exc_info=e)
                return {"error": CHECK_FAILED}

    async def run(self, folder: str, data: bytes) -> dict:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            BOOT,
            folder,
            str(self.program),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.proc = proc
        try:
            out, err = await asyncio.wait_for(proc.communicate(data), self.limit)
        except asyncio.TimeoutError as e:
            log.error("A Starhold check took longer than %s seconds and was stopped", self.limit, exc_info=e)
            return {"error": CHECK_FAILED}
        finally:
            # Also runs when the waiting task is cancelled, so no program outlives its check
            await self.stop(proc)
            self.proc = None
        if proc.returncode != 0:
            log.error("A Starhold check failed: %s", err.decode(errors="replace").strip()[-2000:])
            return {"error": CHECK_FAILED}
        return read_result(out)

    async def close(self) -> None:
        """Stops a check that is running, when the cog unloads"""
        if self.proc is not None:
            await self.stop(self.proc)

    @staticmethod
    async def stop(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            proc.kill()
        except ProcessLookupError as e:
            log.debug("A Starhold check had already ended", exc_info=e)
        await proc.wait()
