import asyncio
import contextlib
import logging
import re
from datetime import datetime
from io import BytesIO
from typing import List, Union
from zipfile import ZIP_DEFLATED, ZipFile

import discord
import orjson
import pandas as pd
import pytz
from aiocache import cached
from discord.app_commands import Choice
from pydantic import ValidationError
from rapidfuzz import fuzz
from redbot.core import app_commands, commands
from redbot.core.utils.chat_formatting import (
    box,
    escape,
    humanize_list,
    humanize_number,
    pagify,
)

from ..abc import MixinMeta
from ..common.utils import (
    extract_message_content,
    fetch_channel_history,
    get_attachments,
    num_tokens_from_string,
    request_embedding,
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
            f"`Enabled:           `{conf.enabled}\n"
            f"`Timezone:          `{conf.timezone}\n"
            f"`Channel:           `{channel}\n"
            f"`? Required:        `{conf.endswith_questionmark}\n"
            f"`Mentions:          `{conf.mention}\n"
            f"`Max Retention:     `{conf.max_retention}\n"
            f"`Retention Expire:  `{conf.max_retention_time}s\n"
            f"`Max Tokens:        `{conf.max_tokens}\n"
            f"`Min Length:        `{conf.min_length}\n"
            f"`System Message:    `{humanize_number(system_tokens)} tokens\n"
            f"`Initial Prompt:    `{humanize_number(prompt_tokens)} tokens\n"
            f"`Model:             `{conf.model}\n"
            f"`Embeddings:        `{humanize_number(len(conf.embeddings))}\n"
            f"`Top N Embeddings:  `{conf.top_n}\n"
            f"`Min Relatedness:   `{conf.min_relatedness}\n"
            f"`Embedding Method:  `{conf.embed_method}"
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

        if conf.regex_blacklist:
            joined = "\n".join(conf.regex_blacklist)
            for p in pagify(joined, page_length=1000):
                embed.add_field(name="Regex Blacklist", value=box(p), inline=False)

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

    @assistant.command(name="timezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone used for prompt placeholders"""
        timezone = timezone.lower()
        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            likely_match = sorted(
                pytz.common_timezones, key=lambda x: fuzz.ratio(timezone, x.lower()), reverse=True
            )[0]
            return await ctx.send(f"Invalid Timezone, did you mean `{likely_match}`?")
        time = datetime.now(tz).strftime("%I:%M %p")  # Convert to 12-hour format
        await ctx.send(f"Timezone set to **{timezone}** (`{time}`)")
        conf = self.db.get_conf(ctx.guild)
        conf.timezone = timezone
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
                try:
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
                            embedding = await request_embedding(text, conf.api_key)
                            if not embedding:
                                continue
                            conf.embeddings[key] = Embedding(text=text, embedding=embedding)
                            created += 1
                except discord.Forbidden:
                    await ctx.send(f"I dont have access to {channel.mention}")

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
        `day` - the current day of the week
        `date` - todays date (Month, Day, Year)
        `time` - current time in 12hr format (HH:MM AM/PM)
        `timetz` - current time in 12hr format (HH:MM AM/PM Timezone)
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
        `py` - python version
        `dpy` - discord.py version
        `red` - red version
        `cogs` - list of currently loaded cogs
        `channelname` - name of the channel the conversation is taking place in
        `channelmention` - current channel mention
        `topic` - topic of current channel (if not forum or thread)
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
        `day` - the current day of the week
        `date` - todays date (Month, Day, Year)
        `time` - current time in 12hr format (HH:MM AM/PM)
        `timetz` - current time in 12hr format (HH:MM AM/PM Timezone)
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
        `py` - python version
        `dpy` - discord.py version
        `red` - red version
        `cogs` - list of currently loaded cogs
        `channelname` - name of the channel the conversation is taking place in
        `channelmention` - current channel mention
        `topic` - topic of current channel (if not forum or thread)
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

        Valid models are `gpt-3.5-turbo`, `gpt-4`, and `gpt-4-32k`
        """
        if model not in MODELS:
            return await ctx.send("Invalid model type!")
        conf = self.db.get_conf(ctx.guild)
        conf.model = model
        await ctx.send(f"The {model} model will now be used")
        await self.save_conf()

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
        Set the embedding inclusion amout

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

    @assistant.command(name="regexblacklist")
    async def regex_blacklist(self, ctx: commands.Context, *, regex: str):
        """Remove certain words/phrases in the bot's responses"""
        try:
            re.compile(regex)
        except re.error:
            return await ctx.send("That regex is invalid")
        conf = self.db.get_conf(ctx.guild)
        if regex in conf.regex_blacklist:
            conf.regex_blacklist.remove(regex)
            await ctx.send(f"`{regex}` has been **Removed** from the blacklist")
        else:
            conf.regex_blacklist.append(regex)
            await ctx.send(f"`{regex}` has been **Added** to the blacklist")
        await self.save_conf()

    @assistant.command(name="embeddingtest", aliases=["etest"])
    async def test_embedding_response(self, ctx: commands.Context, *, question: str):
        """
        Fetch related embeddings according to the current settings along with their scores

        You can use this to fine-tune the minimum relatedness for your assistant
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.embeddings:
            return await ctx.send("You do not have any embeddings configured!")
        async with ctx.typing():
            query = await request_embedding(question, conf.api_key)
            if not query:
                return await ctx.send("Failed to get embedding for your query")
            embeddings = conf.get_related_embeddings(query)
            if not embeddings:
                return await ctx.send(
                    "No embeddings could be related to this query with the current settings"
                )
            for name, em, score in embeddings:
                for p in pagify(em, page_length=4000):
                    embed = discord.Embed(
                        description=f"`Name: `{name}\n`Score: `{score}\n{box(escape(p))}"
                    )
                    await ctx.send(embed=embed)

    @assistant.command(name="embedmethod")
    async def toggle_embedding_method(self, ctx: commands.Context):
        """
        Cycle between embedding methods

        **Dynamic** embeddings mean that the embeddings pulled are dynamically appended to the initial prompt for each individual question.
        When each time the user asks a question, the previous embedding is replaced with embeddings pulled from the current question, this reduces token usage significantly

        **Static** embeddings are applied in front of each user message and get stored with the conversation instead of being replaced with each question.

        **Hybrid** embeddings are a combination, with the first embedding being stored in the conversation and the rest being dynamic, this saves a bit on token usage

        Dynamic embeddings are helpful for Q&A, but not so much for chat when you need to retain the context pulled from the embeddings. The hybrid method is a good middle ground
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.embed_method == "dynamic":
            conf.embed_method = "static"
            await ctx.send("Embedding method has been set to **Static**")
        elif conf.embed_method == "static":
            conf.embed_method = "hybrid"
            await ctx.send("Embedding method has been set to **Hybrid**")
        else:  # Conf is hybrid
            conf.embed_method = "dynamic"
            await ctx.send("Embedding method has been set to **Dynamic**")
        await self.save_conf()

    @assistant.command(name="importcsv")
    async def import_embeddings_csv(self, ctx: commands.Context, overwrite: bool):
        """Import embeddings to use with the assistant

        Args:
            overwrite (bool): overwrite embeddings with existing entry names

        This will read excel files too
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.api_key:
            return await ctx.send("No API key set!")
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                "You must attach **.csv** files to this command or reference a message that has them!"
            )
        frames = []
        files = []
        for attachment in attachments:
            file_bytes = await attachment.read()
            try:
                if attachment.filename.lower().endswith(".csv"):
                    df = pd.read_csv(BytesIO(file_bytes))
                else:
                    df = pd.read_excel(BytesIO(file_bytes))
            except Exception as e:
                log.error("Error reading uploaded file", exc_info=e)
                await ctx.send(f"Error reading **{attachment.filename}**: {box(str(e))}")
                continue
            invalid = ["name" not in df.columns, "text" not in df.columns]
            if any(invalid):
                await ctx.send(
                    f"**{attachment.filename}** contains invalid formatting, columns must be ['name', 'text']",
                )
                continue
            frames.append(df)
            files.append(attachment.filename)

        if not frames:
            return await ctx.send("There are no valid files to import!")

        message_text = (
            f"Processing the following files in the background\n{box(humanize_list(files))}"
        )
        message = await ctx.send(message_text)

        df = await asyncio.to_thread(pd.concat, frames)
        imported = 0
        for index, row in enumerate(df.values):
            if pd.isna(row[0]) or pd.isna(row[1]):
                continue
            name = str(row[0])
            proc = "processing"
            if name in conf.embeddings:
                proc = "overwriting"
                if row[1] == conf.embeddings[name].text or not overwrite:
                    continue
            text = str(row[1])[:4000]

            if index and (index + 1) % 5 == 0:
                with contextlib.suppress(discord.DiscordServerError):
                    await message.edit(
                        content=f"{message_text}\n`Currently {proc}: `**{name}** ({index + 1}/{len(df)})"
                    )
            embedding = await request_embedding(text, conf.api_key)
            if not embedding:
                await ctx.send(f"Failed to process embedding: `{name}`")
                continue

            conf.embeddings[name] = Embedding(text=text, embedding=embedding)
            imported += 1
        await message.edit(content=f"{message_text}\n**COMPLETE**")
        await ctx.send(f"Successfully imported {humanize_number(imported)} embeddings!")
        await self.save_conf()

    @assistant.command(name="importjson")
    async def import_embeddings_json(self, ctx: commands.Context, overwrite: bool):
        """Import embeddings to use with the assistant

        Args:
            overwrite (bool): overwrite embeddings with existing entry names
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.api_key:
            return await ctx.send("No API key set!")
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                "You must attach **.json** files to this command or reference a message that has them!"
            )

        imported = 0
        files = []
        async with ctx.typing():
            for attachment in attachments:
                file_bytes: bytes = await attachment.read()
                try:
                    embeddings = orjson.loads(file_bytes)
                except Exception as e:
                    log.error("Error reading uploaded file", exc_info=e)
                    await ctx.send(f"Error reading **{attachment.filename}**: {box(str(e))}")
                    continue
                try:
                    for name, em in embeddings.items():
                        if not overwrite and name in conf.embeddings:
                            continue
                        conf.embeddings[name] = Embedding.parse_obj(em)
                        conf.embeddings[name].text = conf.embeddings[name].text[:4000]
                        imported += 1
                except ValidationError:
                    await ctx.send(
                        f"Failed to import **{attachment.filename}** because it contains invalid formatting!"
                    )
                    continue
                files.append(attachment.filename)
            await ctx.send(
                f"Imported the following files: `{humanize_list(files)}`\n{humanize_number(imported)} embeddings imported"
            )

    @assistant.command(name="exportcsv")
    async def export_embeddings_csv(self, ctx: commands.Context):
        """Export embeddings to a .csv file

        **Note:** csv exports do not include the embedding values
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.embeddings:
            return await ctx.send("There are no embeddings to export!")
        async with ctx.typing():
            columns = ["name", "text"]
            rows = []
            for name, em in conf.embeddings.items():
                rows.append([name, em.text])
            df = pd.DataFrame(rows, columns=columns)
            df_buffer = BytesIO()
            df.to_csv(df_buffer, index=False)
            df_buffer.seek(0)
            file = discord.File(df_buffer, filename="embeddings_export.csv")

            try:
                await ctx.send("Here is your embeddings export!", file=file)
                return
            except discord.HTTPException:
                await ctx.send("File too large, attempting to compress...")

            def zip_file() -> discord.File:
                zip_buffer = BytesIO()
                with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as arc:
                    arc.writestr(
                        "embeddings_export.csv",
                        df_buffer.getvalue(),
                        compress_type=ZIP_DEFLATED,
                        compresslevel=9,
                    )
                zip_buffer.seek(0)
                file = discord.File(zip_buffer, filename="embeddings_csv_export.zip")
                return file

            file = await asyncio.to_thread(zip_file)
            try:
                await ctx.send("Here is your embeddings export!", file=file)
                return
            except discord.HTTPException:
                await ctx.send("File is still too large even with compression!")

    @assistant.command(name="exportjson")
    async def export_embeddings_json(self, ctx: commands.Context):
        """Export embeddings to a json file"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.embeddings:
            return await ctx.send("There are no embeddings to export!")

        async with ctx.typing():
            dump = {name: em.dict() for name, em in conf.embeddings.items()}
            json_buffer = BytesIO(orjson.dumps(dump))
            file = discord.File(json_buffer, filename="embeddings_export.json")

            try:
                await ctx.send("Here is your embeddings export!", file=file)
                return
            except discord.HTTPException:
                await ctx.send("File too large, attempting to compress...")

            def zip_file() -> discord.File:
                zip_buffer = BytesIO()
                with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as arc:
                    arc.writestr(
                        "embeddings_export.json",
                        json_buffer.getvalue(),
                        compress_type=ZIP_DEFLATED,
                        compresslevel=9,
                    )
                zip_buffer.seek(0)
                file = discord.File(zip_buffer, filename="embeddings_json_export.zip")
                return file

            file = await asyncio.to_thread(zip_file)
            try:
                await ctx.send("Here is your embeddings export!", file=file)
                return
            except discord.HTTPException:
                await ctx.send("File is still too large even with compression!")

    @commands.hybrid_command(name="embeddings", aliases=["emenu"])
    @app_commands.describe(query="Name of the embedding entry")
    @commands.guild_only()
    @commands.admin()
    async def embeddings(self, ctx: commands.Context, *, query: str = ""):
        """Manage embeddings for training

        Embeddings are used to optimize training of the assistant and minimize token usage.

        By using this the bot can store vast amounts of contextual information without going over the token limit.

        **Note**
        You can enter a search query with this command to bring up the menu and go directly to that embedding selection.
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.api_key:
            return await ctx.send(
                f"No API key! Use `{ctx.prefix}assistant openaikey` to set your OpenAI key!"
            )
        if ctx.interaction:
            await ctx.interaction.response.defer()

        view = EmbeddingMenu(ctx, conf, self.save_conf)
        await view.get_pages()
        if not query:
            return await view.start()

        for page_index, embed in enumerate(view.pages):
            found = False
            for place_index, field in enumerate(embed.fields):
                name = field.name.replace("➣ ", "", 1)
                if name != query:
                    continue
                view.change_place(place_index)
                view.page = page_index
                found = True
                break
            if found:
                break

        await view.start()

    @embeddings.autocomplete("query")
    async def embeddings_complete(self, interaction: discord.Interaction, current: str):
        return await self.get_matches(interaction.guild_id, current)

    @cached(ttl=120)
    async def get_embedding_entries(self, guild_id: int) -> List[str]:
        return list(self.db.get_conf(guild_id).embeddings.keys())

    @cached(ttl=30)
    async def get_matches(self, guild_id: int, current: str) -> List[Choice]:
        entries = await self.get_embedding_entries(guild_id)
        return [Choice(name=i, value=i) for i in entries if current.lower() in i.lower()][:25]
