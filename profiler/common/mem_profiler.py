import gc
import logging
import sys
import typing as t
from inspect import isframe

from pympler import muppy, summary
from pympler.util import stringutils
from tabulate import tabulate

if t.TYPE_CHECKING:
    from redbot.core.bot import Red

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
        seen: Set of object ids already counted (shared across calls)
        depth: Current recursion depth
        max_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        Size in bytes of newly seen objects only
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


def profile_cog_memory(bot: "Red", limit: int = 25) -> str:
    """Profile memory usage per cog.

    Calculates the unique memory footprint of each cog by tracking object IDs
    across all cogs. Shared objects (like self.bot) are only counted once,
    attributed to whichever cog is processed first.

    Args:
        bot: The Red bot instance
        limit: Maximum number of cogs to display

    Returns:
        A formatted table string showing cog memory usage
    """
    gc.collect()

    # Shared seen set - objects are only counted once across ALL cogs
    seen: t.Set[int] = set()

    # Pre-mark the bot instance as seen so it's not counted for any cog
    # This gives a cleaner picture of what each cog uniquely owns
    seen.add(id(bot))

    cog_sizes: t.List[t.Tuple[str, int]] = []
    for cog_name, cog_instance in bot.cogs.items():
        try:
            # Mark the cog instance itself
            cog_id = id(cog_instance)
            if cog_id in seen:
                cog_sizes.append((cog_name, 0))
                continue
            seen.add(cog_id)

            size = sys.getsizeof(cog_instance)

            # Traverse only the cog's __dict__ (its instance attributes)
            if hasattr(cog_instance, "__dict__"):
                for attr_name, attr_value in cog_instance.__dict__.items():
                    # Skip self.bot since we pre-marked it
                    if attr_name == "bot":
                        continue
                    size += _sizeof_recursive(attr_value, seen)

            cog_sizes.append((cog_name, size))
        except Exception as e:
            log.debug(f"Failed to get size of cog {cog_name}: {e}")
            cog_sizes.append((cog_name, 0))

    # Sort by size descending
    cog_sizes.sort(key=lambda x: x[1], reverse=True)

    rows = []
    total_size = 0
    for cog_name, size in cog_sizes[:limit]:
        total_size += size
        rows.append([cog_name, stringutils.pp(size)])

    # Add total row
    rows.append(["─" * 20, "─" * 10])
    rows.append(["TOTAL (shown)", stringutils.pp(total_size)])

    return tabulate(rows, headers=["Cog", "Memory"])
