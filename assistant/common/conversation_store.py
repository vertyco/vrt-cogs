import json
import logging
import os
from pathlib import Path

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

    def path_for(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def save(self, key: str, data: dict) -> None:
        # Atomic write: a crash mid-write leaves the old file intact, not a truncated one.
        path = self.path_for(key)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
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
