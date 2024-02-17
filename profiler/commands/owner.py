import asyncio
import logging

from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
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
        txt = (
            f"`Save Stats:     `{self.db.save_stats}\n"
            f"`Verbose Stats:  `{self.db.verbose}\n"
            f"`Data Retention: `{self.db.delta} hours\n"
            f"`Watching:       `{', '.join(self.db.watching) if self.db.watching else 'None'}"
        )
        await ctx.send(txt)

    @profiler.command(name="save")
    async def save_settings(self, ctx: commands.Context):
        """
        Toggle saving stats persistently

        **Warning**: The config size can grow very large if this is enabled for a long time
        """
        self.db.save_stats = not self.db.save_stats
        await self.save()
        await ctx.send(f"Save stats is now **{self.db.save_stats}**")

    @profiler.command(name="verbose")
    async def verbose_settings(self, ctx: commands.Context):
        """
        Toggle verbose stats
        """
        self.db.verbose = not self.db.verbose
        await self.save()
        await ctx.send(f"Verbose stats is now **{self.db.verbose}**")

    @profiler.command(name="attach")
    async def attach_cog(self, ctx: commands.Context, cog_name: str):
        """
        Attach a profiler to a cog
        """
        if not self.bot.get_cog(cog_name):
            return await ctx.send(f"**{cog_name}** is not a valid cog")

        if cog_name in self.db.watching:
            return await ctx.send(f"**{cog_name}** is already being watched")

        self.db.watching.append(cog_name)
        self.rebuild()
        await self.save()
        await ctx.send(f"**{cog_name}** is now being watched")

    @profiler.command(name="detach")
    async def detach_cog(self, ctx: commands.Context, cog_name: str):
        """
        Remove a cog from the profiling list

        This will remove all collected stats for this cog from the config
        """
        if cog_name not in self.db.watching:
            return await ctx.send(f"**{cog_name}** is not being watched")

        self.db.watching.remove(cog_name)
        self.rebuild()

        if cog_name in self.db.stats:
            del self.db.stats[cog_name]

        await self.save()
        await ctx.send(f"**{cog_name}** is no longer being watched")

    @profiler.command(name="memory", aliases=["mem", "m"])
    async def profile_summary(self, ctx: commands.Context, limit: int = 15):
        """
        Profile memory usage of objects in the current environment
        """
        async with ctx.typing():
            res = await asyncio.to_thread(profile_memory, limit)
            for p in pagify(res, page_length=1980):
                await ctx.send(box(p, "py"))

    @profiler.command(name="view", aliases=["v"])
    async def profile_menu(self, ctx: commands.Context):
        """
        View a menu of the current stats
        """
        view = ProfileMenu(ctx, self.db)
        await view.start()
