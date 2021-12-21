import discord
import asyncio
import contextlib
import random
import math
from discord.ext import tasks
from redbot.core import commands, Config, bank
from redbot.core.utils.chat_formatting import box, pagify

from .realms import realms
from .animals import pets
from .market import items
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
        default_global = {
            "users": {},
            "autonomy": False
        }
        self.config.register_global(**default_global)

        self.market = {}

        self.refresh_markets.start()

    def cog_unload(self):
        self.refresh_markets.cancel()

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

    @staticmethod
    def get_chance(chance):
        if chance == "common":
            chance = 0.26
        elif chance == "uncommon":
            chance = 0.14
        elif chance == "rare":
            chance = 0.07
        elif chance == "endangered":
            chance = 0.03
        elif chance == "critically endangered":
            chance = 0.01
        return chance

    @commands.command(name="explore")
    async def explore(self, ctx: commands.Context):
        """Start your journey to find a new companion!"""
        d = "You dig through your bag and find your world map wondering what adventures await, " \
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
        embed = discord.Embed(
            description=f"You start making your way to {place}, unsure of what awaits you."
        )
        embed.set_thumbnail(url="https://i.imgur.com/Z5SXJo7.gif")
        await msg.edit(embed=embed)
        # await ctx.send(realms[place])
        await asyncio.sleep(4)
        d = f"You arrive at your destination and take in the beautiful sights and scenery, " \
            f"what would you like to do here?"
        embed = discord.Embed(
            title=place,
            description=d,
            color=realms[place]["color"]
        )
        embed.set_image(url=realms[place]["img"])
        embed = [embed]
        realm_controls = {
            "\N{SHOPPING TROLLEY}": self.open_market,
            "\N{LEFT-POINTING MAGNIFYING GLASS}": self.explore_place
        }
        await msg.delete()
        await menu(ctx, embed, realm_controls)

    async def open_market(
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
        market = self.market[place]
        b = self.bot.get_cog("Economy")
        if not b:
            return
        if await bank.is_global():
            conf = b.config
        else:
            conf = b.config.guild(ctx.guild)
        pdamount = await conf.PAYDAY_CREDITS()
        cur_name = await bank.get_currency_name(ctx.guild)
        pages = []
        for food, d in market.items():
            price = math.ceil(d[2] * pdamount)
            embed = discord.Embed(
                title=place,
                description=f"{food}\n{price} {cur_name}"
            )
            embed.set_image(url=d[3])
            pages.append(embed)
        del DEFAULT_CONTROLS["\N{FOOTPRINTS}"]
        await menu(ctx, pages, DEFAULT_CONTROLS)

    async def explore_place(
            self,
            ctx: commands.Context,
            pages: list,
            controls: dict,
            msg: discord.Message,
            page: int,
            timeout: float,
            emoji: str,
            ):
        place = pages[page].title
        plist = []
        for pet, d in pets.items():
            if place in d["habitat"]:
                plist.append(pet)
        found_pet = random.choice(plist)
        caught = False
        chance = pets[found_pet]["status"]
        chance = self.get_chance(chance)
        if random.random() < chance:
            caught = True
        if caught:
            await ctx.send(f"You found a {found_pet} and it started following you!")
        else:
            await ctx.send(f"You found a {found_pet} but it ran away")

    @tasks.loop(hours=1)
    async def refresh_markets(self):
        for place in realms:
            self.market[place] = {}
            num_itmes = random.choice(range(1, 3))
            itemlist = random.sample(items.keys(), num_itmes)
            for item in itemlist:
                self.market[place][item] = items[item]

    @refresh_markets.before_loop
    async def before_refresh_markets(self):
        await self.bot.wait_until_red_ready()

    @commands.command(name="animals")
    async def view_animals(self, ctx: commands.Context):
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


    @commands.command(name="ptest")
    async def get_payday(self, ctx):
        b = self.bot.get_cog("Economy")
        if not b:
            return
        await ctx.send(str(await bank.is_global()))
        if await bank.is_global():
            conf = b.config
        else:
            conf = b.config.guild(ctx.guild)
        pdamount = await conf.PAYDAY_CREDITS()
        await ctx.send(pdamount)

    @commands.command(name="ran")
    async def randomt(self, ctx):
        await ctx.send(str(random.random()))

    @commands.command()
    async def nick(self, ctx):
        await ctx.send(str(ctx.author.nick))




