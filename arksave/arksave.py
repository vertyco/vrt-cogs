import discord
import os

from redbot.core import commands, Config, bank

import logging
log = logging.getLogger("red.vrt.arksave")


class ArkSave(commands.Cog):
    """
    Ark data save plugin for ArkShop
    """
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 56171351567654, force_registration=True)
        default_global = {
            "price": 1000
        }
        self.config.register_global(**default_global)

    # Make sure arktools and arkshop are both installed
    async def check(self, ctx):
        shop = self.bot.get_cog("ArkShop")
        if not shop:
            await ctx.send("ArkShop not installed")
            return None
        at = self.bot.get_cog("ArkTools")
        if not at:
            await ctx.send("ArkTools not installed")
            return None
        main = await shop.config.main_server()
        if str(ctx.guild.id) != str(main):
            await ctx.send("This cog can only be used on the Main Server")
            return None
        return True

    async def get_xuid(self, ctx):
        arktools = self.bot.get_cog("ArkTools")
        playerdata = await arktools.config.guild(ctx.guild).players()
        for xuid, data in playerdata.items():
            if "discord" in data:
                if ctx.author.id == data["discord"]:
                    return xuid

    @commands.command(name="setsaveprice")
    @commands.admin()
    async def set_save_price(self, ctx, price: int):
        """Set the price for ark data saves"""
        if await self.check(ctx):
            await self.config.price.set(price)
            await ctx.tick()

    @commands.command(name="savemydata")
    async def save_user_data(self, ctx):
        """Append your ark data file name to the list"""
        if not await self.check(ctx):
            return
        xuid = await self.get_xuid(ctx)
        if not xuid:
            return await ctx.send(f"You need to register with `{ctx.prefix}register` first")

        shop = self.bot.get_cog("ArkShop")
        adir = await shop.config.main_path()
        cur_name = await bank.get_currency_name(ctx.guild)
        price = await self.config.price()

        if not await bank.can_spend(ctx.author, int(price)):
            return await ctx.send(f"You are too poor to buy that :smiling_face_with_tear:\n"
                                  f"Data backups cost {price} {cur_name}")

        if not os.path.exists(adir):
            return await ctx.send("Cant find source dir")

        save_file = os.path.join(adir, "ArkSave.txt")
        if not os.path.exists(save_file):
            with open(save_file, "w") as file:
                file.write(f"{xuid}\n")
        else:
            with open(save_file, "a") as file:
                file.write(f"{xuid}\n")

        await bank.withdraw_credits(ctx.author, int(price))
        embed = discord.Embed(
            description=f"You have succesfully appended your XUID to the data save list for {price} {cur_name}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)















