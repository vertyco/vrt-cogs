import gc
import logging
import sys
import typing as t
from inspect import isframe

from pympler import muppy, summary
from pympler.util import stringutils
from redbot.core.bot import Red
from tabulate import tabulate

log = logging.getLogger("red.vrt.profiler.mem_profiler")


def get_objects() -> t.List[t.Any]:
    def _ignore(obj: t.Any) -> bool:
        try:
            return isframe(obj)
        except Exception:
            return True

    gc.collect()

    tmp = [o for o in gc.get_objects() if not _ignore(o)]

    res = []
    for o in tmp:
        refs = muppy.get_referents(o)
        for ref in refs:
            if not gc.is_tracked(ref):
                res.append(ref)

    res = muppy._remove_duplicates(res)

    return res


def profile_memory(limit: int = 15) -> str:
    objects = get_objects()
    summaries = summary.summarize(objects)

    rows = []
    for i in sorted(summaries, key=lambda x: x[2], reverse=True)[:limit]:
        class_desc, count, size = i
        class_name = class_desc.split(":", 1)[0] if ":" in class_desc else class_desc
        if len(class_name) > 30:
            class_name = class_name[:27] + "..."

        rows.append([class_name, count, stringutils.pp(size)])

    return tabulate(rows, headers=["types", "objects", "total size"])


def _sizeof_recursive(obj: t.Any, seen: t.Set[int], depth: int = 0, max_depth: int = 30) -> int:
    """Recursively calculate the size of an object and its references.

    Args:
        obj: The object to measure
        seen: Set of object ids already counted (for cycle detection)
        depth: Current recursion depth
        max_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        Size in bytes of the object and its children
    """
    if depth > max_depth:
        return 0

    obj_id = id(obj)
    if obj_id in seen:
        return 0
    seen.add(obj_id)

    size = 0
    try:
        size = sys.getsizeof(obj)
    except (TypeError, ValueError):
        return 0

    # Handle common container types
    if isinstance(obj, dict):
        for k, v in obj.items():
            size += _sizeof_recursive(k, seen, depth + 1, max_depth)
            size += _sizeof_recursive(v, seen, depth + 1, max_depth)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            size += _sizeof_recursive(item, seen, depth + 1, max_depth)
    elif isinstance(obj, (str, bytes, bytearray, int, float, bool, type(None))):
        # Primitives - already counted by getsizeof, no children
        pass
    elif hasattr(obj, "__dict__") and not isinstance(obj, type):
        # Instance objects - traverse __dict__
        try:
            for v in obj.__dict__.values():
                size += _sizeof_recursive(v, seen, depth + 1, max_depth)
        except Exception:
            pass
    elif hasattr(obj, "__slots__"):
        for slot in getattr(obj, "__slots__", []):
            try:
                size += _sizeof_recursive(getattr(obj, slot), seen, depth + 1, max_depth)
            except AttributeError:
                pass

    return size


def _get_excluded_ids(bot: Red) -> t.Set[int]:
    """Get IDs of objects that should be excluded from cog memory counting.

    This includes the bot instance and its direct attributes to avoid
    counting shared infrastructure.
    """
    excluded: t.Set[int] = {id(bot)}

    # Exclude bot's direct attributes (guilds, users, channels, etc.)
    if hasattr(bot, "__dict__"):
        for attr_value in bot.__dict__.values():
            excluded.add(id(attr_value))

    return excluded


def _measure_cog(cog_instance: t.Any, excluded_ids: t.Set[int]) -> int:
    """Measure the memory footprint of a single cog.

    Each cog is measured independently with its own seen set,
    but with shared bot-related objects pre-excluded.

    Args:
        cog_instance: The cog to measure
        excluded_ids: Set of object IDs to skip (bot and its attributes)

    Returns:
        Size in bytes
    """
    # Fresh seen set for this cog, pre-populated with exclusions
    seen: t.Set[int] = excluded_ids.copy()

    cog_id = id(cog_instance)
    if cog_id in seen:
        return 0
    seen.add(cog_id)

    size = sys.getsizeof(cog_instance)

    # Traverse the cog's __dict__ (its instance attributes)
    if hasattr(cog_instance, "__dict__"):
        for attr_name, attr_value in cog_instance.__dict__.items():
            # Skip bot references by isinstance check
            if isinstance(attr_value, Red):
                continue
            size += _sizeof_recursive(attr_value, seen, depth=0, max_depth=50)

    return size


def profile_cog_memory(bot: Red, limit: int = 0) -> str:
    """Profile memory usage per cog.

    Each cog is measured independently to show its full memory footprint.
    The bot instance and its direct attributes are excluded to avoid
    counting shared infrastructure.

    Note: Shared objects between cogs (like Config internals) may be
    counted multiple times. This is intentional - it shows the memory
    each cog is "responsible for" rather than unique bytes.

    Args:
        bot: The Red bot instance
        limit: Maximum number of cogs to display (0 for all)

    Returns:
        A formatted table string showing cog memory usage
    """
    gc.collect()

    # Get IDs to exclude (bot and its direct children)
    excluded_ids = _get_excluded_ids(bot)

    cog_sizes: t.List[t.Tuple[str, int]] = []
    for cog_name, cog_instance in bot.cogs.items():
        try:
            size = _measure_cog(cog_instance, excluded_ids)
            cog_sizes.append((cog_name, size))
        except Exception as e:
            log.debug(f"Failed to get size of cog {cog_name}: {e}")
            cog_sizes.append((cog_name, 0))

    # Sort by size descending
    cog_sizes.sort(key=lambda x: x[1], reverse=True)

    # Apply limit (0 means all)
    display_cogs = cog_sizes if limit <= 0 else cog_sizes[:limit]

    rows = []
    total_size = 0
    for cog_name, size in display_cogs:
        total_size += size
        rows.append([cog_name, stringutils.pp(size)])

    # Add total row
    rows.append(["─" * 20, "─" * 10])
    rows.append(["TOTAL", stringutils.pp(total_size)])

    return tabulate(rows, headers=["Cog", "Memory"])
