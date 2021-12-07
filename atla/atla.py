import discord
import asyncio
import contextlib
from discord.ext import tasks
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import box, pagify

from .realms import realms
from .animals import pets
from .menus import menu, DEFAULT_CONTROLS


class ATLA(commands.Cog):
    """
    Explore the world from Avatar: The Last Airbender and find/raise your own animals from the ATLA universe!
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 282827852, force_registration=True)
        default_guild = {
            "global_market": False
        }
        default_global = {
            "users": {},
            "autonomy": False
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

    @staticmethod
    async def clear(ctx: commands.Context, message: discord.Message, reaction: str, user: discord.Member):
        perms = message.channel.permissions_for(ctx.me)
        if perms.manage_messages:
            with contextlib.suppress(discord.NotFound):
                await message.remove_reaction(reaction, user)

    @staticmethod
    async def clearall(ctx, message: discord.Message):
        perms = message.channel.permissions_for(ctx.me)
        try:
            if perms.manage_messages:
                await message.clear_reactions()
            else:
                for r in DEFAULT_CONTROLS:
                    await message.remove_reaction(r, ctx.me)
                    await asyncio.sleep(1)
        except discord.Forbidden:
            return
        except discord.NotFound:
            return
        except discord.HTTPException:
            pass
        return

    @commands.command(name="explore")
    async def explore(self, ctx: commands.Context):
        """Start your journey to find a new companion!"""
        d = "You pull up your world map wondering what adventures await, " \
            "but where would you like to go?"
        img = "https://media4.giphy.com/media/duoBP0IhdbR5G7ywYg/giphy.gif?cid=ecf05e47qy4ibw8jn27wgsp2o57imkrnnqezil0q0i695jwy&rid=giphy.gif&ct=g"
        embed = discord.Embed(
            description=d,
        )
        embed.set_thumbnail(url=img)
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(4.5)
        await msg.delete()
        pages = []
        for place, data in realms.items():
            embed = discord.Embed(
                title=place,
                description=data["desc"],
                color=data["color"]
            )
            embed.set_footer(text=f"Page {list(realms.keys()).index(place) + 1}/{len(realms.keys())}")
            pages.append(embed)
        DEFAULT_CONTROLS["\N{FOOTPRINTS}"] = self.go_to_place
        await menu(ctx, pages, DEFAULT_CONTROLS)

    async def go_to_place(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float,
            emoji: str,
            ):
        await self.clearall(ctx, msg)
        place = pages[page].title
        await ctx.send(f"You go to {place}")
        await ctx.send(realms[place])


    @commands.command(name="pets")
    async def view_places(self, ctx: commands.Context):
        """View all places available to explore"""
        pages = []
        for pet, data in pets.items():
            embed = discord.Embed(
                title=pet,
                description=data["desc"]
            )
            bending = "N/A"
            if data["bending"]:
                bending = data["bending"].capitalize()
            info = f"`Status:    `{data['status'].capitalize()}\n" \
                   f"`Affinity:  `{data['affinity'].capitalize()}\n" \
                   f"`Bending:   `{bending}\n" \
                   f"`Food Type: `{data['food'].capitalize()}"
            embed.add_field(name="Info", value=info)
            embed.set_image(url=data["img"])
            embed.set_footer(text=f"Page {list(pets.keys()).index(pet) + 1}/{len(pets.keys())}")
            pages.append(embed)
        await menu(ctx, pages, DEFAULT_CONTROLS)




