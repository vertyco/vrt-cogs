import asyncio
import io
import logging
import sys
import typing as t
from contextlib import suppress

import discord
import sentry_sdk
from discord import app_commands
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_number, pagify
from sentry_sdk import profiler

from ..abc import MixinMeta
from ..common.formatting import humanize_size
from ..common.mem_profiler import profile_memory
from ..common.models import IGNORED_COGS
from ..views.profile_menu import ProfileMenu

log = logging.getLogger("red.vrt.profiler.commands")


def deep_getsizeof(obj: t.Any, seen: t.Optional[set] = None) -> int:
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return 0
    # Mark object as seen
    seen.add(id(obj))

    size = sys.getsizeof(obj)

    if isinstance(obj, dict):
        # If the object is a dictionary, recursively add the size of keys and values
        size += sum([deep_getsizeof(k, seen) + deep_getsizeof(v, seen) for k, v in obj.items()])
    elif hasattr(obj, "__dict__"):
        # If the object has a __dict__, it's likely an object. Find size of its dictionary
        size += deep_getsizeof(obj.__dict__, seen)
    elif hasattr(obj, "__iter__") and not isinstance(obj, (str, bytes, bytearray)):
        # If the object is an iterable (not a string or bytes), iterate through its items
        size += sum([deep_getsizeof(i, seen) for i in obj])
    elif hasattr(obj, "model_dump"):
        # If the object is a pydantic model, get the size of its dictionary
        size += deep_getsizeof(obj.model_dump(), seen)

    return size


