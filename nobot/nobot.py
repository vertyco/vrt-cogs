import asyncio
import logging
from typing import Union

import discord
from redbot.core import Config, commands

log = logging.getLogger("red.vrt.nobot")


class NoBot(commands.Cog):
    """
    Filter messages from other bots

    Some "Free" bots spam ads and links when using their commands, this cog fixes that.
    Add a bot to the watchlist and add phrases to look for and if that phrase is found in the other bot's
    message, this cog will delete them.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.2.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 711711, force_registration=True)
        default_guild = {"bots": [], "content": []}
        self.config.register_guild(**default_guild)

        self.cache = {}

    def initialize(self):
        asyncio.create_task(self.cache_guilds())

    async def cache_guilds(self):
        await self.bot.wait_until_red_ready()
        self.cache = await self.config.all_guilds()

    @commands.group(name="nobot")
    @commands.has_permissions(manage_messages=True)
    async def nobot_settings(self, ctx):
        """Main setup command for NoBot"""
        pass

    @nobot_settings.command(name="addbot")
    async def add_bot(self, ctx, bot: discord.Member):
        """Add a bot to the filter list"""
        async with self.config.guild(ctx.guild).bots() as bots:
            if str(bot.id) not in bots:
                bots.append(str(bot.id))
                await ctx.tick()
            else:
                await ctx.send("Bot already in list")
        self.initialize()

    @nobot_settings.command(name="delbot")
    async def delete_bot(self, ctx, bot: Union[discord.Member, int]):
        """
        Remove a bot from the filter list

        If bot is no longer in the server, use its ID
        """
        async with self.config.guild(ctx.guild).bots() as bots:
            bid = bot if isinstance(bot, int) else bot.id
            if str(bid) in bots:
                bots.remove(str(bid))
                await ctx.tick()
            else:
                await ctx.send("Bot not found")
        self.initialize()

    @nobot_settings.command(name="addfilter")
    async def add_filter(self, ctx, *, message):
        """Add text context to match against the bot filter list, use phrases that match what the bot sends exactly"""
        async with self.config.guild(ctx.guild).content() as content:
            if message not in content:
                content.append(message)
                await ctx.tick()
            else:
                await ctx.send("Filter already exists")
        self.initialize()

    @nobot_settings.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def no_bot_view(self, ctx):
        """View NoBot settings"""
        config = await self.config.guild(ctx.guild).all()
        botlist = ""
        for bot in config["bots"]:
            botmember = ctx.guild.get_member(int(bot))
            botlist += f"{botmember.mention if botmember else 'Unknown'}: {bot}\n"
        filters = ""
        for filt in config["content"]:
            filters += f"{filt}\n"
        embed = discord.Embed(description="**NoBot Setting Overview**", color=discord.Color.random())
        if botlist:
            embed.add_field(name="Bots", value=botlist, inline=False)
        if filters:
            embed.add_field(name="Filters", value=filters, inline=False)
        await ctx.send(embed=embed)

    @nobot_settings.command(name="delfilter")
    @commands.bot_has_permissions(embed_links=True)
    async def delete_filter(self, ctx):
        """Delete a filter"""
        async with self.config.guild(ctx.guild).content() as content:
            count = 1
            strlist = ""
            for phrase_filter in content:
                strlist += f"{count}. {phrase_filter}\n"
                count += 1
            if not strlist:
                return await ctx.send("There are no filters set")
            msg = await ctx.send(f"Type the number of the filter you want to delete\n" f"{strlist}")

            def check(message: discord.Message):
                return message.author == ctx.author and message.channel == ctx.channel

            try:
                reply = await self.bot.wait_for("message", timeout=60, check=check)
            except asyncio.TimeoutError:
                return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))

            if reply.content.lower() == "cancel":
                return await msg.edit(embed=discord.Embed(description="Selection canceled."))
            elif not reply.content.isdigit():
                return await msg.edit(embed=discord.Embed(description="That's not a number"))
            elif int(reply.content) > len(content):
                return await msg.edit(embed=discord.Embed(description="That's not a valid number"))
            else:
                i = int(reply.content) - 1
                content.pop(i)
                await ctx.tick()
        self.initialize()

    # Only detects messages from bots set
    @commands.Cog.listener("on_message")
    async def no_bot_chat(self, message: discord.Message):
        # Make sure message IS from a bot
        if not message.author.bot:
            return
        # Check if message author is itself
        if message.author.id == self.bot.user.id:
            return
        # Make sure message is from a guild
        if not message.guild:
            return
        # Make sure its a message?
        if not message:
            return
        # Make sure config exists in cache
        if not self.cache:
            asyncio.create_task(self.cache_guilds())
            return
        # Pull config
        if message.guild.id not in self.cache:
            return
        config = self.cache[message.guild.id]
        # Check if message author is in the config
        if str(message.author.id) not in config["bots"]:
            return
        # Get perms
        allowed = message.channel.permissions_for(message.guild.me).manage_messages
        if not allowed:
            log.warning(f"Insufficient permissions to delete message: {message.content}")
            return
        asyncio.create_task(self.handle_message(config, message))

    @staticmethod
    async def handle_message(config: dict, message: discord.Message):
        # Check if filter is contained in message content
        for msg in config["content"]:
            if msg.lower() in message.content.lower():
                await message.delete()
        # Check if message contains an embed
        if message.embeds:
            for embed in message.embeds:
                if embed.description:  # Make sure embed actually has a description
                    for msg in config["content"]:
                        if msg.lower() in embed.description.lower():
                            await message.delete()
                # Iterate through embed fields
                if embed.fields:
                    for field in embed.fields:
                        for msg in config["content"]:
                            if msg.lower() in field.value.lower():
                                await message.delete()
