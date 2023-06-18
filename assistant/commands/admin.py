import asyncio
import contextlib
import logging
import re
import traceback
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
from openai.version import VERSION
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
from ..common.utils import get_attachments, num_tokens_from_string, request_embedding
from ..models import CHAT, COMPLETION, Embedding
from ..views import CodeMenu, EmbeddingMenu, SetAPI

log = logging.getLogger("red.vrt.assistant.admin")


class Admin(MixinMeta):
    @commands.group(name="assistant", aliases=["ass"])
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def assistant(self, ctx: commands.Context):
        """
        Setup the assistant

        You will need an api key to use the assistant. https://platform.openai.com/account/api-keys
        """
        pass

    @assistant.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
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
            f"`OpenAI Version:    `{VERSION}\n"
            f"`Enabled:           `{conf.enabled}\n"
            f"`Timezone:          `{conf.timezone}\n"
            f"`Channel:           `{channel}\n"
            f"`? Required:        `{conf.endswith_questionmark}\n"
            f"`Mentions:          `{conf.mention}\n"
            f"`Max Retention:     `{conf.max_retention}\n"
            f"`Retention Expire:  `{conf.max_retention_time}s\n"
            f"`Max Tokens:        `{conf.max_tokens}\n"
            f"`Min Length:        `{conf.min_length}\n"
            f"`Temperature:       `{conf.temperature}\n"
            f"`System Message:    `{humanize_number(system_tokens)} tokens\n"
            f"`Initial Prompt:    `{humanize_number(prompt_tokens)} tokens\n"
            f"`Model:             `{conf.model}\n"
            f"`Embeddings:        `{humanize_number(len(conf.embeddings))}\n"
            f"`Top N Embeddings:  `{conf.top_n}\n"
            f"`Min Relatedness:   `{conf.min_relatedness}\n"
            f"`Embedding Method:  `{conf.embed_method}\n"
            f"`Function Calling:  `{conf.use_function_calls}\n"
            f"`Maximum Recursion: `{conf.max_function_calls}"
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
            embed.add_field(
                name="Regex Failure Blocking",
                value=f"Block reply if regex replacement fails: **{conf.block_failed_regex}**",
                inline=False,
            )

        persist = (
            "Conversations are stored persistently"
            if self.db.persistent_conversations
            else "conversations are stored in memory until reboot or reload"
        )
        embed.add_field(name="Persistent Conversations", value=persist, inline=False)

        blacklist = []
        for object_id in conf.blacklist:
            discord_obj = (
                ctx.guild.get_role(object_id)
                or ctx.guild.get_member(object_id)
                or ctx.guild.get_channel_or_thread(object_id)
            )
            if discord_obj:
                blacklist.append(discord_obj.mention)
            else:
                blacklist.append(f"{object_id}?")
        if blacklist:
            embed.add_field(name="Blacklist", value=humanize_list(blacklist), inline=False)

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
    @commands.bot_has_permissions(embed_links=True)
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

    @assistant.command(name="persist")
    @commands.is_owner()
    async def toggle_persistent_conversations(self, ctx: commands.Context):
        """Toggle persistent conversations"""
        if self.db.persistent_conversations:
            self.db.persistent_conversations = False
            await ctx.send("Persistent conversations have been **Disabled**")
        else:
            self.db.persistent_conversations = True
            await ctx.send("Persistent conversations have been **Enabled**")
        await self.save_conf()

    @assistant.command(name="prompt", aliases=["pre"])
    async def set_initial_prompt(self, ctx: commands.Context, *, prompt: str = ""):
        """
        Set the initial prompt for GPT to use

        **Placeholders**
        - **botname**: [botname]
        - **timestamp**: discord timestamp
        - **day**: Mon-Sun
        - **date**: MM-DD-YYYY
        - **time**: HH:MM AM/PM
        - **timetz**: HH:MM AM/PM Timezone
        - **members**: server member count
        - **username**: user's name
        - **displayname**: user's display name
        - **roles**: the names of the user's roles
        - **rolementions**: the mentions of the user's roles
        - **avatar**: the user's avatar url
        - **owner**: the owner of the server
        - **servercreated**: the create date/time of the server
        - **server**: the name of the server
        - **py**: python version
        - **dpy**: discord.py version
        - **red**: red version
        - **cogs**: list of currently loaded cogs
        - **channelname**: name of the channel the conversation is taking place in
        - **channelmention**: current channel mention
        - **topic**: topic of current channel (if not forum or thread)
        - **banktype**: whether the bank is global or not
        - **currency**: currency name
        - **bank**: bank name
        - **balance**: the user's current balance
        """
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                prompt = (await attachments[0].read()).decode()
            except Exception as e:
                await ctx.send(
                    f"Failed to read `{attachments[0].filename}`, bot owner can use `{ctx.prefix}traceback` for more information"
                )
                log.error("Failed to parse initial prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()
                return

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

        **Placeholders**
        - **botname**: [botname]
        - **timestamp**: discord timestamp
        - **day**: Mon-Sun
        - **date**: MM-DD-YYYY
        - **time**: HH:MM AM/PM
        - **timetz**: HH:MM AM/PM Timezone
        - **members**: server member count
        - **username**: user's name
        - **displayname**: user's display name
        - **roles**: the names of the user's roles
        - **rolementions**: the mentions of the user's roles
        - **avatar**: the user's avatar url
        - **owner**: the owner of the server
        - **servercreated**: the create date/time of the server
        - **server**: the name of the server
        - **py**: python version
        - **dpy**: discord.py version
        - **red**: red version
        - **cogs**: list of currently loaded cogs
        - **channelname**: name of the channel the conversation is taking place in
        - **channelmention**: current channel mention
        - **topic**: topic of current channel (if not forum or thread)
        - **banktype**: whether the bank is global or not
        - **currency**: currency name
        - **bank**: bank name
        - **balance**: the user's current balance
        """
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                system_prompt = (await attachments[0].read()).decode()
            except Exception as e:
                await ctx.send(
                    f"Failed to read `{attachments[0].filename}`, bot owner can use `{ctx.prefix}traceback` for more information"
                )
                log.error("Failed to parse initial prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()
                return

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

    @assistant.command(name="temperature")
    async def set_temperature(self, ctx: commands.Context, temperature: float):
        """
        Set the temperature for the model (0.0 - 1.0)

        Closer to 0 is more concise and accurate while closer to 1 is more imaginative
        """
        if not 0 <= temperature <= 1:
            return await ctx.send("Temperature must be between 0.0 and 1.0")
        conf = self.db.get_conf(ctx.guild)
        conf.temperature = temperature
        await self.save_conf()
        await ctx.tick()

    @assistant.command(name="functioncalls")
    async def toggle_function_calls(self, ctx: commands.Context):
        """Toggle whether GPT can call functions

        Only the following models can call functions at the moment
        - gpt-3.5-turbo-0613
        - gpt-3.5-turbo-16k-0613
        - gpt-4-0613
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.use_function_calls:
            conf.use_function_calls = False
            await ctx.send("Assistant will not call functions")
        else:
            conf.use_function_calls = True
            await ctx.send("Assistant will now call functions as needed")
        await self.save_conf()

    @assistant.command(name="maxrecursion")
    async def set_max_recursion(self, ctx: commands.Context, recursion: int):
        """Set the maximum function calls allowed in a row

        This sets how many times the model can call functions in a row

        Only the following models can call functions at the moment
        - gpt-3.5-turbo-0613
        - gpt-3.5-turbo-16k-0613
        - gpt-4-0613
        """
        conf = self.db.get_conf(ctx.guild)
        recursion = max(0, recursion)
        if recursion == 0:
            await ctx.send("Function calls will not be used since recursion is 0")
        await ctx.send(
            f"The model can now call various functions up to {recursion} times before returning a response"
        )
        conf.max_function_calls = recursion

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
        if max_tokens < 100:
            return await ctx.send("Use at least 100 tokens for the model")
        conf = self.db.get_conf(ctx.guild)
        conf.max_tokens = max_tokens
        await ctx.send(f"The max tokens the current model will use is {max_tokens}")
        await self.save_conf()

    @assistant.command(name="model")
    async def set_model(self, ctx: commands.Context, model: str = None):
        """
        Set the GPT model to use

        Valid models and their context info:
        - Model-Name: MaxTokens, ModelType
        - gpt-3.5-turbo: 4096, chat
        - gpt-3.5-turbo-16k: 16384, chat
        - gpt-4: 8192, chat
        - gpt-4-32k: 32768, chat
        - code-davinci-002: 8001, chat
        - text-davinci-003: 4097, completion
        - text-davinci-002: 4097, completion
        - text-curie-001: 2049, completion
        - text-babbage-001: 2049, completion
        - text-ada-001: 2049, completion

        Other sub-models are also included
        """
        valid = humanize_list(CHAT + COMPLETION)
        if not model:
            return await ctx.send(f"Valid models are `{valid}`")
        model = model.lower().strip()
        if model not in CHAT + COMPLETION:
            return await ctx.send(f"Invalid model type! Valid model types are `{valid}`")
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

    @assistant.command(name="resetglobalembeddings")
    @commands.is_owner()
    async def wipe_global_embeddings(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved embeddings for all servers

        This will delete any and all saved embedding training data for the assistant.
        """
        if not yes_or_no:
            return await ctx.send("Not wiping embedding data")
        for conf in self.db.configs.values():
            conf.embeddings = {}
        await ctx.send("All embedding data has been wiped for all servers!")
        await self.save_conf()

    @assistant.command(name="resetconversations")
    async def wipe_conversations(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved conversations for the assistant in this server

        This will delete any and all saved conversations for the assistant.
        """
        if not yes_or_no:
            return await ctx.send("Not wiping conversations")
        for key, convo in self.db.conversations.items():
            if ctx.guild.id == int(key.split("-")[2]):
                convo.messages.clear()
        await ctx.send("Conversations have been wiped in this server!")
        await self.save_conf()

    @assistant.command(name="resetglobalconversations")
    @commands.is_owner()
    async def wipe_global_conversations(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved conversations for the assistant in all servers

        This will delete any and all saved conversations for the assistant.
        """
        if not yes_or_no:
            return await ctx.send("Not wiping conversations")
        for convo in self.db.conversations.values():
            convo.messages.clear()
        await ctx.send("Conversations have been wiped for all servers!")
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

    @assistant.command(name="regexfailblock")
    @commands.is_owner()
    async def toggle_regex_fail_blocking(self, ctx: commands.Context):
        """
        Toggle whether failed regex blocks the assistant's reply

        Some regexes can cause [catastrophically backtracking](https://www.rexegg.com/regex-explosive-quantifiers.html)
        The bot can safely handle if this happens and will either continue on, or block the response.
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.block_failed_regex:
            conf.block_failed_regex = False
            await ctx.send("If a regex blacklist fails, the bots reply will be blocked")
        else:
            conf.block_failed_regex = True
            await ctx.send("If a reges blacklist fails, the bot will still reply")
        await self.save_conf()

    @assistant.command(name="embeddingtest", aliases=["etest"])
    @commands.bot_has_permissions(embed_links=True)
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
    @commands.bot_has_permissions(attach_files=True)
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
    @commands.bot_has_permissions(attach_files=True)
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
    @commands.admin_or_permissions(administrator=True)
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

    @commands.hybrid_command(name="customfunctions", aliases=["customfunction", "customfunc"])
    @commands.guild_only()
    @commands.guildowner()
    async def custom_functions(self, ctx: commands.Context):
        """
        Add custom function calls for Assistant to use

        **READ**
        - [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling)
        - [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)
        - [JSON Schema Reference](https://json-schema.org/understanding-json-schema/)

        Only these two models can use function calls as of now:
        - gpt-3.5-turbo-0613
        - gpt-4-0613

        The following objects are passed by default as keyword arguments.
        - **user**: the user currently chatting with the bot (discord.Member)
        - **channel**: channel the user is chatting in (TextChannel|Thread|ForumChannel)
        - **guild**: current guild (discord.Guild)
        - **bot**: the bot object (Red)
        - **conf**: the config model for Assistant (GuildSettings)
        - All functions **MUST** include `*args, **kwargs` in the params and return a string
        ```python
        # Can be either sync or async
        async def func(*args, **kwargs) -> str:
        ```
        Only bot owner can manage this, guild owners can see descriptions but not code
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        view = CodeMenu(ctx, self.db, self.registry, self.save_conf)
        await view.get_pages()
        return await view.start()

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

    @assistant.command(name="wipecog")
    @commands.is_owner()
    async def wipe_cog(self, ctx: commands.Context, confirm: bool):
        """Wipe all settings and data for entire cog"""
        if not confirm:
            return await ctx.send("Not wiping cog")
        self.db.configs.clear()
        self.db.conversations.clear()
        self.db.persistent_conversations = False
        await self.save_conf()
        await ctx.send("Cog has been wiped!")

    @assistant.command(name="blacklist")
    async def blacklist_settings(
        self,
        ctx: commands.Context,
        *,
        channel_role_member: Union[
            discord.Member,
            discord.Role,
            discord.TextChannel,
            discord.CategoryChannel,
            discord.Thread,
            discord.ForumChannel,
        ],
    ):
        """
        Add/Remove items from the blacklist

        `channel_role_member` can be a member, role, channel, or category channel
        """
        conf = self.db.get_conf(ctx.guild)
        if channel_role_member.id in conf.blacklist:
            conf.blacklist.remove(channel_role_member.id)
            await ctx.send(f"{channel_role_member.name} has been removed from the blacklist")
        else:
            conf.blacklist.append(channel_role_member.id)
            await ctx.send(f"{channel_role_member.name} has been added to the blacklist")
        await self.save_conf()
