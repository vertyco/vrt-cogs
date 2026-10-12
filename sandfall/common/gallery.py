import asyncio
import logging
import re
import secrets
import time

from redbot.core import Config
from redbot.core.bot import Red

from .storage import Storage
from .worldfile import check_png, check_world, clean_name, to_text

log = logging.getLogger("red.vrt.sandfall.gallery")

LIMIT = 25
SORTS = ("new", "liked", "mine")
NOT_IN_SERVER = "The gallery works inside a Discord server."
WORLD_GONE = "That world isn't in the gallery any more."
CANT_DELETE = "Only the maker or a server admin can delete this world."
NEED_NAME = "Give the world a name first."
ID_PATTERN = re.compile(r"[0-9a-f]{12}")


def valid_id(world_id: object) -> bool:
    """Whether a world id from a page is exactly 12 lowercase hex digits, so it can never reach a path as anything else"""
    return isinstance(world_id, str) and ID_PATTERN.fullmatch(world_id) is not None


class Gallery:
    """
    Each Discord server's gallery of saved worlds. Config holds the list (name, maker, date, likes) and the files are
    in Storage. Every change to the list runs under one lock, so two saves or likes at once can't undo each other.
    """

    def __init__(self, config: Config, storage: Storage, bot: Red):
        self.config = config
        self.storage = storage
        self.bot = bot
        self.lock = asyncio.Lock()

    async def is_admin(self, ctx) -> bool:
        """The bot owner, the server owner, and members with Manage Server or Red's admin role"""
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id or await self.bot.is_owner(ctx.author):
            return True
        member = ctx.guild.get_member(ctx.author.id)
        return member is not None and (member.guild_permissions.manage_guild or await self.bot.is_admin(member))

    async def list(self, ctx, sort: object) -> dict:
        if ctx.guild is None:
            return {"error": NOT_IN_SERVER}
        sort = sort if sort in SORTS else "new"
        user_id = ctx.author.id
        entries = await self.config.guild(ctx.guild).gallery()
        mine = sum(1 for entry in entries.values() if entry["maker"] == user_id)
        admin = await self.is_admin(ctx)
        # Newest first to start with, so worlds made in the same second keep that order through the sort
        shown = [
            (world_id, entry)
            for world_id, entry in reversed(entries.items())
            if sort != "mine" or entry["maker"] == user_id
        ]
        if sort == "liked":
            shown.sort(key=lambda item: (len(item[1]["likes"]), item[1]["made"]), reverse=True)
        else:
            shown.sort(key=lambda item: item[1]["made"], reverse=True)
        worlds = [
            {
                "id": world_id,
                "name": entry["name"],
                "maker": {"id": str(entry["maker"]), "name": entry["maker_name"]},
                "made": entry["made"],
                "likes": len(entry["likes"]),
                "liked": user_id in entry["likes"],
                "mine": entry["maker"] == user_id,
                "can_delete": admin or entry["maker"] == user_id,
            }
            for world_id, entry in shown
        ]
        return {"worlds": worlds, "mine": mine, "limit": LIMIT}

    async def save(self, ctx, name: object, snap: object, png: object) -> dict:
        if ctx.guild is None:
            return {"error": NOT_IN_SERVER}
        name = clean_name(name)
        if not name:
            return {"error": NEED_NAME}
        try:
            data = await asyncio.to_thread(check_world, snap)
            picture = await asyncio.to_thread(check_png, png)
        except ValueError as e:
            return {"error": str(e)}
        user_id = ctx.author.id
        async with self.lock:
            async with self.config.guild(ctx.guild).gallery() as entries:
                if sum(1 for entry in entries.values() if entry["maker"] == user_id) >= LIMIT:
                    return {"ok": False, "reason": "full", "limit": LIMIT}
                world_id = secrets.token_hex(6)
                while world_id in entries:
                    world_id = secrets.token_hex(6)
                await self.storage.write_gallery(ctx.guild.id, world_id, data, picture)
                entries[world_id] = {
                    "name": name,
                    "maker": user_id,
                    "maker_name": clean_name(ctx.author.display_name) or "Someone",
                    "made": int(time.time()),
                    "likes": [],
                }
        return {"id": world_id}

    async def load(self, ctx, world_id: object) -> dict:
        if ctx.guild is None:
            return {"error": NOT_IN_SERVER}
        if not valid_id(world_id):
            return {"error": WORLD_GONE}
        entries = await self.config.guild(ctx.guild).gallery()
        data = await self.storage.read_gallery(ctx.guild.id, world_id) if world_id in entries else None
        if data is None:
            return {"error": WORLD_GONE}
        return {"snap": to_text(data)}

    async def like(self, ctx, world_id: object) -> dict:
        """Likes the world, or takes the like back when this player already liked it"""
        if ctx.guild is None:
            return {"error": NOT_IN_SERVER}
        if not valid_id(world_id):
            return {"error": WORLD_GONE}
        async with self.lock:
            async with self.config.guild(ctx.guild).gallery() as entries:
                entry = entries.get(world_id)
                if entry is None:
                    return {"error": WORLD_GONE}
                likes = entry["likes"]
                liked = ctx.author.id not in likes
                if liked:
                    likes.append(ctx.author.id)
                else:
                    likes.remove(ctx.author.id)
                return {"likes": len(likes), "liked": liked}

    async def delete(self, ctx, world_id: object) -> dict:
        if ctx.guild is None:
            return {"error": NOT_IN_SERVER}
        if not valid_id(world_id):
            return {"error": WORLD_GONE}
        admin = await self.is_admin(ctx)
        async with self.lock:
            async with self.config.guild(ctx.guild).gallery() as entries:
                entry = entries.get(world_id)
                if entry is None:
                    return {"error": WORLD_GONE}
                if entry["maker"] != ctx.author.id and not admin:
                    return {"error": CANT_DELETE}
                del entries[world_id]
            await self.storage.delete_gallery(ctx.guild.id, world_id)
        return {"ok": True}

    async def picture(self, ctx, world_id: object) -> bytes | None:
        """The PNG of a world in the player's own server, or None when there is none"""
        if ctx.guild is None or not valid_id(world_id):
            return None
        return await self.storage.read_png(ctx.guild.id, world_id)

    async def forget_user(self, user_id: int) -> None:
        """Removes a player's worlds (and their files) from every server, and their likes from everyone else's"""
        async with self.lock:
            for guild_id in await self.config.all_guilds():
                async with self.config.guild_from_id(guild_id).gallery() as entries:
                    gone = [world_id for world_id, entry in entries.items() if entry["maker"] == user_id]
                    for world_id in gone:
                        del entries[world_id]
                    for entry in entries.values():
                        if user_id in entry["likes"]:
                            entry["likes"].remove(user_id)
                for world_id in gone:
                    await self.storage.delete_gallery(guild_id, world_id)
