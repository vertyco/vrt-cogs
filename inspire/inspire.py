import random

import aiohttp
import discord
from redbot.core import commands


class Inspire(commands.Cog):
    """Get Inspiring Messages"""

    __author__ = "Vertyco"
    __version__ = "1.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    async def get_quote(self):
        async with self.session.get("https://zenquotes.io/api/random") as resp:
            data = await resp.json(content_type=None)
            quote = data[0]["q"] + " - " + data[0]["a"]
            return quote

    @commands.command()
    async def inspire(self, ctx):
        quote = await self.get_quote()
        await ctx.send(quote)

    @commands.Cog.listener("on_message")
    async def _message_listener(self, message: discord.Message):
        # check if message is from a guild
        if not message.guild:
            return
        # check if author is a bot
        if message.author.bot:
            return
        # check whether the cog isn't disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        # check whether the channel isn't on the ignore list
        if not await self.bot.ignored_channel_or_guild(message):
            return
        # check whether the message author isn't on allowlist/blocklist
        if not await self.bot.allowed_by_whitelist_blacklist(message.author):
            return
        # check if bot has perms to send messages
        if not message.channel.permissions_for(message.guild.me).send_messages:
            return

        msg = message.content.lower().split()

        sad_words = ["sad", "depressed", "unhappy", "miserable", "depressing"]

        starter_encouragements = [
            "Cheer up!",
            "Hang in there.",
            "You're a great person!",
            "You've got this!",
            "Just keep swimming just keep swimming!",
            "Good luck today! I know you’ll do great.",
            "Sending major good vibes your way.",
            "I know this won’t be easy, but I also know you’ve got what it takes to get through it.",
            "Hope you’re doing awesome!",
            "Keep on keeping on!",
            "Sending you good thoughts—and hoping you believe in yourself just as much as I believe in you.",
            "I know you can do this!",
        ]

        if any(w in msg for w in sad_words):
            await message.channel.send(random.choice(starter_encouragements))
        else:
            return
