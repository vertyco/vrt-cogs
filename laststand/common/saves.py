import asyncio
import base64
import binascii
import json
import logging
import os
import secrets
import shutil
import tempfile
import weakref
import zlib
from pathlib import Path

log = logging.getLogger("red.vrt.laststand.saves")

SLOTS = (1, 2, 3)
MAX_PACKED = 900 * 1024
MAX_UNPACKED = 4 * 1024 * 1024
# Base64 text of the largest allowed save, so an oversized body is refused before it is decoded
MAX_TEXT = (MAX_PACKED + 2) // 3 * 4
MODES = ("runAndGun", "survivor")
MAX_LOOK_KEYS = 16
MAX_LOOK_TEXT = 32
MAX_DAY = 1_000_000
# The largest whole number a page's JavaScript holds exactly
MAX_SAFE = 2**53
# A slot written while it has no file starts at a random revision in this range, so a page still holding a revision
# from before the file went (a player's data deleted) can't match the new one by chance. Increments stay under MAX_SAFE
FIRST_REVISION = 2**32
FIRST_REVISION_SPAN = 2**51

TOO_BIG = "That save is too big to keep."
BAD_SLOT = "That save slot does not exist."
BAD_SAVE = "That save could not be read."


class SaveError(Exception):
    """A save the bot refuses, with a message the player can read"""


def text_within(value: object, limit: int) -> bool:
    """Text up to limit characters that can be sent as UTF-8 (a lone surrogate can't, and breaks the reply)"""
    if not isinstance(value, str) or len(value) > limit:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def safe_number(value: object) -> bool:
    """A number the page reads exactly. NaN and the infinities fail the comparison too"""
    return isinstance(value, int | float) and not isinstance(value, bool) and abs(value) <= MAX_SAFE


def clean_look(look: object) -> dict:
    if not isinstance(look, dict) or len(look) > MAX_LOOK_KEYS:
        raise SaveError(BAD_SAVE)
    for key, value in look.items():
        if not text_within(key, MAX_LOOK_TEXT):
            raise SaveError(BAD_SAVE)
        if not (text_within(value, MAX_LOOK_TEXT) or safe_number(value)):
            raise SaveError(BAD_SAVE)
    return dict(look)


def clean_summary(summary: object) -> dict:
    """The summary the slot panels show, cut down to the fields the bot knows"""
    if not isinstance(summary, dict):
        raise SaveError(BAD_SAVE)
    level = summary.get("level")
    day = summary.get("day")
    valid = (
        text_within(summary.get("name"), 64)
        and whole_number(level)
        and 1 <= level <= 30
        and whole_number(day)
        and 0 <= day <= MAX_DAY
        and text_within(summary.get("area"), 60)
        and text_within(summary.get("street"), 60)
        and summary.get("mode") in MODES
        and isinstance(summary.get("hardcore"), bool)
        and isinstance(summary.get("headshots"), bool)
    )
    if not valid:
        raise SaveError(BAD_SAVE)
    return {
        "name": summary["name"],
        "level": level,
        "area": summary["area"],
        "street": summary["street"],
        "day": day,
        "mode": summary["mode"],
        "hardcore": summary["hardcore"],
        "headshots": summary["headshots"],
        "look": clean_look(summary.get("look")),
    }


def unpack(raw: bytes) -> dict:
    """The save inside gzip bytes, unpacked in a bounded way so a small file can't swell into memory"""
    if len(raw) > MAX_PACKED:
        raise SaveError(TOO_BIG)
    stream = zlib.decompressobj(wbits=31)
    try:
        out = stream.decompress(raw, MAX_UNPACKED + 1)
    except zlib.error as e:
        raise SaveError(BAD_SAVE) from e
    if len(out) > MAX_UNPACKED:
        raise SaveError(TOO_BIG)
    if not stream.eof or stream.unused_data:
        raise SaveError(BAD_SAVE)
    try:
        save = json.loads(out)
    except (ValueError, RecursionError) as e:
        raise SaveError(BAD_SAVE) from e
    if not isinstance(save, dict) or save.get("v") != 1 or not isinstance(save.get("data"), dict):
        raise SaveError(BAD_SAVE)
    return save


def check_slot(slot: object) -> int:
    if not whole_number(slot) or slot not in SLOTS:
        raise SaveError(BAD_SLOT)
    return slot


def decode(text: object) -> bytes:
    if not isinstance(text, str):
        raise SaveError(BAD_SAVE)
    if len(text) > MAX_TEXT:
        raise SaveError(TOO_BIG)
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as e:
        raise SaveError(BAD_SAVE) from e


def check_revision(revision: object) -> None:
    if not isinstance(revision, int) or isinstance(revision, bool) or not 0 <= revision <= MAX_SAFE:
        raise SaveError(BAD_SAVE)


def check_and_decode(text: object) -> bytes:
    raw = decode(text)
    clean_summary(unpack(raw).get("summary"))
    return raw


