import asyncio
import logging
import typing as t
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import chromadb
import chromadb.api
from chromadb.api.types import GetResult
from chromadb.errors import ChromaError

log = logging.getLogger("red.vrt.assistant.embedding_store")


class DimensionMismatchError(Exception):
    """Raised when embedding dimensions don't match the collection's existing dimensions."""

    def __init__(self, expected: int, got: int):
        self.expected = expected
        self.got = got
        super().__init__(f"Embedding dimension {got} does not match collection dimension {expected}")


class EmbeddingStore:
    """Persistent embedding storage backed by ChromaDB.

    All embedding data (vectors + metadata) lives in ChromaDB on disk.
    No embedding data is stored in Red's Config.

    All public methods are async to avoid blocking the event loop.
    """

    def __init__(self, data_path: Path):
        self.data_path = data_path / "chromadb"
        self._client: t.Optional[chromadb.api.ClientAPI] = None

    async def initialize(self) -> None:
        """Create the PersistentClient in a thread to avoid blocking."""

        def _init():
            self.data_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.data_path))

        await asyncio.to_thread(_init)

    @property
    def client(self) -> chromadb.api.ClientAPI:
        if self._client is None:
            raise RuntimeError("EmbeddingStore has not been initialized. Call await initialize() first.")
        return self._client

    # ---- collection helpers (sync, only called from within to_thread) ----

    def _get_or_create_collection(self, guild_id: int) -> chromadb.Collection:
        return self.client.get_or_create_collection(
            f"assistant-{guild_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def _get_collection(self, guild_id: int) -> t.Optional[chromadb.Collection]:
        try:
            return self.client.get_collection(f"assistant-{guild_id}")
        except (ChromaError, ValueError):
            return None

    # ---- read operations ----

    async def has_embeddings(self, guild_id: int) -> bool:
        def _check():
            collection = self._get_collection(guild_id)
            if not collection:
                return False
            return collection.count() > 0

        return await asyncio.to_thread(_check)

    async def count(self, guild_id: int) -> int:
        def _count():
            collection = self._get_collection(guild_id)
            if not collection:
                return 0
            return collection.count()

        return await asyncio.to_thread(_count)

    async def exists(self, guild_id: int, name: str) -> bool:
        def _exists():
            collection = self._get_collection(guild_id)
            if not collection:
                return False
            result = collection.get(ids=[name])
            return bool(result["ids"])

        return await asyncio.to_thread(_exists)

    async def get(self, guild_id: int, name: str) -> t.Optional[dict]:
        """Get a single embedding's metadata + vector by name.

        Returns dict with keys: text, ai_created, created, modified, model, dimensions, embedding
        """

        def _get():
            collection = self._get_collection(guild_id)
            if not collection:
                return None
            result = collection.get(ids=[name], include=["metadatas", "embeddings"])
            if not result["ids"]:
                return None
            metadatas = result["metadatas"]
            embeddings = result["embeddings"]
            meta = dict(metadatas[0]) if metadatas is not None and len(metadatas) > 0 else {}
            meta["embedding"] = embeddings[0] if embeddings is not None and len(embeddings) > 0 else []
            return meta

        return await asyncio.to_thread(_get)

    async def get_all_metadata(self, guild_id: int) -> dict[str, dict]:
        """Get all embeddings' metadata (no vectors).

        Returns: ``{name: {text, ai_created, created, modified, model, dimensions}}``
        """

        def _get():
            collection = self._get_collection(guild_id)
            if not collection:
                return {}
            data = collection.get(include=["metadatas"])
            metadatas = data["metadatas"]
            result: dict[str, dict] = {}
            for i, name in enumerate(data["ids"]):
                result[name] = dict(metadatas[i]) if metadatas is not None and len(metadatas) > 0 else {}
            return result

        return await asyncio.to_thread(_get)

    async def get_all_with_embeddings(self, guild_id: int) -> dict[str, dict]:
        """Get all embeddings including vectors (for resync / export).

        Returns: ``{name: {text, embedding, ai_created, created, modified, model, dimensions}}``
        """

        def _get():
            collection = self._get_collection(guild_id)
            if not collection:
                return {}
            data = collection.get(include=["metadatas", "embeddings"])
            metadatas = data["metadatas"]
            embeddings = data["embeddings"]
            result: dict[str, dict] = {}
            for i, name in enumerate(data["ids"]):
                meta = dict(metadatas[i]) if metadatas is not None and len(metadatas) > 0 else {}
                meta["embedding"] = list(embeddings[i]) if embeddings is not None and len(embeddings) > 0 else []
                result[name] = meta
            return result

        return await asyncio.to_thread(_get)

    # ---- write operations ----

    async def add(
        self,
        guild_id: int,
        name: str,
        text: str,
        embedding: list[float],
        model: str,
        ai_created: bool = False,
    ) -> None:
        """Add a new embedding.

        Raises:
            DimensionMismatchError: If dimensions differ from the collection's existing embeddings.
        """

        def _add():
            collection = self._get_or_create_collection(guild_id)
            now = datetime.now(tz=timezone.utc).isoformat()
            metadata = {
                "text": text,
                "ai_created": ai_created,
                "created": now,
                "modified": now,
                "model": model,
                "dimensions": len(embedding),
            }
            try:
                collection.upsert(ids=[name], embeddings=[embedding], metadatas=[metadata])
            except Exception as e:
                if "dimension" in str(e).lower():
                    existing = collection.peek(limit=1)
                    expected = (
                        len(existing["embeddings"][0]) if existing.get("embeddings") and existing["embeddings"] else 0
                    )
                    raise DimensionMismatchError(expected, len(embedding)) from e
                raise

        await asyncio.to_thread(_add)

    async def update(
        self,
        guild_id: int,
        name: str,
        text: str,
        embedding: list[float],
        model: str,
    ) -> None:
        """Update an existing embedding, preserving original creation metadata."""

        def _update():
            collection = self._get_collection(guild_id)
            if not collection:
                return False  # Signal to fall back to add
            # Preserve original creation date and ai_created flag
            existing = collection.get(ids=[name], include=["metadatas"])
            created = datetime.now(tz=timezone.utc).isoformat()
            ai_created = False
            if existing["ids"] and existing["metadatas"]:
                created = existing["metadatas"][0].get("created", created)
                ai_created = existing["metadatas"][0].get("ai_created", False)

            metadata = {
                "text": text,
                "ai_created": ai_created,
                "created": created,
                "modified": datetime.now(tz=timezone.utc).isoformat(),
                "model": model,
                "dimensions": len(embedding),
            }
            try:
                collection.upsert(ids=[name], embeddings=[embedding], metadatas=[metadata])
            except Exception as e:
                if "dimension" in str(e).lower():
                    existing_peek = collection.peek(limit=1)
                    expected = (
                        len(existing_peek["embeddings"][0])
                        if existing_peek.get("embeddings") and existing_peek["embeddings"]
                        else 0
                    )
                    raise DimensionMismatchError(expected, len(embedding)) from e
                raise
            return True

        result = await asyncio.to_thread(_update)
        if not result:
            await self.add(guild_id, name, text, embedding, model)

    async def delete(self, guild_id: int, name: str) -> None:
        def _delete():
            collection = self._get_collection(guild_id)
            if not collection:
                return
            try:
                collection.delete(ids=[name])
            except (ChromaError, ValueError):
                pass

        await asyncio.to_thread(_delete)

    async def delete_all(self, guild_id: int) -> None:
        """Delete all embeddings for a guild by dropping the collection."""

        def _delete():
            try:
                self.client.delete_collection(f"assistant-{guild_id}")
            except (ChromaError, ValueError):
                pass

        await asyncio.to_thread(_delete)

    # ---- query operations ----

    async def get_related(
        self,
        guild_id: int,
        query_embedding: list[float],
        top_n: int = 3,
        min_relatedness: float = 0.78,
    ) -> list[tuple[str, str, float, int]]:
        """Find related embeddings using cosine similarity.

        Returns: list of ``(name, text, relatedness, dimensions)``
        """
        if not query_embedding:
            return []

        def _query():
            collection = self._get_collection(guild_id)
            if not collection or collection.count() == 0:
                return []

            n_results = min(top_n, collection.count())
            if n_results == 0:
                return []

            # Check dimension compatibility
            existing: GetResult = collection.peek(limit=1)
            existing_embeddings = existing.get("embeddings")
            if existing_embeddings is not None and len(existing_embeddings) > 0:
                expected_dim = len(existing_embeddings[0])
                if len(query_embedding) != expected_dim:
                    log.warning(
                        f"Query embedding dimension {len(query_embedding)} != collection dimension {expected_dim} "
                        f"for guild {guild_id}. Skipping search."
                    )
                    return []

            start = perf_counter()
            try:
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=["metadatas", "distances"],
                )
            except Exception as e:
                log.error(f"Failed to query embeddings for guild {guild_id}: {e}")
                return []

            strings_and_relatedness: list[tuple[str, str, float, int]] = []
            for idx in range(len(results["ids"][0])):
                embed_name = results["ids"][0][idx]
                metadata = results["metadatas"][0][idx] if results["metadatas"] else {}
                distance = results["distances"][0][idx] if results["distances"] else 0.0
                relatedness = 1 - distance

                if relatedness >= min_relatedness:
                    dims = metadata.get("dimensions", 0)
                    strings_and_relatedness.append((embed_name, metadata.get("text", ""), relatedness, dims))

            elapsed = perf_counter() - start
            log.debug(f"Got {len(strings_and_relatedness)} related embeddings in {elapsed:.2f}s for guild {guild_id}")

            strings_and_relatedness.sort(key=lambda x: x[2], reverse=True)
            return strings_and_relatedness[:top_n]

        return await asyncio.to_thread(_query)

    # ---- maintenance operations ----

    async def recreate_collection(self, guild_id: int) -> None:
        """Delete and recreate a guild's collection (for dimension changes)."""
        await self.delete_all(guild_id)

    async def migrate_from_config(self, guild_id: int, embeddings: dict) -> int:
        """Migrate embeddings from old Config format to ChromaDB.

        Args:
            guild_id: The guild ID
            embeddings: Dict of ``name -> Embedding`` model instances (old format)

        Returns: Number of embeddings migrated
        """
        if not embeddings:
            return 0

        def _migrate():
            # Recreate collection synchronously since we're already in a thread
            try:
                self.client.delete_collection(f"assistant-{guild_id}")
            except (ChromaError, ValueError):
                pass
            collection = self._get_or_create_collection(guild_id)

            ids: list[str] = []
            vectors: list[list[float]] = []
            metadatas: list[dict] = []

            for name, em in embeddings.items():
                if isinstance(em, dict):
                    text = em.get("text", "")
                    embedding = em.get("embedding", [])
                    ai_created = em.get("ai_created", False)
                    created = em.get("created", datetime.now(tz=timezone.utc).isoformat())
                    modified = em.get("modified", datetime.now(tz=timezone.utc).isoformat())
                    model = em.get("model", "text-embedding-3-small")
                else:
                    text = em.text
                    embedding = em.embedding
                    ai_created = em.ai_created
                    created = em.created.isoformat() if hasattr(em.created, "isoformat") else str(em.created)
                    modified = em.modified.isoformat() if hasattr(em.modified, "isoformat") else str(em.modified)
                    model = em.model

                if not embedding:
                    log.warning(f"Skipping embedding '{name}' with no vector data during migration")
                    continue

                ids.append(name[:100])
                vectors.append(embedding)
                metadatas.append(
                    {
                        "text": text,
                        "ai_created": ai_created,
                        "created": created if isinstance(created, str) else str(created),
                        "modified": modified if isinstance(modified, str) else str(modified),
                        "model": model,
                        "dimensions": len(embedding),
                    }
                )

            if ids:
                batch_size = 5000
                for i in range(0, len(ids), batch_size):
                    collection.add(
                        ids=ids[i : i + batch_size],
                        embeddings=vectors[i : i + batch_size],
                        metadatas=metadatas[i : i + batch_size],
                    )
                log.info(f"Migrated {len(ids)} embeddings to persistent ChromaDB for guild {guild_id}")

            return len(ids)

        return await asyncio.to_thread(_migrate)
