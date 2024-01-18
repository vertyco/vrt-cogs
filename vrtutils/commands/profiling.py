import asyncio
from io import StringIO

from pympler import muppy, summary
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta


class Profiling(MixinMeta):
    @commands.command(name="profsummary")
    @commands.is_owner()
    async def profile_summary(self, ctx: commands.Context):
        """
        Profile mem usage of objects in the current namespace
        """

        def f():
            all_objects = muppy.get_objects()
            sum1 = summary.summarize(all_objects)

            res = StringIO()
            for line in summary.format_(sum1, 15, "size", "descending"):
                res.write(line + "\n")
            return res.getvalue()

        async with ctx.typing():
            res = await asyncio.to_thread(f)
            for p in pagify(res):
                await ctx.send(box(p, "py"))
