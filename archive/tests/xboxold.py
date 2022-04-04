import asyncio
from redbot.core import commands
from redbot.core.utils.chat_formatting import box
import aiohttp
import discord
import json


class Xbox(commands.Cog):
    #Xbox API Tools, inspiration from flare's ApiTools

    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())


    async def get_gamertag(self, gtag):

        async with self.session.get(f'https://xbl.io/api/v2/friends/search?gt={gtag}', headers={"X-Authorization": "8cgooossows0880s00kks48wcosw4c04ksk"}) as resp: #make request using that session and define its output as a response
            data = await resp.json()
            status = resp.status
            remaining = resp.headers['X-RateLimit-Remaining']
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = data
        return parsed, status, remaining


    @commands.command()
    async def xprofile(self, ctx, gtag): #define gt here whatever the value should be
        data, status, remaining = await self.get_gamertag(gtag)
        color = discord.Color.dark_purple() if status == 200 else discord.Color.dark_red()
        msg = await resp.json()
        if len(msg) > 2029:
            msg += "\n..."
        embed = discord.Embed(
            title=f"Results for **{gtag}**",
            color=color,
            description=box(msg, lang="json"),
        )
        embed.add_field(name="Status Code", value=status)
        embed.add_field(name="Requests Left:", value=remaining)
        await ctx.send(embed=embed)

