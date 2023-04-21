import asyncio
import logging
from datetime import datetime
from io import BytesIO

import aiohttp
import discord
import openai
from aiocache import cached
from openai.error import InvalidRequestError
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
    __version__ = "0.2.10"

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
        async with channel.typing():
            try:
                reply = await self.get_answer(
                    content.lower().strip(), message.author, conf
                )
                await message.reply(reply, mention_author=conf.mention)
            except InvalidRequestError as e:
                await message.reply(str(e.error), mention_author=conf.mention)

    @cached(ttl=120)
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
        timestamp = f"<t:{round(datetime.now().timestamp())}:F>"
        date = datetime.now().astimezone().strftime("%B %d, %Y")
        time = datetime.now().astimezone().strftime("%I:%M %p %Z")
        params = {
            "botname": self.bot.user.name,
            "timestamp": timestamp,
            "date": date,
            "time": time,
            "members": author.guild.member_count,
            "user": author.display_name,
        }
        system_prompt = conf.system_prompt.format(**params)
        initial_prompt = conf.prompt.format(**params)

        conversation = self.chats.get_conversation(author)
        user_message = f"{author.display_name}: {message}"
        conversation.update_messages(conf, user_message, "user")
        messages = conversation.prepare_chat(system_prompt, initial_prompt)

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0,
            api_key=conf.api_key,
        )
        try:
            reply = response["choices"][0]["message"]["content"]
            conversation.update_messages(conf, reply, "assistant")
        except KeyError:
            reply = str(response)
        return reply

    @commands.group(name="assistant", aliases=["ass"])
    @commands.guildowner()
    async def assistant(self, ctx: commands.Context):
        """
        Setup the assistant

        You will need an api key to use the assistant. https://platform.openai.com/account/api-keys
        """
        pass

    @assistant.command(name="view")
    async def view_settings(self, ctx: commands.Context):
        """View current settings"""
        conf = self.db.get_conf(ctx.guild)
        channel = f"<#{conf.channel_id}>" if conf.channel_id else "Not Set"
        desc = (
            f"`Enabled:       `{conf.enabled}\n"
            f"`API Key:       `{conf.api_key if conf.api_key else 'Not Set'}\n"
            f"`Channel:       `{channel}\n"
            f"`? Required:    `{conf.endswith_questionmark}\n"
            f"`Mentions:      `{conf.mention}\n"
            f"`Max Retention: `{conf.max_retention}\n"
            f"`Min Length:    `{conf.min_length}"
        )
        system_file = (
            discord.File(
                BytesIO(conf.system_prompt.encode()),
                filename="SystemPrompt.txt",
            )
            if conf.system_prompt
            else None
        )
        prompt_file = (
            discord.File(
                BytesIO(conf.prompt.encode()), filename="InitialPrompt.txt"
            )
            if conf.prompt
            else None
        )
        embed = discord.Embed(
            title="Assistant Settings",
            description=desc,
            color=ctx.author.color,
        )
        embed.set_footer(text=f"Showing settings for {ctx.guild.name}")
        files = []
        if system_file:
            files.append(system_file)
        if prompt_file:
            files.append(prompt_file)
        try:
            await ctx.author.send(embed=embed, files=files)
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
    async def set_initial_prompt(
        self, ctx: commands.Context, *, prompt: str = None
    ):
        """
        Set the initial prompt for GPT to use

        **Tips**
        You can use the following placeholders in your prompt for real-time info
        To use a place holder simply format your prompt as "`some {placeholder} with text`"
        `botname` - The bots display name
        `timestamp` - the current time in Discord's timestamp format
        `date` - todays date (Month, Day, Year)
        `time` - current time in 12hr format (HH:MM AM/PM Timezone)
        `members` - current member count of the server
        `user` - the current user asking the question
        """
        content = get_attachments(ctx)
        if content:
            url = content[0].url
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        prompt = (await resp.read()).decode()
            except Exception as e:
                return await ctx.send(f"Error:```py\n{e}\n```")

        conf = self.db.get_conf(ctx.guild)

        if not prompt and conf.prompt:
            conf.prompt = ""
            await ctx.send("The initial prompt has been removed!")
        elif not prompt and not conf.prompt:
            await ctx.send("Please include an initial prompt or .txt file!")
        elif prompt and conf.prompt:
            conf.prompt = prompt.strip()
            await ctx.send("The initial prompt has been overwritten!")
        else:
            conf.prompt = prompt.strip()
            await ctx.send("Initial prompt has been set!")

        await self.save_conf()

    @assistant.command(name="system", aliases=["sys"])
    async def set_system_prompt(
        self, ctx: commands.Context, *, system_prompt: str = None
    ):
        """
        Set the system prompt for GPT to use

        **Note**
        The current GPT-3.5-Turbo model doesn't really listen to the system prompt very well.

        **Tips**
        You can use the following placeholders in your prompt for real-time info
        To use a place holder simply format your prompt as "`some {placeholder} with text`"
        `botname` - The bots display name
        `timestamp` - the current time in Discord's timestamp format
        `date` - todays date (Month, Day, Year)
        `time` - current time in 12hr format (HH:MM AM/PM Timezone)
        `members` - current member count of the server
        `user` - the current user asking the question
        """
        content = get_attachments(ctx)
        if content:
            url = content[0].url
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        system_prompt = (await resp.read()).decode()
            except Exception as e:
                return await ctx.send(f"Error:```py\n{e}\n```")

        conf = self.db.get_conf(ctx.guild)

        if not system_prompt and conf.system_prompt:
            conf.system_prompt = ""
            await ctx.send("The system prompt has been removed!")
        elif not system_prompt and not conf.system_prompt:
            await ctx.send("Please include a system prompt or .txt file!")
        elif system_prompt and conf.system_prompt:
            conf.system_prompt = system_prompt.strip()
            await ctx.send("The system prompt has been overwritten!")
        else:
            conf.system_prompt = system_prompt.strip()
            await ctx.send("System prompt has been set!")

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
        """Toggle whether questions need to end with **__?__**"""
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

    @assistant.command(name="mention")
    async def toggle_mention(self, ctx: commands.Context):
        """Toggle whether to ping the user on replies"""
        conf = self.db.get_conf(ctx.guild)
        if conf.mention:
            conf.mention = False
            await ctx.send("Mentions are now **Disabled**")
        else:
            conf.mention = True
            await ctx.send("Mentions are now **Enabled**")
        await self.save_conf()

    @assistant.command(name="maxretention")
    async def max_retention(self, ctx: commands.Context, max_retention: int):
        """
        Set the max messages for a conversation

        Conversation retention is cached and gets reset when the bot restarts or the cog reloads.

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
        set min character length for questions

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
