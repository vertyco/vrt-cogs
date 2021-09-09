import random

import discord
from redbot.core import commands


class Meow(commands.Cog):
    """
    Meow!

    My girlfriend had a dream about this cog sooo ¯\_(ツ)_/¯
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def meow(self, ctx, *, text: str = None):
        if not text:
            if hasattr(ctx.message, "reference") and ctx.message.reference:
                try:
                    text = (
                        await ctx.fetch_message(ctx.message.reference.message_id)
                    ).content
                except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                    pass
            if not text:
                text = (await ctx.channel.history(limit=2).flatten())[
                    1
                ].content
                print(text)
        await self.meowstring(text, ctx)

    async def meowstring(self, text, ctx):
        print(text)
        if "now" in text:
            newstring = text.replace("now", "meow")
            await ctx.send(newstring)
        else:
            cats = ["^._.^",
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
