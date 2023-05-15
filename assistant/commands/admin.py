import logging
from io import BytesIO
from typing import Union

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_list, humanize_number

from ..abc import MixinMeta
from ..common.utils import (
    extract_message_content,
    fetch_channel_history,
    get_attachments,
    get_embedding_async,
    num_tokens_from_string,
)
from ..models import MODELS, Embedding
from ..views import EmbeddingMenu, SetAPI

log = logging.getLogger("red.vrt.assistant.admin")


class Admin(MixinMeta):
    @commands.group(name="assistant", aliases=["ass"])
    @commands.admin()
    @commands.guild_only()
    async def assistant(self, ctx: commands.Context):
        """
        Setup the assistant

        You will need an api key to use the assistant. https://platform.openai.com/account/api-keys
        """
        pass

    @assistant.command(name="view")
    async def view_settings(self, ctx: commands.Context, private: bool = True):
        """
        View current settings

        To send in current channel, use `[p]assistant view false`
        """
        conf = self.db.get_conf(ctx.guild)
        channel = f"<#{conf.channel_id}>" if conf.channel_id else "Not Set"
        system_tokens = num_tokens_from_string(conf.system_prompt)
        prompt_tokens = num_tokens_from_string(conf.prompt)
        desc = (
            f"`Enabled:          `{conf.enabled}\n"
            f"`Channel:          `{channel}\n"
            f"`? Required:       `{conf.endswith_questionmark}\n"
            f"`Mentions:         `{conf.mention}\n"
            f"`Max Retention:    `{conf.max_retention}\n"
            f"`Retention Expire: `{conf.max_retention_time}s\n"
            f"`Max Tokens:       `{conf.max_tokens}\n"
            f"`Min Length:       `{conf.min_length}\n"
            f"`System Message:   `{humanize_number(system_tokens)} tokens\n"
            f"`Initial Prompt:   `{humanize_number(prompt_tokens)} tokens\n"
            f"`Model:            `{conf.model}\n"
            f"`Embeddings:       `{humanize_number(len(conf.embeddings))}\n"
            f"`Top N Embeddings: `{conf.top_n}\n"
            f"`Min Relatedness:  `{conf.min_relatedness}"
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
            discord.File(BytesIO(conf.prompt.encode()), filename="InitialPrompt.txt")
            if conf.prompt
            else None
        )
        embed = discord.Embed(
            title="Assistant Settings",
            description=desc,
            color=ctx.author.color,
        )
        send_key = [ctx.guild.owner_id == ctx.author.id, ctx.author.id in self.bot.owner_ids]
        if private and any(send_key):
            embed.add_field(
                name="OpenAI Key",
                value=conf.api_key if conf.api_key else "Not Set",
                inline=False,
            )
        embed.set_footer(text=f"Showing settings for {ctx.guild.name}")
        files = []
        if system_file:
            files.append(system_file)
        if prompt_file:
            files.append(prompt_file)

        if private:
            try:
                await ctx.author.send(embed=embed, files=files)
                await ctx.send("Sent your current settings for this server in DMs!")
            except discord.Forbidden:
                await ctx.send("You need to allow DMs so I can message you!")
        else:
            await ctx.send(embed=embed, files=files)

    @assistant.command(name="openaikey", aliases=["key"])
    async def set_openai_key(self, ctx: commands.Context):
        """Set your OpenAI key"""
        view = SetAPI(ctx.author)
        embed = discord.Embed(description="Click to set your OpenAI key", color=ctx.author.color)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip()
        if not key:
            return await msg.edit(content="No key was entered!", embed=None, view=None)
        conf = self.db.get_conf(ctx.guild)
        conf.api_key = key
        await msg.edit(content="OpenAI key has been set!", embed=None, view=None)
        await self.save_conf()

    @assistant.command(name="train")
    async def create_training_prompt(
        self,
        ctx: commands.Context,
        *channels: Union[discord.TextChannel, discord.Thread, discord.ForumChannel],
    ):
        """
        Automatically create embedding data to train your assistant

        **How to Use**
        Include channels that give helpful info about your server, NOT normal chat channels.
        The bot will scan all pinned messages in addition to the most recent 50 messages.
        The idea is to have the bot compile the information, condense it and provide a usable training embeddings for your Q&A channel.

        **Note:** This just meant to get you headed in the right direction, creating quality training data takes trial and error.
        """
        if not channels:
            return await ctx.send_help()
        conf = self.db.get_conf(ctx.guild)
        loading = "https://i.imgur.com/l3p6EMX.gif"
        color = ctx.author.color
        channel_list = humanize_list([c.mention for c in channels])
        embed = discord.Embed(
            description="Scanning channels shortly, please wait...",
            color=color,
        )
        embed.set_thumbnail(url=loading)
        embed.add_field(name="Channels being trained", value=channel_list)
        async with ctx.typing():
            msg = await ctx.send(embed=embed)
            created = 0
            for channel in channels:
                messages = []
                for i in await fetch_channel_history(channel, oldest=False, limit=50):
                    messages.append(i)
                text = f"Channel name: {channel.name}\nChannel mention: {channel.mention}\n"
                if isinstance(channel, discord.TextChannel):
                    text += f"Channel topic: {channel.topic}\n"
                    for pin in await channel.pins():
                        messages.append(pin)
                for message in messages:
                    if content := extract_message_content(message):
                        text += content
                        key = f"{channel.name}-{message.id}"
                        embedding = await get_embedding_async(text, conf.api_key)
                        if not embedding:
                            continue
                        conf.embeddings[key] = Embedding(text=text, embedding=embedding)
                        created += 1

            if not created:
                embed.description = "No content found!"
                embed.clear_fields()
                return await msg.edit(embed=embed)
            embed.description = f"Training finished, {created} embedding entries created!"
            embed.clear_fields()
            await msg.edit(embed=embed)
            await self.save_conf()

    @assistant.command(name="prompt", aliases=["pre"])
    async def set_initial_prompt(self, ctx: commands.Context, *, prompt: str = ""):
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
        `roles` - the names of the user's roles
        `avatar` - the user's avatar url
        `owner` - the owner of the server
        `servercreated` - the create date/time of the server
        `server` - the name of the server
        `messages` - count of messages between the user and bot
        `tokens` - the token count of the current conversation
        `retention` - max retention number
        `retentiontime` - max retention time seconds
        """
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                prompt = (await attachments[0].read()).decode()
            except Exception as e:
                return await ctx.send(f"Error:```py\n{e}\n```")

        conf = self.db.get_conf(ctx.guild)

        ptokens = num_tokens_from_string(prompt)
        stokens = num_tokens_from_string(conf.system_prompt)
        combined = ptokens + stokens
        max_tokens = round(conf.max_tokens * 0.9)
        if combined >= max_tokens:
            return await ctx.send(
                (
                    f"Your system and initial prompt combined will use {humanize_number(combined)} tokens!\n"
                    f"Write a prompt combination using {humanize_number(max_tokens)} tokens or less to leave 10% of your configured max tokens for your response."
                )
            )

        if not prompt and conf.prompt:
            conf.prompt = ""
            await ctx.send("The initial prompt has been removed!")
        elif not prompt and not conf.prompt:
            await ctx.send(
                (
                    "Please include an initial prompt or .txt file!\n"
                    f"Use `{ctx.prefix}help assistant prompt` to view details for this command"
                )
            )
        elif prompt and conf.prompt:
            conf.prompt = prompt.strip()
            await ctx.send("The initial prompt has been overwritten!")
        else:
            conf.prompt = prompt.strip()
            await ctx.send("Initial prompt has been set!")

        await self.save_conf()

    @assistant.command(name="system", aliases=["sys"])
    async def set_system_prompt(self, ctx: commands.Context, *, system_prompt: str = None):
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
        `roles` - the names of the user's roles
        `avatar` - the user's avatar url
        `owner` - the owner of the server
        `servercreated` - the create date/time of the server
        `server` - the name of the server
        `messages` - count of messages between the user and bot
        `tokens` - the token count of the current conversation
        `retention` - max retention number
        `retentiontime` - max retention time seconds
        """
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                system_prompt = (await attachments[0].read()).decode()
            except Exception as e:
                return await ctx.send(f"Error:```py\n{e}\n```")

        conf = self.db.get_conf(ctx.guild)

        ptokens = num_tokens_from_string(conf.prompt)
        stokens = num_tokens_from_string(system_prompt)
        combined = ptokens + stokens
        max_tokens = round(conf.max_tokens * 0.9)
        if combined >= max_tokens:
            return await ctx.send(
                (
                    f"Your system and initial prompt combined will use {humanize_number(combined)} tokens!\n"
                    f"Write a prompt combination using {humanize_number(max_tokens)} tokens or less to leave 10% of your configured max tokens for your response."
                )
            )

        if system_prompt and (len(system_prompt) + len(conf.prompt)) >= 16000:
            return await ctx.send(
                "Training data is too large! System and initial prompt need to be under 16k characters"
            )

        if not system_prompt and conf.system_prompt:
            conf.system_prompt = ""
            await ctx.send("The system prompt has been removed!")
        elif not system_prompt and not conf.system_prompt:
            await ctx.send(
                (
                    "Please include a system prompt or .txt file!\n"
                    f"Use `{ctx.prefix}help assistant system` to view details for this command"
                )
            )
        elif system_prompt and conf.system_prompt:
            conf.system_prompt = system_prompt.strip()
            await ctx.send("The system prompt has been overwritten!")
        else:
            conf.system_prompt = system_prompt.strip()
            await ctx.send("System prompt has been set!")

        await self.save_conf()

    @assistant.command(name="channel")
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
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
            await ctx.send("Questions will be answered regardless of if they end with **?**")
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
            return await ctx.send("Max retention needs to be at least 0 or higher")
        conf = self.db.get_conf(ctx.guild)
        conf.max_retention = max_retention
        if max_retention == 0:
            await ctx.send("Conversation retention has been disabled")
        else:
            await ctx.tick()
        await self.save_conf()

        if max_retention > 15:
            await ctx.send(
                (
                    "**NOTE:** Setting message retention too high may result in going over the token limit, "
                    "if this happens the bot may not respond until the retention is lowered."
                )
            )

    @assistant.command(name="maxtime")
    async def max_retention_time(self, ctx: commands.Context, retention_time: int):
        """
        Set the conversation expiration time

        Regardless of this number, the initial prompt and internal system message are always included,
        this only applies to any conversation between the user and bot after that.

        Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded
        """
        if retention_time < 0:
            return await ctx.send("Max retention time needs to be at least 0 or higher")
        conf = self.db.get_conf(ctx.guild)
        conf.max_retention_time = retention_time
        if retention_time == 0:
            await ctx.send(
                "Conversations will be stored until the bot restarts or the cog is reloaded"
            )
        else:
            await ctx.tick()
        await self.save_conf()

    @assistant.command(name="minlength")
    async def min_length(self, ctx: commands.Context, min_question_length: int):
        """
        set min character length for questions

        Set to 0 to respond to anything
        """
        if min_question_length < 0:
            return await ctx.send("Minimum length needs to be at least 0 or higher")
        conf = self.db.get_conf(ctx.guild)
        conf.min_length = min_question_length
        if min_question_length == 0:
            await ctx.send(f"{ctx.bot.user.name} will respond regardless of message length")
        else:
            await ctx.tick()
        await self.save_conf()

    @assistant.command(name="maxtokens")
    async def max_tokens(self, ctx: commands.Context, max_tokens: int):
        """
        Set the max tokens the model can use at once

        For GPT3.5 use 4000 or less.
        For GPT4 user 8000 or less (if 8k version).

        Using more than the model can handle will raise exceptions.
        """
        if max_tokens < 1000:
            return await ctx.send("Use at least 1000 tokens for the model")
        conf = self.db.get_conf(ctx.guild)
        conf.max_tokens = max_tokens
        await ctx.send(f"The max tokens the current model will use is {max_tokens}")
        await self.save_conf()

    @assistant.command(name="model")
    async def set_model(self, ctx: commands.Context, model: str):
        """
        Set the GPT model to use

        Valid models are `gpt-3.5-turbo`, `gpt-4`, and `gpt-4-32k
        """
        if model not in MODELS:
            return await ctx.send("Invalid model type!")
        conf = self.db.get_conf(ctx.guild)
        conf.model = model
        await ctx.send(f"The {model} model will now be used")
        await self.save_conf()

    @assistant.command(name="embeddings", aliases=["embed"])
    async def embeddings(self, ctx: commands.Context):
        """Manage embeddings for training

        Embeddings are used to optimize training of the assistant and minimize token usage.

        By using this the bot can store vast amounts of contextual information without going over the token limit.
        """
        conf = self.db.get_conf(ctx.guild)
        view = EmbeddingMenu(ctx, conf, self.save_conf)
        await view.start()

    @assistant.command(name="resetembeddings")
    async def wipe_embeddings(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved embeddings for the assistant

        This will delete any and all saved embedding training data for the assistant.
        """
        if not yes_or_no:
            return await ctx.send("Not wiping embedding data")
        conf = self.db.get_conf(ctx.guild)
        conf.embeddings = {}
        await ctx.send("All embedding data has been wiped!")
        await self.save_conf()

    @assistant.command(name="topn")
    async def set_topn(self, ctx: commands.Context, top_n: int):
        """
        Set the embedding inclusion about

        Top N is the amount of embeddings to include with the initial prompt
        """
        if not 0 <= top_n <= 10:
            return await ctx.send("Top N must be between 0 and 10")
        conf = self.db.get_conf(ctx.guild)
        conf.top_n = top_n
        await ctx.tick()
        await self.save_conf()

    @assistant.command(name="relatedness")
    async def set_min_relatedness(self, ctx: commands.Context, mimimum_relatedness: float):
        """
        Set the minimum relatedness an embedding must be to include with the prompt

        Relatedness threshold between 0 and 1 to include in embeddings during chat

        Questions are converted to embeddings and compared against stored embeddings to pull the most relevant, this is the score that is derived from that comparison

        **Hint**: The closer to 1 you get, the more deterministic and accurate the results may be, just don't be *too* strict or there wont be any results.
        """
        if not 0 <= mimimum_relatedness <= 1:
            return await ctx.send("Minimum relatedness must be between 0 and 1")
        conf = self.db.get_conf(ctx.guild)
        conf.min_relatedness = mimimum_relatedness
        await ctx.tick()
        await self.save_conf()