class Owner(MixinMeta):
    @commands.group()
    @commands.is_owner()
    async def profiler(self, ctx: commands.Context):
        """Profiling commands"""
        if ctx.invoked_subcommand is None:
            txt = (
                "## Profiler Tips\n"
                f"- Use `{ctx.clean_prefix}profiler methods` to see all available methods that can be tracked.\n"
                "- Start by attaching the profiler to a cog using the `attach` command.\n"
                f" - Example: `{ctx.clean_prefix}attach cog <cog_name>`.\n"
                f"- Identify suspicious methods using the `{ctx.clean_prefix}profiler view` command.\n"
                f"- Attach profilers to specific methods using the `{ctx.clean_prefix}attach` command.\n"
                f" - Attaching to a cog: `{ctx.clean_prefix}attach cog <cog_name>`.\n"
                f" - Attaching to a method: `{ctx.clean_prefix}attach method <method_key>`.\n"
                "- Detach the profiler from the cog and only monitor the necessary methods and save memory overhead.\n"
                "- Add a threshold using the `threshold` command to only record entries that exceed a certain execution time in ms.\n"
            )
            await ctx.send(txt)

    @profiler.command(name="settings", aliases=["s"])
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """
        View the current profiler settings
        """
        txt = "# Profiler Settings\n"
        # PERSISTENT STORAGE
        txt += f"- Persistent Storage: Profiling metrics are **{'Saved' if self.db.save_stats else 'Not Saved'}**\n"

        # DATA RETENTION
        txt += f"- Data retention is set to **{self.db.delta} {'hour' if self.db.delta == 1 else 'hours'}**\n"

        # SENTRY PROFILING
        txt += f"- Sentry Profiling: **{'Enabled' if self.db.sentry_profiler else 'Disabled'}**\n"

        # CONFIG SIZE
        mem_size_raw = await asyncio.to_thread(deep_getsizeof, self.db)
        mem_usage = humanize_size(mem_size_raw)
        txt += f"- Cog RAM Usage: `{mem_usage}`\n"

        # TRACKING COUNTS
        records = 0
        monitoring = 0
        for methods in self.db.stats.values():
            monitoring += len(methods)
            for statprofiles in methods.values():
                records += len(statprofiles)
        txt += f"- Monitoring: `{humanize_number(monitoring)}` methods (`{humanize_number(records)}` Records)\n"

        # TRACKED COGS
        y = "**Included**"
        n = "**Not Included**"
        joined = ", ".join([f"`{i}`" for i in self.db.tracked_cogs]) if self.db.tracked_cogs else "`None`"
        txt += "## Tracked Cogs:\n"
        txt += (
            f"- Methods are {y if self.db.track_methods else n}\n"
            f"- Commands are {y if self.db.track_commands else n}\n"
            f"- Listeners are {y if self.db.track_listeners else n}\n"
            f"- Tasks are {y if self.db.track_tasks else n}\n"
        )
        txt += f"The following cogs are being profiled: {joined}\n"
        joined = ", ".join([f"`{i}`" for i in self.db.ignored_methods]) if self.db.ignored_methods else "`None`"
        txt += f"The following methods are being ignored: {joined}\n"

        # TRACKED METHODS
        joined = ", ".join([f"`{i}`" for i in self.db.tracked_methods]) if self.db.tracked_methods else "`None`"
        txt += "## Tracked Methods:\n"
        txt += f"- All methods with a runtime greater than **{self.db.tracked_threshold}ms** are being recorded\n"
        txt += f"The following methods are being tracked: {joined}\n"

        await ctx.send(txt)

    @profiler.command(name="cleanup", aliases=["c"])
    async def run_cleanup(self, ctx: commands.Context):
        """Run a cleanup of the stats"""
        cleaned = await asyncio.to_thread(self.db.cleanup)
        await ctx.send(f"Cleanup complete, {cleaned} records were removed")
        if cleaned:
            await self.save()

    @profiler.command(name="clear")
    async def clear_metrics(self, ctx: commands.Context):
        """
        Clear all saved metrics
        """
        self.db.stats.clear()
        await self.save()
        await ctx.send("All metrics have been cleared")

    @profiler.command(name="save")
    async def save_toggle(self, ctx: commands.Context):
        """
        Toggle saving stats persistently

        **Warning**: The config size can grow very large if this is enabled for a long time
        """
        self.db.save_stats = not self.db.save_stats
        await self.save()
        await ctx.send(f"Saving of metrics is now **{self.db.save_stats}**")

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

    @profiler.command(name="sentry")
    async def toggle_sentry(self, ctx: commands.Context):
        """
        Toggle Sentry profiling integration

        **Warning**: This will increase memory usage and may have privacy implications.
        Ensure you have configured Sentry SDK in your bot before enabling this.
        """
        # Check sentry version
        if "sentry_sdk" not in sys.modules:
            return await ctx.send("Sentry SDK is not installed or configured in your bot.")
        if not sentry_sdk.Hub.current.client:
            return await ctx.send("Sentry SDK is not initialized in your bot.")
        if not hasattr(profiler, "start_profiler"):
            return await ctx.send("Your version of Sentry SDK does not support profiling. Please update it.")
        self.db.sentry_profiler = not self.db.sentry_profiler
        await self.save()
        await ctx.send(f"Sentry profiling is now **{self.db.sentry_profiler}**")

    @profiler.command(name="tracking")
    async def track_toggle(
        self,
        ctx: commands.Context,
        method: t.Literal["methods", "commands", "listeners", "tasks"],
        state: bool,
    ):
        """
        Toggle tracking of a method

        Enabled methods will be profiled and included in the stats when attaching a profiler to a cog

        **Arguments**:
        - `method`: The method to toggle tracking for (methods, commands, listeners, tasks)
        - `state`: The state to set tracking to (True/False, 1/0, t/f)
        """

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

    @profiler.command(name="ignore")
    async def manage_ignorelist(self, ctx: commands.Context, method_name: str):
        """
        Add or remove a method from the ignore list
        """
        if method_name in self.db.ignored_methods:
            self.db.discard_method(method_name)
            self.db.ignored_methods.remove(method_name)
            await ctx.send(f"**{method_name}** is no longer being ignored")
            await self.save()
            return
        if method_name not in self.methods:
            return await ctx.send(f"Could not find **{method_name}**")
        if method_name in self.db.tracked_methods:
            return await ctx.send(
                f"**{method_name}** is being explicitly tracked, remove it from the tracked list first"
            )
        self.db.ignored_methods.append(method_name)
        await ctx.send(f"**{method_name}** is now being ignored")
        await self.rebuild()
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
        self.map_methods()

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
                self.attach_method(item_name)
                await ctx.send(f"**{item_name}** is now being profiled")
                await self.save()
                return
            if match := _match(self.methods.keys(), item_name):
                return await ctx.send(f"**{item_name}** wasn't being profiled, did you mean **{match}**?")
            return await ctx.send(f"Could not find **{item_name}**")

        if item_name == "all":
            bot: Red = self.bot  # type: ignore
            for cogname in bot.cogs:
                if cogname not in self.db.tracked_cogs and cogname not in IGNORED_COGS:
                    self.db.tracked_cogs.append(cogname)
                    self.attach_cog(cogname)
            await ctx.send("All cogs are now being profiled")
            await self.save()
            return

        elif len(item_name.split()) > 1:
            added = []
            cogs = [i.strip() for i in item_name.split()]
            if any(cog in IGNORED_COGS for cog in cogs):
                return await ctx.send(f"Cannot profile the following cogs: {', '.join(IGNORED_COGS)}")
            for cog in cogs:
                if not self.bot.get_cog(cog):
                    await ctx.send(f"Could not find **{cog}**")
                    continue
                if cog not in self.db.tracked_cogs:
                    self.db.tracked_cogs.append(cog)
                    added.append(cog)
                    self.attach_cog(cog)

            if added:
                await ctx.send(f"**{', '.join(added)}** are now being profiled")
                await self.save()
                return

            return await ctx.send("No valid cogs were given")

        if item_name in self.db.tracked_cogs:
            return await ctx.send(f"**{item_name}** was already being profiled")
        if self.bot.get_cog(item_name):
            if item_name in IGNORED_COGS:
                return await ctx.send(f"Cannot profile the **{item_name}** cog")
            self.db.tracked_cogs.append(item_name)
            await ctx.send(f"**{item_name}** is now being profiled")
            self.attach_cog(item_name)
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
            self.detach_method(item_name)
            await self.save()
            return await ctx.send(f"**{item_name}** is no longer being profiled")

        if item_name == "all":
            self.db.tracked_cogs = []
            await ctx.send("All cogs are no longer being profiled")
            await self.rebuild()
            await self.save()
            return

        elif len(item_name.split()) > 1:
            removed = []
            cogs = [i.strip() for i in item_name.split()]
            for cog in cogs:
                if cog in self.db.tracked_cogs.copy():
                    self.db.tracked_cogs.remove(cog)
                    removed.append(cog)
                    self.detach_cog(cog)
                else:
                    await ctx.send(f"**{cog}** wasn't being profiled")
            if removed:
                await ctx.send(f"**{', '.join(removed)}** are no longer being profiled")
                await self.save()
                return

            return await ctx.send("No valid cogs were given")

        if item_name not in self.db.tracked_cogs:
            if match := _match(self.db.tracked_cogs, item_name):
                return await ctx.send(f"**{item_name}** wasn't being profiled, did you mean **{match}**?")
            return await ctx.send(f"**{item_name}** wasn't being profiled")

        self.db.tracked_cogs.remove(item_name)
        self.detach_cog(item_name)
        await ctx.send(f"**{item_name}** is no longer being profiled")
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

    @profiler.command(name="methods", aliases=["list"])
    async def list_methods(self, ctx: commands.Context):
        """
        List all available methods that can be tracked

        This will send a text file containing all trackable methods organized by cog.
        Useful for finding specific methods to profile without attaching to entire cogs.
        """
        async with ctx.typing():
            self.map_methods()

            if not self.methods:
                return await ctx.send("No methods found. Make sure your cogs are loaded.")

            # Group methods by cog
            cogs_data = {}
            for method_key, method_info in self.methods.items():
                cog_name = method_info.cog_name
                if cog_name not in cogs_data:
                    cogs_data[cog_name] = {"commands": [], "methods": [], "listeners": [], "tasks": []}

                func_type = method_info.func_type
                if func_type in ["command", "hybrid", "slash"]:
                    cogs_data[cog_name]["commands"].append(method_key)
                elif func_type == "method":
                    cogs_data[cog_name]["methods"].append(method_key)
                elif func_type == "listener":
                    cogs_data[cog_name]["listeners"].append(method_key)
                elif func_type == "task":
                    cogs_data[cog_name]["tasks"].append(method_key)

            # Generate the text file content
            content_lines = []
            content_lines.append("PROFILER - AVAILABLE METHODS")
            content_lines.append("=" * 50)
            content_lines.append(f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
            content_lines.append(f"Total Methods: {len(self.methods)}")
            content_lines.append("")

            for cog_name in sorted(cogs_data.keys()):
                cog_data = cogs_data[cog_name]
                content_lines.append(f"COG: {cog_name}")
                content_lines.append("-" * (5 + len(cog_name)))

                total_methods = sum(len(methods) for methods in cog_data.values())
                content_lines.append(f"Total: {total_methods} methods")
                content_lines.append("")

                for category, methods in cog_data.items():
                    if methods:
                        content_lines.append(f"{category.upper()} ({len(methods)}):")
                        for method in sorted(methods):
                            content_lines.append(f"  - {method}")
                        content_lines.append("")

                content_lines.append("")

            content = "\n".join(content_lines)

            # Create the file
            file_content = content.encode("utf-8")
            file = discord.File(
                io.BytesIO(file_content),
                filename=f"profiler_methods_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt",
            )

            embed = discord.Embed(
                title="📋 Available Methods",
                description=(
                    f"Found **{len(self.methods)}** trackable methods across **{len(cogs_data)}** cogs.\n\n"
                    f"Use `{ctx.clean_prefix}attach method <method_key>` to profile specific methods."
                ),
                color=discord.Color.blue(),
            )

            await ctx.send(embed=embed, file=file)

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
