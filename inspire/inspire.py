from redbot.core import commands, checks
import requests
import json
import random
import discord

class Inspire(commands.Cog):
    """Get Inspiring Messages"""

    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot

    def get_quote(self):
        r = requests.get("https://zenquotes.io/api/random")
        json_data = json.loads(r.text)
        quote = json_data[0]['q'] + " - " + json_data[0]['a']
        return(quote)

    @commands.command()
    async def inspire(self, ctx):
        quote = self.get_quote()
        await ctx.send(quote)

    @commands.Cog.listener("on_message")
    async def _message_listener(self, message: discord.Message):

        if message.author.bot:
            return
        msg = message.content.lower().split()
        sad_words = [
            "sad",
            "depressed",
            "unhappy",
            "miserable",
            "depressing"
        ]

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
            "I know you can do this!"
        ]

        if any(w in msg for w in sad_words):
            await message.channel.send(random.choice(starter_encouragements))
