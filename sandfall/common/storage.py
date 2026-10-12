import asyncio
import logging
import os
import uuid
from pathlib import Path

log = logging.getLogger("red.vrt.sandfall.storage")


def write_atomic(path: Path, data: bytes) -> None:
    """Writes to a temporary file in the same folder and then swaps it in, so a crash never leaves half a file"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    except OSError as e:
        log.warning("Couldn't write %s", path, exc_info=e)
        temp.unlink(missing_ok=True)
        raise


def read_file(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


class Storage:
    """
    Sandfall's files under the cog's data folder: `worlds/<user id>.sand` for private worlds (they belong to the
    player, not the server) and `gallery/<server id>/<world id>.sand` and `.png` for the server galleries.
    """

    def __init__(self, root: Path):
        self.root = root

    def private_path(self, user_id: int) -> Path:
        return self.root / "worlds" / f"{int(user_id)}.sand"

    def gallery_path(self, guild_id: int, world_id: str) -> Path:
        return self.root / "gallery" / str(int(guild_id)) / f"{world_id}.sand"

    def png_path(self, guild_id: int, world_id: str) -> Path:
        return self.gallery_path(guild_id, world_id).with_suffix(".png")

    async def read_private(self, user_id: int) -> bytes | None:
        return await asyncio.to_thread(read_file, self.private_path(user_id))

    async def write_private(self, user_id: int, data: bytes) -> None:
        await asyncio.to_thread(write_atomic, self.private_path(user_id), data)

    async def delete_private(self, user_id: int) -> None:
        await asyncio.to_thread(self.private_path(user_id).unlink, missing_ok=True)

    async def write_gallery(self, guild_id: int, world_id: str, data: bytes, png: bytes) -> None:
        await asyncio.to_thread(write_atomic, self.png_path(guild_id, world_id), png)
        await asyncio.to_thread(write_atomic, self.gallery_path(guild_id, world_id), data)

    async def read_gallery(self, guild_id: int, world_id: str) -> bytes | None:
        return await asyncio.to_thread(read_file, self.gallery_path(guild_id, world_id))

    async def read_png(self, guild_id: int, world_id: str) -> bytes | None:
        return await asyncio.to_thread(read_file, self.png_path(guild_id, world_id))

    async def delete_gallery(self, guild_id: int, world_id: str) -> None:
        await asyncio.to_thread(self.gallery_path(guild_id, world_id).unlink, missing_ok=True)
        await asyncio.to_thread(self.png_path(guild_id, world_id).unlink, missing_ok=True)
