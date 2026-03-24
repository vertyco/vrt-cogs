from redbot.core import commands

from ..abc import MixinMeta


class User(MixinMeta):
    @commands.command(name="myid")
    @commands.guild_only()
    async def myid(self, ctx: commands.Context):
        """Get your Discord User ID for survey forms.

        Run this command and copy the number it gives you.
        Paste it into the survey's \"Discord User ID\" field.
        """
        await ctx.send(f"-# Your Discord User ID is: `{ctx.author.id}`")
