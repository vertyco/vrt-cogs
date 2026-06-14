import asyncio
import contextlib
import logging
import re
import traceback
import typing as t
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Union
from urllib.parse import urlparse
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
from redbot.core.utils.views import SimpleMenu

from ..abc import MixinMeta
from ..common.calls import (
    get_client,
    request_chat_completion_raw,
    request_embedding_raw,
)
from ..common.constants import (
    DEFAULT_MOD_PROMPT,
    MAX_SKILL_BODY,
    MOD_CATEGORY_DEFAULTS,
    MODELS,
    OR_SUFFIXES,
    get_min_cache_tokens,
)
from ..common.models import (
    DB,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_THINK_TAG_PREFIX,
    DEFAULT_THINK_TAG_SUFFIX,
    GuildSettings,
    RolePrompt,
    get_category_state,
    render_tool_category,
)
from ..common.utils import (
    DYNAMIC_VARIABLE_NAMES,
    MAX_TRIGGER_LEN,
    get_attachments,
    normalize_skill_name,
    wildcard_to_regex,
)
from ..views import (
    AIToolsView,
    CodeMenu,
    EmbeddingMenu,
    FloatingContextView,
    ModelPickerView,
    SetAPI,
    SkillMenuView,
)

log = logging.getLogger("red.vrt.assistant.admin")
_ = Translator("Assistant", __file__)
ON_STATUS_EMOJI = "🟢"
OFF_STATUS_EMOJI = "🔴"
SKILL_AUDIT_PROMPT = (
    "You are auditing the stored skills of a Discord assistant bot. For each skill below, flag:\n"
    "1. OVERLAP: skills whose descriptions or bodies cover the same ground and should merge\n"
    "2. STALE: skills unused for a long time relative to their age (timestamps provided)\n"
    "3. CONFLICT: skills whose procedures contradict each other\n"
    "4. QUALITY: vague descriptions (the model won't know when to load them) or bodies that "
    "are not actionable step-by-step procedures\n"
    "Be terse. Output one section per finding with the skill name(s), the problem, and a concrete fix. "
    "If everything is fine say so in one line."
)
MIXED_STATUS_EMOJI = "🟡"
STATUS_EMOJIS = {
    "on": ON_STATUS_EMOJI,
    "off": OFF_STATUS_EMOJI,
    "mixed": MIXED_STATUS_EMOJI,
}
THIRD_PARTY_DOCS_URL = "https://github.com/vertyco/vrt-cogs/blob/main/assistant/THIRD%20PARTY.md"


def normalize_endpoint_override(
    endpoint: t.Optional[str],
) -> tuple[t.Optional[str], t.Optional[str]]:
    if endpoint is None:
        return None, None

    normalized = endpoint.strip().rstrip("/")
    parsed = urlparse(normalized)

    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None, _(
            "Endpoint override must be a full base URL, for example `http://127.0.0.1:1234/v1` or `https://example.com/api/v1`."
        )

    if not parsed.path.endswith("/v1"):
        return None, _(
            "Endpoint override must point at the OpenAI-compatible API base path ending in `/v1`. "
            "Do not include routes like `/chat/completions` or `/models`."
        )

    return normalized, None


