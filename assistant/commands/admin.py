import asyncio
import contextlib
import logging
import re
import traceback
import typing as t
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Union
from zipfile import ZIP_DEFLATED, ZipFile

import discord
import openai
import orjson
import pandas as pd
import pytz
from aiocache import cached
from discord.app_commands import Choice
from pydantic import ValidationError
from rapidfuzz import fuzz
from redbot.core import app_commands, commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    pagify,
    text_to_file,
)

from ..abc import MixinMeta
from ..common.constants import MODELS, PRICES
from ..common.models import DB
from ..common.utils import get_attachments
from ..views import CodeMenu, EmbeddingMenu, SetAPI

log = logging.getLogger("red.vrt.assistant.admin")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class Admin(MixinMeta):
    @commands.group(name="assistant", aliases=["assist"])
    @commands.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def assistant(self, ctx: commands.Context):
        """
        Setup the assistant

        You will need an **[api key](https://platform.openai.com/account/api-keys)** from OpenAI to use ChatGPT and their other models.
        """
        pass

    @assistant.command(name="view", aliases=["v"])
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context, private: bool = False):
        """
        View current settings

        To send in current channel, use `[p]assistant view false`
        """
        send_key = [ctx.guild.owner_id == ctx.author.id, ctx.author.id in self.bot.owner_ids]

        conf = self.db.get_conf(ctx.guild)
        model = conf.get_user_model(ctx.author)
        system_tokens = await self.count_tokens(conf.system_prompt, model) if conf.system_prompt else 0
        prompt_tokens = await self.count_tokens(conf.prompt, model) if conf.prompt else 0

        func_list, __ = await self.db.prep_functions(self.bot, conf, self.registry, showall=True)
        func_tokens = await self.count_function_tokens(func_list, model)
        func_count = len(func_list)

        status = await self.openai_status()

        desc = (
            _("`OpenAI Version:      `{}\n").format(openai.VERSION)
            + _("`OpenAI API Status:   `{}\n").format(status)
            + _("`Draw Command:        `{}\n").format(_("Enabled") if conf.image_command else _("Disabled"))
            + _("`Model:               `{}\n").format(conf.model)
            + _("`Embed Model:         `{}\n").format(conf.embed_model)
            + _("`Enabled:             `{}\n").format(conf.enabled)
            + _("`Timezone:            `{}\n").format(conf.timezone)
            + _("`Channel:             `{}\n").format(f"<#{conf.channel_id}>" if conf.channel_id else _("Not Set"))
            + _("`? Required:          `{}\n").format(conf.endswith_questionmark)
            + _("`Question Mode:       `{}\n").format(conf.question_mode)
            + _("`Mention on Reply:    `{}\n").format(conf.mention)
            + _("`Respond to Mentions: `{}\n").format(conf.mention_respond)
            + _("`Collaborative Mode:  `{}\n").format(conf.collab_convos)
            + _("`Max Retention:       `{}\n").format(conf.max_retention)
            + _("`Retention Expire:    `{}s\n").format(conf.max_retention_time)
            + _("`Max Tokens:          `{}\n").format(conf.max_tokens)
            + _("`Max Response Tokens: `{}\n").format(conf.max_response_tokens)
            + _("`Min Length:          `{}\n").format(conf.min_length)
            + _("`Temperature:         `{}\n").format(conf.temperature)
            + _("`Frequency Penalty:   `{}\n").format(conf.frequency_penalty)
            + _("`Presence Penalty:    `{}\n").format(conf.presence_penalty)
            + _("`Seed:                `{}\n").format(conf.seed)
            + _("`Vision Resolution:   `{}\n").format(conf.vision_detail)
            + _("`Reasoning Effort:    `{}\n").format(conf.reasoning_effort)
            + _("`Verbosity:           `{}\n").format(conf.verbosity)
            + _("`System Prompt:       `{} tokens\n").format(humanize_number(system_tokens))
            + _("`User Prompt:         `{} tokens\n").format(humanize_number(prompt_tokens))
            + _("`Endpoint Override:   `{}\n").format(self.db.endpoint_override)
        )

        embed = discord.Embed(
            title=_("Assistant Settings"),
            description=desc,
            color=ctx.author.color,
        )

        name = _("Auto Answer")
        val = _(
            "Auto-answer will trigger the bot outside of the assistant channel if a question is detected and an embedding is not found.\n"
        )
        val += _("`Model:     `{}\n").format(conf.auto_answer_model)
        val += _("`Status:    `{}\n").format(_("Enabled") if conf.auto_answer else _("Disabled"))
        val += _("`Threshold: `{}\n").format(conf.auto_answer_threshold)
        val += _("`Ignored:   `{}\n").format(humanize_list([f"<#{i}>" for i in conf.auto_answer_ignored_channels]))
        embed.add_field(name=name, value=val, inline=False)

        name = _("Trigger Words")
        val = _("Trigger words allow the bot to respond to messages containing specific keywords or regex patterns.\n")
        val += _("`Status:    `{}\n").format(_("Enabled") if conf.trigger_enabled else _("Disabled"))
        val += _("`Phrases:   `{}\n").format(len(conf.trigger_phrases))
        val += _("`Ignored:   `{}\n").format(
            humanize_list([f"<#{i}>" for i in conf.trigger_ignore_channels]) or _("None")
        )
        val += _("`Has Prompt:`{}\n").format(_("Yes") if conf.trigger_prompt else _("No"))
        embed.add_field(name=name, value=val, inline=False)

        if conf.allow_sys_prompt_override:
            val = _("System prompt override is **Allowed**, users can set a personal system prompt per convo.")
        else:
            val = _("System prompt override is **Disabled**, users cannot set a personal system prompt per convo.")
        val += _("\n*This will be restricted to mods if collaborative conversations are enabled!*")
        embed.add_field(name=_("System Prompt Overriding"), value=val, inline=False)

        if conf.channel_prompts:
            valid = [i for i in conf.channel_prompts if ctx.guild.get_channel(i)]
            if len(valid) != len(conf.channel_prompts):
                conf.channel_prompts = {i: conf.channel_prompts[i] for i in valid}
                await self.save_conf()
            embed.add_field(
                name=_("Channel Prompt Overrides"),
                value=humanize_list([f"<#{i}>" for i in valid]),
                inline=False,
            )

        if conf.listen_channels:
            valid = [i for i in conf.listen_channels if ctx.guild.get_channel(i)]
            if len(valid) != len(conf.listen_channels):
                conf.listen_channels = valid
                await self.save_conf()
            embed.add_field(
                name=_("Auto-Reply Channels"),
                value=humanize_list([f"<#{i}>" for i in valid]),
                inline=False,
            )

        all_meta = await self.embedding_store.get_all_metadata(ctx.guild.id)
        types = set(meta.get("dimensions", 0) for meta in all_meta.values())

        if len(types) == 2:
            encoded_by = _("Mixed (Please Refresh!)")
        elif len(types) == 1:
            encoded_by = _("Synced!")
        else:
            encoded_by = _("N/A")

        embedding_field = (
            _("`Top N Embeddings:  `{}\n").format(conf.top_n)
            + _("`Min Relatedness:   `{}\n").format(conf.min_relatedness)
            + _("`Embedding Method:  `{}\n").format(conf.embed_method)
            + _("`Encodings:         `{}").format(encoded_by)
        )
        embed_num = humanize_number(len(all_meta))
        embed.add_field(
            name=_("Embeddings ({})").format(embed_num),
            value=embedding_field,
            inline=False,
        )
        tutors = [ctx.guild.get_member(i) or ctx.guild.get_role(i) for i in conf.tutors]
        mentions = [i.mention for i in tutors if i]
        tutor_field = _(
            "The following roles/users are considered tutors. "
            "If function calls are on and create_memory is enabled, the model can create its own embeddings: "
        )
        tutor_field += humanize_list(sorted(mentions))
        if mentions:
            embed.add_field(name="Tutors", value=tutor_field, inline=False)

        # Planners field
        planners = [ctx.guild.get_member(i) or ctx.guild.get_role(i) for i in conf.planners]
        planner_mentions = [i.mention for i in planners if i]
        if planner_mentions:
            planner_field = _("The following roles/users can use the `think_and_plan` tool: ")
            planner_field += humanize_list(sorted(planner_mentions))
            embed.add_field(name="Planners", value=planner_field, inline=False)

        custom_func_field = (
            _("`Function Calling:  `{}\n").format(conf.use_function_calls)
            + _("`Maximum Recursion: `{}\n").format(conf.max_function_calls)
            + _("`Function Tokens:   `{}\n").format(humanize_number(func_tokens))
        )
        if self.registry:
            cogs = humanize_list([cog for cog in self.registry])
            custom_func_field += _("The following cogs also have functions registered with the assistant\n{}").format(
                box(cogs)
            )

        embed.add_field(
            name=_("Custom Functions ({})").format(humanize_number(func_count)),
            value=custom_func_field,
            inline=False,
        )

        if private and any(send_key):
            embed.add_field(
                name=_("OpenAI Key"),
                value=box(conf.api_key) if conf.api_key else _("Not Set"),
                inline=False,
            )

        if conf.regex_blacklist:
            joined = "\n".join(conf.regex_blacklist)
            for p in pagify(joined, page_length=1000):
                embed.add_field(name=_("Regex Blacklist"), value=box(p), inline=False)
            embed.add_field(
                name=_("Regex Failure Blocking"),
                value=_("Block reply if regex replacement fails: **{}**").format(conf.block_failed_regex),
                inline=False,
            )

        persist = (
            _("Conversations are stored persistently")
            if self.db.persistent_conversations
            else _("conversations are stored in memory until reboot or reload")
        )
        embed.add_field(name=_("Persistent Conversations"), value=persist, inline=False)

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
            embed.add_field(name=_("Blacklist"), value=humanize_list(blacklist), inline=False)

        if not private:
            if overrides := conf.role_overrides:
                field = ""
                roles = {ctx.guild.get_role(k): v for k, v in overrides.copy().items() if ctx.guild.get_role(k)}
                sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
                for role, model in sorted_roles:
                    if not role:
                        continue
                    field += f"{role.mention}: `{model}`\n"
                if field:
                    embed.add_field(name=_("Model Role Overrides"), value=field, inline=False)

            if overrides := conf.max_token_role_override:
                field = ""
                roles = {ctx.guild.get_role(k): v for k, v in overrides.copy().items() if ctx.guild.get_role(k)}
                sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
                for role, tokens in sorted_roles:
                    if not role:
                        continue
                    field += f"{role.mention}: `{humanize_number(tokens)}`\n"
                if field:
                    embed.add_field(name=_("Max Token Role Overrides"), value=field, inline=False)

            if overrides := conf.max_retention_role_override:
                field = ""
                roles = {ctx.guild.get_role(k): v for k, v in overrides.copy().items() if ctx.guild.get_role(k)}
                sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
                for role, retention in sorted_roles:
                    if not role:
                        continue
                    field += f"{role.mention}: `{humanize_number(retention)}`\n"
                if field:
                    embed.add_field(name=_("Max Message Retention Role Overrides"), value=field, inline=False)

            if overrides := conf.max_time_role_override:
                field = ""
                roles = {ctx.guild.get_role(k): v for k, v in overrides.copy().items() if ctx.guild.get_role(k)}
                sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
                for role, retention_time in sorted_roles:
                    if not role:
                        continue
                    field += f"{role.mention}: `{humanize_number(retention_time)}s`\n"
                if field:
                    embed.add_field(
                        name=_("Max Message Retention Time Role Overrides"),
                        value=field,
                        inline=False,
                    )

            if overrides := conf.max_response_token_override:
                field = ""
                roles = {ctx.guild.get_role(k): v for k, v in overrides.copy().items() if ctx.guild.get_role(k)}
                sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
                for role, retention_time in sorted_roles:
                    if not role:
                        continue
                    field += f"{role.mention}: `{humanize_number(retention_time)}s`\n"
                if field:
                    embed.add_field(name=_("Max Response Token Role Overrides"), value=field, inline=False)

        if ctx.author.id in self.bot.owner_ids:
            if self.db.brave_api_key:
                value = _("Your Brave websearch API key is set!")
            else:
                value = _(
                    "Enables the use of the `search_web_brave` function\n"
                    "Get your API key **[Here](https://brave.com/search/api/)**\n"
                )
            embed.add_field(name=_("Brave Websearch API key"), value=value)

        embed.set_footer(text=_("Showing settings for {}").format(ctx.guild.name))

        files = []
        system_file = (
            discord.File(
                BytesIO(conf.system_prompt.encode()),
                filename=_("SystemPrompt") + ".txt",
            )
            if conf.system_prompt
            else None
        )
        prompt_file = (
            discord.File(BytesIO(conf.prompt.encode()), filename=_("InitialPrompt") + ".txt") if conf.prompt else None
        )
        if system_file:
            files.append(system_file)
        if prompt_file:
            files.append(prompt_file)

        if private:
            try:
                await ctx.author.send(embed=embed, files=files)
                await ctx.send(_("Sent your current settings for this server in DMs!"))
            except discord.Forbidden:
                await ctx.send(_("You need to allow DMs so I can message you!"))
        else:
            await ctx.send(embed=embed, files=files)

    @assistant.command(name="usage")
    @commands.bot_has_permissions(embed_links=True)
    async def view_usage(self, ctx: commands.Context):
        """View the token usage stats for this server"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.usage:
            return await ctx.send(_("There is no usage data yet!"))
        embed = discord.Embed(color=ctx.author.color)

        overall_input = 0
        overall_output = 0
        overall_tokens = 0

        total_input_cost = 0
        total_output_cost = 0
        total_cost = 0

        usage_data = conf.usage.copy()
        for model_name, usage in usage_data.items():
            input_price, output_price = PRICES.get(model_name, [0, 0])
            input_cost = (usage.input_tokens / 1000) * input_price
            output_cost = (usage.output_tokens / 1000) * output_price
            model_cost = input_cost + output_cost

            overall_tokens += usage.total_tokens
            overall_input += usage.input_tokens
            overall_output += usage.output_tokens
            total_cost += model_cost
            total_input_cost += input_cost
            total_output_cost += output_cost

            if model_name in [
                "text-embedding-ada-002",
                "text-embedding-ada-002-v2",
                "text-embedding-3-small",
                "text-embedding-3-large",
            ]:
                field = _("`Total:  `{} (${} @ ${}/1k tokens)").format(
                    humanize_number(usage.input_tokens), round(input_cost, 2), input_price
                )
                embed.add_field(name=model_name, value=field, inline=False)
                continue

            if model_name not in MODELS:
                field = _("Free/Self-Hosted")
                embed.add_field(name=model_name, value=field, inline=False)
                continue

            field = _(
                "`Input:  `{} (${} @ ${}/1k tokens)\n`Output: `{} (${} @ ${}/1k tokens)\n`Total:  `{} (${})"
            ).format(
                humanize_number(usage.input_tokens),
                round(input_cost, 2),
                input_price,
                humanize_number(usage.output_tokens),
                round(output_cost, 2),
                output_price,
                humanize_number(usage.total_tokens),
                round(model_cost, 2),
            )
            embed.add_field(name=model_name, value=field, inline=False)

        desc = _(
            "**Overall Token Usage and Cost**\n"
            "`Input:      `{} (${})\n"
            "`Output:     `{} (${})\n"
            "`Total:      `{} (${})\n"
            "`Tool Calls: `{}\n"
        ).format(
            humanize_number(overall_input),
            round(total_input_cost, 2),
            humanize_number(overall_output),
            round(total_output_cost, 2),
            humanize_number(overall_tokens),
            round(total_cost, 2),
            humanize_number(conf.functions_called),
        )
        embed.description = desc
        return await ctx.send(embed=embed)

    @assistant.command(name="resetusage")
    @commands.bot_has_permissions(embed_links=True)
    async def reset_usage(self, ctx: commands.Context):
        """Reset the token usage stats for this server"""
        conf = self.db.get_conf(ctx.guild)
        conf.usage = {}
        await ctx.send(_("Token usage stats have been reset!"))
        await self.save_conf()

    @assistant.command(name="openaikey", aliases=["key"])
    @commands.bot_has_permissions(embed_links=True)
    async def set_openai_key(self, ctx: commands.Context):
        """
        Set your OpenAI key
        """
        conf = self.db.get_conf(ctx.guild)

        view = SetAPI(ctx.author, conf.api_key)
        txt = _("Click to set your OpenAI key\n\nTo remove your keys, enter `none`")
        embed = discord.Embed(description=txt, color=ctx.author.color)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip() if view.key else "none"

        try:
            if key == "none" and conf.api_key:
                conf.api_key = None
                await msg.edit(content=_("OpenAI key has been removed!"), embed=None, view=None)
            elif key == "none" and not conf.api_key:
                conf.api_key = key
                await msg.edit(content=_("No API key was entered!"), embed=None, view=None)
            else:
                conf.api_key = key
                await msg.edit(content=_("OpenAI key has been set!"), embed=None, view=None)
        except discord.NotFound:
            pass

        await self.save_conf()

    @assistant.command(name="braveapikey", aliases=["brave"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.is_owner()
    async def set_brave_key(self, ctx: commands.Context):
        """
        Enables use of the `search_web_brave` function

        Get your API key **[Here](https://brave.com/search/api/)**
        """
        view = SetAPI(ctx.author, self.db.brave_api_key)
        txt = _("Click to set your API key\n\nTo remove your keys, enter `none`")
        embed = discord.Embed(description=txt, color=ctx.author.color)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip() if view.key else "none"

        if key == "none" and self.db.brave_api_key:
            self.db.brave_api_key = None
            await msg.edit(content=_("Brave API key has been removed!"), embed=None, view=None)
        elif key == "none" and not self.db.brave_api_key:
            return await msg.edit(content=_("No API key was entered!"), embed=None, view=None)
        else:
            self.db.brave_api_key = key
            await msg.edit(content=_("Brave API key has been set!"), embed=None, view=None)

        await self.save_conf()

    @assistant.command(name="timezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone used for prompt placeholders"""
        timezone = timezone.lower()
        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            likely_match = sorted(pytz.common_timezones, key=lambda x: fuzz.ratio(timezone, x.lower()), reverse=True)[0]
            return await ctx.send(_("Invalid Timezone, did you mean `{}`?").format(likely_match))
        time = datetime.now(tz).strftime("%I:%M %p")  # Convert to 12-hour format
        await ctx.send(_("Timezone set to **{}** (`{}`)").format(timezone, time))
        conf = self.db.get_conf(ctx.guild)
        conf.timezone = timezone
        await self.save_conf()

    @assistant.command(name="prompt", aliases=["pre"])
    async def set_initial_prompt(self, ctx: commands.Context, *, prompt: str = ""):
        """
        Set the initial prompt for GPT to use

        Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.

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
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse initial prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return

        conf = self.db.get_conf(ctx.guild)
        model = conf.get_user_model(ctx.author)
        ptokens = await self.count_tokens(prompt, model) if prompt else 0
        stokens = await self.count_tokens(conf.system_prompt, model) if conf.system_prompt else 0
        combined = ptokens + stokens
        if conf.max_tokens:
            max_tokens = round(conf.max_tokens * 0.9)
            if combined >= max_tokens:
                return await ctx.send(
                    _(
                        "Your system and initial prompt combined will use {} tokens!\n"
                        "Write a prompt combination using {} tokens or less to leave 10% of your configured max tokens for your response."
                    ).format(humanize_number(combined), humanize_number(max_tokens))
                )

        if not prompt and conf.prompt:
            conf.prompt = ""
            await ctx.send(_("The initial prompt has been removed!"))
        elif not prompt and not conf.prompt:
            await ctx.send(
                _("Please include an initial prompt or .txt file!\nUse `{}` to view details for this command").format(
                    f"{ctx.clean_prefix}help assistant prompt"
                )
            )
        elif prompt and conf.prompt:
            conf.prompt = prompt.strip()
            await ctx.send(_("The initial prompt has been overwritten!"))
        else:
            conf.prompt = prompt.strip()
            await ctx.send(_("Initial prompt has been set!"))

        await self.save_conf()

    @assistant.command(name="channelpromptshow")
    @commands.has_permissions(attach_files=True)
    async def show_channel_prompt(self, ctx: commands.Context, channel: discord.TextChannel = commands.CurrentChannel):
        """Show the channel specific system prompt"""
        conf = self.db.get_conf(ctx.guild)
        if channel.id not in conf.channel_prompts:
            return await ctx.send(_("No channel prompt set for {}").format(channel.mention))
        file = text_to_file(conf.channel_prompts[channel.id], f"{channel.name}_prompt.txt")
        await ctx.send(file=file)

    @assistant.command(name="channelprompt")
    async def set_channel_prompt(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.CurrentChannel,
        *,
        system_prompt: t.Optional[str] = None,
    ):
        """Set a channel specific system prompt"""
        conf = self.db.get_conf(ctx.guild)
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                system_prompt = (await attachments[0].read()).decode()
            except Exception as e:
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse initial prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return
        if system_prompt is None:
            if channel.id in conf.channel_prompts:
                del conf.channel_prompts[channel.id]
                await ctx.send(_("Channel prompt has been removed from {}!").format(channel.mention))
                await self.save_conf()
            else:
                await ctx.send(_("No channel prompt set for {}!").format(channel.mention))
            return
        model = conf.get_user_model(ctx.author)
        ptokens = await self.count_tokens(conf.prompt, model) if conf.prompt else 0
        stokens = await self.count_tokens(system_prompt, model) if system_prompt else 0
        combined = ptokens + stokens
        if conf.max_tokens:
            max_tokens = round(conf.max_tokens * 0.9)
            if combined >= max_tokens:
                return await ctx.send(
                    _(
                        "Your system and initial prompt combined will use {} tokens!\n"
                        "Write a prompt combination using {} tokens or less to leave 10% of your configured max tokens for your response."
                    ).format(humanize_number(combined), humanize_number(max_tokens))
                )
        if channel.id in conf.channel_prompts:
            await ctx.send(_("Channel prompt has been overwritten for {}!").format(channel.mention))
        else:
            await ctx.send(_("Channel prompt has been set for {}!").format(channel.mention))
        conf.channel_prompts[channel.id] = system_prompt
        await self.save_conf()

    @assistant.command(name="system", aliases=["sys"])
    async def set_system_prompt(self, ctx: commands.Context, *, system_prompt: str = None):
        """
        Set the system prompt for GPT to use

        Check out [This Guide](https://platform.openai.com/docs/guides/prompt-engineering) for prompting help.

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
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse initial prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return

        conf = self.db.get_conf(ctx.guild)
        model = conf.get_user_model(ctx.author)
        ptokens = await self.count_tokens(conf.prompt, model) if conf.prompt else 0
        stokens = await self.count_tokens(system_prompt, model) if system_prompt else 0

        combined = ptokens + stokens
        if conf.max_tokens:
            max_tokens = round(conf.max_tokens * 0.9)
            if combined >= max_tokens:
                return await ctx.send(
                    _(
                        "Your system and initial prompt combined will use {} tokens!\n"
                        "Write a prompt combination using {} tokens or less to leave 10% of your configured max tokens for your response."
                    ).format(humanize_number(combined), humanize_number(max_tokens))
                )

        if not system_prompt and conf.system_prompt:
            conf.system_prompt = ""
            await ctx.send(_("The system prompt has been removed!"))
        elif not system_prompt and not conf.system_prompt:
            await ctx.send(
                _("Please include a system prompt or .txt file!\nUse `{}` to view details for this command").format(
                    f"{ctx.clean_prefix}help assistant system"
                )
            )
        elif system_prompt and conf.system_prompt:
            conf.system_prompt = system_prompt.strip()
            await ctx.send(_("The system prompt has been overwritten!"))
        else:
            conf.system_prompt = system_prompt.strip()
            await ctx.send(_("System prompt has been set!"))

        await self.save_conf()

    @assistant.command(name="channel")
    async def set_channel(
        self,
        ctx: commands.Context,
        channel: Union[discord.TextChannel, discord.Thread, discord.ForumChannel, None] = None,
    ):
        """Set the main auto-response channel for the assistant"""
        conf = self.db.get_conf(ctx.guild)
        if channel is None and not conf.channel_id:
            return await ctx.send_help()
        if channel is None and conf.channel_id:
            await ctx.send(_("Assistant channel has been removed"))
            conf.channel_id = 0
        elif channel and conf.channel_id:
            await ctx.send(_("Assistant channel has been overwritten"))
            conf.channel_id = channel.id
        else:
            await ctx.send(_("Channel id has been set"))
            conf.channel_id = channel.id
        await self.save_conf()

    @assistant.command(name="listen")
    async def toggle_listen(self, ctx: commands.Context):
        """Toggle this channel as an auto-response channel"""
        conf = self.db.get_conf(ctx.guild)
        if conf.channel_id == ctx.channel.id:
            return await ctx.send(_("This channel is already set as the assistant channel!"))
        if ctx.channel.id in conf.listen_channels:
            conf.listen_channels.remove(ctx.channel.id)
            await ctx.send(_("I will no longer auto-respond to messages in this channel!"))
        else:
            conf.listen_channels.append(ctx.channel.id)
            await ctx.send(_("I will now auto-respond to messages in this channel!"))
        await self.save_conf()

    @assistant.command(name="sysoverride")
    async def toggle_systemoverride(self, ctx: commands.Context):
        """Toggle allowing per-conversation system prompt overriding"""
        conf = self.db.get_conf(ctx.guild)
        if conf.allow_sys_prompt_override:
            conf.allow_sys_prompt_override = False
            await ctx.send(_("System prompt overriding **Disabled**, users cannot set per-convo system prompts"))
        else:
            conf.allow_sys_prompt_override = True
            await ctx.send(_("System prompt overriding **Enabled**, users can now set per-convo system prompts"))
        await self.save_conf()

    @assistant.command(name="toggle")
    async def toggle_gpt(self, ctx: commands.Context):
        """Toggle the assistant on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.enabled:
            conf.enabled = False
            await ctx.send(_("The assistant is now **Disabled**"))
        else:
            conf.enabled = True
            await ctx.send(_("The assistant is now **Enabled**"))
        await self.save_conf()

    @assistant.command(name="toggledraw", aliases=["drawtoggle"])
    async def toggle_draw_command(self, ctx: commands.Context):
        """Toggle the draw command on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.image_command:
            conf.image_command = False
            await ctx.send(_("The draw command is now **Disabled**"))
        else:
            conf.image_command = True
            await ctx.send(_("The draw command is now **Enabled**"))
        await self.save_conf()

    @assistant.command(name="autoanswer")
    async def toggle_autoanswer(self, ctx: commands.Context):
        """Toggle the auto-answer feature on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.auto_answer:
            conf.auto_answer = False
            await ctx.send(_("Auto-answer has been **Disabled**"))
        else:
            conf.auto_answer = True
            await ctx.send(_("Auto-answer has been **Enabled**"))
        await self.save_conf()

    @assistant.command(name="autoanswerthreshold")
    async def set_autoanswer_threshold(self, ctx: commands.Context, threshold: float):
        """Set the auto-answer threshold for the bot"""
        conf = self.db.get_conf(ctx.guild)
        conf.auto_answer_threshold = threshold
        await ctx.send(_("Auto-answer threshold has been set to **{}**").format(threshold))
        await self.save_conf()

    @assistant.command(name="autoanswerignore")
    async def autoanswer_ignore_channel(
        self, ctx: commands.Context, channel: discord.TextChannel | discord.CategoryChannel | int
    ):
        """Ignore a channel for auto-answer"""
        conf = self.db.get_conf(ctx.guild)
        if isinstance(channel, int):
            channel_id = channel
            mention = f"<#{channel}>"
        else:
            channel_id = channel.id
            mention = channel.mention

        if channel_id in conf.auto_answer_ignored_channels:
            conf.auto_answer_ignored_channels.remove(channel_id)
            await ctx.send(_("Auto-answer will no longer ignore {}").format(mention))
        else:
            if not ctx.guild.get_channel(channel_id):
                return await ctx.send(_("Channel not found!"))
            conf.auto_answer_ignored_channels.append(channel_id)
            await ctx.send(_("Auto-answer will now ignore {}").format(mention))
        await self.save_conf()

    @assistant.command(name="autoanswermodel")
    async def set_autoanswer_model(self, ctx: commands.Context, model: str):
        """Set the model used for auto-answer"""
        conf = self.db.get_conf(ctx.guild)
        if model not in MODELS:
            return await ctx.send(_("Invalid model, valid models are: {}").format(humanize_list(MODELS)))
        conf.auto_answer_model = model
        await ctx.send(_("Auto-answer model has been set to **{}**").format(model))
        await self.save_conf()

    # ---------- Trigger Word Commands ----------

    @assistant.command(name="trigger")
    async def toggle_trigger(self, ctx: commands.Context):
        """Toggle the trigger word feature on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.trigger_enabled:
            conf.trigger_enabled = False
            await ctx.send(_("Trigger word feature has been **Disabled**"))
        else:
            conf.trigger_enabled = True
            await ctx.send(_("Trigger word feature has been **Enabled**"))
        await self.save_conf()

    @assistant.command(name="triggerphrase")
    async def add_trigger_phrase(self, ctx: commands.Context, *, phrase: str):
        """
        Add or remove a trigger phrase (supports regex)

        The bot will respond to messages containing this phrase.
        Phrases are case-insensitive regex patterns.

        **Examples**
        - `hello` - matches messages containing "hello"
        - `\\bhelp\\b` - matches the word "help" (word boundary)
        - `bad.*word` - matches "bad" followed by any characters then "word"
        """
        try:
            re.compile(phrase)
        except re.error:
            return await ctx.send(_("That regex pattern is invalid!"))

        # Warn about overly broad patterns
        broad_patterns = [r".*", r".+", r".", r"^", r"$", r"^.*$", r"^.+$"]
        if phrase in broad_patterns:
            await ctx.send(_("⚠️ Warning: `{}` is a very broad pattern that may match most messages!").format(phrase))

        conf = self.db.get_conf(ctx.guild)
        if phrase in conf.trigger_phrases:
            conf.trigger_phrases.remove(phrase)
            await ctx.send(_("Trigger phrase `{}` has been **Removed**").format(phrase))
        else:
            conf.trigger_phrases.append(phrase)
            await ctx.send(_("Trigger phrase `{}` has been **Added**").format(phrase))
        await self.save_conf()

    @assistant.command(name="triggerprompt")
    async def set_trigger_prompt(self, ctx: commands.Context, *, prompt: str = None):
        """
        Set the prompt to use when a trigger phrase is matched

        This prompt will be appended to the initial prompt when the bot responds to a triggered message.

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
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse trigger prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return

        conf = self.db.get_conf(ctx.guild)

        if not prompt and conf.trigger_prompt:
            conf.trigger_prompt = ""
            await ctx.send(_("The trigger prompt has been removed!"))
        elif not prompt and not conf.trigger_prompt:
            await ctx.send(
                _("Please include a trigger prompt or .txt file!\nUse `{}` to view details for this command").format(
                    f"{ctx.clean_prefix}help assistant triggerprompt"
                )
            )
        elif prompt and conf.trigger_prompt:
            conf.trigger_prompt = prompt.strip()
            await ctx.send(_("The trigger prompt has been overwritten!"))
        else:
            conf.trigger_prompt = prompt.strip()
            await ctx.send(_("Trigger prompt has been set!"))

        await self.save_conf()

    @assistant.command(name="triggerignore")
    async def trigger_ignore_channel(
        self, ctx: commands.Context, channel: discord.TextChannel | discord.CategoryChannel | int
    ):
        """Ignore a channel or category for trigger phrases"""
        conf = self.db.get_conf(ctx.guild)
        if isinstance(channel, int):
            channel_id = channel
            mention = f"<#{channel}>"
        else:
            channel_id = channel.id
            mention = channel.mention

        if channel_id in conf.trigger_ignore_channels:
            conf.trigger_ignore_channels.remove(channel_id)
            await ctx.send(_("Trigger phrases will no longer ignore {}").format(mention))
        else:
            if not ctx.guild.get_channel(channel_id):
                return await ctx.send(_("Channel not found!"))
            conf.trigger_ignore_channels.append(channel_id)
            await ctx.send(_("Trigger phrases will now ignore {}").format(mention))
        await self.save_conf()

    @assistant.command(name="triggerlist")
    @commands.bot_has_permissions(embed_links=True)
    async def list_triggers(self, ctx: commands.Context):
        """View configured trigger phrases"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.trigger_phrases:
            return await ctx.send(_("No trigger phrases configured!"))

        embed = discord.Embed(
            title=_("Trigger Phrases"),
            description=_("The following phrases will trigger a response:\n"),
            color=ctx.author.color,
        )

        phrases = "\n".join([f"• `{phrase}`" for phrase in conf.trigger_phrases])
        for page in pagify(phrases, page_length=1000):
            embed.add_field(name=_("Patterns"), value=page, inline=False)

        embed.add_field(
            name=_("Status"),
            value=_("Enabled") if conf.trigger_enabled else _("Disabled"),
            inline=True,
        )

        if conf.trigger_ignore_channels:
            ignored = humanize_list([f"<#{c}>" for c in conf.trigger_ignore_channels])
            embed.add_field(name=_("Ignored Channels"), value=ignored, inline=False)

        await ctx.send(embed=embed)

    @assistant.command(name="resolution")
    async def switch_vision_resolution(self, ctx: commands.Context):
        """Switch vision resolution between high and low for relevant GPT-4-Turbo models"""
        conf = self.db.get_conf(ctx.guild)
        if conf.vision_detail == "auto":
            conf.vision_detail = "low"
            await ctx.send(_("Vision resolution has been set to **Low**"))
        elif conf.vision_detail == "low":
            conf.vision_detail = "high"
            await ctx.send(_("Vision resolution has been set to **High**"))
        else:
            conf.vision_detail = "auto"
            await ctx.send(_("Vision resolution has been set to **Auto**"))
        await self.save_conf()

    @assistant.command(name="reasoning")
    async def switch_reasoning_effort(self, ctx: commands.Context):
        """Switch reasoning effort for o1 model between low, medium, and high"""
        conf = self.db.get_conf(ctx.guild)
        if conf.reasoning_effort == "minimal":
            conf.reasoning_effort = "low"
            await ctx.send(_("Reasoning effort has been set to **Low**"))
        elif conf.reasoning_effort == "low":
            conf.reasoning_effort = "medium"
            await ctx.send(_("Reasoning effort has been set to **Medium**"))
        elif conf.reasoning_effort == "medium":
            conf.reasoning_effort = "high"
            await ctx.send(_("Reasoning effort has been set to **High**"))
        else:
            conf.reasoning_effort = "minimal"
            await ctx.send(
                _("Reasoning effort has been set to **Minimal** (Only gpt-5 supports this, otherwise it'll use low)")
            )
        await self.save_conf()

    @assistant.command(name="questionmark")
    async def toggle_question(self, ctx: commands.Context):
        """Toggle whether questions need to end with **__?__**"""
        conf = self.db.get_conf(ctx.guild)
        if conf.endswith_questionmark:
            conf.endswith_questionmark = False
            await ctx.send(_("Questions will be answered regardless of if they end with **?**"))
        else:
            conf.endswith_questionmark = True
            await ctx.send(_("Questions must end in **?** to be answered"))
        await self.save_conf()

    @assistant.command(name="mentionrespond")
    async def toggle_mentionrespond(self, ctx: commands.Context):
        """Toggle whether the bot responds to mentions in any channel"""
        conf = self.db.get_conf(ctx.guild)
        if conf.mention_respond:
            conf.mention_respond = False
            await ctx.send(_("The bot will no longer respond to mentions"))
        else:
            conf.mention_respond = True
            await ctx.send(_("The bot will now respond to mentions"))
        await self.save_conf()

    @assistant.command(name="mention")
    async def toggle_mention(self, ctx: commands.Context):
        """Toggle whether to ping the user on replies"""
        conf = self.db.get_conf(ctx.guild)
        if conf.mention:
            conf.mention = False
            await ctx.send(_("Mentions are now **Disabled**"))
        else:
            conf.mention = True
            await ctx.send(_("Mentions are now **Enabled**"))
        await self.save_conf()

    @assistant.command(name="collab")
    async def toggle_collab(self, ctx: commands.Context):
        """
        Toggle collaborative conversations

        Multiple people speaking in a channel will be treated as a single conversation.
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.collab_convos:
            conf.collab_convos = False
            await ctx.send(_("Collaborative conversations are now **Disabled**"))
        else:
            conf.collab_convos = True
            await ctx.send(_("Collaborative conversations are now **Enabled**"))
        await self.save_conf()

    @assistant.command(name="maxretention")
    async def max_retention(self, ctx: commands.Context, max_retention: int):
        """
        Set the max messages for a conversation

        Conversation retention is cached and gets reset when the bot restarts or the cog reloads.

        Regardless of this number, the initial prompt and internal system message are always included,
        this only applies to any conversation between the user and bot after that.

        Set to 0 to disable conversation retention

        **Note:** *actual message count may exceed the max retention during an API call*
        """
        if max_retention < 0:
            return await ctx.send(_("Max retention needs to be at least 0 or higher"))
        conf = self.db.get_conf(ctx.guild)
        conf.max_retention = max_retention
        if max_retention == 0:
            await ctx.send(_("Conversation retention has been disabled"))
        else:
            await ctx.send(_("Conversations can now retain up to **{}** messages").format(max_retention))
        await self.save_conf()

    @assistant.command(name="maxtime")
    async def max_retention_time(self, ctx: commands.Context, retention_seconds: int):
        """
        Set the conversation expiration time

        Regardless of this number, the initial prompt and internal system message are always included,
        this only applies to any conversation between the user and bot after that.

        Set to 0 to store conversations indefinitely or until the bot restarts or cog is reloaded
        """
        if retention_seconds < 0:
            return await ctx.send(_("Max retention time needs to be at least 0 or higher"))
        conf = self.db.get_conf(ctx.guild)
        conf.max_retention_time = retention_seconds
        if retention_seconds == 0:
            await ctx.send(_("Conversations will be stored until the bot restarts or the cog is reloaded"))
        else:
            await ctx.send(_("Conversations will be considered active for **{}** seconds").format(retention_seconds))
        await self.save_conf()

    @assistant.command(name="temperature")
    async def set_temperature(self, ctx: commands.Context, temperature: float):
        """
        Set the temperature for the model (0.0 - 2.0)
        - Defaults is 1

        Closer to 0 is more concise and accurate while closer to 2 is more imaginative
        """
        if not 0 <= temperature <= 2:
            return await ctx.send(_("Temperature must be between **0.0** and **2.0**"))
        temperature = round(temperature, 2)
        conf = self.db.get_conf(ctx.guild)
        conf.temperature = temperature
        await self.save_conf()
        await ctx.send(_("Temperature has been set to **{}**").format(temperature))

    @assistant.command(name="frequency")
    async def set_frequency_penalty(self, ctx: commands.Context, frequency_penalty: float):
        """
        Set the frequency penalty for the model (-2.0 to 2.0)
        - Defaults is 0

        Positive values penalize new tokens based on their existing frequency in the text so far, decreasing the model's likelihood to repeat the same line verbatim.
        """
        if not -2 <= frequency_penalty <= 2:
            return await ctx.send(_("Frequency penalty must be between **-2.0** and **2.0**"))
        frequency_penalty = round(frequency_penalty, 2)
        conf = self.db.get_conf(ctx.guild)
        conf.frequency_penalty = frequency_penalty
        await self.save_conf()
        await ctx.send(_("Frequency penalty has been set to **{}**").format(frequency_penalty))

    @assistant.command(name="presence")
    async def set_presence_penalty(self, ctx: commands.Context, presence_penalty: float):
        """
        Set the presence penalty for the model (-2.0 to 2.0)
        - Defaults is 0

        Positive values penalize new tokens based on whether they appear in the text so far, increasing the model's likelihood to talk about new topics.
        """
        if not -2 <= presence_penalty <= 2:
            return await ctx.send(_("Presence penalty must be between **-2.0** and **2.0**"))
        presence_penalty = round(presence_penalty, 2)
        conf = self.db.get_conf(ctx.guild)
        conf.presence_penalty = presence_penalty
        await self.save_conf()
        await ctx.send(_("Presence penalty has been set to **{}**").format(presence_penalty))

    @assistant.command(name="seed")
    async def set_seed(self, ctx: commands.Context, seed: int = None):
        """
        Make the model more deterministic by setting a seed for the model.
        - Default is None

        If specified, the system will make a best effort to sample deterministically, such that repeated requests with the same seed and parameters should return the same result.
        """
        if seed is not None and seed < 0:
            return await ctx.send(_("Seed must be a positive integer"))
        conf = self.db.get_conf(ctx.guild)
        conf.seed = seed
        await self.save_conf()
        await ctx.send(_("The seed has been set to **{}**").format(seed))

    @assistant.command(name="refreshembeds", aliases=["refreshembeddings", "syncembeds", "syncembeddings"])
    async def refresh_embeddings(self, ctx: commands.Context):
        """
        Refresh embedding weights

        *This command can be used when changing the embedding model*

        Embeddings that were created using OpenAI cannot be use with the self-hosted model and vice versa
        """
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return
        async with ctx.typing():
            synced = await self.resync_embeddings(conf, ctx.guild.id)
            if synced:
                await ctx.send(_("{} embeddings have been updated").format(synced))
            else:
                await ctx.send(_("No embeddings needed to be refreshed"))

    @assistant.command(name="functioncalls", aliases=["usefunctions"])
    async def toggle_function_calls(self, ctx: commands.Context):
        """Toggle whether GPT can call functions"""
        conf = self.db.get_conf(ctx.guild)
        if conf.use_function_calls:
            conf.use_function_calls = False
            await ctx.send(_("Assistant will not call functions"))
        else:
            conf.use_function_calls = True
            await ctx.send(_("Assistant will now call functions as needed"))
        await self.save_conf()

    @assistant.command(name="maxrecursion")
    async def set_max_recursion(self, ctx: commands.Context, recursion: int):
        """Set the maximum function calls allowed in a row

        This sets how many times the model can call functions in a row

        Only the following models can call functions at the moment
        - gpt-4o-mini
        - gpt-4o
        - ect..
        """
        conf = self.db.get_conf(ctx.guild)
        recursion = max(0, recursion)
        if recursion == 0:
            await ctx.send(_("Function calls will not be used since recursion is 0"))
        await ctx.send(
            _("The model can now call various functions up to {} times before returning a response").format(recursion)
        )
        conf.max_function_calls = recursion

    @assistant.command(name="minlength")
    async def min_length(self, ctx: commands.Context, min_question_length: int):
        """
        set min character length for questions

        Set to 0 to respond to anything
        """
        if min_question_length < 0:
            return await ctx.send(_("Minimum length needs to be at least 0 or higher"))
        conf = self.db.get_conf(ctx.guild)
        conf.min_length = min_question_length
        if min_question_length == 0:
            await ctx.send(_("{} will respond regardless of message length").format(ctx.bot.user.name))
        else:
            await ctx.send(
                _("{} will respond to messages with more than **{}** characters").format(
                    ctx.bot.user.name, min_question_length
                )
            )
        await self.save_conf()

    @assistant.command(name="maxtokens")
    async def max_tokens(self, ctx: commands.Context, max_tokens: commands.positive_int):
        """
        Set maximum tokens a convo can consume

        Set to 0 for dynamic token usage

        **Tips**
        - Max tokens are a soft cap, sometimes messages can be a little over
        - If you set max tokens too high the cog will auto-adjust to 100 less than the models natural cap
        - Ideally set max to 500 less than that models maximum, to allow adequate responses

        Using more than the model can handle will raise exceptions.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.max_tokens = max_tokens
        if max_tokens:
            txt = _(
                "The maximum amount of tokens sent in a payload will be {}.\n"
                "*Note that models with token limits lower than this will still be trimmed*"
            ).format(max_tokens)
        else:
            txt = _("The maximum amount of tokens sent in a payload will be dynamic")
        await ctx.send(txt)
        await self.save_conf()

    @assistant.command(name="maxresponsetokens")
    async def max_response_tokens(self, ctx: commands.Context, max_tokens: commands.positive_int):
        """
        Set the max response tokens the model can respond with

        Set to 0 for response tokens to be dynamic
        """
        conf = self.db.get_conf(ctx.guild)
        conf.max_response_tokens = max_tokens
        if max_tokens:
            txt = _("The maximum amount of tokens in the models responses will be {}.").format(max_tokens)
        else:
            txt = _("Response tokens will now be dynamic")
        await ctx.send(txt)
        await self.save_conf()

    @assistant.command(name="model")
    async def set_model(self, ctx: commands.Context, model: str = None):
        """
        Set the OpenAI model to use
        """
        model = model.lower().strip() if model else None
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return

        if not model:
            valid = [i for i in MODELS]
            humanized = humanize_list(valid)
            formatted = box(humanized)
            return await ctx.send(_("Valid models are:\n{}").format(formatted))

        if conf.api_key and "deepseek" not in model and not self.db.endpoint_override:
            try:
                client = openai.AsyncOpenAI(api_key=conf.api_key)
                await client.models.retrieve(model)
            except openai.NotFoundError as e:
                txt = _("Error: {}").format(e.response.json()["error"]["message"])
                return await ctx.send(txt)

        conf.model = model
        await ctx.send(_("The **{}** model will now be used").format(model))
        await self.save_conf()
        if model.startswith("o"):
            txt = _(
                "**Note**: Starting with `o1-2024-12-17`, reasoning models in the API will avoid generating "
                "responses with markdown formatting. To signal to the model when you do want markdown formatting "
                "in the response, include the string `Formatting re-enabled` on the first line of your system message."
            )
            await ctx.send(txt)

    @assistant.command(name="embedmodel")
    async def set_embedding_model(self, ctx: commands.Context, model: str = None):
        """Set the OpenAI Embedding model to use"""
        model = model.lower().strip() if model else None
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return

        valid = [
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
        ]
        if not model or model not in valid:
            return await ctx.send(_("Valid models are:\n{}").format(box(humanize_list(valid))))
        conf.embed_model = model
        await ctx.send(_("The **{}** model will now be used for embeddings").format(model))
        await self.save_conf()

    @assistant.command(name="resetembeddings")
    async def wipe_embeddings(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved embeddings for the assistant

        This will delete any and all saved embedding training data for the assistant.
        """
        if not yes_or_no:
            return await ctx.send(_("Not wiping embedding data"))
        conf = self.db.get_conf(ctx.guild)
        conf.embeddings = {}  # Clear any leftover migration data
        await self.embedding_store.delete_all(ctx.guild.id)
        await ctx.send(_("All embedding data has been wiped!"))
        await self.save_conf()

    @assistant.command(name="resetconversations")
    async def wipe_conversations(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved conversations for the assistant in this server

        This will delete any and all saved conversations for the assistant.
        """
        if not yes_or_no:
            return await ctx.send(_("Not wiping conversations"))
        for key, convo in self.db.conversations.items():
            if ctx.guild.id == int(key.split("-")[2]):
                convo.messages.clear()
        await ctx.send(_("Conversations have been wiped in this server!"))
        await self.save_conf()

    @assistant.command(name="topn")
    async def set_topn(self, ctx: commands.Context, top_n: int):
        """
        Set the embedding inclusion amout

        Top N is the amount of embeddings to include with the initial prompt
        """
        if not 0 <= top_n <= 10:
            return await ctx.send(_("Top N must be between 0 and 10"))
        conf = self.db.get_conf(ctx.guild)
        conf.top_n = top_n
        if not top_n:
            await ctx.send(_("Embeddings will not be pulled during conversations"))
        else:
            await ctx.send(_("Up to **{}** embeddings will be pulled for each interaction").format(top_n))
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
            return await ctx.send(_("Minimum relatedness must be between 0 and 1"))
        conf = self.db.get_conf(ctx.guild)
        conf.min_relatedness = mimimum_relatedness
        await ctx.send(_("Minimum relatedness has been set to **{}**").format(mimimum_relatedness))
        await self.save_conf()

    @assistant.command(name="regexblacklist")
    async def regex_blacklist(self, ctx: commands.Context, *, regex: str):
        """Remove certain words/phrases in the bot's responses"""
        try:
            re.compile(regex)
        except re.error:
            return await ctx.send(_("That regex is invalid"))
        conf = self.db.get_conf(ctx.guild)
        if regex in conf.regex_blacklist:
            conf.regex_blacklist.remove(regex)
            await ctx.send(_("`{}` has been **Removed** from the blacklist").format(regex))
        else:
            conf.regex_blacklist.append(regex)
            await ctx.send(_("`{}` has been **Added** to the blacklist").format(regex))
        await self.save_conf()

    @assistant.command(name="regexfailblock")
    async def toggle_regex_fail_blocking(self, ctx: commands.Context):
        """
        Toggle whether failed regex blocks the assistant's reply

        Some regexes can cause [catastrophically backtracking](https://www.rexegg.com/regex-explosive-quantifiers.html)
        The bot can safely handle if this happens and will either continue on, or block the response.
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.block_failed_regex:
            conf.block_failed_regex = False
            await ctx.send(_("If a regex blacklist fails, the bots reply will be blocked"))
        else:
            conf.block_failed_regex = True
            await ctx.send(_("If a reges blacklist fails, the bot will still reply"))
        await self.save_conf()

    @assistant.command(name="questionmode")
    async def toggle_question_mode(self, ctx: commands.Context):
        """
        Toggle question mode

        If question mode is on, embeddings will only be sourced during the first message of a conversation and messages that end in **?**
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.question_mode:
            conf.question_mode = False
            await ctx.send(_("Question mode is now **Disabled**"))
        else:
            conf.question_mode = True
            await ctx.send(_("Question mode is now **Enabled**"))
        await self.save_conf()

    @assistant.command(name="embedmethod")
    async def toggle_embedding_method(self, ctx: commands.Context):
        """
        Cycle between embedding methods

        **Dynamic** embeddings mean that the embeddings pulled are dynamically appended to the initial prompt for each individual question.
        When each time the user asks a question, the previous embedding is replaced with embeddings pulled from the current question, this reduces token usage significantly

        **Static** embeddings are applied in front of each user message and get stored with the conversation instead of being replaced with each question.

        **Hybrid** embeddings are a combination, with the first embedding being stored in the conversation and the rest being dynamic, this saves a bit on token usage.

        **User** embeddings are injected into the beginning of the prompt as the first user message.

        Dynamic embeddings are helpful for Q&A, but not so much for chat when you need to retain the context pulled from the embeddings. The hybrid method is a good middle ground
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.embed_method == "dynamic":
            conf.embed_method = "static"
            await ctx.send(_("Embedding method has been set to **Static**"))
        elif conf.embed_method == "static":
            conf.embed_method = "hybrid"
            await ctx.send(_("Embedding method has been set to **Hybrid**"))
        elif conf.embed_method == "hybrid":
            conf.embed_method = "user"
            await ctx.send(_("Embedding method has been set to **User**"))
        elif conf.embed_method == "user":
            conf.embed_method = "dynamic"
            await ctx.send(_("Embedding method has been set to **Dynamic**"))
        await self.save_conf()

    @assistant.command(name="importcsv")
    async def import_embeddings_csv(self, ctx: commands.Context, overwrite: bool):
        """Import embeddings to use with the assistant

        Args:
            overwrite (bool): overwrite embeddings with existing entry names

        This will read excel files too
        """
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                _("You must attach **.csv** files to this command or reference a message that has them!")
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
                await ctx.send(_("Error reading **{}**: {}").format(attachment.filename, box(str(e))))
                continue
            invalid = ["name" not in df.columns, "text" not in df.columns]
            if any(invalid):
                await ctx.send(
                    _("**{}** contains invalid formatting, columns must be ").format(attachment.filename)
                    + "['name', 'text']",
                )
                continue
            frames.append(df)
            files.append(attachment.filename)

        if not frames:
            return await ctx.send(_("There are no valid files to import!"))

        message_text = _("Processing the following files in the background\n{}").format(box(humanize_list(files)))
        message = await ctx.send(message_text)

        df = await asyncio.to_thread(pd.concat, frames)

        entries = len(df.index)
        split_by = 10
        if entries > 300:
            split_by = round(entries / 25)
        imported = 0
        for index, row in enumerate(df.values):
            if pd.isna(row[0]) or pd.isna(row[1]):
                continue
            name = str(row[0])
            proc = _("processing")
            if await self.embedding_store.exists(ctx.guild.id, name):
                proc = _("overwriting")
                existing = await self.embedding_store.get(ctx.guild.id, name)
                if (existing and existing.get("text") == str(row[1])) or not overwrite:
                    continue
            text = str(row[1])[:4000]
            if index and (index + 1) % split_by == 0:
                with contextlib.suppress(discord.DiscordServerError):
                    await message.edit(
                        content=_("{}\n`Currently {}: `**{}** ({}/{})").format(
                            message_text, proc, name, index + 1, len(df)
                        )
                    )
            query_embedding = await self.request_embedding(text, conf)
            if len(query_embedding) == 0:
                await ctx.send(_("Failed to process embedding: `{}`").format(name))
                continue

            await self.embedding_store.add(ctx.guild.id, name, text, query_embedding, conf.embed_model)
            imported += 1
        await message.edit(content=_("{}\n**COMPLETE**").format(message_text))
        await ctx.send(_("Successfully imported {} embeddings!").format(humanize_number(imported)))
        await self.save_conf()

    @assistant.command(name="importjson")
    async def import_embeddings_json(self, ctx: commands.Context, overwrite: bool):
        """Import embeddings to use with the assistant

        Args:
            overwrite (bool): overwrite embeddings with existing entry names
        """
        conf = self.db.get_conf(ctx.guild)
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                _("You must attach **.json** files to this command or reference a message that has them!")
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
                    await ctx.send(_("Error reading **{}**: {}").format(attachment.filename, box(str(e))))
                    continue
                try:
                    for name, em in embeddings.items():
                        if not overwrite and await self.embedding_store.exists(ctx.guild.id, name):
                            continue
                        text = str(em.get("text", ""))[:4000]
                        embedding_vec = em.get("embedding", [])
                        model = em.get("model", conf.embed_model)
                        ai_created = em.get("ai_created", False)
                        if not embedding_vec:
                            # Re-embed if no vector present
                            embedding_vec = await self.request_embedding(text, conf)
                            model = conf.embed_model
                        if not embedding_vec:
                            continue
                        await self.embedding_store.add(
                            ctx.guild.id,
                            name[:100],
                            text,
                            embedding_vec,
                            model,
                            ai_created,
                        )
                        imported += 1
                except (ValidationError, KeyError, TypeError):
                    await ctx.send(
                        _("Failed to import **{}** because it contains invalid formatting!").format(attachment.filename)
                    )
                    continue
                files.append(attachment.filename)
            await ctx.send(
                _("Imported the following files: `{}`\n{} embeddings imported").format(
                    humanize_list(files), humanize_number(imported)
                )
            )
        await self.save_conf()

    @assistant.command(name="importexcel")
    async def import_embeddings_excel(self, ctx: commands.Context, overwrite: bool):
        """Import embeddings from an .xlsx file

        Args:
            overwrite (bool): overwrite embeddings with existing entry names
        """
        conf = self.db.get_conf(ctx.guild)
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                _("You must attach **.xlsx** files to this command or reference a message that has them!")
            )

        imported = 0
        files = []
        frames = []
        async with ctx.typing():
            for attachment in attachments:
                file_bytes = await attachment.read()
                try:
                    # Read the Excel file into a DataFrame
                    df = pd.read_excel(BytesIO(file_bytes), sheet_name="embeddings")
                except Exception as e:
                    log.error("Error reading uploaded file", exc_info=e)
                    await ctx.send(_("Error reading **{}**: {}").format(attachment.filename, box(str(e))))
                    continue
                invalid = [
                    "name" not in df.columns,
                    "text" not in df.columns,
                    "created" not in df.columns,
                    "ai_created" not in df.columns,
                ]
                if any(invalid):
                    txt = _("{} is invalid! Must contain the following columns: {}").format(
                        f"**{attachment.filename}**", "name, text, created, ai_created"
                    )
                    await ctx.send(txt)
                    continue
                frames.append(df)
                files.append(attachment.filename)

            message_text = _("Processing the following files in the background\n{}").format(box(humanize_list(files)))
            message = await ctx.send(message_text)
            df = await asyncio.to_thread(pd.concat, frames)
            entries = len(df.index)
            split_by = 10
            if entries > 300:
                split_by = round(entries / 25)
            imported = 0
            for index, row in df.iterrows():
                name = row["name"]
                text = row["text"]
                proc = _("processing")
                if await self.embedding_store.exists(ctx.guild.id, name):
                    proc = _("overwriting")
                    existing = await self.embedding_store.get(ctx.guild.id, name)
                    if not overwrite or (existing and existing.get("text") == text):
                        continue

                if index and (index + 1) % split_by == 0:
                    with contextlib.suppress(discord.DiscordServerError):
                        await message.edit(
                            content=_("{}\n`Currently {}: `**{}** ({}/{})").format(
                                message_text, proc, name, index + 1, len(df)
                            )
                        )

                query_embedding = await self.request_embedding(text, conf)
                if len(query_embedding) == 0:
                    await ctx.send(_("Failed to process embedding: `{}`").format(name))
                    continue

                await self.embedding_store.add(
                    ctx.guild.id,
                    name,
                    text,
                    query_embedding,
                    conf.embed_model,
                    bool(row["ai_created"]),
                )
                imported += 1

            if imported:
                await message.edit(content=_("{}\n**COMPLETE**").format(message_text))
                await ctx.send(_("Successfully imported {} embeddings!").format(humanize_number(imported)))
                await self.save_conf()
            else:
                await message.edit(content=_("{}\n**COMPLETE**").format(message_text))
                await ctx.send(_("No embeddings needed to be updated!"))

    @assistant.command(name="exportexcel")
    @commands.bot_has_permissions(attach_files=True)
    async def export_embeddings_excel(self, ctx: commands.Context):
        """
        Export embeddings to an .xlsx file

        **Note:** csv exports do not include the embedding values
        """
        all_meta = await self.embedding_store.get_all_metadata(ctx.guild.id)
        if not all_meta:
            return await ctx.send(_("There are no embeddings to export!"))

        columns = {
            "name": str,
            "text": str,
            "created": "datetime64[ns]",  # Use numpy datetime64 type for datetime
            "ai_created": bool,
        }

        def _get_file() -> discord.File:
            rows = []
            for name, meta in all_meta.items():
                created_str = meta.get("created", "")
                try:
                    created_dt = datetime.fromisoformat(created_str).astimezone(timezone.utc).replace(tzinfo=None)
                except (ValueError, TypeError):
                    created_dt = datetime.now(tz=timezone.utc).replace(tzinfo=None)
                rows.append([name, meta.get("text", ""), created_dt, meta.get("ai_created", False)])
            df = pd.DataFrame(rows, columns=columns.keys())

            # Convert the columns to the specified types
            for column, dtype in columns.items():
                if dtype == "datetime64[ns]":
                    df[column] = pd.to_datetime(df[column], utc=True).dt.tz_convert(None)
                else:
                    df[column] = df[column].astype(dtype)

            buffer = BytesIO()
            buffer.name = "embeddings-export.xlsx"
            with pd.ExcelWriter(buffer) as f:
                df.to_excel(f, index=False, sheet_name="embeddings")
            buffer.seek(0)
            return discord.File(buffer)

        async with ctx.typing():
            file = await asyncio.to_thread(_get_file)
            await ctx.send(file=file)

    @assistant.command(name="exportcsv")
    @commands.bot_has_permissions(attach_files=True)
    async def export_embeddings_csv(self, ctx: commands.Context):
        """Export embeddings to a .csv file

        **Note:** csv exports do not include the embedding values
        """
        all_meta = await self.embedding_store.get_all_metadata(ctx.guild.id)
        if not all_meta:
            return await ctx.send(_("There are no embeddings to export!"))
        async with ctx.typing():
            columns = ["name", "text"]
            rows = []
            for name, meta in all_meta.items():
                rows.append([name, meta.get("text", "")])
            df = pd.DataFrame(rows, columns=columns)
            df_buffer = BytesIO()
            df.to_csv(df_buffer, index=False)
            df_buffer.seek(0)
            file = discord.File(df_buffer, filename="embeddings_export.csv")

            try:
                await ctx.send(_("Here is your embeddings export!"), file=file)
                return
            except discord.HTTPException:
                await ctx.send(_("File too large, attempting to compress..."))

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
                await ctx.send(_("Here is your embeddings export!"), file=file)
                return
            except discord.HTTPException:
                await ctx.send(_("File is still too large even with compression!"))

    @assistant.command(name="exportjson")
    @commands.bot_has_permissions(attach_files=True)
    async def export_embeddings_json(self, ctx: commands.Context):
        """Export embeddings to a json file"""
        all_data = await self.embedding_store.get_all_with_embeddings(ctx.guild.id)
        if not all_data:
            return await ctx.send(_("There are no embeddings to export!"))

        async with ctx.typing():
            dump = {name: meta for name, meta in all_data.items()}
            json_buffer = BytesIO(orjson.dumps(dump))
            file = discord.File(json_buffer, filename="embeddings_export.json")

            try:
                await ctx.send(_("Here is your embeddings export!"), file=file)
                return
            except discord.HTTPException:
                await ctx.send(_("File too large, attempting to compress..."))

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
                await ctx.send(_("Here is your embeddings export!"), file=file)
                return
            except discord.HTTPException:
                await ctx.send(_("File is still too large even with compression!"))

    @commands.hybrid_command(name="embeddings", aliases=["emenu"])
    @app_commands.describe(query="Name of the embedding entry")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def embeddings(self, ctx: commands.Context, *, query: str = ""):
        """
        Manage embeddings for training

        Embeddings are used to optimize training of the assistant and minimize token usage.

        By using this the bot can store vast amounts of contextual information without going over the token limit.

        **Note**
        You can enter a search query with this command to bring up the menu and go directly to that embedding selection.
        """
        conf = self.db.get_conf(ctx.guild)
        if ctx.interaction:
            await ctx.interaction.response.defer()

        if not await self.can_call_llm(conf, ctx):
            return

        view = EmbeddingMenu(
            ctx,
            conf,
            self.save_conf,
            self.get_embedding_menu_embeds,
            self.request_embedding,
            self.embedding_store,
            ctx.guild.id,
        )
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
    @app_commands.describe(function_name="Name of the custom function")
    @commands.guild_only()
    @commands.bot_has_permissions(attach_files=True, embed_links=True)
    async def custom_functions(self, ctx: commands.Context, function_name: str = None):
        """
        Add custom function calls for Assistant to use

        **READ**
        - [Function Call Docs](https://platform.openai.com/docs/guides/gpt/function-calling)
        - [OpenAI Cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)
        - [JSON Schema Reference](https://json-schema.org/understanding-json-schema/)

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

        view = CodeMenu(ctx, self.db, self.registry, self.save_conf, self.get_function_menu_embeds)
        await view.get_pages()
        if not function_name:
            return await view.start()

        for page_index, embed in enumerate(view.pages):
            name = embed.description
            if name != function_name:
                continue
            view.page = page_index
            break
        await view.start()

    @commands.hybrid_command(name="listfunctions", aliases=["listfuncs", "funclist"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def list_functions(self, ctx: commands.Context):
        """
        List all available functions and their enabled/disabled status

        This provides a quick overview of all custom functions and 3rd party
        registered functions without having to navigate through the full menu.
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        conf = self.db.get_conf(ctx.guild)

        # Gather all functions
        all_functions: list[tuple[str, str, bool]] = []  # (name, source, enabled)

        # Custom functions from bot owner
        for func_name in self.db.functions:
            enabled = conf.function_statuses.get(func_name, False)
            all_functions.append((func_name, "Custom", enabled))

        # Registry functions from other cogs
        for cog_name, function_schemas in self.registry.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for func_name in function_schemas:
                enabled = conf.function_statuses.get(func_name, False)
                all_functions.append((func_name, cog_name, enabled))

        if not all_functions:
            return await ctx.send(_("No functions have been registered yet!"))

        # Sort by enabled status (enabled first), then by name
        all_functions.sort(key=lambda x: (not x[2], x[0].lower()))

        # Build embed pages
        pages: list[discord.Embed] = []
        enabled_count = sum(1 for f in all_functions if f[2])
        disabled_count = len(all_functions) - enabled_count

        lines = []
        for func_name, source, enabled in all_functions:
            status = "\N{WHITE HEAVY CHECK MARK}" if enabled else "\N{CROSS MARK}"
            source_txt = f" ({source})" if source != "Custom" else ""
            lines.append(f"{status} `{func_name}`{source_txt}")

        # Pagify the lines
        chunks = list(pagify("\n".join(lines), page_length=1500))
        total_pages = len(chunks)
        for i, chunk in enumerate(chunks, 1):
            embed = discord.Embed(
                title=_("Function List"),
                description=chunk,
                color=discord.Color.blue(),
            )
            embed.set_footer(
                text=_("Page {}/{} | {} enabled, {} disabled").format(i, total_pages, enabled_count, disabled_count)
            )
            pages.append(embed)

        if len(pages) == 1:
            return await ctx.send(embed=pages[0])

        # Use simple menu for multiple pages
        from redbot.core.utils.views import SimpleMenu

        await SimpleMenu(pages, disable_after_timeout=True).start(ctx)

    @commands.hybrid_command(name="togglefunctions", aliases=["togglefuncs"])
    @app_commands.describe(
        enable="True to enable, False to disable, or omit to toggle current state",
        functions="Function names to toggle (comma-separated, or 'all' to toggle all)",
    )
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def toggle_functions(
        self,
        ctx: commands.Context,
        enable: t.Optional[bool],
        *,
        functions: str,
    ):
        """
        Enable or disable multiple functions at once

        **Arguments**
        - `enable`: True to enable, False to disable. Omit to toggle current state.
        - `functions`: Comma-separated list of function names, or "all" to affect all functions

        **Examples**
        - `[p]togglefunctions get_time, get_weather` - Toggle these functions
        - `[p]togglefunctions True all` - Enable all functions
        - `[p]togglefunctions False get_time, get_weather` - Disable specific functions
        """
        if ctx.interaction:
            await ctx.interaction.response.defer()

        conf = self.db.get_conf(ctx.guild)

        # Gather all valid function names
        valid_functions: set[str] = set()
        for func_name in self.db.functions:
            valid_functions.add(func_name)
        for cog_name, function_schemas in self.registry.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for func_name in function_schemas:
                valid_functions.add(func_name)

        if not valid_functions:
            return await ctx.send(_("No functions have been registered yet!"))

        # Parse the functions argument
        if functions.lower().strip() == "all":
            target_functions = valid_functions
        else:
            # Split by comma and clean up
            target_functions = {f.strip() for f in functions.split(",") if f.strip()}

        if not target_functions:
            return await ctx.send(_("No valid function names provided!"))

        # Validate function names
        invalid_funcs = target_functions - valid_functions
        if invalid_funcs:
            return await ctx.send(
                _("The following functions do not exist: {}").format(humanize_list(list(invalid_funcs)))
            )

        # Apply changes
        enabled_funcs = []
        disabled_funcs = []
        for func_name in target_functions:
            current_state = conf.function_statuses.get(func_name, False)
            if enable is None:
                # Toggle
                new_state = not current_state
            else:
                new_state = enable

            conf.function_statuses[func_name] = new_state
            if new_state:
                enabled_funcs.append(func_name)
            else:
                disabled_funcs.append(func_name)

        await self.save_conf()

        # Build response
        response_parts = []
        if enabled_funcs:
            response_parts.append(
                _("\N{WHITE HEAVY CHECK MARK} **Enabled** ({}):\n{}").format(
                    len(enabled_funcs), humanize_list([f"`{f}`" for f in sorted(enabled_funcs)])
                )
            )
        if disabled_funcs:
            response_parts.append(
                _("\N{CROSS MARK} **Disabled** ({}):\n{}").format(
                    len(disabled_funcs), humanize_list([f"`{f}`" for f in sorted(disabled_funcs)])
                )
            )

        await ctx.send("\n\n".join(response_parts))

    @toggle_functions.autocomplete("functions")
    async def toggle_functions_complete(self, interaction: discord.Interaction, current: str):
        # Check if user is typing multiple functions (after a comma)
        if "," in current:
            # Get the last part after the last comma for autocomplete
            parts = current.rsplit(",", 1)
            prefix = parts[0] + ", "
            search_term = parts[1].strip().lower()
        else:
            prefix = ""
            search_term = current.lower()

        # Add "all" as an option
        entries = ["all"]
        for key in self.db.functions:
            entries.append(key)
        for functions in self.registry.values():
            for key in functions:
                entries.append(key)

        # Filter and format choices
        choices = []
        for entry in entries:
            if search_term in entry.lower():
                display_name = prefix + entry if prefix else entry
                # Discord limits choice name/value to 100 characters
                if len(display_name) <= 100:
                    choices.append(Choice(name=display_name, value=display_name))
                if len(choices) >= 25:
                    break

        return choices

    @custom_functions.autocomplete("function_name")
    async def custom_func_complete(self, interaction: discord.Interaction, current: str):
        return await self.get_function_matches(current)

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

    @cached(ttl=30)
    async def get_function_matches(self, current: str) -> List[Choice]:
        entries = [key for key in self.db.functions]
        for functions in self.registry.values():
            for key in functions:
                entries.append(key)
        return [Choice(name=i, value=i) for i in entries if current.lower() in i.lower()][:25]

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
            await ctx.send(_("{} has been removed from the blacklist").format(channel_role_member.name))
        else:
            conf.blacklist.append(channel_role_member.id)
            await ctx.send(_("{} has been added to the blacklist").format(channel_role_member.name))
        await self.save_conf()

    @assistant.command(name="tutor", aliases=["tutors"])
    async def tutor_settings(
        self,
        ctx: commands.Context,
        *,
        role_or_member: Union[
            discord.Member,
            discord.Role,
        ],
    ):
        """
        Add/Remove items from the tutor list.

        If using OpenAI's function calling and talking to a tutor, the AI is able to create its own embeddings to remember later

        `role_or_member` can be a member or role
        """
        conf = self.db.get_conf(ctx.guild)
        if role_or_member.id in conf.tutors:
            conf.tutors.remove(role_or_member.id)
            await ctx.send(_("{} has been removed from the tutor list").format(role_or_member.name))
        else:
            conf.tutors.append(role_or_member.id)
            await ctx.send(_("{} has been added to the tutor list").format(role_or_member.name))
        await self.save_conf()

    @assistant.command(name="planner", aliases=["planners"])
    async def planner_settings(
        self,
        ctx: commands.Context,
        *,
        role_or_member: Union[
            discord.Member,
            discord.Role,
        ] = None,
    ):
        """
        Add/Remove items from the planner list, or view current planners.

        Users/roles in the planner list can use the `think_and_plan` tool for complex task breakdown.

        If the planner list is empty, everyone can use the planning tool.
        If the planner list has entries, only those users/roles can use it.

        `role_or_member` can be a member or role. Omit to view the current list.
        """
        conf = self.db.get_conf(ctx.guild)

        if role_or_member is None:
            # Show current planners
            if not conf.planners:
                await ctx.send(_("The planner list is empty. Everyone can use the `think_and_plan` tool."))
            else:
                planners = [ctx.guild.get_member(i) or ctx.guild.get_role(i) for i in conf.planners]
                names = [i.display_name if isinstance(i, discord.Member) else i.name for i in planners if i]
                if names:
                    await ctx.send(_("**Planners:** {}").format(humanize_list(sorted(names))))
                else:
                    await ctx.send(_("The planner list has invalid entries. Consider clearing it."))
            return

        if role_or_member.id in conf.planners:
            conf.planners.remove(role_or_member.id)
            await ctx.send(_("{} has been removed from the planner list").format(role_or_member.name))
        else:
            conf.planners.append(role_or_member.id)
            await ctx.send(_("{} has been added to the planner list").format(role_or_member.name))
        await self.save_conf()

    @assistant.command(name="memories")
    async def view_memories(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = None,
    ):
        """
        View all stored user memories for this server.

        Shows what facts the assistant has remembered about users.

        Optionally specify a member to view only their memories.
        If the output is too long, it will be sent as a file.
        """
        guild = ctx.guild
        memories: list[tuple[int, list[str], datetime]] = []

        for key, mem in self.db.user_memories.items():
            if mem.guild_id != guild.id or not mem.facts:
                continue
            if member and mem.user_id != member.id:
                continue
            memories.append((mem.user_id, mem.facts, mem.updated_at))

        if not memories:
            target = f" for {member.display_name}" if member else ""
            return await ctx.send(_("No stored memories{}.").format(target))

        lines: list[str] = []
        total_facts = 0
        for user_id, facts, updated_at in sorted(memories, key=lambda x: x[0]):
            user = guild.get_member(user_id)
            name = f"{user.display_name} ({user_id})" if user else f"Unknown User ({user_id})"
            lines.append(f"## {name}")
            lines.append(f"*Last updated: <t:{int(updated_at.timestamp())}:R>*")
            for i, fact in enumerate(facts, 1):
                lines.append(f"{i}. {fact}")
                total_facts += 1
            lines.append("")

        header = _("**User Memories for {}** — {} user(s), {} fact(s)\n\n").format(
            guild.name, len(memories), total_facts
        )
        output = header + "\n".join(lines)

        if len(output) <= 2000:
            await ctx.send(output)
        else:
            pages = list(pagify(output, delims=["\n## ", "\n"], page_length=1900))
            if len(pages) <= 5:
                for page in pages:
                    await ctx.send(page)
            else:
                await ctx.send(
                    _("Output too long, sending as a file."),
                    file=text_to_file(output, filename="user_memories.md"),
                )

    @assistant.command(name="clearmemories")
    async def clear_memories(
        self,
        ctx: commands.Context,
        *,
        member: discord.Member = None,
    ):
        """
        Clear stored user memories for this server.

        Specify a member to clear only their memories, or omit to clear all memories for the server.
        """
        guild = ctx.guild
        keys_to_remove: list[str] = []

        for key, mem in self.db.user_memories.items():
            if mem.guild_id != guild.id:
                continue
            if member and mem.user_id != member.id:
                continue
            keys_to_remove.append(key)

        if not keys_to_remove:
            target = f" for {member.display_name}" if member else ""
            return await ctx.send(_("No stored memories{} to clear.").format(target))

        for key in keys_to_remove:
            del self.db.user_memories[key]

        await self.save_conf()

        if member:
            await ctx.send(_("Cleared {} memory entries for {}.").format(len(keys_to_remove), member.display_name))
        else:
            await ctx.send(_("Cleared all {} memory entries for this server.").format(len(keys_to_remove)))

    @assistant.group(name="override")
    async def override(self, ctx: commands.Context):
        """
        Override settings for specific roles

        **NOTE**
        If a user has two roles with override settings, override associated with the higher role will be used.
        """

    @override.command(name="model")
    async def model_role_override(self, ctx: commands.Context, model: str, *, role: discord.Role):
        """
        Assign a role to use a model

        *Specify same role and model to remove the override*
        """
        model = model.lower().strip()
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return

        if not model:
            return await ctx.send(_("Valid models are:\n{}").format(box(humanize_list(list(MODELS.keys)))))

        if conf.api_key and "deepseek" not in model and not self.db.endpoint_override:
            try:
                client = openai.AsyncOpenAI(api_key=conf.api_key)
                await client.models.retrieve(model)
            except openai.NotFoundError as e:
                txt = _("Error: {}").format(e.response.json()["error"]["message"])
                return await ctx.send(txt)

        if role.id in conf.role_overrides:
            if conf.role_overrides[role.id] == model:
                del conf.role_overrides[role.id]
                await ctx.send(_("Role override for {} removed!").format(role.mention))
            else:
                conf.role_overrides[role.id] = model
                await ctx.send(_("Role override for {} overwritten!").format(role.mention))
        else:
            conf.role_overrides[role.id] = model
            await ctx.send(_("Role override for {} added!").format(role.mention))

        await self.save_conf()

    @override.command(name="maxtokens")
    async def max_token_override(self, ctx: commands.Context, max_tokens: int, *, role: discord.Role):
        """
        Assign a max token override to a role

        *Specify same role and token count to remove the override*
        """
        conf = self.db.get_conf(ctx.guild)

        if role.id in conf.max_token_role_override:
            if conf.max_token_role_override[role.id] == max_tokens:
                del conf.max_token_role_override[role.id]
                await ctx.send(_("Max token override for {} removed!").format(role.mention))
            else:
                conf.max_token_role_override[role.id] = max_tokens
                await ctx.send(_("Max token override for {} overwritten!").format(role.mention))
        else:
            conf.max_token_role_override[role.id] = max_tokens
            await ctx.send(_("Max token override for {} added!").format(role.mention))

        await self.save_conf()

    @override.command(name="maxresponsetokens")
    async def max_response_token_override(
        self, ctx: commands.Context, max_tokens: commands.positive_int, *, role: discord.Role
    ):
        """
        Assign a max response token override to a role

        Set to 0 for response tokens to be dynamic

        *Specify same role and token count to remove the override*
        """
        conf = self.db.get_conf(ctx.guild)

        if role.id in conf.max_response_token_override:
            if conf.max_response_token_override[role.id] == max_tokens:
                del conf.max_response_token_override[role.id]
                await ctx.send(_("Max response token override for {} removed!").format(role.mention))
            else:
                conf.max_response_token_override[role.id] = max_tokens
                await ctx.send(_("Max response token override for {} overwritten!").format(role.mention))
        else:
            conf.max_response_token_override[role.id] = max_tokens
            await ctx.send(_("Max response token override for {} added!").format(role.mention))
        await self.save_conf()

    @override.command(name="maxretention")
    async def max_retention_override(self, ctx: commands.Context, max_retention: int, *, role: discord.Role):
        """
        Assign a max message retention override to a role

        *Specify same role and retention amount to remove the override*
        """
        if max_retention < 0:
            return await ctx.send(_("Max retention needs to be at least 0 or higher"))
        conf = self.db.get_conf(ctx.guild)

        if role.id in conf.max_retention_role_override:
            if conf.max_retention_role_override[role.id] == max_retention:
                del conf.max_retention_role_override[role.id]
                await ctx.send(_("Max retention override for {} removed!").format(role.mention))
            else:
                conf.max_retention_role_override[role.id] = max_retention
                await ctx.send(_("Max retention override for {} overwritten!").format(role.mention))
        else:
            conf.max_retention_role_override[role.id] = max_retention
            await ctx.send(_("Max retention override for {} added!").format(role.mention))
        await self.save_conf()

    @override.command(name="maxtime")
    async def max_time_override(self, ctx: commands.Context, retention_seconds: int, *, role: discord.Role):
        """
        Assign a max retention time override to a role

        *Specify same role and time to remove the override*
        """
        if retention_seconds < 0:
            return await ctx.send(_("Max retention time needs to be at least 0 or higher"))
        conf = self.db.get_conf(ctx.guild)

        if role.id in conf.max_time_role_override:
            if conf.max_time_role_override[role.id] == retention_seconds:
                del conf.max_time_role_override[role.id]
                await ctx.send(_("Max retention time override for {} removed!").format(role.mention))
            else:
                conf.max_time_role_override[role.id] = retention_seconds
                await ctx.send(_("Max retention time override for {} overwritten!").format(role.mention))
        else:
            conf.max_time_role_override[role.id] = retention_seconds
            await ctx.send(_("Max retention time override for {} added!").format(role.mention))
        await self.save_conf()

    @assistant.command(name="verbosity")
    async def switch_verbosity(self, ctx: commands.Context):
        """
        Switch verbosity level for gpt-5 model between low, medium, and high

        This setting is exclusive to the gpt-5 model and affects how detailed the model's responses are.
        """
        conf = self.db.get_conf(ctx.guild)
        if conf.verbosity == "low":
            conf.verbosity = "medium"
            await ctx.send(_("Verbosity has been set to **Medium**"))
        elif conf.verbosity == "medium":
            conf.verbosity = "high"
            await ctx.send(_("Verbosity has been set to **High**"))
        else:
            conf.verbosity = "low"
            await ctx.send(_("Verbosity has been set to **Low**"))
        await self.save_conf()

    # --------------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------------
    # -------------------------------- OWNER ONLY ------------------------------------------
    # --------------------------------------------------------------------------------------
    # --------------------------------------------------------------------------------------

    @assistant.command(name="endpointoverride")
    @commands.is_owner()
    async def endpoint_override(self, ctx: commands.Context, endpoint: str = None):
        """
        Override the OpenAI endpoint

        **Notes**
        - Using a custom endpoint is not supported!
        - Using an endpoing override will negate model settings like temperature and custom functions
        """
        if self.db.endpoint_override == endpoint:
            return await ctx.send(_("Endpoint is already set to **{}**").format(endpoint))
        if endpoint and not self.db.endpoint_override:
            self.db.endpoint_override = endpoint
            await ctx.send(_("Endpoint has been set to **{}**").format(endpoint))
        elif endpoint and self.db.endpoint_override:
            old = self.db.endpoint_override
            self.db.endpoint_override = endpoint
            await ctx.send(_("Endpoint has been changed from **{}** to **{}**").format(old, endpoint))
        else:
            self.db.endpoint_override = None
            await ctx.send(_("Endpoint override has been removed!"))

    @assistant.command(name="wipecog")
    @commands.is_owner()
    async def wipe_cog(self, ctx: commands.Context, confirm: bool):
        """Wipe all settings and data for entire cog"""
        if not confirm:
            return await ctx.send(_("Not wiping cog"))
        self.db.configs.clear()
        self.db.conversations.clear()
        self.db.persistent_conversations = False
        await self.save_conf()
        await ctx.send(_("Cog has been wiped!"))

    @assistant.command(name="backupcog")
    @commands.is_owner()
    async def backup_cog(self, ctx: commands.Context):
        """
        Take a backup of the cog

        - This does not backup conversation data
        """

        def _dump():
            # Delete and convo data
            self.db.conversations.clear()
            return self.db.json()

        dump = await asyncio.to_thread(_dump)

        buffer = BytesIO(dump.encode())
        buffer.name = f"Assistant_{int(datetime.now().timestamp())}.json"
        buffer.seek(0)
        file = discord.File(buffer)
        try:
            await ctx.send(_("Here is your export!"), file=file)
            return
        except discord.HTTPException:
            await ctx.send(_("File too large, attempting to compress..."))

        def zip_file() -> discord.File:
            zip_buffer = BytesIO()
            zip_buffer.name = f"Assistant_{int(datetime.now().timestamp())}.json"
            with ZipFile(zip_buffer, "w", compression=ZIP_DEFLATED, compresslevel=9) as arc:
                arc.writestr(
                    "embeddings_export.json",
                    dump,
                    compress_type=ZIP_DEFLATED,
                    compresslevel=9,
                )
            zip_buffer.seek(0)
            file = discord.File(zip_buffer)
            return file

        file = await asyncio.to_thread(zip_file)
        try:
            await ctx.send(_("Here is your embeddings export!"), file=file)
            return
        except discord.HTTPException:
            await ctx.send(_("File is still too large even with compression!"))

    @assistant.command(name="restorecog")
    @commands.is_owner()
    async def restore_cog(self, ctx: commands.Context):
        """
        Restore the cog from a backup
        """
        attachments = get_attachments(ctx.message)
        if not attachments:
            return await ctx.send(
                _("You must attach **.json** files to this command or reference a message that has them!")
            )
        dump = await attachments[0].read()
        self.db = await asyncio.to_thread(DB.parse_raw, dump)
        await ctx.send(_("Cog has been restored!"))
        await self.save_conf()

    @assistant.command(name="resetglobalconversations")
    @commands.is_owner()
    async def wipe_global_conversations(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved conversations for the assistant in all servers

        This will delete any and all saved conversations for the assistant.
        """
        if not yes_or_no:
            return await ctx.send(_("Not wiping conversations"))
        for convo in self.db.conversations.values():
            convo.messages.clear()
        await ctx.send(_("Conversations have been wiped for all servers!"))
        await self.save_conf()

    @assistant.command(name="persist")
    @commands.is_owner()
    async def toggle_persistent_conversations(self, ctx: commands.Context):
        """Toggle persistent conversations"""
        if self.db.persistent_conversations:
            self.db.persistent_conversations = False
            await ctx.send(_("Persistent conversations have been **Disabled**"))
        else:
            self.db.persistent_conversations = True
            await ctx.send(_("Persistent conversations have been **Enabled**"))
        await self.save_conf()

    @assistant.command(name="resetglobalembeddings")
    @commands.is_owner()
    async def wipe_global_embeddings(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved embeddings for all servers

        This will delete any and all saved embedding training data for the assistant.
        """
        if not yes_or_no:
            return await ctx.send(_("Not wiping embedding data"))
        for guild_id, conf in self.db.configs.items():
            conf.embeddings = {}  # Clear any leftover migration data
            await self.embedding_store.delete_all(guild_id)
        await ctx.send(_("All embedding data has been wiped for all servers!"))
        await self.save_conf()

    @assistant.command(name="listentobots", aliases=["botlisten", "ignorebots"])
    @commands.is_owner()
    async def toggle_bot_listen(self, ctx: commands.Context):
        """
        Toggle whether the assistant listens to other bots

        **NOT RECOMMENDED FOR PUBLIC BOTS!**
        """
        if self.db.listen_to_bots:
            self.db.listen_to_bots = False
            await ctx.send(_("Assistant will no longer listen to other bot messages"))
        else:
            self.db.listen_to_bots = True
            await ctx.send(_("Assistant will listen to other bot messages"))
        await self.save_conf()
