import random

from redbot.core import commands

CATS = [
    "^._.^",
    "ฅ(＾・ω・＾ฅ)",
    "（＾・ω・＾✿）",
    "（＾・ω・＾❁）",
    "(=^･ω･^=)",
    "(^・x・^)",
    "(=^･ｪ･^=))ﾉ彡☆",
    "/ᐠ｡▿｡ᐟ\\*ᵖᵘʳʳ*",
    "✧/ᐠ-ꞈ-ᐟ\\",
    "/ᐠ –ꞈ –ᐟ\\",
    "龴ↀ◡ↀ龴",
    "^ↀᴥↀ^",
    "(,,,)=(^.^)=(,,,)",
]


class Meow(commands.Cog):
    """
    Meow!


    My girlfriend had a dream about this cog, so I had to make it ¯\\_(ツ)_/¯
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.2.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def meow(self, ctx: commands.Context):
        text = ""
        if hasattr(ctx.message, "reference") and ctx.message.reference:
            try:
                text = ctx.message.reference.resolved.content
            except AttributeError:
                pass
        else:
            async for msg in ctx.channel.history(limit=3, oldest_first=False):
                if text := msg.content:
                    break
        await self.meowstring(text, ctx)

    async def meowstring(self, text: str, ctx: commands.Context):
        if "now" in text:
            await ctx.send(text.replace("now", "meow"))
        else:
            return await ctx.send(self.get_cat())

    def get_cat(self, *args, **kwargs) -> str:
        return random.choice(CATS)

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema = {
            "name": "get_cat",
            "description": "generates ascii art of a cat face emoji",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
        await cog.register_function("Meow", schema)
