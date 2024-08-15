import random

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

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

    Use `[p]automeow` to toggle automatic meow response.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.3.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, True)
        self.config.register_guild(auto_meow=False)

        self.cache = {}  # {guild_id: bool}

    @commands.command()
    async def automeow(self, ctx: commands.Context):
        """Toggle automatic meow response"""
        auto_meow = await self.config.guild(ctx.guild).auto_meow()
        await self.config.guild(ctx.guild).auto_meow.set(not auto_meow)
        self.cache[ctx.guild.id] = not auto_meow
        await ctx.send(f"Auto meow is now {'enabled' if not auto_meow else 'disabled'}")

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return
        if " now " not in message.content:
            return

        if message.guild.id in self.cache:
            enabled = self.cache[message.guild.id]
        else:
            enabled = await self.config.guild(message.guild).auto_meow()
            self.cache[message.guild.id] = enabled

        if not enabled:
            return

        channel = message.channel
        if not channel.permissions_for(channel.guild.me).send_messages:
            return

        if channel.permissions_for(channel.guild.me).manage_webhooks:
            webhooks = await channel.webhooks()
            if webhooks:
                hook = webhooks[0]
            else:
                hook = await channel.create_webhook(name="Meow", reason="Auto Meow")
            await hook.send(
                content=message.content.replace("now", "*meow*").replace("Now", "*Meow*"),
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                files=[await i.to_file() for i in message.attachments],
            )
            if channel.permissions_for(channel.guild.me).manage_messages:
                await message.delete()
        else:
            await message.channel.send(message.content.replace("now", "*meow*").replace("Now", "*Meow*"))
