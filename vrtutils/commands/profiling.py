import asyncio
import typing as t
from time import perf_counter

from pympler import muppy, summary
from pympler.util import stringutils
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify
from tabulate import tabulate

from ..abc import MixinMeta


class Profiling(MixinMeta):
    def __init__(self):
        super().__init__()
        # command_name: [times]
        self.stats: t.Dict[str, t.List[float]] = {}
        self.start_times: t.Dict[str, float] = {}
        self._listen = False

    async def _track(self, command_name: str, coro):
        start_time = perf_counter()
        await coro
        end_time = perf_counter()
        self.stats.setdefault(command_name, []).append(end_time - start_time)

    def _key(self, ctx: commands.Context):
        return f"{ctx.author.id}-{ctx.command.qualified_name}-{ctx.guild.id}-{ctx.channel.id}-{ctx.message.id}"

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if not self._listen or not ctx.command:
            return
        self.start_times[self._key(ctx)] = perf_counter()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not self._listen or not ctx.command or self._key(ctx) not in self.start_times:
            return
        end_time = perf_counter()
        self.stats.setdefault(ctx.command.qualified_name, []).append(end_time - self.start_times.pop(self._key(ctx)))

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if not self._listen or not ctx.command or self._key(ctx) not in self.start_times:
            return
        end_time = perf_counter()
        self.stats.setdefault(ctx.command.qualified_name, []).append(end_time - self.start_times.pop(self._key(ctx)))

    @commands.group(name="profiler")
    @commands.is_owner()
    async def profiler(self, ctx: commands.Context):
        """
        Profiling commands
        """
        if ctx.invoked_subcommand is None:
            if self._listen:
                await ctx.send("Profiler is **On**")
            else:
                await ctx.send("Profiler is **Off**")

    @profiler.command(name="reset")
    async def reset_profiler(self, ctx: commands.Context):
        """
        Reset profiler
        """
        self.stats.clear()
        self.start_times.clear()
        await ctx.send("Profiler reset")

    @profiler.command(name="toggle")
    async def toggle_profiler(self, ctx: commands.Context):
        """
        Toggle profiler
        """
        self._listen = not self._listen
        if self._listen:
            await ctx.send("Profiler is **On**")
        else:
            await ctx.send("Profiler is **Off**")
            self.stats.clear()
            self.start_times.clear()

    @profiler.command(name="mem")
    async def profile_summary(self, ctx: commands.Context, limit: int = 15):
        """
        Profile memory usage of objects in the current environment
        """
        cols = ["types", "objects", "total size"]

        def _f():
            all_objects = muppy.get_objects()
            summaries = summary.summarize(all_objects)

            rows = []
            for i in sorted(summaries, key=lambda x: x[2], reverse=True)[:limit]:
                class_desc, count, size = i
                class_name = class_desc.split(":", 1)[0] if ":" in class_desc else class_desc
                if len(class_name) > 30:
                    class_name = class_name[:27] + "..."

                rows.append([class_name, count, stringutils.pp(size)])

            return tabulate(rows, headers=cols)

        async with ctx.typing():
            res = await asyncio.to_thread(_f)
            for p in pagify(res, page_length=1980):
                await ctx.send(box(p, "py"))

    @profiler.command(name="cmd")
    async def profile_commands(self, ctx: commands.Context, limit: int = 15):
        """
        Profile execution time of commands
        """
        cols = ["command", "count", "average"]
        if not self.stats:
            return await ctx.send("No stats available")

        def _f():
            rows = []
            # Sort by average time
            sorted_stats = sorted(self.stats.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)
            for command_name, times in sorted_stats[:limit]:
                rows.append(
                    [
                        command_name,
                        len(times),
                        stringutils.pp_timestamp(sum(times) / len(times)),
                    ]
                )

            return tabulate(rows, headers=cols)

        async with ctx.typing():
            res = await asyncio.to_thread(_f)
            for p in pagify(res, page_length=1980):
                await ctx.send(box(p, "py"))
