import discord
import asyncio

from redbot.core import commands, Config


class NoBot(commands.Cog):
    """
    Filter messages from other bots

    Some "Free" bots spam ads and links when using their commands, this cog fixes that.
    Vertyco#0117 is in no way liable for how this cog is used
    or any ToS it may violate for the bot it blocks messages from.
    """
    __author__ = "Vertyco"
    __version__ = "1.0.2"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, 711711, force_registration=True)
        default_guild = {
            "bots": [],
            "content": []
        }
        self.config.register_guild(**default_guild)

    @commands.group(name="nobot")
    @commands.admin()
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

    @nobot_settings.command(name="delbot")
    async def delete_bot(self, ctx, bot: discord.Member):
        """Remove a bot from the filter list"""
        async with self.config.guild(ctx.guild).bots() as bots:
            if str(bot.id) in bots:
                bots.remove(str(bot.id))
                await ctx.tick()
            else:
                await ctx.send("Bot not found")

    @nobot_settings.command(name="addfilter")
    async def add_filter(self, ctx, *, message):
        """Add text context to match against the bot filter list, use phrases that match what the bot sends exactly"""
        async with self.config.guild(ctx.guild).content() as content:
            if message not in content:
                content.append(message)
                await ctx.tick()
            else:
                await ctx.send("Filter already exists")

    @nobot_settings.command(name="view")
    async def no_bot_view(self, ctx):
        """View NoBot settings"""
        config = await self.config.guild(ctx.guild).all()
        botlist = ""
        for bot in config["bots"]:
            botmember = ctx.guild.get_member(int(bot))
            botlist += f"{botmember.mention}: {bot}\n"
        filters = ""
        for filter in config["content"]:
            filters += f"{filter}\n"
        embed = discord.Embed(
            description=f"**NoBot Setting Overview**",
            color=discord.Color.random()
        )
        if botlist != "":
            embed.add_field(name="Bots", value=botlist, inline=False)
        if filters != "":
            embed.add_field(name="Filters", value=filters, inline=False)
        await ctx.send(embed=embed)

    @nobot_settings.command(name="delfilter")
    async def delete_filter(self, ctx):
        """Delete a filter"""
        async with self.config.guild(ctx.guild).content() as content:
            count = 1
            strlist = ""
            for filter in content:
                strlist += f"{count}. {filter}\n"
                count += 1
            if strlist == "":
                return await ctx.send("There are no filters set")
            msg = await ctx.send(f"Type the number of the filter you want to delete\n"
                                 f"{strlist}")

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

    # Only detects messages from bots set
    @commands.Cog.listener("on_message")
    async def no_bot_chat(self, message: discord.Message):
        # Make sure message IS from a bot
        if not message.author.bot:
            return

        # Check if message author is itself
        if str(message.author) == str(self.bot.user):
            return

        # Make sure message is from a guild
        if not message.guild:
            return

        # Make sure its a message?
        if not message:
            return

        # Pull config
        config = await self.config.guild(message.guild).all()

        # Check if message author is in the config
        if str(message.author.id) not in config["bots"]:
            return

        # Check if filter is contained in message content
        for msg in config["content"]:
            if msg.lower() in message.content.lower():
                try:
                    await message.delete()
                except discord.Forbidden:
                    pass

        # Check if message contains an embed
        if message.embeds:
            for embed in message.embeds:
                for msg in config["content"]:
                    if embed.description:  # Make sure embed actually has a description
                        if msg.lower() in embed.description.lower():
                            try:
                                await message.delete()
                            except discord.Forbidden:
                                pass
                # Iterate through embed fields
                for field in embed.fields:
                    for msg in config["content"]:
                        if msg.lower() in field.value.lower():
                            try:
                                await message.delete()
                            except discord.Forbidden:
                                pass


