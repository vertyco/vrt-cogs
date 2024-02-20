import asyncio
import cProfile
import functools
import logging
import pstats
import typing as t
from dataclasses import asdict
from datetime import datetime, timedelta
from time import perf_counter

from ..abc import MixinMeta
from .models import StatsProfile

log = logging.getLogger("red.vrt.profiler.wrapper")


class Wrapper(MixinMeta):
    def profile_wrapper(self, func: t.Callable, cog_name: str, func_type: str):
        key = f"{func.__module__}.{func.__name__}"
        self.currently_tracked.add(key)
        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                if any(
                    [
                        self.db.verbose,
                        key in self.db.tracked_methods,
                    ]
                ):
                    with cProfile.Profile() as profile:
                        retval = await func(*args, **kwargs)
                else:
                    start = perf_counter()
                    retval = await func(*args, **kwargs)
                    profile = perf_counter() - start

                await asyncio.to_thread(self.add_stats, func, profile, cog_name, func_type)

                return retval

            # Preserve the signature of the original function
            functools.update_wrapper(async_wrapper, func)
            return async_wrapper

        else:

            def sync_wrapper(*args, **kwargs):
                if any(
                    [
                        self.db.verbose,
                        key in self.db.tracked_methods,
                    ]
                ):
                    with cProfile.Profile() as profile:
                        retval = func(*args, **kwargs)
                else:
                    start = perf_counter()
                    retval = func(*args, **kwargs)
                    profile = perf_counter() - start

                self.add_stats(func, profile, cog_name, func_type)

                return retval

            # Preserve the signature of the original function
            functools.update_wrapper(sync_wrapper, func)
            return sync_wrapper

    def add_stats(
        self,
        func: t.Callable,
        profile_or_delta: t.Union[cProfile.Profile, float],
        cog_name: str,
        func_type: str,
    ):
        try:
            key = f"{func.__module__}.{func.__name__}"
            if isinstance(profile_or_delta, cProfile.Profile):
                results = pstats.Stats(profile_or_delta)
                results.sort_stats(pstats.SortKey.CUMULATIVE)
                stats = asdict(results.get_stats_profile())
                stats_profile = StatsProfile.model_validate(
                    {**stats, "func_type": func_type, "is_coro": asyncio.iscoroutinefunction(func)}
                )
            else:
                stats_profile = StatsProfile(
                    total_tt=profile_or_delta,
                    func_type=func_type,
                    is_coro=asyncio.iscoroutinefunction(func),
                    func_profiles={},
                )

            self.db.stats.setdefault(cog_name, {}).setdefault(key, []).append(stats_profile)

            # Only keep the last delta hours of data
            min_age = datetime.now() - timedelta(hours=self.db.delta)
            if cog_name not in self.db.stats:
                return
            to_keep = [i for i in self.db.stats[cog_name][key] if i.timestamp > min_age]
            if cog_name not in self.db.stats:
                return
            self.db.stats[cog_name][key] = to_keep
        except Exception as e:
            log.exception(f"Failed to {func_type} stats for the {cog_name} cog", exc_info=e)
