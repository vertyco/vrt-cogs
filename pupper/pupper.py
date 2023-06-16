import asyncio
import logging
import random
from datetime import datetime

import discord
from redbot.core import Config, bank, checks, commands
from redbot.core.errors import BalanceTooHigh
from redbot.core.utils.chat_formatting import box, humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions

log = logging.getLogger("red.vrt.pupper")


class Pupper(commands.Cog):
    """Pet the doggo!"""

    __author__ = "Vertyco#0117"
    __version__ = "1.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = (
            f"{helpcmd}\n"
            f"Cog Version: {self.__version__}\n"
            f"Original Author: aikaterna#1393\n"
            f"Maintainer: {self.__author__}"
        )
        return info

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 2767241393, force_registration=True)
        self.pets = {}

        default_guild = {
            "borf_msg": "borf! (thank for pats h00man, have a doggocoin)",
            "channel": [],
            "cooldown": 3600,
            "credits": [100, 500],
            "hello_msg": "Hi! Can someone pet me?",
            "last_pet": 0,
            "toggle": False,
            "delete_after": 10,
        }

        self.config.register_guild(**default_guild)

        self.cache = {}

    async def initialize(self, target: discord.Guild = None):
        if target:
            data = await self.config.guild(target).all()

            # Some cleanup for new schema, using timestamps not isoformat
            if isinstance(data["last_pet"], str):
                await self.config.guild(target).last_pet.set(0)
                data["last_pat"] = 0

            self.cache[target.id] = data
            self.pets[target.id] = False
            return

        configs = await self.config.all_guilds()
        for gid, data in configs.items():
            guild = self.bot.get_guild(gid)
            if not guild:
                continue

            # Some cleanup for new schema, using timestamps not isoformat
            if isinstance(data["last_pet"], str):
                await self.config.guild(guild).last_pet.set(0)
                data["last_pat"] = 0

            self.cache[gid] = data
            self.pets[gid] = False

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @commands.group(name="pets", aliases=["pupper"])
    async def petscmd(self, ctx):
        """Manage your pet."""
        if ctx.invoked_subcommand is None:
            if ctx.guild.id not in self.cache:
                await self.initialize(ctx.guild)
            guild_data = self.cache[ctx.guild.id]
            if not guild_data["channel"]:
                channel_names = ["No channels set."]
            else:
                channel_names = []
                for channel_id in guild_data["channel"]:
                    channel_obj = self.bot.get_channel(channel_id)
                    if channel_obj:
                        channel_names.append(channel_obj.name)

            last_pet = guild_data["last_pet"]
            if isinstance(last_pet, str):
                await self.config.guild(ctx.guild).last_pet.set(0)
                await self.initialize(ctx.guild)

            space = "\N{EN SPACE}"
            toggle = "Active" if guild_data["toggle"] else "Inactive"
            delete_after = (
                "No deletion" if not guild_data["delete_after"] else guild_data["delete_after"]
            )

            msg = f"[Channels]:       {humanize_list(channel_names)}\n"
            msg += f"[Cooldown]:       {guild_data['cooldown']} seconds\n"
            msg += f"[Credit range]:   {guild_data['credits'][0]} - {guild_data['credits'][1]} credits\n"
            msg += f"[Delete after]:   {delete_after}\n"
            msg += f"[Toggle]:         {toggle}\n"
            msg += f"{space}\n"
            msg += f"[Hello message]:  {guild_data['hello_msg']}\n"
            msg += f"[Thanks message]: {guild_data['borf_msg']}\n"

            for page in pagify(msg, delims=["\n"]):
                await ctx.send(box(page, lang="ini"))
            await ctx.send(f"Last pet: <t:{int(last_pet)}:R>")

    @petscmd.command()
    async def toggle(self, ctx):
        """Toggle pets on the server."""
        toggle = await self.config.guild(ctx.guild).toggle()
        await self.config.guild(ctx.guild).toggle.set(not toggle)
        await ctx.send(f"The pet is now {'' if not toggle else 'in'}active.")
        await self.initialize(ctx.guild)

    @petscmd.command()
    async def delete(self, ctx, amount: int = 0):
        """
        Set how long to wait before deleting the thanks message.
        To leave the thanks message with no deletion, use 0 as the amount.
        10 is the default.
        Max is 5 minutes (300).
        """

        if amount < 0:
            return await ctx.send("Use a positive number.")
        if 1 <= amount <= 5:
            return await ctx.send("Use a slightly larger number, greater than 5.")
        if amount > 300:
            return await ctx.send("Use a smaller number, less than or equal to 300.")

        set_amount = None if amount == 0 else amount
        await self.config.guild(ctx.guild).delete_after.set(set_amount)
        msg = f"Timer set to {amount}." if set_amount else "Delete timer has been turned off."
        await ctx.send(msg)
        await self.initialize(ctx.guild)

    @petscmd.command()
    async def cooldown(self, ctx, seconds: int = None):
        """Set the pet appearance cooldown in seconds.

        300s/5 minute minimum. Default is 3600s/1 hour."""

        if not seconds:
            seconds = 3600
        if seconds < 60:
            seconds = 60
        await self.config.guild(ctx.guild).cooldown.set(seconds)
        await ctx.send(f"Pet appearance cooldown set to {seconds}.")
        await self.initialize(ctx.guild)

    @petscmd.command()
    async def credits(self, ctx, min_amt: int, max_amt: int):
        """Set the pet credits range on successful petting."""
        if min_amt > max_amt:
            return await ctx.send("Min must be less than max.")
        if min_amt < 1 or max_amt < 1:
            return await ctx.send("Min and max amounts must be greater than 1.")
        await self.config.guild(ctx.guild).credits.set([min_amt, max_amt])
        await ctx.send(f"Pet credit range set to {min_amt} - {max_amt}.")
        await self.initialize(ctx.guild)

    @petscmd.command()
    async def hello(self, ctx, *, message: str = None):
        """Set the pet greeting message."""
        if not message:
            hello = await self.config.guild(ctx.guild).hello_msg()
            return await ctx.send(
                f"Current greeting message: `{hello}`\nUse this command with the message you would like to set."
            )
        if len(message) > 1000:
            return await ctx.send("That dog sure likes to talk a lot. Try a shorter message.")
        await self.config.guild(ctx.guild).hello_msg.set(message)
        await ctx.send(f"Pet hello message set to: `{message}`.")
        await self.initialize(ctx.guild)

    @petscmd.command()
    async def thanks(self, ctx, *, message: str = None):
        """Set the pet thanks message."""
        if not message:
            bye = await self.config.guild(ctx.guild).borf_msg()
            return await ctx.send(
                f"Current thanks message: `{bye}`\nUse this command with the message you would like to set."
            )
        if len(message) > 1000:
            return await ctx.send("That dog sure likes to talk a lot. Try a shorter message.")
        await self.config.guild(ctx.guild).borf_msg.set(message)
        await ctx.send(f"Pet thanks message set to: `{message}`.")
        await self.initialize(ctx.guild)

    @commands.guild_only()
    @checks.mod_or_permissions(administrator=True)
    @petscmd.group(invoke_without_command=True)
    async def channel(self, ctx):
        """Channel management for pet appearance."""
        await ctx.send_help()
        channel_list = await self.config.guild(ctx.guild).channel()
        channel_msg = "[Petting Channels]:\n"
        if not channel_list:
            channel_msg += "None."
        for chan in channel_list:
            channel_obj = self.bot.get_channel(chan)
            channel_msg += f"{channel_obj.name}\n"
        await ctx.send(box(channel_msg, lang="ini"))

    @channel.command()
    async def add(self, ctx, channel: discord.TextChannel):
        """Add a text channel for pets."""
        channel_list = await self.config.guild(ctx.guild).channel()
        if channel.id not in channel_list:
            channel_list.append(channel.id)
            await self.config.guild(ctx.guild).channel.set(channel_list)
            await ctx.send(f"{channel.mention} added to the valid petting channels.")
            await self.initialize(ctx.guild)
        else:
            await ctx.send(f"{channel.mention} is already in the list of petting channels.")

    @channel.command()
    async def addall(self, ctx):
        """Add all valid channels for the guild that the bot can speak in."""
        bot_text_channels = [
            c
            for c in ctx.guild.text_channels
            if c.permissions_for(ctx.guild.me).send_messages is True
        ]
        channel_list = await self.config.guild(ctx.guild).channel()
        channels_appended = []
        channels_in_list = []

        for text_channel in bot_text_channels:
            if text_channel.id not in channel_list:
                channel_list.append(text_channel.id)
                channels_appended.append(text_channel.mention)
            else:
                channels_in_list.append(text_channel.mention)
                pass

        first_msg = ""
        second_msg = ""
        await self.config.guild(ctx.guild).channel.set(channel_list)
        if len(channels_appended) > 0:
            first_msg = (
                f"{humanize_list(channels_appended)} added to the valid petting channels.\n"
            )
        if len(channels_in_list) > 0:
            second_msg = (
                f"{humanize_list(channels_in_list)}: already in the list of petting channels."
            )
        txt = f"{first_msg}\n{second_msg}"
        for p in pagify(txt, page_length=2000):
            await ctx.send(p)
        await self.initialize(ctx.guild)

    @channel.command()
    async def remove(self, ctx, channel: discord.TextChannel):
        """Remove a text channel from petting."""
        channel_list = await self.config.guild(ctx.guild).channel()
        if channel.id in channel_list:
            channel_list.remove(channel.id)
        else:
            return await ctx.send(f"{channel.mention} not in the active channel list.")
        await self.config.guild(ctx.guild).channel.set(channel_list)
        await ctx.send(f"{channel.mention} removed from the list of petting channels.")
        await self.initialize(ctx.guild)

    @channel.command()
    async def removeall(self, ctx):
        """Remove all petting channels from the list."""
        await self.config.guild(ctx.guild).channel.set([])
        await ctx.send("All channels have been removed from the list of petting channels.")
        await self.initialize(ctx.guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message:
            return
        if not message.guild:
            return
        if message.author.bot:
            return
        if isinstance(message.channel, discord.abc.PrivateChannel):
            return
        if not self.cache:
            await self.initialize()
        if message.guild.id not in self.cache:
            await self.initialize(message.guild)
        if self.pets[message.guild.id]:
            return
        self.pets[message.guild.id] = True
        try:
            await self.do_pet_stuff(message)
        except Exception as e:
            log.error(f"Error in pupper loop: {e}")
        finally:
            self.pets[message.guild.id] = False

    async def do_pet_stuff(self, message: discord.Message):
        guild_data = self.cache[message.guild.id].copy()
        if not guild_data["toggle"]:
            return
        if not guild_data["channel"]:
            return

        last_time = datetime.fromtimestamp(guild_data["last_pet"])
        now = datetime.now()
        if int((now - last_time).total_seconds()) > guild_data["cooldown"]:
            await asyncio.sleep(random.randint(30, 480))
            while True:
                if not guild_data["channel"]:
                    return
                rando_channel = random.choice(guild_data["channel"])
                rando_channel_obj = self.bot.get_channel(rando_channel)
                if not rando_channel_obj:
                    guild_data["channel"].remove(rando_channel)
                    self.cache[message.guild.id]["channel"].remove(rando_channel)
                else:
                    break
            if not rando_channel_obj:
                return
            if not rando_channel_obj.permissions_for(message.guild.me).send_messages:
                return

            borf_msg = await rando_channel_obj.send(guild_data["hello_msg"])

            emojis = ["👋", "\N{WAVING HAND SIGN}"]

            start_adding_reactions(borf_msg, emojis)

            def check(r, u):
                if u.bot:
                    return False
                return r.message.id == borf_msg.id and any(
                    emoji in str(r.emoji) for emoji in emojis
                )

            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", check=check, timeout=300.0
                )
            except asyncio.TimeoutError:
                return await borf_msg.delete()

            if str(reaction.emoji) in emojis:
                await borf_msg.delete()
                deposit = random.randint(guild_data["credits"][0], guild_data["credits"][1])
                try:
                    large_bank = False
                    await bank.deposit_credits(user, deposit)
                except BalanceTooHigh as e:
                    large_bank = True
                    await bank.set_balance(user, e.max_balance)
                credits_name = await bank.get_currency_name(message.guild)
                msg = (
                    f"{guild_data['borf_msg']} (`+{deposit}` {credits_name})"
                    if not large_bank
                    else guild_data["borf_msg"]
                )
                await rando_channel_obj.send(content=msg, delete_after=guild_data["delete_after"])
            else:
                pass
            self.cache[message.guild.id]["last_pet"] = int(now.timestamp())
            await self.config.guild(message.guild).last_pet.set(int(now.timestamp()))
