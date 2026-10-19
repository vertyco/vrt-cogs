import gzip
import json
import logging
from pathlib import Path

log = logging.getLogger("red.vrt.blockblaster.levels")

PACK_DIR = Path(__file__).resolve().parent.parent / "web" / "levels"
PACK_SIZE = 100
LEVEL_COUNT = 2600

# pack number (1 to 26) -> {level number: compact level}; a pack stays here once opened
packs: dict[int, dict[int, dict]] = {}


def open_pack(pack_no: int) -> dict[int, dict]:
    path = PACK_DIR / f"pack-{pack_no:02d}.json.gz"
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        log.warning("Couldn't read level pack %s", path, exc_info=e)
        raise
    return {level["n"]: level for level in data["levels"]}


def load_level(n: int) -> dict:
    """The compact level number n (1 to 2,600), straight from its pack. Expand it with sim.level.expand."""
    if not 1 <= n <= LEVEL_COUNT:
        raise ValueError(f"Level {n} does not exist, levels run from 1 to {LEVEL_COUNT}")
    pack_no = (n - 1) // PACK_SIZE + 1
    if pack_no not in packs:
        packs[pack_no] = open_pack(pack_no)
    return packs[pack_no][n]
