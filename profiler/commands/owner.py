import asyncio
import logging
import sys
from contextlib import suppress

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, humanize_number, pagify

from ..abc import MixinMeta
from ..common.constants import IGNORED_COGS
from ..common.formatting import humanize_size
from ..common.mem_profiler import profile_memory
from ..views.profile_menu import ProfileMenu

log = logging.getLogger("red.vrt.profiler.commands")


class Owner(MixinMeta):
    @commands.group()
    @commands.is_owner()
    async def profiler(self, ctx: commands.Context):
        """Profiling commands"""
        pass

    @profiler.command(name="settings")
    async def view_settings(self, ctx: commands.Context):
        """
        View the current profiler settings
        """
        txt = "## Profiler Settings"
        if self.db.save_stats:
            txt += "\n- Persistent Storage: Profiling metrics are **Saved**"
        else:
            txt += "\n- Persistent Storage: Profiling metrics are **Not Saved**"

        if self.db.verbose:
            txt += f"\n- Verbose stat metrics are **Enabled**, you can use the `Inspect` button in the `{ctx.clean_prefix}profiler view` menu to view detailed stats"
        else:
            txt += "\n- Verbose stat metrics are **Disabled**, the `Inspect` button in the menu will not be available"

        txt += f"\n- Data retention is set to **{self.db.delta} {'hour' if self.db.delta == 1 else 'hours'}**"

        mem_usage = humanize_size(sys.getsizeof(self.db.stats))
        txt += f"\n- Config Size: **{mem_usage}**"

        records = 0
        monitoring = 0
        for methods in self.db.stats.values():
            monitoring += len(methods)
            for statprofiles in methods.values():
                records += len(statprofiles)

        txt += f"\n- Monitoring: **{humanize_number(monitoring)}** methods (`{humanize_number(records)}` Records)"

        txt += (
            f"\n### Tracking:\n"
            f"- Methods: **{self.db.track_methods}**\n"
            f"- Commands: **{self.db.track_commands}**\n"
            f"- Listeners: **{self.db.track_listeners}**\n"
            f"- Tasks: **{self.db.track_tasks}**"
        )

        txt += f"\n### Profiling the following cogs:\n{', '.join(self.db.watching) if self.db.watching else 'None'}"

        await ctx.send(txt)

    @profiler.command(name="save")
    async def save_settings(self, ctx: commands.Context):
        """
        Toggle saving stats persistently

        **Warning**: The config size can grow very large if this is enabled for a long time
        """
        self.db.save_stats = not self.db.save_stats
        await self.save()
        await ctx.send(f"Saving of metrics is now **{self.db.save_stats}**")

    @profiler.command(name="verbose")
    async def verbose_settings(self, ctx: commands.Context):
        """
        Toggle verbose stats
        """
        self.db.verbose = not self.db.verbose
        if not await self.cleanup():
            await self.save()
        await ctx.send(f"Verbose stats is now **{self.db.verbose}**")

    @profiler.command(name="delta")
    async def set_delta(self, ctx: commands.Context, delta: int):
        """
        Set the data retention period in hours
        """
        if delta < 1:
            return await ctx.send("Delta must be at least 1 hour")
        self.db.delta = delta
        if not await self.cleanup():
            await self.save()
        await ctx.send(f"Data retention is now set to **{delta} {'hour' if delta == 1 else 'hours'}**")

    @profiler.command(name="track")
    async def track_settings(self, ctx: commands.Context, method: str, state: bool):
        """
        Toggle tracking of a method

        **Arguments**:
        - `method`: The method to toggle tracking for (methods, commands, listeners, tasks)
        - `state`: The state to set tracking to (True/False, 1/0, t/f)
        """
        if method not in ("methods", "commands", "listeners", "tasks"):
            return await ctx.send("Invalid method, use one of: `methods`, `commands`, `listeners`, `tasks`")

        if getattr(self.db, f"track_{method}") == state:
            return await ctx.send(f"Tracking of {method} is already set to **{state}**")

        # setattr(self.db, f"track_{method}", state)
        if method == "methods":
            self.db.track_methods = state
        elif method == "commands":
            self.db.track_commands = state
        elif method == "listeners":
            self.db.track_listeners = state
        elif method == "tasks":
            self.db.track_tasks = state

        if not await self.cleanup():
            await self.save()
        await ctx.send(f"Tracking of {method} is now set to **{state}**")
        await self.rebuild()

    @profiler.command(name="attach", aliases=["add"])
    async def attach_cog(self, ctx: commands.Context, *cogs: str):
        """
        Attach a profiler to a cog
        """
        if cogs[0].lower() == "all":
            cogs = [cog for cog in self.bot.cogs if cog not in IGNORED_COGS]
            self.db.watching = cogs
            await self.rebuild()
            await self.save()
            return await ctx.send("All cogs are now being profiled")

        attached = False
        for cog_name in cogs:
            if not self.bot.get_cog(cog_name):
                await ctx.send(f"**{cog_name}** isn't valid cog")
                continue
            elif cog_name in self.db.watching:
                await ctx.send(f"**{cog_name}** was already being profiled")
                continue
            self.db.watching.append(cog_name)
            attached = True

        if not attached:
            return await ctx.send("No valid cogs were provided")

        await self.rebuild()
        await self.save()
        if len(cogs) == 1:
            await ctx.send(f"**{cogs[0]}** is now being profiled")
        else:
            joined = ", ".join([f"`{i}`" for i in cogs])
            await ctx.send(f"The following cogs are now being profiled: {joined}")

    @profiler.command(name="detach", aliases=["remove"])
    async def detach_cog(self, ctx: commands.Context, *cogs: str):
        """
        Remove a cog from the profiling list

        This will remove all collected stats for this cog from the config
        """
        if not self.db.watching:
            return await ctx.send("No cogs are being profiled")

        if cogs[0].lower() == "all":
            self.db.watching.clear()
            await self.rebuild()
            self.db.stats.clear()
            await self.save()
            return await ctx.send("All cogs removed from profiling")

        for cog_name in cogs:
            if cog_name not in self.db.watching:
                await ctx.send(f"**{cog_name}** wasn't being profiled")
                continue
            self.db.watching.remove(cog_name)
            if cog_name in self.db.stats:
                del self.db.stats[cog_name]

        await self.rebuild()
        await self.save()
        if len(cogs) == 1:
            await ctx.send(f"**{cogs[0]}** is no longer being profiled")
        else:
            joined = ", ".join([f"`{i}`" for i in cogs])
            await ctx.send(f"The following cogs are no longer being profiled: {joined}")

    @profiler.command(name="memory", aliases=["mem", "m"])
    async def profile_summary(self, ctx: commands.Context, limit: int = 15):
        """
        Profile memory usage of objects in the current environment
        """
        async with ctx.typing():
            msg = await ctx.send("Profiling memory usage, standby...")
            res = await asyncio.to_thread(profile_memory, limit)
            with suppress(discord.NotFound):
                await msg.delete()
            for p in pagify(res, page_length=1980):
                await ctx.send(box(p, "py"))

    @profiler.command(name="view", aliases=["v"])
    async def profile_menu(self, ctx: commands.Context):
        """
        View a menu of the current stats
        """
        view = ProfileMenu(ctx, self.db)
        await view.start()