def write_atomic(path: Path, raw: bytes) -> None:
    """Write beside the old file and rename over it, so a crash never leaves half a save"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    except Exception as e:
        log.warning("Could not write %s", path, exc_info=e)
        temp.unlink(missing_ok=True)
        raise


def read_record(path: Path) -> tuple[int, bytes | None]:
    """A slot's revision and its save's gzip bytes, from the one file that holds both: the revision as text, a newline,
    then the save. (0, None) for a slot never written; an emptied slot keeps its revision with nothing after it"""
    try:
        record = path.read_bytes()
    except FileNotFoundError:
        return 0, None
    head, _, raw = record.partition(b"\n")
    try:
        revision = int(head)
    except ValueError as e:
        log.warning("Could not read the slot at %s", path, exc_info=e)
        return 0, None
    return revision, raw or None


def read_slot(path: Path) -> tuple[dict | None, int]:
    """A slot's summary for the slot list (None for an empty one) and its revision. A slot that can't be read or holds
    a save the bot refuses is listed as empty, so it never stops the list of the others"""
    try:
        revision, raw = read_record(path)
    except OSError as e:
        log.warning("Could not read the slot at %s", path, exc_info=e)
        return None, 0
    if raw is None:
        return None, revision
    try:
        return clean_summary(unpack(raw).get("summary")), revision
    except Exception as e:
        log.warning("Could not read the save at %s", path, exc_info=e)
        return None, revision


class SaveStore:
    """Three save slots per Discord user, each one file holding its revision and the gzip bytes the page sent.

    Every save and wipe moves the revision on by one. A page sends the revision it last heard of, so a device that fell
    behind can't overwrite newer progress or bring back a wiped slot. A wipe keeps the revision. The revision and the
    save are replaced together in one write, so a crash can't change one without the other.
    """

    def __init__(self, root: Path):
        self.root = root
        # One lock per player, so two windows can't interleave a read and a write. A lock nobody holds or waits for
        # is let go, so the map doesn't keep one for every player who ever played
        self.locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()

    def lock(self, user_id: int) -> asyncio.Lock:
        lock = self.locks.get(user_id)
        if lock is None:
            lock = self.locks[user_id] = asyncio.Lock()
        return lock

    def folder(self, user_id: int) -> Path:
        return self.root / str(int(user_id))

    def path(self, user_id: int, slot: int) -> Path:
        return self.folder(user_id) / f"slot{slot}.save"

    def read_slots(self, user_id: int) -> tuple[list[dict | None], list[int]]:
        found = [read_slot(self.path(user_id, slot)) for slot in SLOTS]
        return [summary for summary, _ in found], [revision for _, revision in found]

    def replace(self, user_id: int, slot: int, revision: int, raw: bytes | None) -> tuple[bool, int]:
        """Under the player's lock: raw goes over the slot (None empties it) and the revision moves on, only when the
        page's revision is the slot's. Returns (True, the new revision), or (False, the slot's revision) when the slot
        moved on and nothing changed"""
        path = self.path(user_id, slot)
        current = read_record(path)[0]
        if revision != current:
            return False, current
        following = current + 1 if current else FIRST_REVISION + secrets.randbelow(FIRST_REVISION_SPAN)
        write_atomic(path, str(following).encode("ascii") + b"\n" + (raw or b""))
        return True, following

    async def summaries(self, user_id: int) -> tuple[list[dict | None], list[int]]:
        """Each slot's summary (None for an empty one) and its revision"""
        async with self.lock(user_id):
            return await asyncio.to_thread(self.read_slots, user_id)

    async def load(self, user_id: int, slot: int) -> tuple[str | None, int]:
        """The slot's save in base64 (None for an empty slot) and its revision"""
        path = self.path(user_id, check_slot(slot))
        async with self.lock(user_id):
            revision, raw = await asyncio.to_thread(read_record, path)
        if raw is None:
            return None, revision
        return base64.b64encode(raw).decode("ascii"), revision

    async def save(self, user_id: int, slot: int, b64: str, revision: int) -> tuple[bool, int]:
        """Keeps a save. Returns (True, the slot's new revision), or (False, its revision) when another device saved or
        wiped it first"""
        check_slot(slot)
        check_revision(revision)
        raw = await asyncio.to_thread(check_and_decode, b64)
        async with self.lock(user_id):
            return await asyncio.to_thread(self.replace, user_id, slot, revision, raw)

    async def wipe(self, user_id: int, slot: int, revision: int) -> tuple[bool, int]:
        """Empties a slot. Returns (True, its new revision), or (False, its revision) when another device saved or
        wiped it first"""
        check_slot(slot)
        check_revision(revision)
        async with self.lock(user_id):
            return await asyncio.to_thread(self.replace, user_id, slot, revision, None)

    async def delete_user(self, user_id: int) -> None:
        folder = self.folder(user_id)
        async with self.lock(user_id):
            try:
                await asyncio.to_thread(shutil.rmtree, folder)
            except FileNotFoundError:
                pass
