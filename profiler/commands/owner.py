import asyncio
import logging
import sys
import typing as t
from contextlib import suppress

import discord
from discord import app_commands
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, humanize_number, pagify

from ..abc import MixinMeta
from ..common.formatting import humanize_size
from ..common.mem_profiler import profile_memory
from ..views.profile_menu import ProfileMenu

log = logging.getLogger("red.vrt.profiler.commands")


class Owner(MixinMeta):
    @commands.group()
    @commands.is_owner()
    async def profiler(self, ctx: commands.Context):
        """Profiling commands"""
        if ctx.invoked_subcommand is None:
            txt = (
                "## Profiler Tips\n"
                "- Start by attaching the profiler to a cog using the `attach` command\n"
                " - Example: `[p]profiler attach cog MyCog`\n"
                "- Identify suspicious methods using the `[p]profiler view` command\n"
                "- Attach profilers to specific methods to be tracked verbosely using the `attach` command and specifying the method.\n"
                "- Detach the profiler from the cog and only monitor the necessary methods and save memory overhead.\n"
                "- Add a threshold using the `threshold` command to only record entries that exceed a certain execution time in ms\n"
            )
            await ctx.send(txt)

    @profiler.command(name="cleanup")
    async def run_cleanup(self, ctx: commands.Context):
        """Run a cleanup of the stats"""
        cleaned = await asyncio.to_thread(self.db.cleanup)
        await ctx.send(f"Cleanup complete, {cleaned} records were removed")
        if cleaned:
            await self.save()

    @profiler.command(name="settings", aliases=["s"])
    async def view_settings(self, ctx: commands.Context):
        """
        View the current profiler settings
        """
        txt = "# Profiler Settings"
        if self.db.save_stats:
            txt += "\n- Persistent Storage: Profiling metrics are **Saved**"
        else:
            txt += "\n- Persistent Storage: Profiling metrics are **Not Saved**"

        if self.db.verbose:
            txt += f"\n- Globally verbose stat metrics are **Enabled**, you can use the `Inspect` button in the `{ctx.clean_prefix}profiler view` menu to view detailed stats"
        else:
            txt += "\n- Globally verbose stat metrics are **Disabled**, the `Inspect` button in the menu will only be available for methods being tracked verbosely"

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

        joined = ", ".join([f"`{i}`" for i in self.db.tracked_cogs]) if self.db.tracked_cogs else "`None`"
        txt += f"\n## General Profiling:\nThe following cogs are being profiled: {joined}\n"

        txt += (
            f"**Tracking:**\nApplies to the cogs above that are being profiled without specific methods targeted.\n"
            f"- Methods: **{self.db.track_methods}**\n"
            f"- Commands: **{self.db.track_commands}**\n"
            f"- Listeners: **{self.db.track_listeners}**\n"
            f"- Tasks: **{self.db.track_tasks}**\n"
        )

        joined = ", ".join([f"`{i}`" for i in self.db.tracked_methods]) if self.db.tracked_methods else "`None`"
        txt += (
            "## Fine Grain Profiling:\nMethods that are being profiled verbosely and independently of the cogs above.\n"
        )
        txt += f"The current threshold for tracking is `{self.db.tracked_threshold}ms` so only runtimes above this will be stored.\n"
        txt += f"{joined}\n"

        await ctx.send(txt)

    @profiler.command(name="save")
    async def save_toggle(self, ctx: commands.Context):
        """
        Toggle saving stats persistently

        **Warning**: The config size can grow very large if this is enabled for a long time
        """
        self.db.save_stats = not self.db.save_stats
        await self.save()
        await ctx.send(f"Saving of metrics is now **{self.db.save_stats}**")

    @profiler.command(name="globalverbose")
    async def verbose_global_toggle(self, ctx: commands.Context):
        """
        Toggle verbose stats for all methods

        **WARNING**: Enabling this will increase memory usage significantly
        """
        self.db.verbose = not self.db.verbose
        cleaned = await asyncio.to_thread(self.db.cleanup)
        if cleaned:
            await self.save()
        if self.db.verbose:
            txt = (
                "Verbose stats are now **Enabled**\n"
                "**Warning**: This will increase memory usage significantly\n"
                f"Use `{ctx.clean_prefix}profiler verbose add/remove` to add/remove specific methods to/from verbose tracking"
            )
            await ctx.send(txt)
        else:
            await ctx.send("Globally verbose stats are now **Disabled**")

    @profiler.command(name="delta")
    async def set_delta(self, ctx: commands.Context, delta: int):
        """
        Set the data retention period in hours
        """
        if delta < 1:
            return await ctx.send("Delta must be at least 1 hour")
        self.db.delta = delta
        cleaned = await asyncio.to_thread(self.db.cleanup)
        if cleaned:
            await self.save()
        await ctx.send(f"Data retention is now set to **{delta} {'hour' if delta == 1 else 'hours'}**")

    @profiler.command(name="tracking")
    async def track_toggle(self, ctx: commands.Context, method: str, state: bool):
        """
        Toggle tracking of a method

        Enabled methods will be profiled and included in the stats when attaching a profiler to a cog

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

        cleaned = await asyncio.to_thread(self.db.cleanup)
        if cleaned:
            await self.save()
        await ctx.send(f"Tracking of {method} is now set to **{state}**")
        await self.rebuild()

    @profiler.command(name="threshold")
    async def set_threshold(self, ctx: commands.Context, threshold: float):
        """
        Set the minimum execution delta to record a profile of tracked methods
        """
        self.db.tracked_threshold = threshold
        await ctx.send(f"Tracking threshold is now set to **{threshold}ms**")
        await self.save()

    @commands.hybrid_command(name="attach", description="Attach a profiler to a cog or method")
    @app_commands.describe(
        item="'cog' or 'method'",
        item_name="Name of the cog or method to profile",
    )
    @commands.is_owner()
    async def profile_an_item(self, ctx: commands.Context, item: t.Literal["cog", "method"], *, item_name: str):
        """
        Attach a profiler to a cog or method
        """

        def _match(data: t.List[str], name: str):
            matches = map(lambda x: (x, fuzz.ratio(name.lower(), x.lower())), data)
            matches = [i for i in matches if i[1] > 50]
            if not matches:
                return None
            matches = sorted(matches, key=lambda x: x[1], reverse=True)
            return matches[0][0]

        if item.lower().startswith("m"):
            if item_name in self.db.tracked_methods:
                return await ctx.send(f"**{item_name}** is already being profiled")
            elif self.attach_method(item_name):
                self.db.tracked_methods.append(item_name)
                await ctx.send(f"**{item_name}** is now being profiled")
                await self.rebuild()
                await self.save()
                return
            if match := _match(self.methods.keys(), item_name):
                return await ctx.send(f"**{item_name}** wasn't being profiled, did you mean **{match}**?")
            return await ctx.send(f"Could not find **{item_name}**")

        if item == "all":
            for cog in self.bot.cogs:
                if cog not in self.db.tracked_cogs:
                    self.db.tracked_cogs.append(cog)
            await ctx.send("All cogs are now being profiled")
            await self.rebuild()
            await self.save()
            return
        elif len(item_name.split()) > 1:
            added = []
            cogs = [i.strip() for i in item_name.split()]
            for cog in cogs:
                if not self.bot.get_cog(cog):
                    await ctx.send(f"Could not find **{cog}**")
                    continue
                if cog not in self.db.tracked_cogs:
                    self.db.tracked_cogs.append(cog)
                    added.append(cog)

            if added:
                await ctx.send(f"**{', '.join(added)}** are now being profiled")
                await self.rebuild()
                await self.save()
                return

            return await ctx.send("No valid cogs were given")

        if item_name in self.db.tracked_cogs:
            return await ctx.send(f"**{item_name}** was already being profiled")
        if self.bot.get_cog(item_name):
            self.db.tracked_cogs.append(item_name)
            await ctx.send(f"**{item_name}** is now being profiled")
            await self.rebuild()
            await self.save()
            return
        if match := _match(self.bot.cogs, item_name):
            return await ctx.send(f"Could not find **{item_name}**. Closest match is **{match}**")
        await ctx.send(f"Could not find **{item_name}**")

    @commands.hybrid_command(name="detach")
    @app_commands.describe(
        item="'cog' or 'method'",
        item_name="Name of the cog or method to profile",
    )
    @commands.is_owner()
    async def detach_item(self, ctx: commands.Context, item: t.Literal["cog", "method"], *, item_name: str):
        """
        Remove the profiler from a cog or method
        """

        def _match(data: t.List[str], name: str):
            matches = map(lambda x: (x, fuzz.ratio(name, x)), data)
            matches = [i for i in matches if i[1] > 50]
            if not matches:
                return None
            matches = sorted(matches, key=lambda x: x[1], reverse=True)
            return matches[0][0]

        if not self.db.tracked_cogs and not self.db.tracked_methods:
            return await ctx.send("No cogs or methods are being profiled")

        if item.lower().startswith("m"):
            if item_name not in self.db.tracked_methods:
                if match := _match(self.db.tracked_methods, item_name):
                    return await ctx.send(f"**{item_name}** wasn't being profiled, did you mean **{match}**?")
                return await ctx.send(f"**{item_name}** wasn't being profiled")
            self.db.tracked_methods.remove(item_name)
            await self.rebuild()
            await self.save()
            return await ctx.send(f"**{item_name}** is no longer being profiled")

        if item == "all":
            self.db.tracked_cogs = []
            await ctx.send("All cogs are no longer being profiled")
            await self.rebuild()
            await self.save()
            return

        elif len(item_name.split()) > 1:
            removed = []
            cogs = [i.strip() for i in item_name.split()]
            for cog in cogs:
                if cog in self.db.tracked_cogs:
                    self.db.tracked_cogs.remove(cog)
                    removed.append(cog)
                else:
                    await ctx.send(f"**{cog}** wasn't being profiled")
            if removed:
                await ctx.send(f"**{', '.join(removed)}** are no longer being profiled")
                await self.rebuild()
                await self.save()
                return

            return await ctx.send("No valid cogs were given")

        if item_name not in self.db.tracked_cogs:
            if match := _match(self.db.tracked_cogs, item_name):
                return await ctx.send(f"**{item_name}** wasn't being profiled, did you mean **{match}**?")
            return await ctx.send(f"**{item_name}** wasn't being profiled")
        self.db.tracked_cogs.remove(item_name)
        await ctx.send(f"**{item_name}** is no longer being profiled")
        await self.rebuild()
        await self.save()

    @profile_an_item.autocomplete("item")
    @detach_item.autocomplete("item")
    async def autocomplete_item(self, interaction: discord.Interaction, current: str) -> t.List[app_commands.Choice]:
        options = ["cog", "method"]
        choices = [app_commands.Choice(name=i, value=i) for i in options if current.lower() in i.lower()]
        return choices

    @profile_an_item.autocomplete("item_name")
    async def autocomplete_names_attach(
        self, interaction: discord.Interaction, current: str
    ) -> t.List[app_commands.Choice]:
        choices: t.List[app_commands.Choice] = []
        for i in self.bot.cogs:
            if current.lower() in i.lower() and len(choices) < 25:
                choices.append(app_commands.Choice(name=i, value=i))
        for i in self.methods.keys():
            if current.lower() in i.lower() and len(choices) < 25:
                choices.append(app_commands.Choice(name=i, value=i))
        choices.sort(key=lambda x: x.name.lower())
        return choices

    @detach_item.autocomplete("item_name")
    async def autocomplete_names_detach(
        self, interaction: discord.Interaction, current: str
    ) -> t.List[app_commands.Choice]:
        print(f"Current: {current}")
        choices: t.List[app_commands.Choice] = []
        for i in self.db.tracked_cogs:
            if current.lower() in i.lower() and len(choices) < 25:
                choices.append(app_commands.Choice(name=i, value=i))
        for i in self.db.tracked_methods:
            if current.lower() in i.lower() and len(choices) < 25:
                choices.append(app_commands.Choice(name=i, value=i))
        choices.sort(key=lambda x: x.name.lower())
        return choices

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

        **Columns**:
        - Method: The method being profiled
        - Max: The highest recorded runtime of the method
        - Min: The lowest recorded runtime of the method
        - Avg: The average runtime of the method
        - Calls/Min: The average calls per minute of the method over the set delta
        - Last X: The total number of times the method was called over the set delta
        - Impact Score: A score calculated from the average runtime and calls per minute

        **Note**: The `Inspect` button will only be available if verbose stats are enabled

        **Impact Score**:
        The impact score represents the impact of the method on the bot's performance.
        ```python
        variability_score = standard_deviation_of_runtimes / avg_runtime
        impact_score = (avg_runtime * calls_per_minute) * (1 + variability_score)
        ```
        The higher the score, the more impact the method has on the bot's performance
        """
        view = ProfileMenu(ctx, self)
        await view.start()
