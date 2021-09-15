import discord
import asyncio
import math
import shutil
import os

from redbot.core import commands, Config, bank
from redbot.core.utils.chat_formatting import box, pagify

import rcon

import logging

log = logging.getLogger("red.vrt.arkshop")

SELECTORS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
SHOP_ICON = "https://i.imgur.com/iYpszMO.jpg"


class ArkShop(commands.Cog):
    """
    Integrated Shop for Ark!
    """
    __author__ = "Vertyco"
    __version__ = "1.1.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 117117, force_registration=True)
        default_global = {
            "main_server": None,
            "main_path": None,
            "viewchannel": None,
            "clusters": {},
            "datashops": {},

        }
        default_guild = {
            "shops": {},
            "logchannel": None,
            "viewchannel": None,
            "users": {},
            "logs": {"items": {}, "users": {}}
        }
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)

    @commands.group(name="shopset")
    @commands.admin()
    async def _shopset(self, ctx):
        """Base Ark Shop Setup Command"""
        arktools = self.bot.get_cog("ArkTools")
        # check if cog is installed
        if not arktools:
            embed = discord.Embed(
                title="ArkTools Not Installed",
                description="The `ArkTools` cog is required for this cog to function, "
                            "please install that first and load it.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            pass

    @_shopset.command(name="mainserver")
    @commands.is_owner()
    async def set_main_server(self, ctx):
        """Set the Main Server for the data shop"""
        await self.config.main_server.set(ctx.guild.id)
        return await ctx.send(f"**{ctx.guild}** is now set as the main server!")

    @_shopset.group(name="data")
    @commands.is_owner()
    async def _datashopset(self, ctx):
        """Base Data Shop Setup Command"""
        check = await self.config.main_server()
        # check if main server has been set
        if check is None:
            embed = discord.Embed(
                title="Main Server Not Set",
                description="The Data Shop portion of this cog needs a main server set by the bot owner.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        # check if command was used in main server
        elif check != ctx.guild.id:
            embed = discord.Embed(
                title="Not Main Server",
                description="This feature can only be used on the main bot owner server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            pass

    @_shopset.group(name="file")
    @commands.admin()
    async def _file(self, ctx):
        """
        Manage and create data packs for use in the data shop

        To create a pack follow these steps:
        1. Make the pack in-game manually, put what you want in the pack in your ark data.
        2. Upload the pack with the `upload` subcommand. (pack name will be the actual file and shop name). This will
        move the file from the cluster folder into the "MainPath" folder you set the cog to.
        3. Add the item to the data shop, make sure the item(or option name if item has options) is the exact same name
        as the file name.
        3. For other management tools, see the commands below.
        """
        check = await self.config.main_server()
        # check if main server has been set
        if check is None:
            embed = discord.Embed(
                title="Main Server Not Set",
                description="The Data Shop portion of this cog needs a main server set by the bot owner.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        # check if command was used in main server
        elif check != ctx.guild.id:
            embed = discord.Embed(
                title="Not Main Server",
                description="This feature can only be used on the main bot owner server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            pass

    @_shopset.group(name="rcon")
    @commands.admin()
    async def _rconshopset(self, ctx):
        """Base RCON Shop Setup Command"""
        pass

    @_shopset.command(name="logchannel")
    @commands.guildowner()
    async def set_log_channel(self, ctx, channel: discord.TextChannel):
        """Set a log channel for all purchases to be logged to"""
        await self.config.guild(ctx.guild).logchannel.set(channel.id)
        await ctx.send(f"Log channle set to {channel.mention}")

    @_datashopset.command(name="mainpath")
    async def set_main_path(self, ctx, *, path):
        """Set main path for Data Pack folder"""
        await self.config.main_path.set(path)
        return await ctx.send(f"DataPack path has been set as:\n`{path}`")

    @_datashopset.command(name="addcluster")
    async def add_cluster(self, ctx, cluster_name, *, path):
        """Add a cluster path to the Data Shop"""
        arktools = self.bot.get_cog("ArkTools")
        clusters = await arktools.config.guild(ctx.guild).clusters()
        for cluster in clusters:
            # check if cluster exists in arktools config
            if cluster == cluster_name:
                break
        else:
            return await ctx.send(f"{cluster_name} Cluster does not exist, check your ArkTools settings.")

        # set path for cluster
        async with self.config.clusters() as clusters:
            clusters[cluster_name] = path
            return await ctx.send(f"{cluster} cluster path set as:\n`{path}`")

    @_datashopset.command(name="delcluster")
    async def delete_cluster(self, ctx, cluster_name):
        """Delete a cluster path from the Data Shop"""
        async with self.config.clusters() as clusters:
            for cluster in clusters:

                # check if cluster exists
                if cluster_name == cluster:
                    del clusters[cluster]
                    return await ctx.send(f"{cluster_name} cluster deleted!")
            else:
                return await ctx.send(f"Cluster name `{cluster_name}` not found!")

    @_file.command(name="upload")
    async def upload_pack(self, ctx, clustername, packname, xuid):
        """
        Upload/Create a pre-made pack from your ark data.

        Pack name will be the actual file name and xuid is your xuid
        If the pack name already exists, it will be overwritten by the new pack
        """
        destination_dir = await self.config.main_path()
        item_destination = os.path.join(destination_dir, packname)

        clusters = await self.config.clusters()

        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            return await ctx.send(f"Invalid clustername, try one of these instead:\n"
                                  f"{clist}")

        source_dir = clusters[clustername]
        item_source_file = os.path.join(source_dir, xuid)

        # check source dir
        if not os.path.exists(source_dir):
            return await ctx.send("Source path does not exist!")

        # check destination dir
        if not os.path.exists(destination_dir):
            return await ctx.send("Destination path does not exist!")

        # move/replace pack
        if os.path.exists(item_destination):
            try:
                os.remove(item_destination)
                shutil.move(item_source_file, item_destination)
                return await ctx.send(f"Pack uploaded and overwritten as `{packname}`")
            except Exception as e:
                return await ctx.send(f"Data upload failed!\nError: {e}")
        else:
            shutil.move(item_source_file, item_destination)
            return await ctx.send(f"Pack uploaded and saved as `{packname}`")

    @_file.command(name="check")
    async def check_player_data(self, ctx, clustername, xuid):
        """
        Check a player's in-game data to see if there is anything in it

        If file size is anything other than 0, then there is something in their data.
        """
        clusters = await self.config.clusters()

        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            return await ctx.send(f"Invalid clustername, try one of these instead:\n"
                                  f"{clist}")

        source_dir = clusters[clustername]
        if not os.path.exists(source_dir):
            embed = discord.Embed(
                description=f"Cluster path does not exist!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        player_data_file = os.path.join(source_dir, xuid)
        if not os.path.exists(player_data_file):
            embed = discord.Embed(
                description=f"Player has no data saved.",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

        size = os.path.getsize(player_data_file)
        size = "{:,}".format(int(size))
        embed = discord.Embed(
            description=f"Player data size: `{size} bytes`",
            color=discord.Color.blue()
        )
        return await ctx.send(embed=embed)

    @_file.command(name="send")
    async def send_pack(self, ctx, clustername, packname, xuid):
        """Send a data pack to a player manually"""
        source_dir = await self.config.main_path()
        item_source_file = os.path.join(source_dir, packname)

        clusters = await self.config.clusters()

        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            embed = discord.Embed(
                description=f"Invalid clustername, try one of these instead:\n"
                            f"{clist}",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)

        destination_dir = clusters[clustername]
        item_destination = os.path.join(destination_dir, xuid)

        # check source dir
        if not os.path.exists(source_dir):
            return await ctx.send("Source path does not exist!")

        # check destination dir
        if not os.path.exists(destination_dir):
            return await ctx.send("Destination path does not exist!")

        # remove any existing data from destination
        if os.path.exists(item_destination):
            try:
                os.remove(item_destination)
                shutil.copyfile(item_source_file, item_destination)
                embed = discord.Embed(
                    description=f"Pack sent to XUID: `{xuid}`",
                    color=discord.Color.blue()
                )
                return await ctx.send(embed=embed)
            except Exception as e:
                return await ctx.send(f"Data send failed!\nError: {e}")

        else:
            shutil.copyfile(item_source_file, item_destination)
            embed = discord.Embed(
                description=f"Pack sent to XUID: `{xuid}`",
                color=discord.Color.blue()
            )
            return await ctx.send(embed=embed)

    @_file.command(name="listpacks")
    async def list_packs(self, ctx):
        """List all data packs in the main path as well as their file size"""
        path = await self.config.main_path()
        packs = os.listdir(path)
        packlist = "NAME - SIZE IN BYTES\n"
        for pack in packs:
            fullpath = os.path.join(path, pack)
            size = os.path.getsize(fullpath)
            packlist += f"{pack} - {size}\n"

        for p in pagify(packlist):
            await ctx.send(box(p, lang="python"))

    @_file.command(name="rename")
    async def rename_pack(self, ctx, current_name, new_name):
        """Rename a data pack"""
        directory = await self.config.main_path()
        oldfile = os.path.join(directory, current_name)
        newfile = os.path.join(directory, new_name)

        if os.path.exists(oldfile):
            try:
                os.rename(oldfile, newfile)
                return await ctx.send(f"`{current_name}` pack renamed to `{new_name}`")
            except Exception as e:
                return await ctx.send(f"Failed to rename file!\nError: {e}")
        else:
            return await ctx.send("File not found!")

    @_file.command(name="copyplayerdata")
    async def copy_player_data(self, ctx, clustername, source_xuid, destination_xuid):
        """
        Copy a players ark data to your own.

        useful for checking other players data for various reasons
        """
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            embed = discord.Embed(
                description=f"Invalid clustername, try one of these instead:\n"
                            f"{clist}",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)

        directory = clusters[clustername]
        source = os.path.join(directory, source_xuid)
        target = os.path.join(directory, destination_xuid)

        # check source file
        if not os.path.exists(source):
            embed = discord.Embed(
                description="Source file does not exist!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # check if target already exists
        if os.path.exists(target):
            os.remove(target)

        shutil.copyfile(source, target)
        embed = discord.Embed(
            description=f"Player data from `{source_xuid}` copied to `{destination_xuid}`",
            color=discord.Color.blue()
        )
        return await ctx.send(embed=embed)

    @_file.command(name="delete")
    async def delete_pack(self, ctx, packname):
        """Delete a data pack"""
        directory = await self.config.main_path()
        file = os.path.join(directory, packname)

        if os.path.exists(file):
            try:
                os.remove(file)
                return await ctx.send(f"`{packname}` removed.")
            except Exception as e:
                return await ctx.send(f"Failed to delete datapack!\nError: {e}")
        else:
            return await ctx.send("File not found!")

    @_file.command(name="wipeplayerdata")
    async def wipe_player_data(self, ctx, clustername, player_xuid):
        """Wipe a players Ark data"""
        clusters = await self.config.clusters()
        # check if clustername exists
        if clustername not in clusters:
            clist = ""
            for clustername in clusters:
                clist += f"`{clustername}`\n"
            embed = discord.Embed(
                description=f"Invalid clustername, try one of these instead:\n"
                            f"{clist}",
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed)
        directory = clusters[clustername]
        file = os.path.join(directory, player_xuid)
        if os.path.exists(file):
            try:
                os.remove(file)
                return await ctx.send(f"Player data matching XUID `{player_xuid}` has been wiped.")
            except Exception as e:
                return await ctx.send(f"Failed to delete player data!\nError: {e}")
        else:
            return await ctx.send("File not found!")

    @_datashopset.command(name="addcategory")
    async def add_category(self, ctx, shop_name):
        """Add a data shop category"""
        async with self.config.datashops() as shops:
            if shop_name in shops:
                return await ctx.send(f"{shop_name} shop already exists!")
            else:
                shops[shop_name] = {}
                return await ctx.send(f"{shop_name} shop created!")

    @_datashopset.command(name="delcategory")
    async def delete_category(self, ctx, shop_name):
        """Delete a data shop category"""
        async with self.config.datashops() as shops:
            if shop_name in shops:
                del shops[shop_name]
                return await ctx.send(f"{shop_name} shop removed!")
            else:
                return await ctx.send(f"{shop_name} shop doesn't exist!")

    @_datashopset.command(name="renamecategory")
    async def rename_category(self, ctx, current_name, new_name):
        """Rename a data shop category"""
        async with self.config.datashops() as shops:
            if current_name in shops:
                shops[new_name] = shops.pop(current_name)
                return await ctx.send(f"{current_name} shop has been renamed to {new_name}!")
            else:
                return await ctx.send(f"{current_name} shop doesn't exist!")

    @_datashopset.command(name="additem")
    async def add_data_item(self, ctx, shop_name, item_name, price=None):
        """
        Add an item to the data shop

        Use quotes if item name has spaces

        If item has options, the item name doesn't have to match the file name and you can leave out the price
        """
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            if item_name in shops[shop_name]:
                return await ctx.send(f"{item_name} item already exists!")

            if price:
                shops[shop_name][item_name] = {"price": price, "options": {}}
                currency_name = await bank.get_currency_name(ctx.guild)
                return await ctx.send(
                    f"{item_name} has been added to the {shop_name} shop for {price} {currency_name}"
                )
            else:
                shops[shop_name][item_name] = {"price": False, "options": {}}
                return await ctx.send(
                    f"{item_name} has been added to the {shop_name} shop with options.\n"
                    f"You will need to add options to it with `{ctx.prefix}shopset data addoption`"
                )

    @_datashopset.command(name="delitem")
    async def delete_data_item(self, ctx, shop_name, item_name):
        """Delete an item from a shop, whether it has options or not"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            else:
                del shops[shop_name][item_name]
                return await ctx.tick()

    @_datashopset.command(name="addoption")
    async def add_data_item_option(self, ctx, shop_name, item_name, option, price):
        """Add an option to an existing item in the data shop"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option already exists!")
            else:
                shops[shop_name][item_name]["options"][option] = price
                return await ctx.tick()

    @_datashopset.command(name="deloption")
    async def del_data_item_option(self, ctx, shop_name, item_name, option):
        """Delete an option from an existing item in the data shop"""
        async with self.config.datashops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option not in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option not found!")
            else:
                del shops[shop_name][item_name]["options"][option]
                return await ctx.tick()

    @commands.command(name="setcluster")
    async def set_cluster(self, ctx):
        """Set a cluster for the data shop so the cog knows where to send your data"""
        arktools = self.bot.get_cog("ArkTools")
        clusters = await arktools.config.guild(ctx.guild).clusters()
        clist = ""
        for clustername in clusters:
            clist += f"`{clustername}`\n"

        embed = discord.Embed(
            description=f"**Type one of the cluster names below.**\n"
                        f"{clist}"
        )
        msg = await ctx.send(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        if reply.content.lower() not in clusters:
            return await msg.edit(embed=discord.Embed(description="Cluster doesn't exist!"))
        else:
            async with self.config.guild(ctx.guild).users() as users:
                users[ctx.author.id] = reply.content.lower()
                embed = discord.Embed(
                    description=f"Cluster has been set for {ctx.author.name}!",
                    color=discord.Color.green()
                )
                return await msg.edit(embed=embed)

    @_rconshopset.command(name="addcategory")
    async def add_rcon_category(self, ctx, shop_name):
        """Add an rcon shop category"""
        async with self.config.guild(ctx.guild).shops() as shops:
            if shop_name in shops:
                return await ctx.send(f"{shop_name} shop already exists!")
            else:
                shops[shop_name] = {}
                return await ctx.send(f"{shop_name} shop created!")

    @_rconshopset.command(name="delcategory")
    async def delete_rcon_category(self, ctx, shop_name):
        """Delete an rcon shop category"""
        async with self.config.guild(ctx.guild).shops() as shops:
            if shop_name in shops:
                del shops[shop_name]
                return await ctx.send(f"{shop_name} shop removed!")
            else:
                return await ctx.send(f"{shop_name} shop doesn't exist!")

    @_rconshopset.command(name="renamecategory")
    async def rename_rcon_category(self, ctx, current_name, new_name):
        """Rename an rcon shop category"""
        async with self.config.guild(ctx.guild).shops() as shops:
            if current_name in shops:
                shops[new_name] = shops.pop(current_name)
                return await ctx.send(f"{current_name} shop has been renamed to {new_name}!")
            else:
                return await ctx.send(f"{current_name} shop doesn't exist!")

    @_rconshopset.command(name="additem")
    async def add_rcon_item(self, ctx, shop_name, item_name, price=None):
        """
        Add an item to an rcon shop category

        Use quotes if item name has spaces
        """
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            if item_name in shops[shop_name]:
                return await ctx.send(f"{item_name} item already exists!")

            if price:
                shops[shop_name][item_name] = {"price": price, "options": {}, "paths": []}

                msg = await ctx.send(
                    "Type the full blueprint paths including quantity/quality/blueprint numbers below.\n"
                    "Separate each full path with a new line for multiple items in one pack.\n"
                    "Type `cancel` to cancel the item.")

                def check(message: discord.Message):
                    return message.author == ctx.author and message.channel == ctx.channel

                try:
                    reply = await self.bot.wait_for("message", timeout=240, check=check)
                    if reply.content.lower() == "cancel":
                        return await ctx.send("Item add canceled.")
                    else:
                        paths = reply.content.split("\n")
                        shops[shop_name][item_name]["paths"] = paths
                        return await ctx.send(f"Item paths set!")

                except asyncio.TimeoutError:
                    return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

            else:
                shops[shop_name][item_name] = {"price": False, "options": {}, "paths": []}
                return await ctx.send(f"Item added, please add options to it with `{ctx.prefix}shopset rcon addoption`")

    @_rconshopset.command(name="delitem")
    async def delete_rcon_item(self, ctx, shop_name, item_name):
        """
        Delete an item from an rcon shop category
        """
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            else:
                del shops[shop_name][item_name]
                return await ctx.tick()

    @_rconshopset.command(name="addoption")
    async def add_rcon_item_option(self, ctx, shop_name, item_name, option, price):
        """
        Add an option to an existing item in the rcon shop

        When it asks for paths, be sure to include the FULL blueprint path and <quantity> <quality> <BP T/F> identifiers
        for BP identifier: 1=True and 0=False
        """
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option already exists!")
            else:
                msg = await ctx.send(
                    "Type the full blueprint paths including quantity/quality/blueprint numbers below.\n"
                    "Separate each full path with a new line for multiple items in one option.\n"
                    "Type `cancel` to cancel the option.")

                def check(message: discord.Message):
                    return message.author == ctx.author and message.channel == ctx.channel

                try:
                    reply = await self.bot.wait_for("message", timeout=240, check=check)

                    if reply.content.lower() == "cancel":
                        return await ctx.send("Option add canceled.")
                    else:
                        paths = reply.content.split("\n")
                        shops[shop_name][item_name]["options"][option] = {"price": price, "paths": paths}
                        return await ctx.send(f"Option set!")
                except asyncio.TimeoutError:
                    return await msg.edit("You took too long :yawning_face:")

    @_rconshopset.command(name="deloption")
    async def del_rcon_item_option(self, ctx, shop_name, item_name, option):
        """Delete an option from an existing item in the rcon shop"""
        async with self.config.guild(ctx.guild).shops() as shops:
            # check if shop exists
            if shop_name not in shops:
                return await ctx.send(f"{shop_name} shop not found!")
            # check if item exists
            elif item_name not in shops[shop_name]:
                return await ctx.send(f"{item_name} item not found!")
            # check if option exists
            elif option not in shops[shop_name][item_name]["options"]:
                return await ctx.send(f"{option} option not found!")
            else:
                del shops[shop_name][item_name]["options"][option]
                return await ctx.tick()

    @_rconshopset.command(name="checkitem")
    async def check_rcon_item(self, ctx, shop_name, item_name):
        """Check the blueprint strings in an item"""
        shops = await self.config.guild(ctx.guild).shops()
        # check if shop exists
        if shop_name not in shops:
            return await ctx.send(f"{shop_name} shop not found!")
        # check if item exists
        elif item_name not in shops[shop_name]:
            return await ctx.send(f"{item_name} item not found!")
        else:
            pathmsg = ""
            for path in shops[shop_name][item_name]["paths"]:
                pathmsg += f"`{path}`\n"
            return await ctx.send(pathmsg)

    async def get_xuid_from_arktools(self, ctx):
        arktools = self.bot.get_cog("ArkTools")
        if not arktools:
            return await ctx.send("The `ArkTools` cog is required for this cog to function, "
                                  "please have the bot owner install that first and load it.")
        playerdata = await arktools.config.guild(ctx.guild).playerstats()
        for player in playerdata:
            if "discord" in playerdata[player]:
                if ctx.author.id == playerdata[player]["discord"]:
                    xuid = playerdata[player]["xuid"]
                    break
        else:
            return None
        return xuid

    # USER COMMANDS
    @commands.command(name="shoplb")
    async def shop_leaderboard(self, ctx):
        """Get leaderboard for most items bought"""
        pass

    @commands.command(name="shopstats")
    async def shop_stats(self, ctx):
        """Get ordered list of items purchased"""
        pass

    @commands.command(name="rconshop")
    async def _rconshop(self, ctx):
        """
        Open up the rcon shop

        This shop uses RCON to send items directly to your inventory
        """
        # check if player is registered in arktools config and get their xuid if they are
        xuid = await self.get_xuid_from_arktools(ctx)
        if xuid is None:
            embed = discord.Embed(
                description=f"Your discord ID has not been found in the database.\n"
                            f"Please register with `{ctx.prefix}arktools register`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # check if player has set a cluster
        users = await self.config.guild(ctx.guild).users()
        if str(ctx.author.id) not in users:
            embed = discord.Embed(
                description=f"You need to set the cluster you play on.\n"
                            f"You can set it with `{ctx.prefix}setcluster`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            cname = users[str(ctx.author.id)]

        return await self.rcon_category_compiler(ctx, xuid, cname)

    async def rcon_category_compiler(self, ctx, xuid, cname, message=None):
        categories = await self.config.guild(ctx.guild).shops()
        # how many categories
        category_count = len(categories.keys())

        # how many pages
        pages = math.ceil(category_count / 4)
        if pages == 0:
            embed = discord.Embed(
                description="There are no categories added!",
                color=discord.Color.red()
            )
            if message:
                await message.clear_reactions()
                return await message.edit(embed=embed)
            else:
                return await ctx.send(embed=embed)

        # category info setup
        shop_categories = []
        for category in categories:
            num_items = len(categories[category].keys())
            shop_categories.append((category, num_items))

        # sort that bitch
        shop_categories = sorted(shop_categories, key=lambda x: x[0])

        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title="RCON Shop",
                description="Category list"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(shop_categories):
                stop = len(shop_categories)
            for i in range(start, stop, 1):
                category_name = shop_categories[i][0]
                item_count = shop_categories[i][1]
                embed.add_field(
                    name=f"{SELECTORS[count]} {category_name}",
                    value=f"Items: {item_count}",
                    inline=False
                )
                count += 1
            embedlist.append(embed)
            start += 4
            stop += 4
        if message is None:
            return await self.shop_menu(ctx, xuid, cname, embedlist, "rconcategory")
        else:
            return await self.shop_menu(ctx, xuid, cname, embedlist, "rconcategory", message)

    async def rcon_item_compiler(self, ctx, message, category_name, xuid, cname, oname=None):
        categories = await self.config.guild(ctx.guild).shops()
        category = {}
        if category_name:
            category = categories[category_name]
        else:
            for catname in categories:
                for item in categories[catname]:
                    if oname in categories[catname][item]["options"]:
                        category = categories[catname]
                        break

        # how many items
        item_count = len(category.keys())

        # how many pages
        pages = math.ceil(item_count / 4)
        if pages == 0:
            await message.clear_reactions()
            embed = discord.Embed(
                description="Category has no items in it!",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)

        # item info setup
        items = []
        for item in category:
            num_options = len(category[item]["options"].keys())
            if num_options == 0:
                price = category[item]["price"]
            else:
                price = None
            items.append((item, num_options, price))

        # sort that bitch
        items = sorted(items, key=lambda x: x[0])

        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title="RCON Shop",
                description="Item list"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(items):
                stop = len(items)
            for i in range(start, stop, 1):
                item_name = items[i][0]
                option_count = items[i][1]
                price = items[i][2]
                if option_count == 0:
                    embed.add_field(
                        name=f"{SELECTORS[count]} {item_name}",
                        value=f"Price: {price}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"{SELECTORS[count]} {item_name}",
                        value=f"Options: {option_count}",
                        inline=False
                    )
                count += 1
            embedlist.append(embed)
            start += 4
            stop += 4
        return await self.shop_menu(ctx, xuid, cname, embedlist, "rconitem", message)

    async def rcon_buy_or_goto_options(self, ctx, message, name, xuid, cname):
        categories = await self.config.guild(ctx.guild).shops()
        full_item = {}
        for category in categories:
            for item in categories[category]:
                if name == item:
                    full_item = categories[category][name]
                    break
        options = full_item["options"]
        price = full_item["price"]

        # if item has no options
        if price and not options:
            await message.clear_reactions()
            return await self.make_rcon_purchase(ctx, name, xuid, price, cname, message)

        # go back to menu if item contains options
        else:
            # how many options
            option_count = len(options.keys())

            # how many pages
            pages = math.ceil(option_count / 4)

            # option info setup
            optionlist = []
            for option in options:
                option_price = options[option]["price"]
                optionlist.append((option, option_price))

            # sort that bitch
            optionlist = sorted(optionlist, key=lambda x: x[0])

            # menu setup
            start = 0
            stop = 4
            embedlist = []
            for page in range(int(pages)):
                embed = discord.Embed(
                    title="RCON Shop",
                    description=f"{name} options"
                )
                embed.set_thumbnail(url=SHOP_ICON)
                count = 0
                if stop > len(optionlist):
                    stop = len(optionlist)
                for i in range(start, stop, 1):
                    oname = optionlist[i][0]
                    oprice = optionlist[i][1]
                    embed.add_field(
                        name=f"{SELECTORS[count]} {oname}",
                        value=f"Price: {oprice}",
                        inline=False
                    )
                    count += 1
                embedlist.append(embed)
                start += 4
                stop += 4
            return await self.shop_menu(ctx, xuid, cname, embedlist, "rconoption", message, name)

    async def rcon_option_path_finder(self, ctx, message, name, xuid, cname, itemname):
        categories = await self.config.guild(ctx.guild).shops()
        price = 0
        paths = []
        for category in categories:
            for item in categories[category]:
                if itemname == item:
                    price = categories[category][item]["options"][name]["price"]
                    paths = categories[category][item]["options"][name]["paths"]
                    break
        return await self.make_rcon_purchase(ctx, itemname, xuid, price, cname, message, paths)

    async def make_rcon_purchase(self, ctx, name, xuid, price, cname, message, paths):
        # check if user can afford the item
        currency_name = await bank.get_currency_name(ctx.guild)
        if not await bank.can_spend(ctx.author, int(price)):
            await message.clear_reactions()
            embed = discord.Embed(
                description=f"You don't have enough {currency_name} to buy this :smiling_face_with_tear:",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)

        # gather server data
        arktools = self.bot.get_cog("ArkTools")
        clusters = await arktools.config.guild(ctx.guild).clusters()
        serverlist = []
        for server in clusters[cname]["servers"]:
            serverlist.append(clusters[cname]["servers"][server])

        await message.clear_reactions()

        # ask for implant ID
        embed = discord.Embed(
            description=f"**Type your implant ID below.**\n",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url="https://i.imgur.com/PZmR6QW.png")
        await message.edit(embed=embed)

        def check(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=check)
        except asyncio.TimeoutError:
            return await message.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

        commandlist = []
        for path in paths:
            commandlist.append(f"giveitemtoplayer {reply.content} {path}")

        tasks = []
        for server in serverlist:
            for command in commandlist:
                tasks.append(self.rcon(server, command))

        await asyncio.gather(*tasks)

        # withdraw credits and send purchase message
        await bank.withdraw_credits(ctx.author, int(price))
        embed = discord.Embed(
            description=f"You have purchased the {name} item for {price} {currency_name}!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=SHOP_ICON)
        await message.edit(embed=embed)

        logchannel = await self.config.guild(ctx.guild).logchannel()
        logchannel = ctx.guild.get_channel(logchannel)
        embed = discord.Embed(
            title="DATA Purchase",
            description=f"**{ctx.author.name}** has purchased the {name} item.\n"
                        f"**Price:** {price} {currency_name}\n"
                        f"**XUID:** {xuid}"
        )
        await logchannel.send(embed=embed)

        async with self.config.guild(ctx.guild).logs() as logs:
            # shop logs
            if name not in logs["items"]:
                logs["items"][name] = {"type": "rcon", "count": 1}
            else:
                logs["items"][name]["count"] += 1

            # individual user logs
            if ctx.author.id not in logs["users"]:
                logs["users"][ctx.author.id] = {}
            else:
                if name not in logs["users"][ctx.author.id]:
                    logs["users"][ctx.author.id][name] = {"type": "rcon", "count": 1}
                else:
                    logs["users"][ctx.author.id][name]["count"] += 1
            return

    async def rcon(self, server, command):
        try:
            await rcon.asyncio.rcon(
                command=command,
                host=server["ip"],
                port=server["port"],
                passwd=server["password"]
            )
        except WindowsError as e:
            log.exception(f"Rcon failed:", e)
        except Exception:
            log.exception(f"Other RCON failure", Exception)

    @commands.command(name="dshop")
    async def _datashop(self, ctx):
        """
        Open up the data shop

        This shop uses pre-made data packs created in-game and then moved to a separate folder.

        The ark data, when purchased, gets copied to the cluster folder as the person's XUID, allowing
        them to access it as their own data.

        """

        # check if command was used in main server
        check = await self.config.main_server()
        if check != ctx.guild.id:
            embed = discord.Embed(
                title="Not Main Server",
                description="This feature can only be used on the main bot owner server!",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # check if player is registered in arktools config and get their xuid if they are
        xuid = await self.get_xuid_from_arktools(ctx)
        if xuid is None:
            embed = discord.Embed(
                description=f"Your discord ID has not been found in the database.\n"
                            f"Please register with `{ctx.prefix}arktools register`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        # check if player has set a cluster
        users = await self.config.guild(ctx.guild).users()
        if str(ctx.author.id) not in users:
            embed = discord.Embed(
                description=f"You need to set the cluster you play on.\n"
                            f"You can set it with `{ctx.prefix}setcluster`",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        else:
            cname = users[str(ctx.author.id)]

        return await self.category_compiler(ctx, xuid, cname)

    async def category_compiler(self, ctx, xuid, cname, message=None):
        categories = await self.config.datashops()
        # how many categories
        category_count = len(categories.keys())

        # how many pages
        pages = math.ceil(category_count / 4)
        if pages == 0:
            embed = discord.Embed(
                description="There are no categories added!",
                color=discord.Color.red()
            )
            if message:
                await message.clear_reactions()
                return await message.edit(embed=embed)
            else:
                return await ctx.send(embed=embed)

        # category info setup
        shop_categories = []
        for category in categories:
            num_items = len(categories[category].keys())
            shop_categories.append((category, num_items))

        # sort that bitch
        shop_categories = sorted(shop_categories, key=lambda x: x[0])

        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title="Data Shop",
                description="Category list"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(shop_categories):
                stop = len(shop_categories)
            for i in range(start, stop, 1):
                category_name = shop_categories[i][0]
                item_count = shop_categories[i][1]
                embed.add_field(
                    name=f"{SELECTORS[count]} {category_name}",
                    value=f"Items: {item_count}",
                    inline=False
                )
                count += 1
            embedlist.append(embed)
            start += 4
            stop += 4
        if message is None:
            return await self.shop_menu(ctx, xuid, cname, embedlist, "category")
        else:
            return await self.shop_menu(ctx, xuid, cname, embedlist, "category", message)

    async def item_compiler(self, ctx, message, category_name, xuid, cname, oname=None):
        categories = await self.config.datashops()
        category = {}
        if category_name:
            category = categories[category_name]
        else:
            for catname in categories:
                for item in categories[catname]:
                    if oname in categories[catname][item]["options"]:
                        category = categories[catname]
                        break

        # how many items
        item_count = len(category.keys())

        # how many pages
        pages = math.ceil(item_count / 4)
        if pages == 0:
            await message.clear_reactions()
            embed = discord.Embed(
                description="Category has no items in it!",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)

        # item info setup
        items = []
        for item in category:
            num_options = len(category[item]["options"].keys())
            if num_options == 0:
                price = category[item]["price"]
            else:
                price = None
            items.append((item, num_options, price))

        # sort that bitch
        items = sorted(items, key=lambda x: x[0])

        # menu setup
        start = 0
        stop = 4
        embedlist = []
        for page in range(int(pages)):
            embed = discord.Embed(
                title="Data Shop",
                description="Item list"
            )
            embed.set_thumbnail(url=SHOP_ICON)
            count = 0
            if stop > len(items):
                stop = len(items)
            for i in range(start, stop, 1):
                item_name = items[i][0]
                option_count = items[i][1]
                price = items[i][2]
                if option_count == 0:
                    embed.add_field(
                        name=f"{SELECTORS[count]} {item_name}",
                        value=f"Price: {price}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"{SELECTORS[count]} {item_name}",
                        value=f"Options: {option_count}",
                        inline=False
                    )
                count += 1
            embedlist.append(embed)
            start += 4
            stop += 4
        return await self.shop_menu(ctx, xuid, cname, embedlist, "item", message)

    async def buy_or_goto_options(self, ctx, message, name, xuid, cname):
        categories = await self.config.datashops()
        full_item = {}
        for category in categories:
            for item in categories[category]:
                if name == item:
                    full_item = categories[category][name]
                    break
        options = full_item["options"]
        price = full_item["price"]

        # if item has no options
        if price and not options:
            await message.clear_reactions()
            return await self.make_purchase(ctx, name, xuid, price, cname, message)

        # go back to menu if item contains options
        else:
            # how many options
            option_count = len(options.keys())

            # how many pages
            pages = math.ceil(option_count / 4)

            # option info setup
            optionlist = []
            for key, value in options.items():
                option_name = key
                option_price = value
                optionlist.append((option_name, option_price))

            # sort that bitch
            optionlist = sorted(optionlist, key=lambda x: x[0])

            # menu setup
            start = 0
            stop = 4
            embedlist = []
            for page in range(int(pages)):
                embed = discord.Embed(
                    title="Data Shop",
                    description=f"{name} options"
                )
                embed.set_thumbnail(url=SHOP_ICON)
                count = 0
                if stop > len(optionlist):
                    stop = len(optionlist)
                for i in range(start, stop, 1):
                    oname = optionlist[i][0]
                    oprice = optionlist[i][1]
                    embed.add_field(
                        name=f"{SELECTORS[count]} {oname}",
                        value=f"Price: {oprice}",
                        inline=False
                    )
                    count += 1
                embedlist.append(embed)
                start += 4
                stop += 4
            return await self.shop_menu(ctx, xuid, cname, embedlist, "option", message)

    async def option_path_finder(self, ctx, message, name, xuid, cname):
        categories = await self.config.datashops()
        price = 0
        for category in categories:
            for item in categories[category]:
                if categories[category][item]["options"]:
                    for key, value in categories[category][item]["options"].items():
                        if name == key:
                            price = value
                            break
        return await self.make_purchase(ctx, name, xuid, price, cname, message)

    async def make_purchase(self, ctx, name, xuid, price, cname, message):
        source_directory = await self.config.main_path()
        clusters = await self.config.clusters()
        dest_directory = clusters[cname]
        currency_name = await bank.get_currency_name(ctx.guild)
        if not await bank.can_spend(ctx.author, int(price)):
            await message.clear_reactions()
            embed = discord.Embed(
                description=f"You don't have enough {currency_name} to buy this :smiling_face_with_tear:",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)
        # check source path
        if not os.path.exists(source_directory):
            await message.clear_reactions()
            embed = discord.Embed(
                description=f"Source path does not exist!",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)

        # check destination path
        if not os.path.exists(dest_directory):
            await message.clear_reactions()
            embed = discord.Embed(
                description=f"Destination path does not exist!",
                color=discord.Color.red()
            )
            return await message.edit(embed=embed)

        destination = os.path.join(dest_directory, xuid)

        # remove any existing data from destination
        if os.path.exists(destination):
            try:
                os.remove(destination)
            except PermissionError:
                await message.clear_reactions()
                embed = discord.Embed(
                    description=f"Failed to clean source file!\n",
                    color=discord.Color.red()
                )
                return await message.edit(embed=embed)

        item_source_file = os.path.join(source_directory, name)
        shutil.copyfile(item_source_file, destination)
        await bank.withdraw_credits(ctx.author, int(price))
        embed = discord.Embed(
            description=f"You have purchased the {name} item for {price} {currency_name}!",
            color=discord.Color.green()
        )
        await message.clear_reactions()
        await message.edit(embed=embed)

        logchannel = await self.config.guild(ctx.guild).logchannel()
        logchannel = ctx.guild.get_channel(logchannel)
        embed = discord.Embed(
            title="RCON Purchase",
            description=f"**{ctx.author.name}** has purchased the {name} item.\n"
                        f"**Price:** {price} {currency_name}\n"
                        f"**XUID:** {xuid}"
        )
        await logchannel.send(embed=embed)

        async with self.config.guild(ctx.guild).logs() as logs:
            # shop logs
            if name not in logs["items"]:
                logs["items"][name] = {"type": "data", "count": 1}
            else:
                logs["items"][name]["count"] += 1

            # individual user logs
            if ctx.author.id not in logs["users"]:
                logs["users"][ctx.author.id] = {}
            else:
                if name not in logs["users"][ctx.author.id]:
                    logs["users"][ctx.author.id][name] = {"type": "data", "count": 1}
                else:
                    logs["users"][ctx.author.id][name]["count"] += 1
            return

    async def shop_menu(self, ctx, xuid, cname, embeds, type, message=None, itemname=None):
        pages = len(embeds)
        cur_page = 1
        if type in ["category", "opiton", "item"]:
            embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}\n"
                                                 f"Remember to empty your Ark data before purchasing from the Data Shop!")
        if type in ["rconcategory", "rconopiton", "rconitem"]:
            embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}\n"
                                                 f"Make sure you are ONLINE when purchasing from the RCON shop!")
        if message is None:
            message = await ctx.send(embed=embeds[cur_page - 1])
        else:
            await message.edit(embed=embeds[cur_page - 1])

        await message.add_reaction("↩️")
        await message.add_reaction("◀️")
        await message.add_reaction("❌")
        await message.add_reaction("▶️")
        await message.add_reaction("1️⃣")
        await message.add_reaction("2️⃣")
        await message.add_reaction("3️⃣")
        await message.add_reaction("4️⃣")

        reactions = ["↩️", "◀️", "❌", "▶️", "1️⃣", "2️⃣", "3️⃣", "4️⃣"]

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in reactions

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)

                if str(reaction.emoji) == "▶️" and cur_page + 1 <= pages:
                    cur_page += 1
                    if type in ["category", "opiton", "item"]:
                        embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}\n"
                                                             f"Remember to empty your Ark data before purchasing from the Data Shop!")
                    if type in ["rconcategory", "rconopiton", "rconitem"]:
                        embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}\n"
                                                             f"Make sure you are ONLINE when purchasing from the RCON shop!")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    if type in ["category", "opiton", "item"]:
                        embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}\n"
                                                             f"Remember to empty your Ark data before purchasing from the Data Shop!")
                    if type in ["rconcategory", "rconopiton", "rconitem"]:
                        embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}\n"
                                                             f"Make sure you are ONLINE when purchasing from the RCON shop!")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "1️⃣":
                    name = embeds[cur_page - 1].fields[0].name
                    name = name.split(' ', 1)[-1]
                    await message.remove_reaction(reaction, user)
                    if type == "category":
                        return await self.item_compiler(ctx, message, name, xuid, cname)
                    if type == "item":
                        return await self.buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "option":
                        return await self.option_path_finder(ctx, message, name, xuid, cname)
                    if type == "rconcategory":
                        return await self.rcon_item_compiler(ctx, message, name, xuid, cname)
                    if type == "rconitem":
                        return await self.rcon_buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "rconoption":
                        return await self.rcon_option_path_finder(ctx, message, name, xuid, cname, itemname)

                elif str(reaction.emoji) == "2️⃣" and len(embeds[cur_page - 1].fields) > 1:
                    name = embeds[cur_page - 1].fields[1].name
                    name = name.split(' ', 1)[-1]
                    await message.remove_reaction(reaction, user)
                    if type == "category":
                        return await self.item_compiler(ctx, message, name, xuid, cname)
                    if type == "item":
                        return await self.buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "option":
                        return await self.option_path_finder(ctx, message, name, xuid, cname)
                    if type == "rconcategory":
                        return await self.rcon_item_compiler(ctx, message, name, xuid, cname)
                    if type == "rconitem":
                        return await self.rcon_buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "rconoption":
                        return await self.rcon_option_path_finder(ctx, message, name, xuid, cname, itemname)

                elif str(reaction.emoji) == "3️⃣" and len(embeds[cur_page - 1].fields) > 2:
                    name = embeds[cur_page - 1].fields[2].name
                    name = name.split(' ', 1)[-1]
                    await message.remove_reaction(reaction, user)
                    if type == "category":
                        return await self.item_compiler(ctx, message, name, xuid, cname)
                    if type == "item":
                        return await self.buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "option":
                        return await self.option_path_finder(ctx, message, name, xuid, cname)
                    if type == "rconcategory":
                        return await self.rcon_item_compiler(ctx, message, name, xuid, cname)
                    if type == "rconitem":
                        return await self.rcon_buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "rconoption":
                        return await self.rcon_option_path_finder(ctx, message, name, xuid, cname, itemname)

                elif str(reaction.emoji) == "4️⃣" and len(embeds[cur_page - 1].fields) > 3:
                    name = embeds[cur_page - 1].fields[3].name
                    name = name.split(' ', 1)[-1]
                    await message.remove_reaction(reaction, user)
                    if type == "category":
                        return await self.item_compiler(ctx, message, name, xuid, cname)
                    if type == "item":
                        return await self.buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "option":
                        return await self.option_path_finder(ctx, message, name, xuid, cname)
                    if type == "rconcategory":
                        return await self.rcon_item_compiler(ctx, message, name, xuid, cname)
                    if type == "rconitem":
                        return await self.rcon_buy_or_goto_options(ctx, message, name, xuid, cname)
                    if type == "rconoption":
                        return await self.rcon_option_path_finder(ctx, message, name, xuid, cname, itemname)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return await message.edit(embed=discord.Embed(description="Menu closed."))

                elif str(reaction.emoji) == "↩️":
                    name = embeds[cur_page - 1].fields[0].name
                    oname = name.split(' ', 1)[-1]
                    await message.remove_reaction(reaction, user)
                    if type == "item":
                        return await self.category_compiler(ctx, xuid, cname, message)
                    if type == "rconitem":
                        return await self.rcon_category_compiler(ctx, xuid, cname, message)
                    if type == "option":
                        return await self.item_compiler(ctx, message, None, xuid, cname, oname)
                    if type == "rconoption":
                        return await self.rcon_item_compiler(ctx, message, None, xuid, cname, oname)

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                try:
                    return await message.clear_reactions()
                except discord.NotFound:
                    return

    @commands.command(name="import", hidden=True)
    @commands.is_owner()
    async def import_settings(self, ctx):
        xuid = self.bot.get_cog("XUID")
        xshop = await xuid.data.guild(ctx.guild).shops()
        async with self.config.datashops() as shops:
            for category in xshop:
                shops[category] = {}
                for item in xshop[category]["items"]:
                    if xshop[category]["items"][item]["options"]:
                        shops[category][item] = {"price": False, "options": {}}
                        for option in xshop[category]["items"][item]["options"]:
                            o = xshop[category]["items"][item]["options"][option].items()
                            iterate = iter(o)
                            price_pair = next(iterate)
                            price = price_pair[1]
                            shops[category][item]["options"][option] = price
                    else:
                        price = xshop[category]["items"][item]["price"]
                        shops[category][item] = {"price": price, "options": {}}
            await ctx.send("Finished importing the config from Papi's absolute fucking dumpster fire of a cog")

    @commands.command(name="dshoplist")
    async def data_status(self, ctx):
        """List all items in the data shop"""
        shops = await self.config.datashops()
        embeds = []
        for category in shops:
            category_items = ""
            for item in shops[category]:
                if shops[category][item]["options"] == {}:
                    price = shops[category][item]["price"]
                    category_items += f"🔸 {item}: `{price}`\n"
                else:
                    category_items += f"🔸 {item}\n```py\n"
                    for k, v in shops[category][item]["options"].items():
                        price = v
                        option = k
                        category_items += f"• {option}: {price}\n"
                    category_items += "```"
            embed = discord.Embed(
                title=f"🔰 {category}",
                description=f"{category_items}"
            )
            embeds.append(embed)
        await self.paginate(ctx, embeds)

    @commands.command(name="rshoplist")
    async def rcon_status(self, ctx):
        """List all items in the rcon shop"""
        shops = await self.config.guild(ctx.guild).shops()
        embeds = []
        for category in shops:
            category_items = ""
            for item in shops[category]:
                if shops[category][item]["options"] == {}:
                    price = shops[category][item]["price"]
                    category_items += f"🔸 {item}: `{price}`\n"
                else:
                    category_items += f"🔸 {item}\n```py\n"
                    for k, v in shops[category][item]["options"].items():
                        price = v["price"]
                        option = k
                        category_items += f"• {option}: {price}\n"
                    category_items += "```"
            embed = discord.Embed(
                title=f"🔰 {category}",
                description=f"{category_items}"
            )
            embeds.append(embed)
        await self.paginate(ctx, embeds)

    # Menu for doing menu things
    async def paginate(self, ctx, embeds):
        pages = len(embeds)
        cur_page = 1
        embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")

        message = await ctx.send(embed=embeds[cur_page - 1])

        await message.add_reaction("◀️")
        await message.add_reaction("❌")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "❌", "▶️"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=60, check=check)

                if str(reaction.emoji) == "▶️" and cur_page + 1 <= pages:
                    cur_page += 1
                    embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "◀️" and cur_page > 1:
                    cur_page -= 1
                    embeds[cur_page - 1].set_footer(text=f"Page {cur_page}/{pages}")
                    await message.edit(embed=embeds[cur_page - 1])
                    await message.remove_reaction(reaction, user)

                elif str(reaction.emoji) == "❌":
                    await message.clear_reactions()
                    return await message.edit(embed=discord.Embed(description="Menu closed."))

                else:
                    await message.remove_reaction(reaction, user)

            except asyncio.TimeoutError:
                try:
                    return await message.clear_reactions()
                except discord.NotFound:
                    return
