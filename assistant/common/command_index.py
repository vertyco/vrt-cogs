import asyncio
import hashlib
import logging
import re
import typing as t

import chromadb
import discord
from chromadb.errors import ChromaError
from rapidfuzz import fuzz, process
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.commands.requires import PrivilegeLevel

from .embedding_store import EmbeddingStore

log = logging.getLogger("red.vrt.assistant.command_index")

DOC_MAX_CHARS = 2000
COLLECTION_PREFIX = "cmdindex-"


def sanitize_model_name(model: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "-", model).strip("._-")
    return cleaned or "unknown"


def collection_name_for_model(model: str) -> str:
    return f"{COLLECTION_PREFIX}{sanitize_model_name(model)}"[:512]


def get_privilege_hint(command: commands.Command) -> str:
    """Static human-readable hint of who can run a command, derived from Red's Requires."""
    requires = getattr(command, "requires", None)
    if requires is None:
        return "everyone"
    level = getattr(requires, "privilege_level", None)
    if level == PrivilegeLevel.BOT_OWNER:
        return "bot owner only"
    if level == PrivilegeLevel.GUILD_OWNER:
        return "guild owner only"
    if level == PrivilegeLevel.ADMIN:
        return "requires admin"
    if level == PrivilegeLevel.MOD:
        return "requires mod"
    user_perms: t.Optional[discord.Permissions] = getattr(requires, "user_perms", None)
    if user_perms is not None and user_perms.value:
        names = sorted(name for name, value in user_perms if value)
        if names:
            return "requires permissions: " + ", ".join(names)
    return "everyone"


async def member_can_run(bot: Red, command: commands.Command, member: discord.Member) -> bool:
    """can_run-style evaluation without a Context, using Red's Requires data."""
    if await bot.is_owner(member):
        return True
    requires = getattr(command, "requires", None)
    if requires is None:
        return True
    level = getattr(requires, "privilege_level", None)
    if level == PrivilegeLevel.BOT_OWNER:
        return False
    if level == PrivilegeLevel.GUILD_OWNER:
        return member.guild.owner_id == member.id
    if level == PrivilegeLevel.ADMIN:
        return member.guild_permissions.administrator or await bot.is_admin(member)
    if level == PrivilegeLevel.MOD:
        return member.guild_permissions.manage_messages or await bot.is_mod(member)
    user_perms = getattr(requires, "user_perms", None)
    if user_perms is not None and user_perms.value:
        return member.guild_permissions.is_superset(user_perms)
    return True


def build_command_doc(command: commands.Command) -> str:
    cog_name = command.cog.qualified_name if command.cog else "Core"
    lines = [f"Command: {command.qualified_name}"]
    if command.aliases:
        lines.append("Aliases: " + ", ".join(command.aliases))
    lines.append(f"Cog: {cog_name}")
    usage = f"[p]{command.qualified_name}"
    if command.signature:
        usage += f" {command.signature}"
    lines.append(f"Usage: {usage}")
    lines.append(f"Privilege: {get_privilege_hint(command)}")
    helptext = command.help or command.short_doc or ""
    if helptext:
        lines.append(f"Help: {helptext}")
    return "\n".join(lines)[:DOC_MAX_CHARS]


def build_command_documents(bot: Red) -> dict[str, dict]:
    """Walk all text commands and return {qualified_name: {text, hash, cog, privilege}}."""
    documents: dict[str, dict] = {}
    for command in bot.walk_commands():
        if command.qualified_name in documents:
            continue
        text = build_command_doc(command)
        documents[command.qualified_name] = {
            "text": text,
            "hash": hashlib.sha256(text.encode()).hexdigest(),
            "cog": command.cog.qualified_name if command.cog else "Core",
            "privilege": get_privilege_hint(command),
        }
    return documents


def fuzzy_search_commands(bot: Red, query: str, limit: int = 8) -> list[tuple[str, str, float]]:
    """Fallback when semantic search is unavailable. Returns (qualified_name, doc_text, score 0-100)."""
    documents = build_command_documents(bot)
    choices = {name: f"{name} {data['text']}" for name, data in documents.items()}
    results = process.extract(query, choices, scorer=fuzz.WRatio, limit=limit)
    return [(key, documents[key]["text"], float(score)) for match, score, key in results]


class CommandIndexStore:
    """Command index collections living in the same ChromaDB instance as EmbeddingStore.

    One collection per embedding model: cmdindex-<sanitized-model>.
    All public methods are async (ChromaDB calls run in a thread).
    """

    def __init__(self, embedding_store: EmbeddingStore):
        self.store = embedding_store

    @property
    def client(self) -> chromadb.api.ClientAPI:
        return self.store.client

    async def list_collections(self) -> list[str]:
        def run():
            try:
                return [c.name for c in self.client.list_collections() if c.name.startswith(COLLECTION_PREFIX)]
            except (ChromaError, ValueError):
                return []

        return await asyncio.to_thread(run)

    async def count(self, collection_name: str) -> int:
        def run():
            try:
                return self.client.get_collection(collection_name).count()
            except (ChromaError, ValueError):
                return 0

        return await asyncio.to_thread(run)

    async def get_hashes(self, collection_name: str) -> dict[str, str]:
        def run():
            try:
                collection = self.client.get_collection(collection_name)
            except (ChromaError, ValueError):
                return {}
            data = collection.get(include=["metadatas"])
            metadatas = data["metadatas"]
            result: dict[str, str] = {}
            for i, name in enumerate(data["ids"]):
                meta = dict(metadatas[i]) if metadatas is not None and len(metadatas) > 0 else {}
                result[name] = meta.get("hash", "")
            return result

        return await asyncio.to_thread(run)

    async def upsert(self, collection_name: str, entries: list[dict], embeddings: list[list[float]]) -> None:
        """entries: [{qualified_name, text, hash, cog, privilege}], parallel to embeddings."""
        if not entries:
            return

        def run():
            collection = self.client.get_or_create_collection(collection_name, metadata={"hnsw:space": "cosine"})
            collection.upsert(
                ids=[e["qualified_name"] for e in entries],
                embeddings=embeddings,
                metadatas=[
                    {"text": e["text"], "hash": e["hash"], "cog": e["cog"], "privilege": e["privilege"]}
                    for e in entries
                ],
            )

        await asyncio.to_thread(run)

    async def delete_ids(self, collection_name: str, ids: list[str]) -> None:
        if not ids:
            return

        def run():
            try:
                self.client.get_collection(collection_name).delete(ids=ids)
            except (ChromaError, ValueError):
                pass

        await asyncio.to_thread(run)

    async def drop(self, collection_name: str) -> None:
        def run():
            try:
                self.client.delete_collection(collection_name)
            except (ChromaError, ValueError):
                pass

        await asyncio.to_thread(run)

    async def query(
        self, collection_name: str, query_embedding: list[float], top_k: int = 8
    ) -> list[tuple[str, str, float]]:
        """Returns [(qualified_name, doc_text, relatedness)] sorted by relevance."""
        if not query_embedding:
            return []

        def run():
            try:
                collection = self.client.get_collection(collection_name)
            except (ChromaError, ValueError):
                return []
            total = collection.count()
            if total == 0:
                return []
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, total),
                include=["metadatas", "distances"],
            )
            hits: list[tuple[str, str, float]] = []
            for idx in range(len(results["ids"][0])):
                name = results["ids"][0][idx]
                metadata = results["metadatas"][0][idx] if results["metadatas"] else {}
                distance = results["distances"][0][idx] if results["distances"] else 0.0
                hits.append((name, metadata.get("text", ""), 1 - distance))
            return hits

        return await asyncio.to_thread(run)
