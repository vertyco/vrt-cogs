import json
import logging
import os
import threading
from pathlib import Path
from uuid import uuid4

log = logging.getLogger("red.vrt.assistant.conversation_store")


class ConversationStore:
    """One JSON file per conversation under <base>/conversations/.

    Pure dict<->file persistence: callers pass and receive plain dicts
    (Conversation.model_dump(mode="json") in, dict out for model_validate).
    Sidesteps Red's whole-file Config driver so each save is a tiny write.
    """

    def __init__(self, base_path: Path):
        self.dir = Path(base_path) / "conversations"
        self.dir.mkdir(parents=True, exist_ok=True)
        # Per-key locks so concurrent saves for the same key are serialized.
        # A unique temp name per call keeps different keys fully independent.
        self.locks: dict[str, threading.Lock] = {}
        self.locks_guard = threading.Lock()

    def lock_for(self, key: str) -> threading.Lock:
        with self.locks_guard:
            if key not in self.locks:
                self.locks[key] = threading.Lock()
            return self.locks[key]

    def path_for(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def save(self, key: str, data: dict) -> None:
        # Atomic write with a unique temp name so concurrent saves for the same
        # key can't collide (the loser of os.replace would otherwise hit FileNotFoundError).
        # A per-key lock serializes concurrent saves for the same key (required on Windows
        # where os.replace raises PermissionError if the destination is being replaced
        # simultaneously by another thread).
        path = self.path_for(key)
        tmp = self.dir / f"{key}.{uuid4().hex}.json.tmp"
        tmp.write_text(json.dumps(data), encoding="utf-8")
        with self.lock_for(key):
            os.replace(tmp, path)

    def delete(self, key: str) -> None:
        self.path_for(key).unlink(missing_ok=True)

    def clear(self) -> None:
        for f in self.dir.glob("*.json"):
            f.unlink(missing_ok=True)
        for f in self.dir.glob("*.json.tmp"):
            f.unlink(missing_ok=True)

    def load_all(self) -> dict:
        out: dict = {}
        for f in self.dir.glob("*.json"):
            try:
                out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                log.error("Skipping unreadable conversation file %s: %s", f.name, e)
        return out
