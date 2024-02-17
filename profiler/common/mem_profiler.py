import gc
import logging
import typing as t
from inspect import isframe

from pympler import muppy, summary
from pympler.util import stringutils
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
