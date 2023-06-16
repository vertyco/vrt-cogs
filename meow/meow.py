import random

from redbot.core import commands


class Meow(commands.Cog):
    """
    Meow!

    My girlfriend had a dream about this cog, so I had to make it ¯\_(ツ)_/¯
    """

    __author__ = "Vertyco"
    __version__ = "0.0.4"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def meow(self, ctx, *, text: str = None):
        if not text:
            if hasattr(ctx.message, "reference") and ctx.message.reference:
                try:
                    text = ctx.message.reference.resolved.content
                except AttributeError:
                    pass
            if not text:
                async for msg in ctx.channel.history(limit=3):
                    text = msg.content
                    if text:
                        break
        await self.meowstring(text, ctx)

    async def meowstring(self, text, ctx):
        if "now" in text:
            newstring = text.replace("now", "meow")
            await ctx.send(newstring)
        else:
            cats = [
                "^._.^",
                "ฅ(＾・ω・＾ฅ)",
                "（＾・ω・＾✿）",
                "（＾・ω・＾❁）",
                "(=^･ω･^=)",
                "(^・x・^)",
                "(=^･ｪ･^=))ﾉ彡☆",
                "/ᐠ｡▿｡ᐟ\*ᵖᵘʳʳ*",
                "✧/ᐠ-ꞈ-ᐟ\\",
                "/ᐠ –ꞈ –ᐟ\\",
            ]
            return await ctx.send(random.choice(cats))