def format_think_tag(tag: str) -> str:
    return tag.encode("unicode_escape").decode("ascii") or _("Empty")


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

    # ---- Group definitions (must be before any subcommand references) ----
    @assistant.group(name="api")
    async def api(self, ctx: commands.Context):
        """Manage API keys and endpoint URLs"""
        pass

    @api.group(name="guild")
    async def api_guild(self, ctx: commands.Context):
        """Per-guild endpoint and key overrides (chat + embeddings)"""
        pass

    @assistant.group(name="set", aliases=["settings"])
    async def asettings(self, ctx: commands.Context):
        """Configure general guild settings"""
        pass

    @assistant.group(name="prompt")
    async def prompt(self, ctx: commands.Context):
        """Configure assistant prompts"""
        pass

    @assistant.group(name="features")
    async def features(self, ctx: commands.Context):
        """Configure feature toggles"""
        pass

    @assistant.group(name="autoanswer", aliases=["autoanswers"])
    async def autoanswer(self, ctx: commands.Context):
        """Configure auto-answer settings"""
        pass

    @assistant.group(name="trigger")
    async def trigger(self, ctx: commands.Context):
        """Configure trigger phrase system"""
        pass

    @assistant.group(name="filter")
    async def afilter(self, ctx: commands.Context):
        """Configure content filtering"""
        pass

    @assistant.group(name="limits")
    async def limits(self, ctx: commands.Context):
        """Configure token and retention limits"""
        pass

    @assistant.group(name="params", aliases=["parameters"])
    async def params(self, ctx: commands.Context):
        """Configure model behavior parameters"""
        pass

    @assistant.group(name="embed", aliases=["embeddings"])
    async def embed(self, ctx: commands.Context):
        """Configure embeddings and RAG settings"""
        pass

    @assistant.group(name="admin")
    async def assistant_admin(self, ctx: commands.Context):
        """Admin maintenance commands"""
        pass

    @assistant.group(name="openroutercache", aliases=["orcache"])
    @commands.admin_or_permissions(administrator=True)
    async def openrouter_cache(self, ctx: commands.Context):
        """Configure OpenRouter response & prompt caching."""
        pass

    @assistant.group(name="override")
    async def override(self, ctx: commands.Context):
        """Manage role-based overrides"""
        pass

    @assistant.group(name="scheduler", aliases=["tasks"])
    async def scheduler(self, ctx: commands.Context):
        """Manage scheduled autonomous tasks"""
        pass

    @assistant.group(name="compaction")
    async def compaction(self, ctx: commands.Context):
        """Configure conversation compaction"""
        pass

    @assistant.group(name="smartmod", aliases=["automod"])
    async def smartmod(self, ctx: commands.Context):
        """AI moderation: scan messages, review flagged ones, and propose staff actions."""
        pass

    @assistant.group(name="skills", aliases=["skill"])
    async def skills_group(self, ctx: commands.Context):
        """Manage on-demand skills (stored procedures the AI can load and propose)"""
        pass

    # ---- Helper methods ----

    def get_tool_catalog(self) -> list[dict]:
        catalog = self.db.get_function_catalog(self.bot, self.registry)
        return sorted(catalog, key=lambda entry: (entry["category"], entry["name"].lower()))

    def get_tool_categories(self) -> dict[str, list[dict]]:
        grouped = self.db.get_functions_by_category(self.bot, self.registry)
        return {
            category: sorted(entries, key=lambda entry: entry["name"].lower())
            for category, entries in sorted(grouped.items(), key=lambda item: item[0])
        }

    def get_context_variable_catalog(self) -> list[dict]:
        catalog = self.db.get_context_variable_catalog(self.bot, self.context_registry)
        return sorted(catalog, key=lambda entry: (entry["source"], entry["name"].lower()))

    async def retry_discord_server_error(self, operation: t.Callable[[], t.Awaitable[t.Any]]):
        last_error = None
        for attempt in range(3):
            try:
                return await operation()
            except discord.DiscordServerError as error:
                last_error = error
                if attempt == 2:
                    break
                await asyncio.sleep(attempt + 1)
        if last_error is not None:
            raise last_error

    def format_endpoint_model_box(self, model_ids: List[str], active_model: str = "") -> str:
        ordered = [active_model] if active_model and active_model in model_ids else []
        ordered.extend(sorted(model_id for model_id in model_ids if model_id != active_model))
        lines = []
        for model_id in ordered[:20]:
            label = f"{model_id} (active)" if model_id == active_model else model_id
            lines.append(label)
        if len(ordered) > 20:
            lines.append(_("... and {} more").format(len(ordered) - 20))
        return box("\n".join(lines))

    async def describe_endpoint_chat_model_options(
        self,
        ctx: commands.Context,
        configured_model: str,
        configured_label: t.Optional[str] = None,
        conf: t.Optional[GuildSettings] = None,
    ) -> str:
        profile = await self.refresh_endpoint_profile(conf)
        label = configured_label or _("Configured chat model")
        lines = [_("{}: **{}**").format(label, configured_model)]
        if not profile:
            lines.append(
                _(
                    "No endpoint model cache is available yet. Run `{}` to refresh it, or enter a model id manually."
                ).format(f"{ctx.clean_prefix}assist endpointprobe")
            )
            return "\n".join(lines)

        if profile.active_chat_model:
            lines.append(_("Runtime chat model: **{}**").format(profile.active_chat_model))

        chat_models = list(profile.chat_models)
        if chat_models:
            lines.append(
                _("Discovered chat models:\n{}").format(
                    self.format_endpoint_model_box(chat_models, profile.active_chat_model)
                )
            )
        else:
            lines.append(
                _("No chat models were discovered from this endpoint yet. You can still enter a model id manually.")
            )

        lines.append(
            _(
                "Use this command again with one of these model ids, or enter another id manually if your endpoint supports it."
            )
        )
        return "\n".join(lines)

    async def describe_endpoint_embedding_model_options(
        self, ctx: commands.Context, configured_model: str, conf: t.Optional[GuildSettings] = None
    ) -> str:
        profile = await self.refresh_endpoint_profile(conf)
        lines = [_("Configured embedding model: **{}**").format(configured_model)]
        if not profile:
            lines.append(
                _(
                    "No endpoint model cache is available yet. Run `{}` to refresh it, or enter a model id manually."
                ).format(f"{ctx.clean_prefix}assist endpointprobe")
            )
            return "\n".join(lines)

        if profile.active_embedding_model:
            lines.append(_("Runtime embedding model: **{}**").format(profile.active_embedding_model))

        embedding_models = list(profile.embedding_models)
        if embedding_models:
            lines.append(
                _("Discovered embedding models:\n{}").format(
                    self.format_endpoint_model_box(embedding_models, profile.active_embedding_model)
                )
            )
        else:
            lines.append(
                _(
                    "No embedding models were discovered from this endpoint yet. You can still enter a model id manually."
                )
            )

        lines.append(
            _(
                "Use this command again with one of these model ids, or enter another id manually if your endpoint supports it."
            )
        )
        return "\n".join(lines)

    async def get_endpoint_model_warning(
        self, model: str, embedding: bool = False, conf: t.Optional[GuildSettings] = None
    ) -> t.Optional[str]:
        profile = await self.refresh_endpoint_profile(conf)
        if not profile:
            return None

        discovered = profile.embedding_models if embedding else profile.chat_models
        kind = _("embedding") if embedding else _("chat")
        resolved_model = (
            self.resolve_embedding_model(model, conf) if embedding else self.resolve_chat_model(model, conf)
        )

        if profile.provider == "openrouter" and not embedding:
            if model.lower().startswith("openrouter/"):
                return None
            # Suppress warning when the model has a known OR suffix but the base is discovered.
            base = model
            for sfx in OR_SUFFIXES:
                if base.endswith(sfx):
                    base = base[: -len(sfx)]
                    break
            if base in discovered:
                return None

        if discovered and model not in discovered:
            if resolved_model and resolved_model != model:
                return _(
                    "Note: `{}` is not in the endpoint's discovered {} model list. Requests on this endpoint will automatically use `{}` instead."
                ).format(model, kind, resolved_model)
            return _(
                "Note: `{}` is not in the endpoint's discovered {} model list. The cog will still try to use it directly, but the endpoint may reject it."
            ).format(model, kind)
        return None

    async def get_embedding_model_dimensions(self, model: str, conf: GuildSettings) -> t.Optional[int]:
        try:
            response = await request_embedding_raw(
                text="ping",
                api_key=self.get_api_key(conf),
                model=model,
                base_url=self.get_guild_endpoint_url(conf),
            )
        except Exception as e:
            log.debug("Failed to probe embedding dimensions for %s", model, exc_info=e)
            return None

        if not response.data:
            return None

        dimensions = len(response.data[0].embedding)
        observed_model = response.model or model
        self.observe_embedding_runtime(observed_model, dimensions, conf)
        return dimensions

    async def get_embedding_dimension_sync_warning(
        self,
        guild: discord.Guild,
        model: str,
        conf: GuildSettings,
        prefix: str,
    ) -> t.Optional[str]:
        all_meta = await self.embedding_store.get_all_metadata(guild.id)
        stored_dimensions = sorted(
            {
                int(meta.get("dimensions", 0) or 0)
                for meta in all_meta.values()
                if int(meta.get("dimensions", 0) or 0) > 0
            }
        )
        if not stored_dimensions:
            return None

        sync_command = f"{prefix}assistant embed refresh"
        if len(stored_dimensions) > 1:
            dims_display = humanize_list([humanize_number(dimension) for dimension in stored_dimensions])
            return _(
                "Warning: stored embeddings currently use mixed dimensions ({}). Run `{}` to resync them with `{}`."
            ).format(dims_display, sync_command, model)

        new_dimensions = await self.get_embedding_model_dimensions(model, conf)
        if not new_dimensions:
            return None

        stored_dimension = stored_dimensions[0]
        if new_dimensions == stored_dimension:
            return None

        return _(
            "Warning: stored embeddings are `{}` dimensions, but `{}` returns `{}` dimensions. Run `{}` to resync them after switching models."
        ).format(
            humanize_number(stored_dimension),
            model,
            humanize_number(new_dimensions),
            sync_command,
        )

    async def get_embedding_model_change_notice(
        self,
        guild: discord.Guild,
        model: str,
        conf: GuildSettings,
        prefix: str,
    ) -> t.Optional[str]:
        notices: list[str] = []
        endpoint_warning = await self.get_endpoint_model_warning(model, embedding=True, conf=conf)
        if endpoint_warning:
            notices.append(endpoint_warning)
        effective_model = self.resolve_embedding_model(model, conf)
        dimension_warning = await self.get_embedding_dimension_sync_warning(guild, effective_model, conf, prefix)
        if dimension_warning:
            notices.append(dimension_warning)
        if not notices:
            return None
        return "\n".join(notices)

    @assistant.command(name="view", aliases=["v"])
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context, private: bool = False):
        """
        View current settings

        To send in current channel, use `[p]assistant view false`
        """
        send_key = [
            ctx.guild.owner_id == ctx.author.id,
            ctx.author.id in self.bot.owner_ids,
        ]

        conf = self.db.get_conf(ctx.guild)
        model = conf.get_user_model(ctx.author)
        effective_model = self.resolve_chat_model(conf.model, conf)
        effective_embed_model = self.resolve_embedding_model(conf.embed_model, conf)
        effective_system_prompt = self.db.get_effective_system_prompt(conf)
        system_tokens = await self.count_tokens(effective_system_prompt, model) if effective_system_prompt else 0
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
            + _("`Endpoint Override:   `{}\n").format(self.db.endpoint_override or _("Not set"))
            + _("`Guild Endpoint:      `{}\n").format(conf.endpoint_override or _("Not set"))
        )

        if effective_model != conf.model:
            desc += _("`Effective Model:     `{}\n").format(effective_model)
        if effective_embed_model != conf.embed_model:
            desc += _("`Effective Embed:     `{}\n").format(effective_embed_model)

        embed = discord.Embed(
            title=_("Assistant Settings"),
            description=desc,
            color=ctx.author.color,
        )

        effective_endpoint = conf.endpoint_override or self.db.endpoint_override
        if effective_endpoint:
            profile = await self.refresh_endpoint_profile(conf)
            if profile:
                embed.add_field(
                    name=_("Endpoint Runtime"),
                    value=self.describe_endpoint_profile(profile),
                    inline=False,
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

        name = _("Think Tags")
        val = _("Reasoning blocks wrapped in these tags are removed from chat output.\n")
        val += _("`Upload as Files:`{}\n").format(_("Enabled") if self.db.reasoning_as_files else _("Disabled"))
        val += _("Prefix\n{}\nSuffix\n{}").format(
            box(format_think_tag(conf.think_tag_prefix)),
            box(format_think_tag(conf.think_tag_suffix)),
        )
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

        # Dynamic variable warning: any prompt containing dynamic-variable
        # placeholders bypasses cache-safe mode and breaks prompt prefix
        # caching on every request.
        def find_dyn_vars(text: t.Optional[str]) -> list[str]:
            if not text:
                return []
            return sorted({name for name in DYNAMIC_VARIABLE_NAMES if "{" + name + "}" in text})

        warning_lines: list[str] = []
        sys_vars = find_dyn_vars(conf.system_prompt)
        if sys_vars:
            warning_lines.append(_("• System prompt - `{}`").format(", ".join(sys_vars)))
        init_vars = find_dyn_vars(conf.prompt)
        if init_vars:
            warning_lines.append(_("• Initial prompt - `{}`").format(", ".join(init_vars)))
        for channel_id, channel_prompt in conf.channel_prompts.items():
            chan_vars = find_dyn_vars(channel_prompt)
            if not chan_vars:
                continue
            warning_lines.append(_("• <#{}> - `{}`").format(channel_id, ", ".join(chan_vars)))
        for role_id, role_prompt in conf.role_prompts.items():
            role_vars = find_dyn_vars(role_prompt.text)
            if not role_vars:
                continue
            warning_lines.append(_("• <@&{}> role prompt - `{}`").format(role_id, ", ".join(role_vars)))
        if warning_lines:
            embed.add_field(
                name=_("⚠️ Cache Warning"),
                value=_(
                    "These prompts contain dynamic variable placeholders that break prompt prefix caching on every "
                    "request. Use `{prefix}floatingcontext` to move them to the floating context block instead.\n"
                ).format(prefix=ctx.clean_prefix)
                + "\n".join(warning_lines[:10]),
                inline=False,
            )

        # OpenRouter cache settings (only shown if endpoint override is set)
        effective_endpoint = conf.endpoint_override or self.db.endpoint_override
        if effective_endpoint and "openrouter.ai" in effective_endpoint.lower():
            cache_state = (
                _("Enabled ({}s TTL)").format(conf.openrouter_cache_ttl)
                if conf.openrouter_cache_enabled
                else _("Disabled")
            )
            prompt_cache_label = {
                "off": _("Off"),
                "5m": _("5 minutes"),
                "1h": _("1 hour"),
            }.get(conf.openrouter_prompt_cache_ttl, conf.openrouter_prompt_cache_ttl)
            embed.add_field(
                name=_("OpenRouter Caching"),
                value=(
                    _("`Response Cache:        `{}\n").format(cache_state)
                    + _("`Provider Prompt Cache: `{}\n").format(prompt_cache_label)
                ),
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
            + _("`Encodings:         `{}").format(encoded_by)
        )
        embed_num = humanize_number(len(all_meta))
        embed.add_field(
            name=_("Embeddings ({})").format(embed_num),
            value=embedding_field,
            inline=False,
        )
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

        threshold_display = humanize_number(conf.compaction_threshold) if conf.compaction_threshold else _("Max tokens")
        compaction_field = (
            _("`Compaction:        `{}\n").format(_("Enabled") if conf.compaction_enabled else _("Disabled"))
            + _("`Compaction Model:  `{}\n").format(conf.compaction_model or _("Same as chat"))
            + _("`Threshold:         `{}\n").format(threshold_display)
        )
        embed.add_field(name=_("Context Compaction"), value=compaction_field, inline=False)

        if private and any(send_key):
            embed.add_field(
                name=_("API Key"),
                value=box(conf.api_key) if conf.api_key else _("Not Set"),
                inline=False,
            )

        if private and ctx.author.id in self.bot.owner_ids:
            embed.add_field(
                name=_("Endpoint Override API Key"),
                value=box(self.db.endpoint_api_key) if self.db.endpoint_api_key else _("Not Set"),
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
                    embed.add_field(
                        name=_("Max Message Retention Role Overrides"),
                        value=field,
                        inline=False,
                    )

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
                    embed.add_field(
                        name=_("Max Response Token Role Overrides"),
                        value=field,
                        inline=False,
                    )

            if overrides := conf.reasoning_effort_role_override:
                field = ""
                roles = {ctx.guild.get_role(k): v for k, v in overrides.copy().items() if ctx.guild.get_role(k)}
                sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
                for role, effort in sorted_roles:
                    if not role:
                        continue
                    field += f"{role.mention}: `{effort}`\n"
                if field:
                    embed.add_field(
                        name=_("Reasoning Effort Role Overrides"),
                        value=field,
                        inline=False,
                    )

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
                BytesIO(effective_system_prompt.encode()),
                filename=_("SystemPrompt") + ".txt",
            )
            if effective_system_prompt
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

    @api.command(name="key", aliases=["openai", "apikey"])
    @commands.bot_has_permissions(embed_links=True)
    async def api_openai(self, ctx: commands.Context):
        """
        Set this server's API key

        Used for all requests from this guild - whether routing to OpenAI
        directly, the guild's endpoint override, or the global endpoint
        override. If not set, the global endpoint key is used as a fallback.
        """
        conf = self.db.get_conf(ctx.guild)

        view = SetAPI(ctx.author, conf.api_key)
        txt = _("Click to set this server's API key\n\nTo remove your key, enter `none`")
        embed = discord.Embed(description=txt, color=ctx.author.color)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip() if view.key else "none"

        try:
            if key == "none" and conf.api_key:
                conf.api_key = None
                await msg.edit(content=_("API key has been removed!"), embed=None, view=None)
            elif key == "none" and not conf.api_key:
                conf.api_key = key
                await msg.edit(content=_("No API key was entered!"), embed=None, view=None)
            else:
                conf.api_key = key
                await msg.edit(content=_("API key has been set!"), embed=None, view=None)
        except discord.NotFound:
            pass

        await self.save_conf()

    @api.command(name="brave")
    @commands.bot_has_permissions(embed_links=True)
    @commands.is_owner()
    async def api_brave(self, ctx: commands.Context):
        """
        Set the Brave Search API key (owner) - used by the web-search tool

        Get your API key **[here](https://brave.com/search/api/)**.
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

    @api.command(name="globalkey", aliases=["endpoint", "endpointkey"])
    @commands.bot_has_permissions(embed_links=True)
    @commands.is_owner()
    async def api_endpoint(self, ctx: commands.Context):
        """
        Set the global API key for the default endpoint override (owner)

        This key is only used when a global endpoint override is set
        (see `[p]assistant api globalendpoint`) and the requesting guild
        has not provided its own API key.
        """
        view = SetAPI(ctx.author, self.db.endpoint_api_key)
        txt = _("Click to set the API key used for the endpoint override\n\nTo remove the key, enter `none`")
        embed = discord.Embed(description=txt, color=ctx.author.color)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip() if view.key else "none"

        if key == "none" and self.db.endpoint_api_key:
            self.db.endpoint_api_key = None
            await msg.edit(
                content=_("Endpoint override API key has been removed!"),
                embed=None,
                view=None,
            )
        elif key == "none" and not self.db.endpoint_api_key:
            return await msg.edit(content=_("No API key was entered!"), embed=None, view=None)
        else:
            self.db.endpoint_api_key = key
            await msg.edit(
                content=_("Endpoint override API key has been set!"),
                embed=None,
                view=None,
            )

        await self.save_conf()

    @api_guild.command(name="endpoint")
    @commands.bot_has_permissions(embed_links=True)
    async def api_guild_endpoint(self, ctx: commands.Context, *, endpoint: str = None):
        """
        Set this guild's endpoint URL (used for both chat and embeddings)

        The endpoint must be a full base URL ending in `/v1`, for example:
        `https://openrouter.ai/api/v1`

        Set the API key for this endpoint with `[p]assistant api key`.

        After setting, use `[p]assistant set model` (no args) to open an
        interactive model picker. Router endpoints like OpenRouter also
        accept special aliases like `openrouter/auto` or `openrouter/free`.

        Run without arguments to view the current guild endpoint.
        Use `none` to remove the guild endpoint override.
        """
        conf = self.db.get_conf(ctx.guild)

        if endpoint is None:
            if conf.endpoint_override:
                embed = discord.Embed(
                    title=_("Guild Endpoint Override"),
                    description=_("Current endpoint: `{}`").format(conf.endpoint_override),
                    color=ctx.author.color,
                )
                if conf.endpoint_profile:
                    embed.add_field(
                        name=_("Endpoint Runtime"),
                        value=self.describe_endpoint_profile(conf.endpoint_profile),
                        inline=False,
                    )
                return await ctx.send(embed=embed)
            return await ctx.send(_("No guild endpoint override is set."))

        normalized = endpoint.strip().lower()
        if normalized == "none":
            if conf.endpoint_override:
                conf.endpoint_override = None
                conf.endpoint_profile = None
                await ctx.send(_("Guild endpoint override has been removed!"))
                await self.save_conf()
            else:
                await ctx.send(_("No guild endpoint override was set."))
            return

        url, error = normalize_endpoint_override(endpoint)
        if error:
            return await ctx.send(error)

        conf.endpoint_override = url
        conf.endpoint_profile = None
        await ctx.send(_("Guild endpoint override set to `{}`").format(url))
        await self.save_conf()

        # Try to probe the endpoint immediately
        async with ctx.typing():
            profile = await self.refresh_endpoint_profile(conf, force=True)
            if profile:
                txt = _("Endpoint probed successfully!\n{}").format(self.describe_endpoint_profile(profile))
                chat_warning = await self.get_endpoint_model_warning(conf.model, conf=conf)
                if chat_warning:
                    txt += f"\n\n\N{WARNING SIGN} {chat_warning}"
                embed_notice = await self.get_embedding_model_change_notice(
                    ctx.guild,
                    conf.embed_model,
                    conf,
                    ctx.clean_prefix,
                )
                if embed_notice:
                    txt += f"\n\n\N{WARNING SIGN} {embed_notice}"
                await ctx.send(txt)
            else:
                await ctx.send(
                    _(
                        "Could not probe the endpoint automatically. "
                        "You can still use it, but model discovery may be limited."
                    )
                )

    @api_guild.command(name="clear")
    async def api_guild_clear(self, ctx: commands.Context):
        """Clear this guild's endpoint override (URL and cached profile)"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.endpoint_override:
            return await ctx.send(_("No per-guild endpoint override is set."))
        conf.endpoint_override = None
        conf.endpoint_profile = None
        await ctx.send(_("Guild endpoint override has been cleared!"))
        await self.save_conf()

    @api_guild.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def api_guild_view(self, ctx: commands.Context):
        """Show this guild's API key and endpoint override status"""
        conf = self.db.get_conf(ctx.guild)
        embed = discord.Embed(
            title=_("Guild API Overrides"),
            color=ctx.author.color,
        )
        embed.add_field(
            name=_("Guild API Key"),
            value=_("Set") if conf.api_key else _("Not set (using global key)"),
            inline=False,
        )
        embed.add_field(
            name=_("Endpoint Override"),
            value=conf.endpoint_override or _("Not set (using global)"),
            inline=False,
        )
        if conf.endpoint_override and conf.endpoint_profile:
            embed.add_field(
                name=_("Endpoint Runtime"),
                value=self.describe_endpoint_profile(conf.endpoint_profile),
                inline=False,
            )
        await ctx.send(embed=embed)

    @asettings.command(name="timezone")
    async def set_timezone(self, ctx: commands.Context, timezone: str):
        """Set the timezone used for prompt placeholders"""
        timezone = timezone.lower()
        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            likely_match = sorted(
                pytz.common_timezones,
                key=lambda x: fuzz.ratio(timezone, x.lower()),
                reverse=True,
            )[0]
            return await ctx.send(_("Invalid Timezone, did you mean `{}`?").format(likely_match))
        time = datetime.now(tz).strftime("%I:%M %p")  # Convert to 12-hour format
        await ctx.send(_("Timezone set to **{}** (`{}`)").format(timezone, time))
        conf = self.db.get_conf(ctx.guild)
        conf.timezone = timezone
        await self.save_conf()

    @prompt.command(name="system", aliases=["sys"])
    async def prompt_system(self, ctx: commands.Context, *, system_prompt: str = None):
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
        - **activities**: the user's current Discord activities and statuses
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
        - **model**: the current chat model being used
        - **botowner**: the bot owner's name
        - **modelinfo**: bundled information about the current model/runtime
        - **prefix**: one active bot prefix for this server
        - **prefixes**: all active bot prefixes for this server
        - **uptime**: the bot's current uptime
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

    @prompt.command(name="defaultsystem")
    @commands.is_owner()
    async def prompt_default_system(self, ctx: commands.Context, *, system_prompt: str = None):
        """
        Set the global default system prompt used by servers that inherit the default prompt

        - Run without arguments to view the current global default prompt
        - Use `none` to reset to the built-in default prompt
        - Servers with a custom system prompt keep using their custom prompt
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
                log.error("Failed to parse default system prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return

        if system_prompt is None:
            current = self.db.default_system_prompt
            file = text_to_file(current, "DefaultSystemPrompt.txt")
            lines = [
                _("Current global default system prompt for servers using the default or an unset system prompt:"),
                _("Servers with a custom system prompt are unchanged."),
            ]
            if current == DEFAULT_SYSTEM_PROMPT:
                lines.append(_("This is currently using the built-in default prompt."))
            else:
                lines.append(_("This is currently using a custom default prompt."))
            return await ctx.send("\n".join(lines), file=file)

        normalized = system_prompt.strip()
        if not normalized:
            return await ctx.send(
                _("Please include a system prompt or .txt file, or use `none` to reset to the built-in default.")
            )

        if normalized.lower() == "none":
            self.db.default_system_prompt = DEFAULT_SYSTEM_PROMPT
            await ctx.send(
                _(
                    "The global default system prompt has been reset to the built-in default. "
                    "Servers using the default or an unset system prompt will use it immediately."
                )
            )
            await self.save_conf()
            return

        self.db.default_system_prompt = normalized
        await ctx.send(
            _(
                "The global default system prompt has been updated. "
                "Servers using the default or an unset system prompt will use it immediately."
            )
        )
        await self.save_conf()

    @prompt.command(name="initial", aliases=["pre"])
    async def prompt_initial(self, ctx: commands.Context, *, prompt: str = ""):
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
        - **activities**: the user's current Discord activities and statuses
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
        - **model**: the current chat model being used
        - **botowner**: the bot owner's name
        - **modelinfo**: bundled information about the current model/runtime
        - **prefix**: one active bot prefix for this server
        - **prefixes**: all active bot prefixes for this server
        - **uptime**: the bot's current uptime
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
        effective_system_prompt = self.db.get_effective_system_prompt(conf)
        stokens = await self.count_tokens(effective_system_prompt, model) if effective_system_prompt else 0
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

    @prompt.command(name="channelshow")
    @commands.bot_has_permissions(attach_files=True)
    async def prompt_channel_show(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.CurrentChannel,
    ):
        """Show the channel specific system prompt"""
        conf = self.db.get_conf(ctx.guild)
        if channel.id not in conf.channel_prompts:
            return await ctx.send(_("No channel prompt set for {}").format(channel.mention))
        f = text_to_file(conf.channel_prompts[channel.id], f"{channel.name}_prompt.txt")
        await ctx.send(file=f)

    @prompt.command(name="channelcustom")
    async def prompt_channel_custom(
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

    @prompt.group(name="role")
    async def prompt_role(self, ctx: commands.Context):
        """Configure per-role system prompts"""
        pass

    @prompt_role.command(name="set")
    async def prompt_role_set(
        self,
        ctx: commands.Context,
        role: discord.Role,
        *,
        text: t.Optional[str] = None,
    ):
        """
        Set the system prompt for a role

        Attach a `.txt` file or type the prompt inline, same as the system prompt.
        Role prompts support the same variable placeholders.
        """
        conf = self.db.get_conf(ctx.guild)
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                text = (await attachments[0].read()).decode()
            except Exception as e:
                await ctx.send(
                    _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                        attachments[0].filename, f"{ctx.clean_prefix}traceback"
                    )
                )
                log.error("Failed to parse role prompt", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return
        if not text:
            return await ctx.send_help()
        if role.id in conf.role_prompts:
            conf.role_prompts[role.id].text = text
            await ctx.send(_("Role prompt overwritten for {}!").format(role.mention))
        else:
            conf.role_prompts[role.id] = RolePrompt(text=text)
            await ctx.send(_("Role prompt set for {}!").format(role.mention))
        await self.save_conf()

    @prompt_role.command(name="clear", aliases=["delete", "remove"])
    async def prompt_role_clear(self, ctx: commands.Context, *, role: discord.Role):
        """Clear the prompt for a role"""
        conf = self.db.get_conf(ctx.guild)
        if role.id not in conf.role_prompts:
            return await ctx.send(_("No role prompt set for {}!").format(role.mention))
        del conf.role_prompts[role.id]
        await self.save_conf()
        await ctx.send(_("Role prompt cleared for {}!").format(role.mention))

    @prompt_role.command(name="stack")
    async def prompt_role_stack(self, ctx: commands.Context, *, role: discord.Role):
        """Toggle whether this role's prompt stacks on the base prompt or replaces it"""
        conf = self.db.get_conf(ctx.guild)
        if role.id not in conf.role_prompts:
            return await ctx.send(_("No role prompt set for {}!").format(role.mention))
        rp = conf.role_prompts[role.id]
        rp.replace = not rp.replace
        await self.save_conf()
        mode = _("replace the base prompt") if rp.replace else _("stack on the base prompt")
        await ctx.send(_("Role prompt for {} will now {}.").format(role.mention, mode))

    @prompt_role.command(name="stacktype")
    async def prompt_role_stacktype(self, ctx: commands.Context):
        """
        Toggle how multiple matched role prompts combine

        Stacked: all of a user's matched role prompts stack together.
        Highest: only the user's highest role prompt is used.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.role_prompts_stack = not conf.role_prompts_stack
        await self.save_conf()
        state = (
            _("stack all matched roles together")
            if conf.role_prompts_stack
            else _("use only the highest role")
        )
        await ctx.send(_("Role prompts will now {}.").format(state))

    @prompt_role.command(name="view", aliases=["list", "settings"])
    async def prompt_role_view(self, ctx: commands.Context):
        """View role prompt settings and all linked roles"""
        conf = self.db.get_conf(ctx.guild)
        stacktype = _("Stacked (all matched roles)") if conf.role_prompts_stack else _("Highest role only")
        roles = {ctx.guild.get_role(k): v for k, v in conf.role_prompts.items() if ctx.guild.get_role(k)}
        if roles:
            sorted_roles = sorted(roles.items(), key=lambda x: x[0].position, reverse=True)
            linked = "\n".join(
                f"{role.mention} - `{_('replace') if rp.replace else _('stack')}`" for role, rp in sorted_roles
            )
        else:
            linked = _("No role prompts set.")
        embed = discord.Embed(title=_("Role Prompts"), color=await ctx.embed_color())
        embed.add_field(name=_("Stack Type"), value=stacktype, inline=False)
        embed.add_field(name=_("Linked Roles"), value=linked, inline=False)
        await ctx.send(embed=embed)

    @prompt_role.command(name="show")
    @commands.bot_has_permissions(attach_files=True)
    async def prompt_role_show(self, ctx: commands.Context, *, role: discord.Role):
        """Show a role's prompt and its mode"""
        conf = self.db.get_conf(ctx.guild)
        if role.id not in conf.role_prompts:
            return await ctx.send(_("No role prompt set for {}!").format(role.mention))
        rp = conf.role_prompts[role.id]
        mode = _("replace") if rp.replace else _("stack")
        await ctx.send(
            _("Mode: **{}**").format(mode),
            file=text_to_file(rp.text, f"{role.name}_prompt.txt"),
        )

    @asettings.command(name="channel")
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

    @asettings.command(name="listen")
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

    @asettings.command(name="sysoverride")
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

    @features.command(name="enable")
    async def features_enable(self, ctx: commands.Context):
        """Toggle the assistant on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.enabled:
            conf.enabled = False
            await ctx.send(_("The assistant is now **Disabled**"))
        else:
            conf.enabled = True
            await ctx.send(_("The assistant is now **Enabled**"))
        await self.save_conf()

    @features.command(name="draw", aliases=["drawtoggle"])
    async def features_draw(self, ctx: commands.Context):
        """Toggle the draw command on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.image_command:
            conf.image_command = False
            await ctx.send(_("The draw command is now **Disabled**"))
        else:
            conf.image_command = True
            await ctx.send(_("The draw command is now **Enabled**"))
        await self.save_conf()

    @autoanswer.command(name="toggle")
    async def autoanswer_toggle(self, ctx: commands.Context):
        """Toggle the auto-answer feature on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.auto_answer:
            conf.auto_answer = False
            await ctx.send(_("Auto-answer has been **Disabled**"))
        else:
            conf.auto_answer = True
            await ctx.send(_("Auto-answer has been **Enabled**"))
        await self.save_conf()

    @autoanswer.command(name="threshold")
    async def autoanswer_threshold(self, ctx: commands.Context, threshold: float):
        """Set the auto-answer threshold for the bot"""
        conf = self.db.get_conf(ctx.guild)
        conf.auto_answer_threshold = threshold
        await ctx.send(_("Auto-answer threshold has been set to **{}**").format(threshold))
        await self.save_conf()

    @autoanswer.command(name="ignore")
    async def autoanswer_ignore(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | discord.CategoryChannel | int,
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

    @autoanswer.command(name="model")
    async def autoanswer_model(self, ctx: commands.Context, model: str = None):
        """Set the model used for auto-answer"""
        model = model.lower().strip() if model else None
        conf = self.db.get_conf(ctx.guild)
        has_endpoint = bool(self.db.endpoint_override or conf.endpoint_override)
        if not model:
            if has_endpoint:
                return await ctx.send(
                    await self.describe_endpoint_chat_model_options(
                        ctx, conf.auto_answer_model, _("Configured auto-answer model"), conf=conf
                    )
                )
            return await ctx.send(_("Valid models are:\n{}").format(box(humanize_list(list(MODELS.keys())))))
        if not has_endpoint and model not in MODELS:
            return await ctx.send(_("Invalid model, valid models are: {}").format(humanize_list(MODELS)))
        conf.auto_answer_model = model
        await ctx.send(_("Auto-answer model has been set to **{}**").format(model))
        if has_endpoint:
            warning = await self.get_endpoint_model_warning(model, conf=conf)
            if warning:
                await ctx.send(warning)
        await self.save_conf()

    @trigger.command(name="toggle")
    async def trigger_toggle(self, ctx: commands.Context):
        """Toggle the trigger word feature on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.trigger_enabled:
            conf.trigger_enabled = False
            await ctx.send(_("Trigger word feature has been **Disabled**"))
        else:
            conf.trigger_enabled = True
            await ctx.send(_("Trigger word feature has been **Enabled**"))
        await self.save_conf()

    @trigger.command(name="phrase")
    async def trigger_phrase(self, ctx: commands.Context, *, phrase: str):
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

    @trigger.command(name="prompt")
    async def trigger_prompt(self, ctx: commands.Context, *, prompt: str = None):
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
        - **activities**: the user's current Discord activities and statuses
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
        - **model**: the current chat model being used
        - **botowner**: the bot owner's name
        - **modelinfo**: bundled information about the current model/runtime
        - **prefix**: one active bot prefix for this server
        - **prefixes**: all active bot prefixes for this server
        - **uptime**: the bot's current uptime
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

    @trigger.command(name="ignore")
    async def trigger_ignore(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | discord.CategoryChannel | int,
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

    @trigger.command(name="list")
    @commands.bot_has_permissions(embed_links=True)
    async def trigger_list(self, ctx: commands.Context):
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

    @asettings.command(name="thinkprefix")
    async def set_think_prefix(self, ctx: commands.Context, *, prefix: str = None):
        """
        Set the prefix used to detect model thinking blocks

        Omit the value to reset to the default prefix.
        You can attach a .txt file instead if the prefix includes newlines.
        """
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                prefix = (await attachments[0].read()).decode()
            except Exception as e:
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse think prefix", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return

        conf = self.db.get_conf(ctx.guild)
        if prefix is None:
            if conf.think_tag_prefix == DEFAULT_THINK_TAG_PREFIX:
                return await ctx.send(_("Think tag prefix is already set to the default value."))
            conf.think_tag_prefix = DEFAULT_THINK_TAG_PREFIX
            await ctx.send(
                _("Think tag prefix reset to default:\n{}").format(box(format_think_tag(conf.think_tag_prefix)))
            )
            await self.save_conf()
            return

        if prefix == "":
            return await ctx.send(_("Think tag prefix cannot be empty."))

        if conf.think_tag_prefix == prefix:
            return await ctx.send(_("Think tag prefix is already set to that value."))

        conf.think_tag_prefix = prefix
        await ctx.send(_("Think tag prefix has been set to:\n{}").format(box(format_think_tag(prefix))))
        await self.save_conf()

    @asettings.command(name="thinksuffix")
    async def set_think_suffix(self, ctx: commands.Context, *, suffix: str = None):
        """
        Set the suffix used to detect model thinking blocks

        Omit the value to reset to the default suffix.
        You can attach a .txt file instead if the suffix includes newlines.
        """
        attachments = get_attachments(ctx.message)
        if attachments:
            try:
                suffix = (await attachments[0].read()).decode()
            except Exception as e:
                txt = _("Failed to read `{}`, bot owner can use `{}` for more information").format(
                    attachments[0].filename, f"{ctx.clean_prefix}traceback"
                )
                await ctx.send(txt)
                log.error("Failed to parse think suffix", exc_info=e)
                self.bot._last_exception = traceback.format_exc()  # type: ignore
                return

        conf = self.db.get_conf(ctx.guild)
        if suffix is None:
            if conf.think_tag_suffix == DEFAULT_THINK_TAG_SUFFIX:
                return await ctx.send(_("Think tag suffix is already set to the default value."))
            conf.think_tag_suffix = DEFAULT_THINK_TAG_SUFFIX
            await ctx.send(
                _("Think tag suffix reset to default:\n{}").format(box(format_think_tag(conf.think_tag_suffix)))
            )
            await self.save_conf()
            return

        if suffix == "":
            return await ctx.send(_("Think tag suffix cannot be empty."))

        if conf.think_tag_suffix == suffix:
            return await ctx.send(_("Think tag suffix is already set to that value."))

        conf.think_tag_suffix = suffix
        await ctx.send(_("Think tag suffix has been set to:\n{}").format(box(format_think_tag(suffix))))
        await self.save_conf()

    @afilter.command(name="question")
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

    @features.command(name="mention-respond")
    async def features_mention_respond(self, ctx: commands.Context):
        """Toggle whether the bot responds to mentions in any channel"""
        conf = self.db.get_conf(ctx.guild)
        if conf.mention_respond:
            conf.mention_respond = False
            await ctx.send(_("The bot will no longer respond to mentions"))
        else:
            conf.mention_respond = True
            await ctx.send(_("The bot will now respond to mentions"))
        await self.save_conf()

    @features.command(name="mention")
    async def features_mention(self, ctx: commands.Context):
        """Toggle whether to ping the user on replies"""
        conf = self.db.get_conf(ctx.guild)
        if conf.mention:
            conf.mention = False
            await ctx.send(_("Mentions are now **Disabled**"))
        else:
            conf.mention = True
            await ctx.send(_("Mentions are now **Enabled**"))
        await self.save_conf()

    @features.command(name="collaborative")
    async def features_collaborative(self, ctx: commands.Context):
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

    @limits.command(name="retention")
    async def limits_retention(self, ctx: commands.Context, max_retention: int):
        """
        Set the max messages for a conversation

        Conversation retention is cached and gets reset when the bot restarts or the cog reloads.

        Regardless of this number, the initial prompt and internal system message are always included,
        this only applies to any conversation between the user and bot after that.

        Set to 0 for unlimited conversation retention

        **Note:** *actual message count may exceed the max retention during an API call*
        """
        if max_retention < 0:
            return await ctx.send(_("Max retention needs to be at least 0 or higher"))
        conf = self.db.get_conf(ctx.guild)
        conf.max_retention = max_retention
        if max_retention == 0:
            await ctx.send(_("Message retention is now **unlimited**"))
        else:
            await ctx.send(_("Conversations can now retain up to **{}** messages").format(max_retention))
        await self.save_conf()

    @limits.command(name="time")
    async def limits_time(self, ctx: commands.Context, retention_seconds: int):
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

    @limits.command(name="tokens")
    async def limits_tokens(self, ctx: commands.Context, max_tokens: commands.positive_int):
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

    @limits.command(name="response")
    async def limits_response(self, ctx: commands.Context, max_tokens: commands.positive_int):
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

    @params.command(name="temperature")
    async def params_temperature(self, ctx: commands.Context, temperature: float):
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

    @params.command(name="frequency")
    async def params_frequency(self, ctx: commands.Context, frequency_penalty: float):
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

    @params.command(name="presence")
    async def params_presence(self, ctx: commands.Context, presence_penalty: float):
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

    @params.command(name="resolution")
    async def params_resolution(self, ctx: commands.Context):
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

    @params.command(name="reasoning")
    async def params_reasoning(self, ctx: commands.Context):
        """Switch reasoning effort between none, minimal, low, medium, high, and xhigh

        Not all models support every level. Unsupported levels are automatically mapped to the closest supported value.
        - **none**: No reasoning (gpt-5.4/5.5 only, skipped for other models)
        - **minimal**: Minimal reasoning (gpt-5 only, mapped to low for o-series)
        - **low**: Low reasoning effort
        - **medium**: Medium reasoning effort
        - **high**: High reasoning effort
        - **xhigh**: Maximum reasoning (gpt-5.4/5.5 only, mapped to high for other models)
        """
        cycle = ["none", "minimal", "low", "medium", "high", "xhigh"]
        conf = self.db.get_conf(ctx.guild)
        try:
            idx = cycle.index(conf.reasoning_effort)
            conf.reasoning_effort = cycle[(idx + 1) % len(cycle)]
        except ValueError:
            conf.reasoning_effort = "low"
        await ctx.send(_("Reasoning effort has been set to **{}**").format(conf.reasoning_effort.capitalize()))
        await self.save_conf()

    @params.command(name="seed")
    async def params_seed(self, ctx: commands.Context, seed: int = None):
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

    @embed.command(
        name="refresh",
        aliases=["refreshembeddings", "syncembeds", "syncembeddings"],
    )
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

    @features.command(name="functions", aliases=["usefunctions"])
    async def features_functions(self, ctx: commands.Context):
        """Toggle whether GPT can call functions"""
        conf = self.db.get_conf(ctx.guild)
        if conf.use_function_calls:
            conf.use_function_calls = False
            await ctx.send(_("Assistant will not call functions"))
        else:
            conf.use_function_calls = True
            await ctx.send(_("Assistant will now call functions as needed"))
        await self.save_conf()

    @asettings.command(name="maxrecursion")
    async def set_max_recursion(self, ctx: commands.Context, recursion: int):
        """Set the maximum function calls allowed in a row

        This sets how many times the model can call functions in a row
        """
        conf = self.db.get_conf(ctx.guild)
        recursion = max(0, recursion)
        if recursion == 0:
            await ctx.send(_("Function calls will not be used since recursion is 0"))
        await ctx.send(
            _("The model can now call various functions up to {} times before returning a response").format(recursion)
        )
        conf.max_function_calls = recursion

    @afilter.command(name="minlength")
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

    @asettings.command(name="model")
    async def set_model(self, ctx: commands.Context, model: str = None):
        """
        Set the chat model to use

        Run without arguments to open an interactive picker that lists every
        model your endpoint advertises, grouped by provider. The picker also
        accepts manual entry - useful for router aliases like
        `openrouter/auto` or `openrouter/free`.
        """
        model = model.lower().strip() if model else None
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return

        has_endpoint = bool(self.db.endpoint_override or conf.endpoint_override)

        if not model:
            if has_endpoint:
                endpoint_url = self.get_guild_endpoint_url(conf)
                async with ctx.typing():
                    profile = await self.refresh_endpoint_profile(conf)
                if not profile:
                    return await ctx.send(
                        _(
                            "Could not probe `{}` to discover available models. "
                            "Try setting a model id manually, e.g. `{}assistant set model openrouter/auto`."
                        ).format(endpoint_url, ctx.clean_prefix)
                    )
                view = ModelPickerView(
                    ctx=ctx,
                    conf=conf,
                    kind="chat",
                    save_func=self.save_conf,
                    reprobe_func=lambda: self.refresh_endpoint_profile(conf, force=True, save=True),
                    get_profile=lambda: self.get_cached_endpoint_profile(conf),
                    endpoint_url=endpoint_url,
                )
                return await view.start()
            valid = [i for i in MODELS]
            humanized = humanize_list(valid)
            formatted = box(humanized)
            return await ctx.send(_("Valid models are:\n{}").format(formatted))

        if conf.api_key and "deepseek" not in model and not has_endpoint:
            try:
                client = get_client(conf.api_key)
                await client.models.retrieve(model)
            except openai.NotFoundError as e:
                txt = _("Error: {}").format(e.response.json()["error"]["message"])
                return await ctx.send(txt)

        conf.model = model
        await ctx.send(_("The **{}** model will now be used").format(model))
        if has_endpoint:
            warning = await self.get_endpoint_model_warning(model, conf=conf)
            if warning:
                await ctx.send(warning)
        await self.save_conf()
        if model.startswith("o"):
            txt = _(
                "**Note**: Starting with `o1-2024-12-17`, reasoning models in the API will avoid generating "
                "responses with markdown formatting. To signal to the model when you do want markdown formatting "
                "in the response, include the string `Formatting re-enabled` on the first line of your system message."
            )
            await ctx.send(txt)

    @embed.command(name="model")
    async def set_embedding_model(self, ctx: commands.Context, model: str = None):
        """
        Set the embedding model to use

        Run without arguments to open an interactive picker that lists
        every embedding model your endpoint advertises, grouped by provider.
        Embeddings use the same endpoint as chat.
        """
        model = model.lower().strip() if model else None
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return

        has_endpoint = bool(self.db.endpoint_override or conf.endpoint_override)
        endpoint_url = self.get_guild_endpoint_url(conf)

        valid = [
            "text-embedding-ada-002",
            "text-embedding-3-small",
            "text-embedding-3-large",
        ]
        if not model:
            if endpoint_url:
                async with ctx.typing():
                    profile = await self.refresh_endpoint_profile(conf)
                if not profile:
                    return await ctx.send(
                        _(
                            "Could not probe `{}` to discover available embedding models. "
                            "Try setting an id manually, e.g. `{}assistant embed model text-embedding-3-small`."
                        ).format(endpoint_url, ctx.clean_prefix)
                    )
                view = ModelPickerView(
                    ctx=ctx,
                    conf=conf,
                    kind="embedding",
                    save_func=self.save_conf,
                    reprobe_func=lambda: self.refresh_endpoint_profile(conf, force=True, save=True),
                    get_profile=lambda: self.get_cached_endpoint_profile(conf),
                    endpoint_url=endpoint_url,
                    post_select=lambda model_id: self.get_embedding_model_change_notice(
                        ctx.guild,
                        model_id,
                        conf,
                        ctx.clean_prefix,
                    ),
                )
                return await view.start()
            return await ctx.send(_("Valid models are:\n{}").format(box(humanize_list(valid))))
        if not has_endpoint and model not in valid:
            return await ctx.send(_("Valid models are:\n{}").format(box(humanize_list(valid))))
        conf.embed_model = model
        await ctx.send(_("The **{}** model will now be used for embeddings").format(model))
        warning = await self.get_embedding_model_change_notice(ctx.guild, model, conf, ctx.clean_prefix)
        if warning:
            await ctx.send(warning)
        await self.save_conf()

    @embed.command(name="reset")
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

    @assistant_admin.command(name="resetconversations")
    async def wipe_conversations(self, ctx: commands.Context, yes_or_no: bool):
        """
        Wipe saved conversations for the assistant in this server

        This will delete any and all saved conversations for the assistant.
        """
        if not yes_or_no:
            return await ctx.send(_("Not wiping conversations"))
        # Snapshot the items: save_conversation awaits, so a concurrent chat turn could
        # insert a key mid-loop and trigger "dict changed size during iteration".
        for key, convo in list(self.db.conversations.items()):
            if ctx.guild.id == int(key.split("-")[2]):
                convo.messages.clear()
                await self.save_conversation(key)
        await ctx.send(_("Conversations have been wiped in this server!"))

    @embed.command(name="topn")
    async def set_topn(self, ctx: commands.Context, top_n: int):
        """
        Set the embedding inclusion amout

        Top N is the amount of retrieved embeddings to include in the grounded RAG context block before the live user query
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

    @embed.command(name="relatedness")
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

    @afilter.command(name="regex")
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

    @afilter.command(name="failblock")
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

    @features.command(name="question-mode")
    async def features_question_mode(self, ctx: commands.Context):
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

    @embed.command(name="importcsv")
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
            query_embedding, observed_model = await self.request_embedding_with_info(text, conf)
            if len(query_embedding) == 0:
                await ctx.send(_("Failed to process embedding: `{}`").format(name))
                continue

            await self.embedding_store.add(ctx.guild.id, name, text, query_embedding, observed_model)
            imported += 1
        await message.edit(content=_("{}\n**COMPLETE**").format(message_text))
        await ctx.send(_("Successfully imported {} embeddings!").format(humanize_number(imported)))
        await self.save_conf()

    @embed.command(name="importjson")
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
                        if not embedding_vec:
                            # Re-embed if no vector present
                            (
                                embedding_vec,
                                model,
                            ) = await self.request_embedding_with_info(text, conf)
                        if not embedding_vec:
                            continue
                        await self.embedding_store.add(
                            ctx.guild.id,
                            name[:100],
                            text,
                            embedding_vec,
                            model,
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

    @embed.command(name="importexcel")
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
                ]
                if any(invalid):
                    txt = _("{} is invalid! Must contain the following columns: {}").format(
                        f"**{attachment.filename}**", "name, text"
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

                (
                    query_embedding,
                    observed_model,
                ) = await self.request_embedding_with_info(text, conf)
                if len(query_embedding) == 0:
                    await ctx.send(_("Failed to process embedding: `{}`").format(name))
                    continue

                await self.embedding_store.add(
                    ctx.guild.id,
                    name,
                    text,
                    query_embedding,
                    observed_model,
                )
                imported += 1

            if imported:
                await message.edit(content=_("{}\n**COMPLETE**").format(message_text))
                await ctx.send(_("Successfully imported {} embeddings!").format(humanize_number(imported)))
                await self.save_conf()
            else:
                await message.edit(content=_("{}\n**COMPLETE**").format(message_text))
                await ctx.send(_("No embeddings needed to be updated!"))

    @embed.command(name="exportexcel")
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
        }

        def _get_file() -> discord.File:
            rows = []
            for name, meta in all_meta.items():
                created_str = meta.get("created", "")
                try:
                    created_dt = datetime.fromisoformat(created_str).astimezone(timezone.utc).replace(tzinfo=None)
                except (ValueError, TypeError):
                    created_dt = datetime.now(tz=timezone.utc).replace(tzinfo=None)
                rows.append([name, meta.get("text", ""), created_dt])
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

    @embed.command(name="exportcsv")
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

    @embed.command(name="exportjson")
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
            self.request_embedding_with_info,
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

    @asettings.command(name="customvars", aliases=["customvariables"])
    @commands.bot_has_permissions(embed_links=True)
    async def custom_variables(self, ctx: commands.Context):
        """List custom prompt context variables registered by other cogs."""
        catalog = self.get_context_variable_catalog()
        docs_line = _("3rd party docs: {}").format(THIRD_PARTY_DOCS_URL)
        if not catalog:
            text = _("No custom context variables have been registered yet!\n{}").format(docs_line)
            return await self.retry_discord_server_error(lambda: ctx.send(text))

        lines = [docs_line, ""]
        for entry in catalog:
            suffix = f" · {entry['permission_level']}" if entry["permission_level"] != "user" else ""
            lines.append(f"**{{{entry['name']}}}** · {entry['source']}{suffix}")
            lines.append(entry["description"])
            lines.append("")

        chunks = list(pagify("\n".join(lines).strip(), page_length=1600))
        pages: list[discord.Embed] = []
        for index, chunk in enumerate(chunks, 1):
            embed = discord.Embed(
                title=_("Custom Variables"),
                url=THIRD_PARTY_DOCS_URL,
                description=chunk,
                color=discord.Color.blue(),
            )
            embed.set_footer(text=_("Page {}/{} | {} variables").format(index, len(chunks), len(catalog)))
            pages.append(embed)

        if len(pages) == 1:
            return await self.retry_discord_server_error(lambda: ctx.send(embed=pages[0]))

        await self.retry_discord_server_error(lambda: SimpleMenu(pages, disable_after_timeout=True).start(ctx))

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

        grouped = self.get_tool_categories()
        if not grouped:
            return await ctx.send(_("No functions have been registered yet!"))

        # Build embed pages
        pages: list[discord.Embed] = []
        all_entries = [entry for entries in grouped.values() for entry in entries]
        enabled_count = sum(conf.function_statuses.get(entry["name"], False) for entry in all_entries)
        disabled_count = len(all_entries) - enabled_count

        lines = []
        for category, entries in grouped.items():
            function_names = [entry["name"] for entry in entries]
            category_state = get_category_state(function_names, conf.function_statuses)
            enabled_in_category = sum(conf.function_statuses.get(name, False) for name in function_names)
            lines.append(
                f"{STATUS_EMOJIS[category_state]} **{render_tool_category(category)}** ({enabled_in_category}/{len(entries)})"
            )
            for entry in entries:
                enabled = conf.function_statuses.get(entry["name"], False)
                source_txt = f" · {entry['source']}" if entry["source"] != "Custom" else ""
                lines.append(f"{ON_STATUS_EMOJI if enabled else OFF_STATUS_EMOJI} {entry['name']}{source_txt}")
            lines.append("")

        # Pagify the lines
        chunks = list(pagify("\n".join(lines).strip(), page_length=1500))
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

    @commands.hybrid_command(name="aitools")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def ai_tools(self, ctx: commands.Context):
        """Open the mobile-friendly AI tools manager."""
        view = AIToolsView(ctx, self.db, self.registry, self.save_conf)
        await view.start()

    @commands.hybrid_command(name="floatingcontext", aliases=["floatcontext", "fctx"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def floating_context_vars(self, ctx: commands.Context):
        """Open the floating context block manager.

        Toggled variables are appended to a trailing payload-only user
        message after conversation history. Because that message rides
        after the cached prefix, putting dynamic (per-request) values
        there keeps the prompt prefix stable across requests so
        provider-side prompt caching can hit.
        """
        view = FloatingContextView(ctx, self.db, self.context_registry, self.save_conf)
        await view.start()

    @commands.hybrid_command(name="cacheinfo")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def cache_info(self, ctx: commands.Context):
        """Show prompt-cache stats from the most recent API call."""

        stats = getattr(self, "last_cache_stats", None)
        if not stats:
            return await ctx.send(_("No cache stats yet - make a request first."))
        cached = stats.get("cached", 0)
        cache_write = stats.get("cache_write", 0)
        total = stats.get("total", 0)
        model = stats.get("model", _("Unknown"))
        pct = (cached / total * 100) if total else 0.0

        lines = [
            _(
                "Last API call: **{cached}**/**{total}** prompt tokens cached "
                "({pct:.0f}%) · **{write}** cache-write tokens · model `{model}`"
            ).format(
                cached=humanize_number(cached),
                total=humanize_number(total),
                pct=pct,
                write=humanize_number(cache_write),
                model=model,
            ),
        ]

        min_tokens = get_min_cache_tokens(model)
        model_lower = str(model).lower()
        if min_tokens > 0 and total < min_tokens and not cached and not cache_write:
            lines.append(
                _(
                    "\n💡 This model requires at least **{min_tokens}** prompt tokens "
                    "before the provider will cache. Your prompt was only "
                    "**{total}** tokens - below the threshold, so no cache write "
                    "or read occurred. A longer system prompt, more conversation "
                    "history, or enabling variables in the "
                    "`[p]floatingcontext` block will push it over."
                ).format(min_tokens=humanize_number(min_tokens), total=humanize_number(total))
            )

        automatic_cache_model = model_lower.startswith(
            ("openai/", "gpt-", "o1", "o3", "grok", "deepseek/", "groq/", "moonshot/")
        )
        if automatic_cache_model and total >= min_tokens and not cached and not cache_write:
            lines.append(
                _(
                    "\nℹ️ This provider uses automatic prompt caching. A **0** "
                    "cache-write count does not necessarily mean caching is "
                    "disabled, because some automatic-cache providers do not "
                    "charge for or clearly expose cache writes. The more useful "
                    "signal is whether similar follow-up turns start showing "
                    "non-zero cached tokens. Also note that the relevant threshold "
                    "is the repeated stable prefix, not the full prompt length, so "
                    "a large request can still miss if most of its tokens are in "
                    "the changing tail of the payload."
                )
            )

        if "gpt-oss" in model_lower and not cached:
            lines.append(
                _(
                    "\nℹ️ `gpt-oss` is a reasoning model running over Chat "
                    "Completions. Cache reuse can be weaker than on non-reasoning "
                    "chat models because not all reasoning state is preserved "
                    "between turns."
                )
            )

        if cache_write > 0 and not cached:
            lines.append(
                _(
                    "\n⚠️ **Cache writes occurred but no reads.** This means the "
                    "provider cached your prompt prefix, but the next request "
                    "didn't match it - the prefix changed between calls. Common "
                    "causes include dynamic variables like `{{time}}`, `{{date}}`, "
                    "or `{{username}}` being substituted into your prompt prefix, "
                    "per-turn context being injected before the cacheable tail, or "
                    "tool definitions changing between calls. Use `[p]floatingcontext` "
                    "to move dynamic context out of the prompt prefix."
                )
            )

        await ctx.send("\n".join(lines))

    @openrouter_cache.command(name="enable")
    async def openrouter_cache_enable(self, ctx: commands.Context):
        """Enable OpenRouter response caching (Mode A)."""
        conf = self.db.get_conf(ctx.guild)
        conf.openrouter_cache_enabled = True
        await self.save_conf()
        await ctx.send(_("OpenRouter response caching **enabled** (TTL: {}s).").format(conf.openrouter_cache_ttl))

    @openrouter_cache.command(name="disable")
    async def openrouter_cache_disable(self, ctx: commands.Context):
        """Disable OpenRouter response caching (Mode A)."""
        conf = self.db.get_conf(ctx.guild)
        conf.openrouter_cache_enabled = False
        await self.save_conf()
        await ctx.send(_("OpenRouter response caching **disabled**."))

    @openrouter_cache.command(name="ttl")
    async def openrouter_cache_ttl_cmd(self, ctx: commands.Context, seconds: int):
        """Set the OpenRouter response cache TTL in seconds (1–86400)."""
        if seconds < 1 or seconds > 86400:
            return await ctx.send(_("TTL must be between 1 and 86400 seconds (24 hours)."))
        conf = self.db.get_conf(ctx.guild)
        conf.openrouter_cache_ttl = seconds
        await self.save_conf()
        await ctx.send(_("OpenRouter response cache TTL set to **{}** seconds.").format(seconds))

    @openrouter_cache.command(name="promptcache")
    async def openrouter_prompt_cache_cmd(self, ctx: commands.Context, mode: str):
        """Set the OpenRouter provider prompt cache TTL.

        Choices: `off`, `5m`, `1h`. Applies to Anthropic / Gemini / Qwen
        models routed via OpenRouter.
        """
        mode = mode.lower().strip()
        if mode not in ("off", "5m", "1h"):
            return await ctx.send(_("Mode must be one of: `off`, `5m`, `1h`."))
        conf = self.db.get_conf(ctx.guild)
        conf.openrouter_prompt_cache_ttl = mode
        await self.save_conf()
        await ctx.send(_("OpenRouter provider prompt cache set to **{}**.").format(mode))

    # ------------------------------------------------------------------
    # OpenRouter provider routing preferences
    # ------------------------------------------------------------------

    @assistant.group(name="openrouterprovider", aliases=["orprovider"])
    @commands.admin_or_permissions(administrator=True)
    async def openrouter_provider(self, ctx: commands.Context):
        """Configure OpenRouter provider routing and model slug preferences."""
        pass

    @openrouter_provider.command(name="settings")
    async def or_provider_settings(self, ctx: commands.Context):
        """Show current OpenRouter provider routing settings."""
        conf = self.db.get_conf(ctx.guild)

        def fmt_list(lst: list) -> str:
            return humanize_list([f"`{v}`" for v in lst]) if lst else _("not set")

        def fmt_opt(val) -> str:
            return f"`{val}`" if val is not None else _("not set (OR default)")

        embed = discord.Embed(title=_("OpenRouter Provider Settings"), color=discord.Color.blue())
        embed.add_field(name=_("Model suffix"), value=fmt_opt(conf.openrouter_model_suffix), inline=True)
        embed.add_field(name=_("Allow fallbacks"), value=fmt_opt(conf.openrouter_allow_fallbacks), inline=True)
        embed.add_field(name=_("Provider order"), value=fmt_list(conf.openrouter_provider_order), inline=False)
        embed.set_footer(text=_("Tip: `providers Fireworks` + `fallbacks false` hard-pins to that provider."))
        await ctx.send(embed=embed)

    @openrouter_provider.command(name="suffix")
    async def or_provider_suffix(self, ctx: commands.Context, value: str):
        """Set a guild-wide model slug suffix applied to every OpenRouter request.

        Valid values: `:nitro` (throughput priority), `:floor` (price priority),
        `:extended`, `clear` (remove suffix).
        The suffix is appended after model resolution and replaces any per-model suffix.
        """
        value = value.strip()
        if value.lower() == "clear":
            self.db.get_conf(ctx.guild).openrouter_model_suffix = None
            await self.save_conf()
            return await ctx.send(_("OpenRouter model suffix cleared."))
        if value not in OR_SUFFIXES:
            return await ctx.send(
                _("Invalid suffix `{}`. Valid: {}.").format(value, humanize_list([f"`{s}`" for s in OR_SUFFIXES]))
            )
        self.db.get_conf(ctx.guild).openrouter_model_suffix = value
        await self.save_conf()
        await ctx.send(_("OpenRouter model suffix set to `{}`.").format(value))

    @openrouter_provider.command(name="providers")
    async def or_provider_providers(self, ctx: commands.Context, *providers: str):
        """Set the ordered list of providers OpenRouter should use (space-separated).

        Pass `clear` to reset. Combined with `fallbacks false` this hard-pins routing
        to only the listed providers in order.
        Example: `providers Fireworks Together`
        """
        conf = self.db.get_conf(ctx.guild)
        if not providers or providers[0].lower() == "clear":
            conf.openrouter_provider_order = []
            await self.save_conf()
            return await ctx.send(_("OpenRouter provider list cleared."))
        conf.openrouter_provider_order = list(providers)
        await self.save_conf()
        await ctx.send(
            _("OpenRouter will try providers in order: {}.").format(humanize_list([f"`{p}`" for p in providers]))
        )

    @openrouter_provider.command(name="fallbacks")
    async def or_provider_fallbacks(self, ctx: commands.Context, value: str):
        """Set whether OpenRouter may fall back to other providers.

        Values: `true`, `false`, `clear` (restore OR default which is true).
        Set to `false` with `providers` to hard-pin routing to those providers only.
        """
        val = value.lower().strip()
        conf = self.db.get_conf(ctx.guild)
        if val == "clear":
            conf.openrouter_allow_fallbacks = None
            await self.save_conf()
            return await ctx.send(_("OpenRouter fallbacks reset to OR default (enabled)."))
        if val not in ("true", "false"):
            return await ctx.send(_("Value must be `true`, `false`, or `clear`."))
        conf.openrouter_allow_fallbacks = val == "true"
        await self.save_conf()
        await ctx.send(_("OpenRouter fallbacks set to `{}`.").format(val))

    @commands.hybrid_command(name="listcategories", aliases=["listcats", "toolcategories"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def list_categories(self, ctx: commands.Context):
        """List tool categories and their current enabled state."""
        if ctx.interaction:
            await ctx.interaction.response.defer()

        conf = self.db.get_conf(ctx.guild)
        grouped = self.get_tool_categories()
        if not grouped:
            return await ctx.send(_("No functions have been registered yet!"))

        lines = []
        total_enabled = 0
        total_tools = 0
        for category, entries in grouped.items():
            function_names = [entry["name"] for entry in entries]
            enabled_count = sum(conf.function_statuses.get(name, False) for name in function_names)
            total_enabled += enabled_count
            total_tools += len(function_names)
            category_state = get_category_state(function_names, conf.function_statuses)
            lines.append(
                f"{STATUS_EMOJIS[category_state]} {render_tool_category(category)} ({enabled_count}/{len(function_names)})"
            )

        chunks = list(pagify("\n".join(lines), page_length=1800))
        pages: list[discord.Embed] = []
        for index, chunk in enumerate(chunks, 1):
            embed = discord.Embed(
                title=_("Tool Categories"),
                description=chunk,
                color=discord.Color.blue(),
            )
            embed.set_footer(
                text=_("Page {}/{} | {} enabled of {} total").format(index, len(chunks), total_enabled, total_tools)
            )
            pages.append(embed)

        if len(pages) == 1:
            return await ctx.send(embed=pages[0])

        from redbot.core.utils.views import SimpleMenu

        await SimpleMenu(pages, disable_after_timeout=True).start(ctx)

    @commands.hybrid_command(name="togglecategories", aliases=["togglecats"])
    @app_commands.describe(
        enable="True to enable, False to disable, or omit to cycle the category state",
        categories="Category names to toggle (comma-separated, or 'all' to toggle all)",
    )
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def toggle_categories(
        self,
        ctx: commands.Context,
        enable: t.Optional[bool],
        *,
        categories: str,
    ):
        """Enable or disable all tools in one or more categories."""
        if ctx.interaction:
            await ctx.interaction.response.defer()

        conf = self.db.get_conf(ctx.guild)
        grouped = self.get_tool_categories()
        if not grouped:
            return await ctx.send(_("No functions have been registered yet!"))

        valid_categories = set(grouped)
        raw_categories = categories.lower().strip()
        if raw_categories == "all":
            target_categories = valid_categories
        else:
            target_categories = {category.strip().lower() for category in categories.split(",") if category.strip()}

        if not target_categories:
            return await ctx.send(_("No valid category names provided!"))

        invalid_categories = target_categories - valid_categories
        if invalid_categories:
            invalid_display = humanize_list([render_tool_category(category) for category in sorted(invalid_categories)])
            return await ctx.send(_("The following categories do not exist: {}").format(invalid_display))

        enabled_categories = []
        disabled_categories = []
        for category in sorted(target_categories):
            entries = grouped[category]
            function_names = [entry["name"] for entry in entries]
            current_state = get_category_state(function_names, conf.function_statuses)
            new_state = enable if enable is not None else current_state != "on"
            for function_name in function_names:
                conf.function_statuses[function_name] = new_state
            payload = f"{render_tool_category(category)} ({len(function_names)})"
            if new_state:
                enabled_categories.append(payload)
            else:
                disabled_categories.append(payload)

        await self.save_conf()

        response_parts = []
        if enabled_categories:
            response_parts.append(
                _("{} **Enabled Categories** ({}):\n{}").format(
                    ON_STATUS_EMOJI,
                    len(enabled_categories),
                    humanize_list(enabled_categories),
                )
            )
        if disabled_categories:
            response_parts.append(
                _("{} **Disabled Categories** ({}):\n{}").format(
                    OFF_STATUS_EMOJI,
                    len(disabled_categories),
                    humanize_list(disabled_categories),
                )
            )

        await ctx.send("\n\n".join(response_parts))

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
                    len(enabled_funcs),
                    humanize_list([f"`{f}`" for f in sorted(enabled_funcs)]),
                )
            )
        if disabled_funcs:
            response_parts.append(
                _("\N{CROSS MARK} **Disabled** ({}):\n{}").format(
                    len(disabled_funcs),
                    humanize_list([f"`{f}`" for f in sorted(disabled_funcs)]),
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
        entries = ["all", *[entry["name"] for entry in self.get_tool_catalog()]]

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

    @toggle_categories.autocomplete("categories")
    async def toggle_categories_complete(self, interaction: discord.Interaction, current: str):
        if "," in current:
            parts = current.rsplit(",", 1)
            prefix = parts[0] + ", "
            search_term = parts[1].strip().lower()
        else:
            prefix = ""
            search_term = current.lower()

        entries = ["all", *self.get_tool_categories().keys()]
        choices = []
        for entry in entries:
            if search_term in entry.lower():
                display_name = prefix + entry if prefix else entry
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

    @afilter.command(name="blacklist")
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

    @asettings.command(name="planner", aliases=["planners"])
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

    # ---- Smartmod (AI moderation) ----
    async def show_smartmod_id_list(self, ctx: commands.Context, ids: List[int], title: str) -> None:
        if not ids:
            await ctx.send(_("**{}:** empty").format(title))
            return
        names = []
        for i in ids:
            obj = ctx.guild.get_role(i) or ctx.guild.get_member(i) or ctx.guild.get_channel_or_thread(i)
            names.append(obj.mention if obj and hasattr(obj, "mention") else f"`{i}`")
        await ctx.send(_("**{}:** {}").format(title, ", ".join(names)))

    @smartmod.command(name="status", aliases=["settings", "show", "view"])
    async def smartmod_status(self, ctx: commands.Context):
        """Show the current smartmod configuration."""
        conf = self.db.get_conf(ctx.guild)
        sm = conf.smartmod
        chan = ctx.guild.get_channel(sm.report_channel) if sm.report_channel else None
        key_ok = self.resolve_smartmod_key(conf) is not None
        roles = ", ".join(f"<@&{r}>" for r in sm.staff_ping_roles) or _("None")
        desc = (
            _("`Enabled:       `{}\n").format("✅" if sm.enabled else "❌")
            + _("`Report channel:`{}\n").format(chan.mention if chan else _("Not set"))
            + _("`OpenAI key:    `{}\n").format(_("OK") if key_ok else _("Missing"))
            + _("`Review model:  `{}\n").format(f"{sm.review_model}" if sm.review_model else _("(default)"))
            + _("`Context:       `{} before / {} after\n").format(sm.context_before, sm.context_after)
            + _("`Panel timeout: `{}s\n").format(sm.action_timeout)
            + _("`Auto-action:   `{}\n").format("✅" if sm.auto_action_on_timeout else "❌")
            + _("`Exempt staff:  `{}\n").format("✅" if sm.exempt_staff else "❌")
            + _("`Staff ping:    `{}\n").format(roles)
            + _("`Blacklist:     `{} items\n").format(len(sm.blacklist))
            + _("`Whitelist:     `{} items\n").format(len(sm.whitelist))
            + _("`Triggers:      `{} phrases").format(len(sm.triggers))
        )
        embed = discord.Embed(title=_("Smartmod (AI Moderation)"), description=desc, color=await ctx.embed_color())
        await ctx.send(embed=embed)

    @smartmod.command(name="toggle")
    async def smartmod_toggle(self, ctx: commands.Context, state: bool = None):
        """Enable or disable AI moderation. Omit the state to flip it."""
        conf = self.db.get_conf(ctx.guild)
        sm = conf.smartmod
        sm.enabled = (not sm.enabled) if state is None else state
        warning = ""
        if sm.enabled and self.resolve_smartmod_key(conf) is None:
            warning += _("\n⚠️ No OpenAI key for the scan. Set one with `{p}assistant smartmod key`.").format(
                p=ctx.clean_prefix
            )
        if sm.enabled and not sm.report_channel:
            warning += _("\n⚠️ No report channel set. Set one with `{p}assistant smartmod channel`.").format(
                p=ctx.clean_prefix
            )
        await ctx.send(_("Smartmod is now **{}**.").format(_("enabled") if sm.enabled else _("disabled")) + warning)
        await self.save_conf()

    @smartmod.command(name="channel")
    async def smartmod_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set the channel where moderation proposals are posted. Omit to clear."""
        conf = self.db.get_conf(ctx.guild)
        conf.smartmod.report_channel = channel.id if channel else None
        msg = _("set to {}").format(channel.mention) if channel else _("cleared")
        await ctx.send(_("Report channel {}.").format(msg))
        await self.save_conf()

    @skills_group.command(name="toggle")
    async def skills_toggle(self, ctx: commands.Context):
        """Toggle the skills system for this server (also enables/disables the skill tools)"""
        conf = self.db.get_conf(ctx.guild)
        conf.skills_enabled = not conf.skills_enabled
        conf.function_statuses["load_skill"] = conf.skills_enabled
        conf.function_statuses["propose_skill"] = conf.skills_enabled
        status = _("**enabled**") if conf.skills_enabled else _("**disabled**")
        await ctx.send(_("Skills system is now {}").format(status))
        await self.save_conf()

    @skills_group.command(name="channel")
    async def skills_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set (or clear) a dedicated channel for skill proposals

        When set, all proposals post here instead of the conversation they came from.
        When cleared, proposals fall back to whatever channel the chat happened in.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.skill_channel = channel.id if channel else None
        if channel:
            await ctx.send(_("Skill proposals will be posted in {}").format(channel.mention))
        else:
            await ctx.send(_("Skill proposal channel cleared. Proposals will post in the current chat channel."))
        await self.save_conf()

    @skills_group.command(name="pingrole")
    async def skills_pingrole(self, ctx: commands.Context, role: discord.Role):
        """Add or remove a role to ping when a skill proposal is posted"""
        conf = self.db.get_conf(ctx.guild)
        if role.id in conf.skill_ping_roles:
            conf.skill_ping_roles.remove(role.id)
            await ctx.send(_("{} will no longer be pinged for skill proposals").format(role.name))
        else:
            conf.skill_ping_roles.append(role.id)
            await ctx.send(_("{} will be pinged for skill proposals").format(role.name))
        await self.save_conf()

    @skills_group.command(name="proposeusers")
    async def skills_propose_users(self, ctx: commands.Context):
        """Toggle whether the AI may propose skills from conversations with normal users"""
        conf = self.db.get_conf(ctx.guild)
        conf.skill_propose_users = not conf.skill_propose_users
        status = _("**enabled**") if conf.skill_propose_users else _("**disabled**")
        await ctx.send(_("Skill proposals from normal-user conversations: {}").format(status))
        await self.save_conf()

    @skills_group.command(name="adminmode")
    async def skills_admin_mode(self, ctx: commands.Context, mode: str):
        """Set how skills behave in admin conversations: off, propose, or auto

        - off: the AI never drafts skills from admin chats
        - propose: drafts go to the review channel like everyone else's
        - auto: skills bake immediately with no approval panel
        """
        mode = mode.lower().strip()
        if mode not in ("off", "propose", "auto"):
            await ctx.send(_("Mode must be one of: off, propose, auto"))
            return
        conf = self.db.get_conf(ctx.guild)
        conf.skill_admin_mode = mode
        await ctx.send(_("Admin skill mode set to **{}**").format(mode))
        await self.save_conf()

    @skills_group.command(name="list")
    async def skills_list(self, ctx: commands.Context):
        """List this server's skills with usage stats"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.skills:
            await ctx.send(_("No skills configured."))
            return
        lines = []
        for name, skill in sorted(conf.skills.items()):
            flags = []
            if not skill.enabled:
                flags.append(_("disabled"))
            if skill.permission_level != "user":
                flags.append(skill.permission_level)
            suffix = f" ({', '.join(flags)})" if flags else ""
            lines.append(f"`{name}`{suffix}: {skill.description} - used {skill.use_count}x")
        for page in pagify("\n".join(lines), page_length=1900):
            await ctx.send(page)

    @skills_group.command(name="add")
    async def skills_add(self, ctx: commands.Context, name: str, description: str, *, body: str):
        """Add a skill manually

        Wrap the description in quotes. The rest of the message is the procedure body.
        Attach a .md/.txt file instead of typing the body to use longer content.
        """
        conf = self.db.get_conf(ctx.guild)
        name = normalize_skill_name(name)
        attachments = get_attachments(ctx.message)
        if attachments:
            body = (await attachments[0].read()).decode("utf-8", errors="replace")
        if len(body) > MAX_SKILL_BODY:
            await ctx.send(_("Body too long ({} chars, max {})").format(len(body), MAX_SKILL_BODY))
            return
        if name in conf.skills:
            await ctx.send(_("A skill named `{}` already exists. Use the menu to edit it.").format(name))
            return
        if len(conf.skills) >= conf.max_skills:
            await ctx.send(_("Skill limit reached ({})").format(conf.max_skills))
            return
        self.bake_skill(
            conf=conf,
            name=name,
            description=description,
            body=body,
            author_id=ctx.author.id,
            approver_id=ctx.author.id,
        )
        await ctx.send(_("Skill `{}` added and active.").format(name))
        await self.save_conf()

    @skills_group.command(name="delete", aliases=["del", "remove"])
    async def skills_delete(self, ctx: commands.Context, name: str):
        """Delete a skill"""
        conf = self.db.get_conf(ctx.guild)
        name = normalize_skill_name(name)
        if name not in conf.skills:
            await ctx.send(_("No skill named `{}`").format(name))
            return
        del conf.skills[name]
        await ctx.send(_("Skill `{}` deleted.").format(name))
        await self.save_conf()

    @skills_group.command(name="menu", aliases=["view"])
    async def skills_menu(self, ctx: commands.Context):
        """Open the interactive skill management menu"""
        conf = self.db.get_conf(ctx.guild)
        view = SkillMenuView(self, ctx, conf)
        view.message = await ctx.send(view=view)

    @skills_group.command(name="audit")
    async def skills_audit(self, ctx: commands.Context, name: str = None):
        """Have the AI audit all skills (or one) for overlap, staleness, conflicts, and quality"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.skills:
            await ctx.send(_("No skills to audit."))
            return
        name = normalize_skill_name(name) if name else None
        if name and name not in conf.skills:
            await ctx.send(_("No skill named `{}`").format(name))
            return
        targets = {name: conf.skills[name]} if name else conf.skills
        now = datetime.now(tz=timezone.utc)
        blocks = []
        for skill_name, skill in sorted(targets.items()):
            age_days = (now - skill.created).days
            idle_days = (now - skill.last_used).days if skill.last_used else None
            idle = f"{idle_days}d ago" if idle_days is not None else "never"
            blocks.append(
                f"## {skill_name}\nWhen: {skill.description}\nAge: {age_days}d | Last used: {idle} | "
                f"Uses: {skill.use_count} | Level: {skill.permission_level} | Enabled: {skill.enabled}\n"
                f"Body:\n{skill.body}"
            )
        messages = [
            {"role": "system", "content": SKILL_AUDIT_PROMPT},
            {"role": "user", "content": "\n\n".join(blocks)},
        ]
        async with ctx.typing():
            response = await request_chat_completion_raw(
                model=self.db.get_effective_model(conf, ctx.author),
                messages=messages,
                temperature=0.0,
                api_key=self.get_api_key(conf),
                max_tokens=2000,
                base_url=conf.endpoint_override or self.db.endpoint_override,
            )
        report = response.choices[0].message.content or _("No response from model.")
        for page in pagify(report, page_length=1900):
            await ctx.send(page)

    @smartmod.command(name="model")
    async def smartmod_model(self, ctx: commands.Context, *, model: str = ""):
        """Set the smartmod review model (empty = use the server's default chat model).

        Run with no model to open the interactive model picker — endpoint-discovered models when a
        custom endpoint is set, otherwise the built-in OpenAI list.
        """
        conf = self.db.get_conf(ctx.guild)
        model = model.strip()
        if model:
            conf.smartmod.review_model = model
            await ctx.send(_("Review model set to `{}`.").format(model))
            return await self.save_conf()

        endpoint_url = self.get_guild_endpoint_url(conf)
        if endpoint_url:
            if not await self.can_call_llm(conf, ctx):
                return
            async with ctx.typing():
                profile = await self.refresh_endpoint_profile(conf)
            if not profile:
                return await ctx.send(
                    _(
                        "Could not probe `{}` to discover models. Set one manually with "
                        "`{}assistant smartmod model <name>`."
                    ).format(endpoint_url, ctx.clean_prefix)
                )
            view = ModelPickerView(
                ctx=ctx,
                conf=conf,
                kind="chat",
                save_func=self.save_conf,
                reprobe_func=lambda: self.refresh_endpoint_profile(conf, force=True, save=True),
                get_profile=lambda: self.get_cached_endpoint_profile(conf),
                endpoint_url=endpoint_url,
                get_current=lambda: conf.smartmod.review_model or conf.model,
                set_current=lambda chosen: setattr(conf.smartmod, "review_model", chosen),
            )
            return await view.start()

        # No custom endpoint (OpenAI): no live discovery, so show the built-in model list.
        await ctx.send(
            _(
                "The review model uses the server's default chat model unless set. Valid OpenAI models:\n{}\n"
                "Set one with `{}assistant smartmod model <name>`."
            ).format(box(humanize_list(list(MODELS))), ctx.clean_prefix)
        )

    @smartmod.command(name="prompt")
    async def smartmod_prompt(self, ctx: commands.Context, *, text: str = ""):
        """Set the moderation review prompt.

        Supports the {flagged_categories} placeholder plus the same standard prompt variables
        as the main system prompt (server name, channel name, display name, custom cog
        variables, etc.).

        Run with no text to view the current prompt. Use `defaultprompt` to grab the built-in
        default to customize, and `resetprompt` to restore it.
        """
        conf = self.db.get_conf(ctx.guild)
        if not text.strip():
            await ctx.send(
                _("Current moderation prompt (edit and re-set with `{p}assistant smartmod prompt <text>`):").format(
                    p=ctx.clean_prefix
                ),
                file=text_to_file(conf.smartmod.mod_prompt, filename="smartmod_prompt.txt"),
            )
            return
        conf.smartmod.mod_prompt = text.strip()
        await ctx.send(_("Moderation prompt updated."))
        await self.save_conf()

    @smartmod.command(name="defaultprompt", aliases=["promptdefault"])
    async def smartmod_default_prompt(self, ctx: commands.Context):
        """Get the built-in default moderation prompt to copy and customize."""
        await ctx.send(
            _("Default moderation prompt - copy, edit, then set with `{p}assistant smartmod prompt <text>`:").format(
                p=ctx.clean_prefix
            ),
            file=text_to_file(DEFAULT_MOD_PROMPT, filename="smartmod_default_prompt.txt"),
        )

    @smartmod.command(name="resetprompt")
    async def smartmod_reset_prompt(self, ctx: commands.Context):
        """Reset the moderation review prompt to the built-in default."""
        conf = self.db.get_conf(ctx.guild)
        conf.smartmod.mod_prompt = DEFAULT_MOD_PROMPT
        await ctx.send(_("Moderation prompt reset to default."))
        await self.save_conf()

    @smartmod.command(name="threshold")
    async def smartmod_threshold(self, ctx: commands.Context, category: str = None, value: float = None):
        """Set a category's flag threshold (0.0-1.0), e.g. `harassment 0.4`.

        Run with no arguments to list every moderation category and its current threshold.
        """
        conf = self.db.get_conf(ctx.guild)
        if category is None or value is None:
            eff = conf.smartmod.effective_thresholds()
            lines = [f"{c:<28}{eff[c]:.2f}" for c in sorted(eff)]
            await ctx.send(
                _("Set one with `{p}assistant smartmod threshold <category> <0.0-1.0>`:\n{box}").format(
                    p=ctx.clean_prefix, box=box("\n".join(lines), "ini")
                )
            )
            return
        category = category.strip().lower()
        if category not in MOD_CATEGORY_DEFAULTS:
            valid = ", ".join(f"`{c}`" for c in MOD_CATEGORY_DEFAULTS)
            await ctx.send(_("Unknown category. Valid categories:\n{}").format(valid))
            return
        if not 0.0 <= value <= 1.0:
            await ctx.send(_("Value must be between 0.0 and 1.0."))
            return
        conf.smartmod.thresholds[category] = value
        await ctx.send(_("Threshold for `{}` set to `{}`.").format(category, value))
        await self.save_conf()

    @smartmod.command(name="thresholds")
    async def smartmod_thresholds(self, ctx: commands.Context):
        """View the effective per-category flag thresholds."""
        conf = self.db.get_conf(ctx.guild)
        eff = conf.smartmod.effective_thresholds()
        lines = [f"{c:<28}{eff[c]:.2f}" for c in sorted(eff)]
        await ctx.send(box("\n".join(lines), "ini"))

    def smartmod_score_lines(self, scores: dict, thr: dict) -> tuple[list, list]:
        """Return (flagged_categories, formatted_table_lines) comparing each score to its threshold."""
        flagged = []
        lines = []
        for cat in sorted(scores):
            score = scores[cat] or 0.0
            limit = thr.get(cat, 1.1)
            hit = score >= limit
            if hit:
                flagged.append(cat)
            lines.append(f"{'>>' if hit else '  '} {cat:<26}{score:>7.3f} / {limit:.2f}")
        return flagged, lines

    @smartmod.command(name="test")
    async def smartmod_test(self, ctx: commands.Context, *, content: str):
        """Preview a sample message: which trigger phrases match plus each moderation score vs its threshold."""
        conf = self.db.get_conf(ctx.guild)
        keyword_hits = self.smartmod_match_triggers(content, conf)
        key_ok = self.resolve_smartmod_key(conf) is not None
        if not key_ok and not conf.smartmod.triggers:
            return await ctx.send(
                _("No OpenAI key available for the scan. Set one with `{p}assistant smartmod key`.").format(
                    p=ctx.clean_prefix
                )
            )
        scores = None
        if key_ok:
            async with ctx.typing():
                scores = await self.smartmod_score(content, conf)
            if scores is None:
                return await ctx.send(_("Moderation scan failed — check the key or the bot logs."))
        flagged, lines = self.smartmod_score_lines(scores or {}, conf.smartmod.effective_thresholds())
        would_trigger = bool(flagged or keyword_hits)
        parts = [_("🚩 **Would trigger review**") if would_trigger else _("✅ **Would not trigger**")]
        if keyword_hits:
            parts.append(_("Matched triggers: {}").format(", ".join(f"`{p}`" for p in keyword_hits)))
        if flagged:
            parts.append(_("Scan flagged: {}").format(", ".join(flagged)))
        if lines:
            parts.append(box("\n".join(lines)))
        await ctx.send("\n".join(parts))

    @smartmod.command(name="simulate", aliases=["dryrun"])
    async def smartmod_simulate(self, ctx: commands.Context, *, content: str):
        """Dry-run the FULL pipeline on sample text: scan / triggers -> review model -> action panel.

        The review model runs for real (tools, embeddings, this channel's recent context) with you as
        the simulated offender, but the panel's buttons take no real action. The review runs if a
        category trips its threshold OR a trigger phrase matches (same as production).
        """
        conf = self.db.get_conf(ctx.guild)
        keyword_hits = self.smartmod_match_triggers(content, conf)
        key_ok = self.resolve_smartmod_key(conf) is not None
        if not key_ok and not conf.smartmod.triggers:
            return await ctx.send(
                _("No OpenAI key available for the scan. Set one with `{p}assistant smartmod key`.").format(
                    p=ctx.clean_prefix
                )
            )
        tripped: dict = {}
        if key_ok:
            async with ctx.typing():
                scores = await self.smartmod_score(content, conf)
            if scores is None:
                return await ctx.send(_("Moderation scan failed — check the key or the bot logs."))
            flagged, lines = self.smartmod_score_lines(scores, conf.smartmod.effective_thresholds())
            tripped.update({c: scores[c] for c in flagged})
            await ctx.send(box("\n".join(lines)))
        for phrase in keyword_hits:
            tripped[f"keyword '{phrase}'"] = 1.0
        if not tripped:
            return await ctx.send(
                _("✅ Would not trigger — no category over its threshold and no trigger phrase matched.")
            )
        await ctx.send(_("🚩 Tripped: {}").format(", ".join(tripped)))
        try:
            async with ctx.typing():
                outcome, detail = await self.simulate_smartmod(ctx.message, conf, tripped, content, ctx.channel)
        except Exception as e:
            await ctx.send(_("Simulation error: {}").format(e))
            return
        if outcome == "no_action":
            await ctx.send(_("🧪 Model chose **no action**.\n-# {}").format(detail or _("no reason given")))
        elif outcome == "no_decision":
            await ctx.send(_("🧪 Model didn't reach a decision within the review turn limit."))
        else:
            await ctx.send(_("🧪 Model **proposed** an action — see the dry-run panel above (buttons are no-ops)."))

    @smartmod.command(name="blacklist", aliases=["bl"])
    async def smartmod_blacklist(
        self,
        ctx: commands.Context,
        *,
        target: Union[
            discord.Member,
            discord.Role,
            discord.TextChannel,
            discord.CategoryChannel,
            discord.Thread,
            discord.ForumChannel,
        ] = None,
    ):
        """Toggle a channel/category/role/member on the moderation ignore list. Omit to view."""
        conf = self.db.get_conf(ctx.guild)
        if target is None:
            await self.show_smartmod_id_list(ctx, conf.smartmod.blacklist, _("Smartmod blacklist (ignored)"))
            return
        lst = conf.smartmod.blacklist
        if target.id in lst:
            lst.remove(target.id)
            await ctx.send(_("{} removed from the smartmod blacklist.").format(target.name))
        else:
            lst.append(target.id)
            await ctx.send(_("{} added to the smartmod blacklist.").format(target.name))
        await self.save_conf()

    @smartmod.command(name="whitelist", aliases=["wl"])
    async def smartmod_whitelist(
        self,
        ctx: commands.Context,
        *,
        target: Union[
            discord.Member,
            discord.Role,
            discord.TextChannel,
            discord.CategoryChannel,
            discord.Thread,
            discord.ForumChannel,
        ] = None,
    ):
        """Only moderate these channel/category/role/members (used only when the blacklist is empty). Omit to view."""
        conf = self.db.get_conf(ctx.guild)
        if target is None:
            await self.show_smartmod_id_list(ctx, conf.smartmod.whitelist, _("Smartmod whitelist (only these)"))
            return
        lst = conf.smartmod.whitelist
        if target.id in lst:
            lst.remove(target.id)
            await ctx.send(_("{} removed from the smartmod whitelist.").format(target.name))
        else:
            lst.append(target.id)
            await ctx.send(_("{} added to the smartmod whitelist.").format(target.name))
        await self.save_conf()

    @smartmod.command(name="staffrole", aliases=["pingrole"])
    async def smartmod_staffrole(self, ctx: commands.Context, *, role: discord.Role = None):
        """Toggle a role to ping (and authorize) when an action is proposed. Omit to view."""
        conf = self.db.get_conf(ctx.guild)
        if role is None:
            await self.show_smartmod_id_list(ctx, conf.smartmod.staff_ping_roles, _("Smartmod staff ping roles"))
            return
        lst = conf.smartmod.staff_ping_roles
        if role.id in lst:
            lst.remove(role.id)
            await ctx.send(_("{} removed from the staff ping roles.").format(role.name))
        else:
            lst.append(role.id)
            await ctx.send(_("{} added to the staff ping roles.").format(role.name))
        await self.save_conf()

    @smartmod.command(name="context")
    async def smartmod_context(self, ctx: commands.Context, before: int, after: int):
        """Set how many messages of context to capture before/after a flagged message."""
        conf = self.db.get_conf(ctx.guild)
        conf.smartmod.context_before = max(0, min(before, 50))
        conf.smartmod.context_after = max(0, min(after, 25))
        await ctx.send(
            _("Context window set to {} before / {} after.").format(
                conf.smartmod.context_before, conf.smartmod.context_after
            )
        )
        await self.save_conf()

    @smartmod.command(name="timeout")
    async def smartmod_timeout(self, ctx: commands.Context, seconds: int):
        """Set how long the action panel stays interactive, in seconds (60-86400)."""
        conf = self.db.get_conf(ctx.guild)
        conf.smartmod.action_timeout = max(60, min(seconds, 86400))
        await ctx.send(_("Panel timeout set to {} seconds.").format(conf.smartmod.action_timeout))
        await self.save_conf()

    @smartmod.command(name="autoaction")
    async def smartmod_autoaction(self, ctx: commands.Context, state: bool = None):
        """Toggle whether the proposed action auto-executes when the panel times out."""
        conf = self.db.get_conf(ctx.guild)
        sm = conf.smartmod
        sm.auto_action_on_timeout = (not sm.auto_action_on_timeout) if state is None else state
        state_txt = _("on") if sm.auto_action_on_timeout else _("off")
        await ctx.send(_("Auto-action on timeout is now **{}**.").format(state_txt))
        await self.save_conf()

    @smartmod.command(name="exemptstaff", aliases=["exempt"])
    async def smartmod_exempt(self, ctx: commands.Context, state: bool = None):
        """Toggle skipping moderation for members with ban/kick/manage-messages permissions."""
        conf = self.db.get_conf(ctx.guild)
        sm = conf.smartmod
        sm.exempt_staff = (not sm.exempt_staff) if state is None else state
        await ctx.send(_("Exempt staff is now **{}**.").format(_("on") if sm.exempt_staff else _("off")))
        await self.save_conf()

    @smartmod.command(name="trigger", aliases=["triggerword", "addtrigger"])
    async def smartmod_trigger(self, ctx: commands.Context, *, phrase: str):
        """Add or remove a trigger phrase that sends a message straight to moderation review.

        A match fires the review pipeline **in place of** the OpenAI moderation scan — so
        triggers work even with no OpenAI key set. Re-run with the exact same phrase to remove it.

        Only `*` is a wildcard (it matches any run of characters); everything else is literal,
        so pasting real regex is safe and can never lock the bot up. With no `*`, the phrase
        matches on word boundaries (`idiot` hits the word "idiot" but not "idiotic"); add `*`
        to loosen it: `idiot*` (prefix), `*idiot` (suffix), `*idiot*` (substring anywhere).
        """
        conf = self.db.get_conf(ctx.guild)
        sm = conf.smartmod
        phrase = phrase.strip()
        if phrase in sm.triggers:
            sm.triggers.remove(phrase)
            await ctx.send(_("Removed smartmod trigger: `{}`").format(phrase))
            return await self.save_conf()
        if not phrase.replace("*", "").strip():
            return await ctx.send(_("A trigger needs at least one non-`*` character."))
        if len(phrase) > MAX_TRIGGER_LEN:
            return await ctx.send(_("That trigger is too long (max {} characters).").format(MAX_TRIGGER_LEN))
        sm.triggers.append(phrase)
        await ctx.send(
            _("Added smartmod trigger `{phrase}` (matches as `{regex}`).").format(
                phrase=phrase, regex=wildcard_to_regex(phrase)
            )
        )
        await self.save_conf()

    @smartmod.command(name="triggers", aliases=["triggerlist"])
    async def smartmod_triggers(self, ctx: commands.Context):
        """List the smartmod trigger phrases and the safe pattern each one compiles to."""
        conf = self.db.get_conf(ctx.guild)
        sm = conf.smartmod
        if not sm.triggers:
            return await ctx.send(
                _("No smartmod triggers set. Add one with `{p}assistant smartmod trigger <phrase>`.").format(
                    p=ctx.clean_prefix
                )
            )
        text = "\n".join(f"{p}  ->  {wildcard_to_regex(p)}" for p in sm.triggers)
        if len(text) > 1900:
            return await ctx.send(file=text_to_file(text, filename="smartmod_triggers.txt"))
        await ctx.send(box(text, "ini"))

    @smartmod.command(name="key", aliases=["openaikey"])
    async def smartmod_key(self, ctx: commands.Context):
        """Set a dedicated OpenAI key for the moderation scan (opens a secure modal).

        Use this when your chat endpoint is a custom/non-OpenAI endpoint (OpenRouter, LM Studio,
        etc.): the free OpenAI moderation scan still runs against api.openai.com with this key,
        while the review LLM keeps using your configured endpoint. Enter `none` to clear it.
        """
        conf = self.db.get_conf(ctx.guild)
        view = SetAPI(ctx.author, conf.smartmod.openai_key)
        txt = _("Click to set the OpenAI key used for the smartmod moderation scan\n\nTo remove the key, enter `none`")
        embed = discord.Embed(description=txt, color=ctx.author.color)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()
        key = view.key.strip() if view.key else "none"
        if key == "none" and conf.smartmod.openai_key:
            conf.smartmod.openai_key = None
            await msg.edit(content=_("Smartmod OpenAI key has been removed!"), embed=None, view=None)
        elif key == "none":
            return await msg.edit(content=_("No API key was entered!"), embed=None, view=None)
        else:
            conf.smartmod.openai_key = key
            await msg.edit(content=_("Smartmod OpenAI key has been set!"), embed=None, view=None)
        await self.save_conf()

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

        has_endpoint = bool(self.db.endpoint_override or conf.endpoint_override)

        if not model:
            if has_endpoint:
                txt = _(
                    "Enter a model id supported by your custom endpoint. If it exposes `/v1/models`, you can copy one from there."
                )
                return await ctx.send(txt)
            return await ctx.send(_("Valid models are:\n{}").format(box(humanize_list(list(MODELS.keys())))))

        if conf.api_key and "deepseek" not in model and not has_endpoint:
            try:
                client = get_client(conf.api_key)
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
        self,
        ctx: commands.Context,
        max_tokens: commands.positive_int,
        *,
        role: discord.Role,
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

    @override.command(name="reasoning")
    async def reasoning_effort_override(self, ctx: commands.Context, effort: str, *, role: discord.Role):
        """
        Assign a reasoning effort override to a role

        Valid values: none, minimal, low, medium, high, xhigh

        *Specify same role and effort to remove the override*
        """
        valid = ("none", "minimal", "low", "medium", "high", "xhigh")
        effort = effort.lower().strip()
        if effort not in valid:
            return await ctx.send(_("Invalid effort level. Valid values: {}").format(humanize_list(list(valid))))

        conf = self.db.get_conf(ctx.guild)

        if role.id in conf.reasoning_effort_role_override:
            if conf.reasoning_effort_role_override[role.id] == effort:
                del conf.reasoning_effort_role_override[role.id]
                await ctx.send(_("Reasoning effort override for {} removed!").format(role.mention))
            else:
                conf.reasoning_effort_role_override[role.id] = effort
                await ctx.send(_("Reasoning effort override for {} overwritten!").format(role.mention))
        else:
            conf.reasoning_effort_role_override[role.id] = effort
            await ctx.send(_("Reasoning effort override for {} added!").format(role.mention))
        await self.save_conf()

    @asettings.command(name="verbosity")
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

    @api.command(name="globalmodel", aliases=["defaultmodel"])
    @commands.is_owner()
    async def api_globalmodel(self, ctx: commands.Context, *, model: str = None):
        """Set the global default chat model for guilds that haven't picked their own (owner).

        Pairs with `[p]assistant api globalendpoint`: e.g. set `openrouter/free` so new servers
        route to OpenRouter's free models instead of the built-in `gpt-5.4` default. Guilds that
        chose their own model are unaffected. Omit to view; pass `none` to clear.
        """
        if not model:
            current = self.db.default_model or _("(not set - guilds use their own model)")
            return await ctx.send(
                _("Global default model: `{}`\nSet with `{}assistant api globalmodel <model>`.").format(
                    current, ctx.clean_prefix
                )
            )
        if model.strip().lower() == "none":
            self.db.default_model = ""
            await ctx.send(_("Global default model cleared."))
        else:
            self.db.default_model = model.strip()
            await ctx.send(
                _("Global default model set to `{}`. Guilds without their own model will use it.").format(model.strip())
            )
        await self.save_conf()

    @api.command(name="globalendpoint", aliases=["override"])
    @commands.is_owner()
    async def api_override(self, ctx: commands.Context, endpoint: str = None):
        """
        Set the global default endpoint URL (owner)

        When set, every guild without its own endpoint override calls this
        URL instead of OpenAI's default. Pass the full base URL including
        the scheme and the `/v1` suffix.

        **Examples**
        - `http://127.0.0.1:1234/v1`
        - `http://localhost:5001/v1`
        - `https://example.com/api/v1`
        - `https://openrouter.ai/api/v1`

        **Notes**
        - Endpoints must be OpenAI-compatible
        - This is the SDK `base_url`, not a specific route like `/chat/completions`
        - Use `[p]assistant api globalkey` to set the API key for this endpoint
        - Router endpoints like OpenRouter accept special model aliases
          (e.g. `openrouter/auto`, `openrouter/free`) via `[p]assistant set model`
        - Omit the argument to remove the override
        """
        endpoint, error = normalize_endpoint_override(endpoint)
        if error:
            return await ctx.send(error)

        if self.db.endpoint_override == endpoint:
            return await ctx.send(_("Endpoint is already set to **{}**").format(endpoint))
        if endpoint and not self.db.endpoint_override:
            self.db.endpoint_override = endpoint
            profile = await self.refresh_endpoint_profile(force=True)
            txt = _("Endpoint has been set to **{}**").format(endpoint)
            if profile:
                txt += "\n\n" + self.describe_endpoint_profile(profile)
            await ctx.send(txt)
        elif endpoint and self.db.endpoint_override:
            old = self.db.endpoint_override
            self.db.endpoint_override = endpoint
            profile = await self.refresh_endpoint_profile(force=True)
            txt = _("Endpoint has been changed from **{}** to **{}**").format(old, endpoint)
            if profile:
                txt += "\n\n" + self.describe_endpoint_profile(profile)
            await ctx.send(txt)
        else:
            self.db.endpoint_override = None
            self.clear_endpoint_profile()
            await ctx.send(_("Endpoint override has been removed!"))
        await self.save_conf()

    @assistant_admin.command(name="probe")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def endpoint_probe(self, ctx: commands.Context):
        """Probe the active endpoint and refresh its cached model/capability profile

        Checks the guild endpoint override first; if none is set, probes the
        global endpoint override. Reports an error if no endpoint is configured.
        """
        conf = self.db.get_conf(ctx.guild)
        endpoint_url = self.get_guild_endpoint_url(conf)
        if not endpoint_url:
            return await ctx.send(_("No endpoint override is configured for this guild or globally."))

        async with ctx.typing():
            profile = await self.refresh_endpoint_profile(conf, force=True, save=True)

        if not profile:
            return await ctx.send(_("Failed to probe `{}`.").format(endpoint_url))

        await ctx.send(self.describe_endpoint_profile(profile))

    @assistant_admin.command(name="wipe")
    @commands.is_owner()
    async def wipe_cog(self, ctx: commands.Context, confirm: bool):
        """Wipe all settings and data for entire cog"""
        if not confirm:
            return await ctx.send(_("Not wiping cog"))
        self.db.configs.clear()
        self.db.conversations.clear()
        self.db.persistent_conversations = False
        await asyncio.to_thread(self.conversation_store.clear)
        await self.save_conf()
        await ctx.send(_("Cog has been wiped!"))

    @assistant_admin.command(name="backup")
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

    @assistant_admin.command(name="restore")
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

    @assistant_admin.command(name="resetglobalconversations")
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
        await asyncio.to_thread(self.conversation_store.clear)
        await ctx.send(_("Conversations have been wiped for all servers!"))

    @features.command(name="persist")
    @commands.is_owner()
    async def features_persist(self, ctx: commands.Context):
        """Toggle persistent conversations"""
        if self.db.persistent_conversations:
            self.db.persistent_conversations = False
            # Purge the on-disk files now. In-memory conversations are left intact (this
            # session keeps working); they just won't survive a restart anymore.
            await asyncio.to_thread(self.conversation_store.clear)
            await ctx.send(_("Persistent conversations have been **Disabled**"))
        else:
            self.db.persistent_conversations = True
            # Flush current in-memory conversations to disk so this session persists too,
            # not only conversations that get mutated after enabling.
            for key in list(self.db.conversations):
                await self.save_conversation(key)
            await ctx.send(_("Persistent conversations have been **Enabled**"))
        await self.save_conf()

    @asettings.command(name="reasoningfiles")
    @commands.is_owner()
    async def toggle_reasoning_files(self, ctx: commands.Context):
        """Toggle whether reasoning/think blocks are uploaded as files globally"""
        if self.db.reasoning_as_files:
            self.db.reasoning_as_files = False
            await ctx.send(_("Reasoning blocks will now be stripped from replies without uploading think files."))
        else:
            self.db.reasoning_as_files = True
            await ctx.send(_("Reasoning blocks will now be uploaded as think files when present."))
        await self.save_conf()

    @embed.command(name="resetglobal")
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

    @asettings.command(name="listenbots", aliases=["botlisten", "ignorebots"])
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

    @scheduler.command(name="list", aliases=["view"])
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    @commands.bot_has_permissions(embed_links=True)
    async def view_scheduled_tasks(self, ctx: commands.Context):
        """View and manage all scheduled autonomous tasks in this server."""
        guild_tasks = [stask for stask in self.db.scheduled_tasks.values() if stask.guild_id == ctx.guild.id]
        if not guild_tasks:
            return await ctx.send(_("No scheduled tasks in this server."))

        guild_tasks.sort(key=lambda stask: stask.execute_at)
        lines = []
        for stask in guild_tasks:
            member = ctx.guild.get_member(stask.user_id)
            user_display = member.display_name if member else f"Unknown ({stask.user_id})"
            channel = ctx.guild.get_channel(stask.channel_id)
            channel_display = channel.mention if channel else f"#{stask.channel_id}"
            timestamp = int(stask.execute_at.timestamp())
            instruction_preview = stask.instruction[:80] + ("..." if len(stask.instruction) > 80 else "")
            lines.append(
                f"**`{stask.id}`** | {user_display} | {channel_display}\n"
                f"  Executes <t:{timestamp}:R> (<t:{timestamp}:f>)\n"
                f"  {instruction_preview}"
            )

        text = "\n\n".join(lines)
        embed = discord.Embed(
            title=_("Scheduled Tasks ({})").format(len(guild_tasks)),
            description=text[:4000],
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    @scheduler.command(name="cancel")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def cancel_task_admin(self, ctx: commands.Context, task_id: str):
        """Cancel a scheduled task by its ID (admin override)."""
        task = self.db.scheduled_tasks.get(task_id)
        if not task:
            return await ctx.send(_("No scheduled task found with ID `{}`.").format(task_id))
        if task.guild_id != ctx.guild.id:
            return await ctx.send(_("That task belongs to a different server."))

        job_id = f"task_{task_id}"
        job = self.scheduler.get_job(job_id)
        if job:
            job.remove()

        del self.db.scheduled_tasks[task_id]
        await self.save_conf()
        await ctx.send(_("Scheduled task `{}` has been cancelled.").format(task_id))

    @scheduler.command(name="clear")
    @commands.guild_only()
    @commands.admin_or_permissions(administrator=True)
    async def clear_all_tasks(self, ctx: commands.Context, yes_or_no: bool):
        """Clear all scheduled tasks in this server."""
        if not yes_or_no:
            return await ctx.send(_("Not clearing tasks."))

        task_ids = [tid for tid, t in self.db.scheduled_tasks.items() if t.guild_id == ctx.guild.id]
        for tid in task_ids:
            job_id = f"task_{tid}"
            job = self.scheduler.get_job(job_id)
            if job:
                job.remove()
            del self.db.scheduled_tasks[tid]

        await self.save_conf()
        await ctx.send(_("Cleared {} scheduled tasks.").format(len(task_ids)))

    @compaction.command(name="toggle")
    async def compaction_toggle(self, ctx: commands.Context):
        """Toggle LLM-based conversation compaction on or off"""
        conf = self.db.get_conf(ctx.guild)
        if conf.compaction_enabled:
            conf.compaction_enabled = False
            await ctx.send(_("Conversation compaction is now **Disabled** (blind degradation will be used)"))
        else:
            conf.compaction_enabled = True
            await ctx.send(_("Conversation compaction is now **Enabled**"))
        await self.save_conf()

    @compaction.command(name="model")
    async def compaction_model(self, ctx: commands.Context, model: str = ""):
        """Set the model used for compaction (leave blank to use the chat model)"""
        conf = self.db.get_conf(ctx.guild)
        has_endpoint = bool(self.db.endpoint_override or conf.endpoint_override)
        if not model:
            conf.compaction_model = ""
            await ctx.send(_("Compaction model cleared, the main chat model will be used"))
        elif not has_endpoint and model not in MODELS:
            return await ctx.send(_("Invalid model, valid models are: {}").format(humanize_list(MODELS)))
        else:
            conf.compaction_model = model
            await ctx.send(_("Compaction model set to **{}**").format(model))
        await self.save_conf()

    @compaction.command(name="threshold")
    async def compaction_threshold(self, ctx: commands.Context, token_limit: int = 0):
        """Set the token threshold at which compaction triggers

        When set, the bot will proactively compact conversations once they
        exceed this many tokens, even if the model's context window is larger.

        Set to **0** to only compact when hitting the model's max token limit.

        **Examples**
        - `[p]assistant compaction threshold 16000` - compact at 16k tokens
        - `[p]assistant compaction threshold 0` - reset to default behavior
        """
        if token_limit < 0:
            return await ctx.send(_("Token limit must be 0 or higher"))
        conf = self.db.get_conf(ctx.guild)
        conf.compaction_threshold = token_limit
        if token_limit:
            await ctx.send(_("Compaction will now trigger at **{}** tokens").format(humanize_number(token_limit)))
        else:
            await ctx.send(_("Compaction threshold reset, will only compact at the model's max token limit"))
        await self.save_conf()
