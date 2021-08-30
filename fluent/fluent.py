from redbot.core import commands, Config, checks
import discord
import googletrans

translator = googletrans.Translator()


class Fluent(commands.Cog):
    """
    Seamless translation between two languages in one channel.

    Inspired by Obi-Wan3's translation cog.
    """

    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=11701170)
        default_guild = {
            "channels": {}
        }
        self.config.register_guild(**default_guild)

    # Gets lang identifier from string
    async def _converter(self, language):
        for key, value in googletrans.LANGUAGES.items():
            if language == "chinese":
                language = "chinese (simplified)"
            if language == value:
                return key

    async def _detector(self, msg):
        source = translator.detect(str(msg))
        return source.lang

    async def _translator(self, msg, dest):
        translated_msg = translator.translate(msg, dest=str(dest))
        return translated_msg

    @commands.group(name="fluent")
    @commands.guildowner()
    async def _fluent(self, ctx):
        """Base command"""
        pass

    @_fluent.command(name="add")
    async def _add(self, ctx, channel: discord.TextChannel, language1, language2):
        """Add a channel and languages to translate between"""
        language1 = await self._converter(language1)
        language2 = await self._converter(language2)
        async with self.config.guild(ctx.guild).channels() as channels:
            if channel.id in channels.keys():
                return await ctx.send(embed=discord.Embed(description=f"❌ {channel.mention} is already a fluent channel."))
            else:
                channels[channel.id] = {
                    "lang1": language1,
                    "lang2": language2
                }
                color = discord.Color.green()
                return await ctx.send(embed=discord.Embed(description=f"✅ Fluent channel has been set!", color=color))

    @_fluent.command(name="remove")
    async def _remove(self, ctx, channel: discord.TextChannel):
        """Remove a channel from Fluent"""
        async with self.config.guild(ctx.guild).channels() as channels:
            for channel_id in channels:
                if int(channel.id) == int(channel_id):
                    del channels[channel_id]
                    color = discord.Color.green()
                    return await ctx.send(
                        embed=discord.Embed(description=f"✅ Fluent channel has deleted!", color=color))
                else:
                    return await ctx.send(embed=discord.Embed(description=f"❌ {channel.mention} isn't a fluent channel."))

    @_fluent.command(name="view")
    async def _view(self, ctx):
        """View all fluent channels"""
        channels = await self.config.guild(ctx.guild).channels()
        embed = discord.Embed(
            title="Fluent Settings",
            description="Below is a list of fluent channels and their translated languages."
        )
        for channel in channels:
            if channel:
                discordchannel = ctx.guild.get_channel(int(channel))
                lang1 = channels[channel]["lang1"]
                lang2 = channels[channel]["lang2"]
                embed.add_field(
                    name=discordchannel.name,
                    value=f"Channel ID: {discordchannel.id}\nFluent in: {lang1} <-> {lang2}"
                )
        return await ctx.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def _message_handler(self, message: discord.Message):
        if message.author.bot:
            return
        channels = await self.config.guild(message.guild).channels()
        for channel_id in channels:
            if int(message.channel.id) == int(channel_id):
                mentions = discord.AllowedMentions.all()
                print("channel match!")
                author = message.author
                lang1 = channels[channel_id]["lang1"]
                lang2 = channels[channel_id]["lang2"]
                channel = message.channel
                trans = await self._translator(message.content, lang1)
                print(f"SOURCE: {trans}")
                if trans is None:
                    return await channel.send(embed=discord.Embed(description=f"❌ API seems to be down at the moment."))
                elif trans.src == lang2:
                    print(f"Detected: Lang2")
                    await message.delete()
                    return await channel.send(f"`{author.name}: {message.content}`\n"
                                              f"**{trans.text}**", allowed_mentions=mentions)
                elif trans.src == lang1:
                    print(f"Detected: Lang2")
                    trans = await self._translator(message.content, lang2)
                    await message.delete()
                    return await channel.send(f"`{author.name}:` {message.content}\n"
                                              f"**{trans.text}**", allowed_mentions=mentions)
                else:
                    return



