import asyncio

import aiohttp
import discord
from redbot.core import Config, commands

from .formatter import ships
from .menus import DEFAULT_CONTROLS, menu

LOADING = "https://i.gifer.com/4eta.gif"


class SCTools(commands.Cog):
    """
    Star Citizen info tools
    """

    __author__ = "Vertyco"
    __version__ = "0.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 619619619619619, force_registration=True)

        default_global = {
            "sckey": None,
        }
        self.config.register_global(**default_global)

    async def get_info(self, url):
        headers = {"Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False) as res:
                return await res.json(content_type=None)

    @commands.command(name="sckey")
    async def add_key(self, ctx, api_key=None):
        """
        Add your api key from the star citizen api discord

        https://starcitizen-api.com/startup.php#getting-started
        """
        if not api_key:
            return await ctx.send(
                "View this page for getting started and aqcuiring your api key\n"
                "https://starcitizen-api.com/startup.php#getting-started"
            )
        await self.config.sckey.set(api_key)
        await ctx.message.delete()
        await ctx.send("Api key has been set!")

    @commands.command(name="scships")
    async def get_sc_ships(self, ctx, *, shipname=None):
        """View all ships available in Star Citizen"""
        key = await self.config.sckey()
        if not key:
            return await ctx.send("API key has not been set yet!")
        embed = discord.Embed(
            description="Gathering data...", color=discord.Color.random()
        )
        embed.set_thumbnail(url=LOADING)
        msg = await ctx.send(embed=embed)
        url = f"https://api.starcitizen-api.com/{key}/v1/auto/ships"
        async with ctx.typing():
            data = await self.get_info(url)
            if not shipname:
                pages = await ships(data)
                await msg.delete()
                await menu(ctx, pages, DEFAULT_CONTROLS)
            else:
                shiplist = []
                for ship in data["data"]:
                    if not ship:
                        continue
                    if shipname.lower() in ship["name"].lower():
                        shiplist.append(ship["name"])
                if len(shiplist) == 0:
                    embed = discord.Embed(
                        description="No ships found with that name.",
                        color=discord.Color.random(),
                    )
                    return await msg.edit(embed=embed)
                if len(shiplist) > 1:
                    shipstring = ""
                    count = 1
                    for i in shiplist:
                        shipstring += f"**{count}.** {i}\n"
                        count += 1
                    embed = discord.Embed(
                        title="Type the number corresponding to the ship you want to select",
                        description=shipstring,
                        color=discord.Color.random(),
                    )
                    embed.set_footer(text='Reply "cancel" to close the menu')
                    await msg.edit(embed=embed)

                    def mcheck(message: discord.Message):
                        return (
                            message.author == ctx.author
                            and message.channel == ctx.channel
                        )

                    try:
                        reply = await self.bot.wait_for(
                            "message", timeout=60, check=mcheck
                        )
                    except asyncio.TimeoutError:
                        return await msg.edit(
                            embed=discord.Embed(
                                description="You took too long :yawning_face:"
                            )
                        )
                    if reply.content.lower() == "cancel":
                        return await msg.edit(
                            embed=discord.Embed(description="Game search canceled.")
                        )
                    elif not reply.content.isdigit():
                        return await msg.edit(
                            embed=discord.Embed(description="That's not a number")
                        )
                    elif int(reply.content) > len(shiplist):
                        return await msg.edit(
                            embed=discord.Embed(description="That's not a valid number")
                        )
                    i = int(reply.content) - 1
                    name = shiplist[i]
                else:
                    name = shipname
                for ship in data["data"]:
                    if not ship:
                        continue
                    if name.lower() == ship["name"].lower():
                        s = {"data": [ship]}
                        break
                page = await ships(s)
                page = page[0]
                await msg.edit(embed=page)
