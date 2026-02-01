import gc
import logging
import sys
import typing as t
from inspect import isframe

from pympler import asizeof, muppy, summary
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


def _get_cog_size(cog_instance: t.Any) -> int:
    """Get the size of a cog instance with fallback methods.

    Primary method uses pympler.asizeof for deep traversal.
    Falls back to a manual traversal of __dict__ if that fails.
    """
    try:
        # Use asizeof for deep size calculation
        # limit=50 prevents infinite recursion on circular references
        # code=True includes bytecode size for methods
        return asizeof.asizeof(cog_instance, limit=50, code=True)
    except Exception:
        pass

    # Fallback: manually traverse __dict__ and sum sizes
    # This is less accurate but handles Pydantic edge cases
    total = sys.getsizeof(cog_instance)
    seen: t.Set[int] = {id(cog_instance)}

    def _sizeof_fallback(obj: t.Any, depth: int = 0) -> int:
        if depth > 20 or id(obj) in seen:
            return 0
        seen.add(id(obj))

        size = 0
        try:
            size = sys.getsizeof(obj)
        except (TypeError, ValueError):
            return 0

        # Handle common container types
        if isinstance(obj, dict):
            for k, v in obj.items():
                size += _sizeof_fallback(k, depth + 1)
                size += _sizeof_fallback(v, depth + 1)
        elif isinstance(obj, (list, tuple, set, frozenset)):
            for item in obj:
                size += _sizeof_fallback(item, depth + 1)
        elif hasattr(obj, "__dict__") and not isinstance(obj, type):
            # Skip class objects, only traverse instances
            try:
                for v in obj.__dict__.values():
                    size += _sizeof_fallback(v, depth + 1)
            except Exception:
                pass
        elif hasattr(obj, "__slots__"):
            for slot in obj.__slots__:
                try:
                    size += _sizeof_fallback(getattr(obj, slot), depth + 1)
                except AttributeError:
                    pass

        return size

    # Traverse cog's __dict__
    if hasattr(cog_instance, "__dict__"):
        for value in cog_instance.__dict__.values():
            total += _sizeof_fallback(value)

    return total


def profile_cog_memory(bot: "Red", limit: int = 25) -> str:
    """Profile memory usage per cog.

    Uses pympler's asizeof to calculate the deep size of each cog instance,
    traversing all objects reachable from the cog. Falls back to a simpler
    traversal method if asizeof fails (e.g., with Pydantic models).

    Args:
        bot: The Red bot instance
        limit: Maximum number of cogs to display

    Returns:
        A formatted table string showing cog memory usage
    """
    gc.collect()

    cog_sizes: t.List[t.Tuple[str, int]] = []
    for cog_name, cog_instance in bot.cogs.items():
        try:
            size = _get_cog_size(cog_instance)
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
