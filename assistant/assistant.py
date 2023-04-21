import asyncio
import logging
from datetime import datetime
from io import BytesIO

import aiohttp
import discord
import openai
from aiocache import cached
from redbot.core import Config, commands

from .models import DB, Conversations, GuildSettings
from .views import SetAPI

log = logging.getLogger("red.vrt.assistant")


def get_attachments(ctx: commands.Context) -> list:
    """Get all attachments from context"""
    content = []
    if ctx.message.attachments:
        atchmts = [a for a in ctx.message.attachments]
        content.extend(atchmts)
    if hasattr(ctx.message, "reference"):
        try:
            atchmts = [a for a in ctx.message.reference.resolved.attachments]
            content.extend(atchmts)
        except AttributeError:
            pass
    return content


class Assistant(commands.Cog):
    """
    Set up a helpful assistant for your Discord server, powered by ChatGPT

    This cog uses GPT-3.5-Turbo **Only** right now.
    """

    __author__ = "Vertyco#0117"
    __version__ = "0.2.5"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, 117117117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.chats: Conversations = Conversations()

    async def cog_load(self) -> None:
        asyncio.create_task(self.init_cog())

    async def cog_unload(self) -> None:
        pass

    async def init_cog(self):
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.parse_obj, data)

    async def save_conf(self):
        data = await asyncio.to_thread(self.db.dict)
        await self.config.db.set(data)

    @commands.Cog.listener("on_message_without_command")
    async def handler(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message was from a bot
        if message.author.bot:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # Ignore messages without content
        if not message.content:
            return
        # Ignore if channel doesn't exist
        if not message.channel:
            return
        conf = self.db.get_conf(message.guild)
        if not conf.enabled:
            return
        if not conf.api_key:
            return
        channel = message.channel
        if channel.id != conf.channel_id:
            return
        content = message.content
        if not content.endswith("?") and conf.endswith_questionmark:
            return
        if len(content.strip()) < conf.min_length:
            return
        reply = await self.get_answer(
            content.lower().strip(), message.author, conf
        )
        await message.reply(reply)

    @cached(ttl=172800)
    async def get_answer(
        self, message: str, author: discord.Member, conf: GuildSettings
    ):
        reply = await asyncio.to_thread(
            self.call_openai, message, author, conf
        )
        return reply

    def call_openai(
        self, message: str, author: discord.Member, conf: GuildSettings
    ):
        date = datetime.now().astimezone().strftime("%B %d, %Y")
        timestamp = f"<t:{round(datetime.now().timestamp())}:F>"
        system = (
            f"You are {self.bot.user.name},"
            f"Current date and time: {timestamp},"
            f"Todays date: {date},"
            f"Member count: {author.guild.member_count},"
            f"Server owner: {author.guild.owner.display_name},"
            f"User's name: {author.display_name}"
        )

        conversation = self.chats.get_conversation(author)
        conversation.update_messages(conf, message, "user")
        messages = conversation.prepare_chat(system, conf.prompt)

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0,
            api_key=conf.api_key,
        )
        try:
            reply = response["choices"][0]["message"]["content"]
            conversation.update_messages(conf, reply, "system")
        except KeyError:
            reply = str(response)
        return reply

    @commands.group(name="assistant", aliases=["ass"])
    @commands.guildowner()
    async def assistant(self, ctx: commands.Context):
        """Setup the assistant"""
        pass

    @assistant.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View current settings"""
        conf = self.db.get_conf(ctx.guild)
        channel = f"<#{conf.channel_id}>" if conf.channel_id else "Not Set"
        desc = (
            f"`API Key:       `{conf.api_key if conf.api_key else 'Not Set'}\n"
            f"`Channel:       `{channel}\n"
            f"`? Required:    `{conf.endswith_questionmark}\n"
            f"`Max Retention: `{conf.max_retention}\n"
            f"`Min Length:    `{conf.min_length}"
        )
        file = (
            discord.File(
                BytesIO(conf.prompt.encode()), filename="CurrentPrompt.txt"
            )
            if conf.prompt
            else None
        )
        embed = discord.Embed(
            title="Assistant Settings",
            description=desc,
            color=ctx.author.color,
        )
        try:
            await ctx.author.send(embed=embed, file=file)
            await ctx.send(
                "Sent your current settings for this server in DMs!"
            )
        except discord.Forbidden:
            await ctx.send("You need to allow DMs so I can message you!")

    @assistant.command(name="openaikey", aliases=["key"])
    async def set_openai_key(self, ctx: commands.Context):
        """Set your OpenAI key"""
        view = SetAPI(ctx.author)
        embed = discord.Embed(
            description="Click to set your OpenAI key", color=ctx.author.color
        )
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip()
        if not key:
            return await msg.edit(
                content="No key was entered!", embed=None, view=None
            )
        conf = self.db.get_conf(ctx.guild)
        conf.api_key = key
        await msg.edit(
            content="OpenAI key has been set!", embed=None, view=None
        )
        await self.save_conf()

    @assistant.command(name="prompt", aliases=["pre"])
    async def set_pre_prompt(
        self, ctx: commands.Context, *, prompt: str = None
    ):
        """Set the initial prompt for GPT to use"""
        content = get_attachments(ctx)
        if content:
            url = content[0].url
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        prompt = (await resp.read()).decode()
            except Exception as e:
                return await ctx.send(f"Error:```py\n{e}\n```")
        if not prompt:
            return await ctx.send(
                "Please provide a prompt or text file containing a prompt"
            )
        conf = self.db.get_conf(ctx.guild)
        conf.prompt = prompt.strip()
        await ctx.send("Initial prompt has been set!")
        await self.save_conf()

    @assistant.command(name="channel")
    async def set_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel for the assistant"""
        conf = self.db.get_conf(ctx.guild)
        conf.channel_id = channel.id
        await ctx.send("Channel id has been set")
        await self.save_conf()

    @assistant.command(name="questionmark")
    async def toggle_question(self, ctx: commands.Context):
        """Toggle whether questions need to end with a question mark to be answered"""
        conf = self.db.get_conf(ctx.guild)
        if conf.endswith_questionmark:
            conf.endswith_questionmark = False
            await ctx.send(
                "Questions will be answered regardless of if they end with **?**"
            )
        else:
            conf.endswith_questionmark = True
            await ctx.send("Questions must end in **?** to be answered")
        await self.save_conf()

    @assistant.command(name="toggle")
    async def toggle_gpt(self, ctx: commands.Context):
        """Toggle the assistant on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.enabled:
            conf.enabled = False
            await ctx.send("The assistant is now **Disabled**")
        else:
            conf.enabled = True
            await ctx.send("The assistant is now **Enabled**")
        await self.save_conf()

    @assistant.command(name="maxretention")
    async def max_retention(self, ctx: commands.Context, max_retention: int):
        """
        Set the max messages for a conversation

        Regardless of this number, the initial prompt and internal system message are always included,
        this only applies to any conversation between the user and bot after that.

        Set to 0 to disable conversation retention
        """
        if max_retention < 0:
            return await ctx.send(
                "Max retention needs to be at least 0 or higher"
            )
        conf = self.db.get_conf(ctx.guild)
        conf.max_retention = max_retention
        if max_retention == 0:
            await ctx.send("Conversation retention has been disabled")
        else:
            await ctx.tick()
        await self.save_conf()

    @assistant.command(name="minlength")
    async def min_length(
        self, ctx: commands.Context, min_question_length: int
    ):
        """
        set the minimum character length for questions to be answered

        Set to 0 to respond to anything
        """
        if min_question_length < 0:
            return await ctx.send(
                "Minimum length needs to be at least 0 or higher"
            )
        conf = self.db.get_conf(ctx.guild)
        conf.min_length = min_question_length
        if min_question_length == 0:
            await ctx.send(
                f"{ctx.bot.user.name} will respond regardless of message length"
            )
        else:
            await ctx.tick()
        await self.save_conf()
