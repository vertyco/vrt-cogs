import asyncio
import functools
import logging
import typing as t
from time import perf_counter

from ..abc import MixinMeta
from .models import StatsProfile

log = logging.getLogger("red.vrt.profiler.wrapper")


class Wrapper(MixinMeta):
    def profile_wrapper(self, func: t.Callable, cog_name: str, func_type: str):
        key = f"{func.__module__}.{func.__name__}"
        if key in self.currently_tracked:
            raise ValueError(f"{key} is already being profiled")

        self.currently_tracked.add(key)
        log.debug(f"Attaching profiler to {func_type.upper()}: {key}")

        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                exception = None
                start = perf_counter()
                try:
                    retval = await func(*args, **kwargs)
                    return retval
                except Exception as exc:
                    exception = str(exc)
                    raise exc
                finally:
                    delta = perf_counter() - start
                    await asyncio.to_thread(
                        self.add_stats,
                        func,
                        delta,
                        cog_name,
                        func_type,
                        exception,
                        self.bot.latency,
                    )

            # Preserve the signature of the original function
            functools.update_wrapper(async_wrapper, func)
            return async_wrapper

        else:

            def sync_wrapper(*args, **kwargs):
                exception = None
                start = perf_counter()
                try:
                    retval = func(*args, **kwargs)
                    return retval
                except Exception as exc:
                    exception = str(exc)
                    raise exc
                finally:
                    delta = perf_counter() - start
                    self.add_stats(
                        func,
                        delta,
                        cog_name,
                        func_type,
                        exception,
                        self.bot.latency,
                    )

            # Preserve the signature of the original function
            functools.update_wrapper(sync_wrapper, func)
            return sync_wrapper

    def add_stats(
        self,
        func: t.Callable,
        profile_or_delta: float,
        cog_name: str,
        func_type: str,
        exception_thrown: t.Optional[str] = None,
        latency: t.Optional[float] = None,
    ):
        if self.saving:
            # Dont record stats while saving to avoid conflicts
            return
        try:
            key = f"{func.__module__}.{func.__name__}"
            stats_profile = StatsProfile(
                total_tt=profile_or_delta,
                func_type=func_type,
                is_coro=asyncio.iscoroutinefunction(func),
                exception_thrown=exception_thrown,
                latency=latency,
            )
            self.db.stats.setdefault(cog_name, {}).setdefault(key, []).append(stats_profile)
        except Exception as e:
            log.exception(f"Failed to {func_type} stats for the {cog_name} cog", exc_info=e)
