import asyncio
import inspect
import json
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
import discord
import orjson
import tiktoken
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.create_embedding_response import CreateEmbeddingResponse
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from .calls import request_chat_completion_raw, request_embedding_raw
from .constants import (
    COMPACTION_KEEP_RECENT,
    COMPACTION_SUMMARY_ROLE,
    COMPACTION_SYSTEM_PROMPT,
    MEMORY_CONSOLIDATION_PROMPT,
    MEMORY_FLUSH_PROMPT,
    MODELS,
    SUPPORTS_VISION,
    VISION_COSTS,
)
from .models import (
    Conversation,
    EndpointModelProfile,
    EndpointProfile,
    GuildSettings,
    UserMemory,
)

log = logging.getLogger("red.vrt.assistant.api")
_ = Translator("Assistant", __file__)
ENDPOINT_PROFILE_TTL_SECONDS = 300


@cog_i18n(_)
class API(MixinMeta):
    def get_api_key(self, conf: GuildSettings) -> str:
        """Return the effective API key for a guild.

        If the guild has its own key, use that.  Otherwise, if a global
        endpoint override is configured, use the owner-configured endpoint
        key if available. Fall back to a placeholder so the openai client
        doesn't reject a ``None`` key for endpoints that don't validate it.
        """
        if conf.api_key:
            return conf.api_key
        if self.db.endpoint_override:
            return self.db.endpoint_api_key or "n/a"
        return ""

    def get_cached_endpoint_profile(self) -> Optional[EndpointProfile]:
        profile = self.db.endpoint_profile
        if not self.db.endpoint_override or not profile:
            return None
        if profile.base_url != self.db.endpoint_override:
            return None
        return profile

    def clear_endpoint_profile(self) -> None:
        self.db.endpoint_profile = None

    def resolve_chat_model(self, requested_model: str) -> str:
        if not self.db.endpoint_override:
            return requested_model
        profile = self.get_cached_endpoint_profile()
        if not profile:
            return requested_model
        if requested_model in profile.chat_models:
            return requested_model
        if profile.provider == "lmstudio" and profile.active_chat_model:
            return profile.active_chat_model
        return requested_model

    def resolve_embedding_model(self, requested_model: str) -> str:
        if not self.db.endpoint_override:
            return requested_model
        profile = self.get_cached_endpoint_profile()
        if not profile:
            return requested_model
        if requested_model in profile.embedding_models:
            return requested_model
        if profile.provider == "lmstudio" and profile.active_embedding_model:
            return profile.active_embedding_model
        return requested_model

    def describe_endpoint_profile(self, profile: EndpointProfile) -> str:
        chat_model = profile.active_chat_model or _("Unknown")
        embed_model = profile.active_embedding_model or _("Unknown")
        chat_info = profile.chat_models.get(profile.active_chat_model) if profile.active_chat_model else None
        vision = chat_info.supports_vision if chat_info else None
        reasoning = chat_info.supports_reasoning if chat_info else None
        max_context = chat_info.max_context_length if chat_info else 0
        lines = [
            _("`Provider:           `{}").format(profile.provider),
            _("`Runtime Chat Model: `{}").format(chat_model),
            _("`Runtime Embed Model:`{}").format(embed_model),
            _("`Vision:             `{}").format(vision if vision is not None else _("Unknown")),
            _("`Reasoning:          `{}").format(reasoning if reasoning is not None else _("Unknown")),
            _("`Max Context:        `{}").format(humanize_number(max_context) if max_context else _("Unknown")),
            _("`Embed Dimensions:   `{}").format(
                humanize_number(profile.active_embedding_dimensions) if profile.active_embedding_dimensions else _("Unknown")
            ),
            _("`Models Discovered:  `{}").format(humanize_number(len(profile.available_models))),
        ]
        return "\n".join(lines)

    def observe_chat_runtime(self, model_id: str, message: Optional[ChatCompletionMessage] = None) -> None:
        if not self.db.endpoint_override or not model_id:
            return
        profile = self.get_cached_endpoint_profile()
        if not profile:
            return
        entry = profile.chat_models.get(model_id) or EndpointModelProfile(id=model_id, kind="llm")
        entry.loaded = True
        if message is not None and isinstance(getattr(message, "reasoning_content", None), str):
            entry.supports_reasoning = True
        profile.chat_models[model_id] = entry
        profile.active_chat_model = model_id
        if model_id not in profile.available_models:
            profile.available_models.append(model_id)

    def observe_embedding_runtime(self, model_id: str, dimensions: int) -> None:
        if not self.db.endpoint_override or not model_id:
            return
        profile = self.get_cached_endpoint_profile()
        if not profile:
            return
        entry = profile.embedding_models.get(model_id) or EndpointModelProfile(id=model_id, kind="embedding")
        entry.loaded = True
        profile.embedding_models[model_id] = entry
        profile.active_embedding_model = model_id
        profile.active_embedding_dimensions = dimensions
        if model_id not in profile.available_models:
            profile.available_models.append(model_id)

    async def refresh_endpoint_profile(self, force: bool = False, save: bool = False) -> Optional[EndpointProfile]:
        if not self.db.endpoint_override:
            self.clear_endpoint_profile()
            if save:
                await self.save_conf()
            return None

        cached = self.get_cached_endpoint_profile()
        if cached and not force:
            age = (datetime.now(tz=timezone.utc) - cached.discovered_at).total_seconds()
            if age < ENDPOINT_PROFILE_TTL_SECONDS:
                return cached

        profile = await self.probe_endpoint_profile(self.db.endpoint_override)
        if profile is None:
            return cached

        self.db.endpoint_profile = profile
        if save:
            await self.save_conf()
        return profile

    async def probe_endpoint_profile(self, base_url: str) -> Optional[EndpointProfile]:
        headers = {}
        if self.db.endpoint_api_key:
            headers["Authorization"] = f"Bearer {self.db.endpoint_api_key}"

        timeout = aiohttp.ClientTimeout(total=5)
        root_url = base_url.rstrip("/")
        native_root = root_url[:-3] if root_url.endswith("/v1") else root_url

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            native_url = f"{native_root}/api/v1/models"
            try:
                async with session.get(native_url) as res:
                    if res.ok:
                        data = await res.json()
                        models = data.get("models") if isinstance(data, dict) else None
                        if isinstance(models, list):
                            return self.parse_lmstudio_profile(base_url, models)
            except Exception as e:
                log.debug("Native endpoint probe failed for %s", native_url, exc_info=e)

            compat_url = f"{root_url}/models"
            try:
                async with session.get(compat_url) as res:
                    if not res.ok:
                        return None
                    data = await res.json()
                    items = data.get("data") if isinstance(data, dict) else None
                    if isinstance(items, list):
                        return self.parse_openai_compatible_profile(base_url, items)
            except Exception as e:
                log.debug("OpenAI-compatible model probe failed for %s", compat_url, exc_info=e)

        return None

    def parse_lmstudio_profile(self, base_url: str, models: list[dict]) -> EndpointProfile:
        profile = EndpointProfile(base_url=base_url, provider="lmstudio")
        for model in models:
            model_id = model.get("key")
            if not model_id:
                continue

            capabilities = model.get("capabilities") or {}
            loaded_instances = model.get("loaded_instances") or []
            loaded_config = loaded_instances[0].get("config", {}) if loaded_instances else {}
            entry = EndpointModelProfile(
                id=model_id,
                kind=model.get("type", "llm"),
                loaded=bool(loaded_instances),
                max_context_length=loaded_config.get("context_length", 0) or model.get("max_context_length", 0) or 0,
                supports_vision=capabilities.get("vision"),
                supports_reasoning=bool(capabilities.get("reasoning")) if "reasoning" in capabilities else None,
                supports_tools=capabilities.get("trained_for_tool_use"),
            )
            profile.available_models.append(model_id)
            if entry.kind == "embedding":
                profile.embedding_models[model_id] = entry
                if entry.loaded and not profile.active_embedding_model:
                    profile.active_embedding_model = model_id
            else:
                profile.chat_models[model_id] = entry
                if entry.loaded and not profile.active_chat_model:
                    profile.active_chat_model = model_id

        if not profile.active_chat_model and len(profile.chat_models) == 1:
            profile.active_chat_model = next(iter(profile.chat_models))
        if not profile.active_embedding_model and len(profile.embedding_models) == 1:
            profile.active_embedding_model = next(iter(profile.embedding_models))
        return profile

    def parse_openai_compatible_profile(self, base_url: str, items: list[dict]) -> EndpointProfile:
        provider = "llamacpp" if any(item.get("owned_by") == "llamacpp" for item in items) else "openai-compatible"
        profile = EndpointProfile(base_url=base_url, provider=provider)
        for item in items:
            model_id = item.get("id")
            if not model_id:
                continue
            lower = model_id.lower()
            is_embedding = "embedding" in lower or "embed" in lower
            entry = EndpointModelProfile(id=model_id, kind="embedding" if is_embedding else "llm")
            profile.available_models.append(model_id)
            if is_embedding:
                profile.embedding_models[model_id] = entry
            else:
                profile.chat_models[model_id] = entry

        if len(profile.chat_models) == 1:
            profile.active_chat_model = next(iter(profile.chat_models))
        if len(profile.embedding_models) == 1:
            profile.active_embedding_model = next(iter(profile.embedding_models))
        return profile

    async def endpoint_supports_vision(
        self,
        conf: GuildSettings,
        user: Optional[discord.Member] = None,
        requested_model: Optional[str] = None,
    ) -> bool:
        model = requested_model or conf.get_user_model(user)
        if not self.db.endpoint_override:
            return model in SUPPORTS_VISION

        profile = await self.refresh_endpoint_profile()
        if profile:
            requested = profile.chat_models.get(model)
            if requested and requested.supports_vision is not None:
                return bool(requested.supports_vision)
            if profile.active_chat_model:
                active = profile.chat_models.get(profile.active_chat_model)
                if active and active.supports_vision is not None:
                    return bool(active.supports_vision)

        # Default to permissive for custom endpoints so we do not silently drop images.
        return True

    async def openai_status(self) -> str:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url="https://status.openai.com/api/v2/status.json") as res:
                    data = await res.json()
                    status = data["status"]["description"]
                    # ind = data["status"]["indicator"]
        except Exception as e:
            log.error("Failed to fetch OpenAI API status", exc_info=e)
            status = _("Failed to fetch: {}").format(str(e))
        return status

    async def request_response(
        self,
        messages: List[dict],
        conf: GuildSettings,
        functions: Optional[List[dict]] = None,
        member: Optional[discord.Member] = None,
        response_token_override: int = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
    ) -> ChatCompletionMessage:
        requested_model = model_override or conf.get_user_model(member)
        if self.db.endpoint_override:
            await self.refresh_endpoint_profile()
        model = self.resolve_chat_model(requested_model)

        max_convo_tokens = self.get_max_tokens(conf, member)
        max_response_tokens = conf.get_user_max_response_tokens(member)

        current_convo_tokens = await self.count_payload_tokens(messages, model)
        if functions:
            current_convo_tokens += await self.count_function_tokens(functions, model)

        # Dynamically adjust to lower model to save on cost
        if "-16k" in model and current_convo_tokens < 3000:
            model = model.replace("-16k", "")
        if "-32k" in model and current_convo_tokens < 4000:
            model = model.replace("-32k", "")

        max_model_tokens = MODELS.get(model)

        # Ensure that user doesn't set max response tokens higher than model can handle
        if response_token_override:
            response_tokens = response_token_override
        else:
            response_tokens = 0  # Dynamic
            if max_response_tokens:
                # Calculate max response tokens
                response_tokens = max(max_convo_tokens - current_convo_tokens, 0)
                # If current convo exceeds the max convo tokens for that user, use max model tokens
                if not response_tokens and max_model_tokens:
                    response_tokens = max(max_model_tokens - current_convo_tokens, 0)
                # Use the lesser of caculated vs set response tokens
                response_tokens = min(response_tokens, max_response_tokens)

        if model not in MODELS and self.db.endpoint_override is None:
            log.error(f"This model is no longer supported: {model}. Switching to gpt-5.4")
            model = "gpt-5.4"
            await self.save_conf()

        response: ChatCompletion = await request_chat_completion_raw(
            model=model,
            messages=messages,
            temperature=temperature_override if temperature_override is not None else conf.temperature,
            api_key=self.get_api_key(conf),
            max_tokens=response_tokens,
            functions=functions,
            frequency_penalty=conf.frequency_penalty,
            presence_penalty=conf.presence_penalty,
            seed=conf.seed,
            base_url=self.db.endpoint_override,
            reasoning_effort=conf.get_user_reasoning_effort(member),
            verbosity=conf.verbosity,
        )
        message: ChatCompletionMessage = response.choices[0].message

        if response.usage:
            conf.update_usage(
                response.model,
                response.usage.total_tokens,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        self.observe_chat_runtime(response.model, message)
        log.debug(f"MESSAGE TYPE: {type(message)}")
        return message

    async def request_embedding_with_info(self, text: str, conf: GuildSettings) -> tuple[List[float], str]:
        if self.db.endpoint_override:
            await self.refresh_endpoint_profile()
        requested_model = self.resolve_embedding_model(conf.embed_model)
        response: CreateEmbeddingResponse = await request_embedding_raw(
            text=text,
            api_key=self.get_api_key(conf),
            model=requested_model,
            base_url=self.db.endpoint_override,
        )

        if response.usage:
            conf.update_usage(
                response.model,
                response.usage.total_tokens,
                response.usage.prompt_tokens,
                0,
            )
        embedding = response.data[0].embedding
        observed_model = response.model or requested_model
        self.observe_embedding_runtime(observed_model, len(embedding))
        return embedding, observed_model

    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        embedding, __ = await self.request_embedding_with_info(text, conf)
        return embedding

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- HELPERS -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    async def count_payload_tokens(self, messages: List[dict], model: str = "gpt-5.1") -> int:
        if not messages:
            return 0

        def _count_payload():
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("o200k_base")

            tokens_per_message = 3
            tokens_per_name = 1
            num_tokens = 0
            for message in messages:
                num_tokens += tokens_per_message
                for key, value in message.items():
                    if key == "name":
                        num_tokens += tokens_per_name

                    if key == "content" and isinstance(value, list):
                        for item in value:
                            if item["type"] == "text":
                                num_tokens += len(encoding.encode(item["text"]))
                            elif item["type"] == "image_url":
                                num_tokens += VISION_COSTS.get(model, [1000])[
                                    0
                                ]  # Just assume around 1k tokens for images
                    else:  # String, probably
                        num_tokens += len(encoding.encode(str(value)))

            num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
            return num_tokens

        return await asyncio.to_thread(_count_payload)

    async def count_function_tokens(self, functions: List[dict], model: str = "gpt-5.1") -> int:
        # Initialize function settings to 0
        func_init = 0
        prop_init = 0
        prop_key = 0
        enum_init = 0
        enum_item = 0
        func_end = 0

        if model in [
            "gpt-4o",
            "gpt-4o-2024-05-13",
            "gpt-4o-2024-08-06",
            "gpt-4o-2024-11-20",
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
            "gpt-4.1",
            "gpt-4.1-2025-04-14",
            "gpt-4.1-mini",
            "gpt-4.1-mini-2025-04-14",
            "gpt-4.1-nano",
            "gpt-4.1-nano-2025-04-14",
            "o1-preview",
            "o1-preview-2024-09-12",
            "o1",
            "o1-2024-12-17",
            "o1-mini",
            "o1-mini-2024-09-12",
            "o3-mini",
            "o3-mini-2025-01-31",
            "o3",
            "o3-2025-04-16",
            "gpt-5",
            "gpt-5-2025-04-16",
            "gpt-5-mini",
            "gpt-5-mini-2025-04-16",
            "gpt-5-nano",
            "gpt-5-nano-2025-04-16",
            "gpt-5.1",
            "gpt-5.1-2025-11-13",
            "gpt-5.2",
            "gpt-5.2-2025-12-11",
            "gpt-5.4",
            "gpt-5.4-2026-03-05",
            "gpt-5.4-mini",
            "gpt-5.4-mini-2026-03-17",
            "gpt-5.4-nano",
            "gpt-5.4-nano-2026-03-17",
        ]:
            # Set function settings for the above models
            func_init = 7
            prop_init = 3
            prop_key = 3
            enum_init = -3
            enum_item = 3
            func_end = 12
        elif model in [
            "gpt-3.5-turbo-1106",
            "gpt-3.5-turbo-0125",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4-0125-preview",
            "gpt-4-1106-preview",
        ]:
            # Set function settings for the above models
            func_init = 10
            prop_init = 3
            prop_key = 3
            enum_init = -3
            enum_item = 3
            func_end = 12
        else:
            log.warning(f"Incompatible model: {model}")

        def _count_tokens():
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("o200k_base")

            func_token_count = 0

            if len(functions) > 0:
                for f in functions:
                    if "function" not in f.keys():
                        f = {"function": f, "name": f["name"], "description": f["description"]}
                    func_token_count += func_init  # Add tokens for start of each function
                    function = f["function"]
                    f_name = function["name"]
                    f_desc = function["description"]
                    if f_desc.endswith("."):
                        f_desc = f_desc[:-1]
                    line = f_name + ":" + f_desc
                    func_token_count += len(encoding.encode(line))  # Add tokens for set name and description
                    if len(function["parameters"]["properties"]) > 0:
                        func_token_count += prop_init  # Add tokens for start of each property
                        for key in list(function["parameters"]["properties"].keys()):
                            func_token_count += prop_key  # Add tokens for each set property
                            p_name = key
                            p_type = function["parameters"]["properties"][key].get("type", "")
                            p_desc = function["parameters"]["properties"][key].get("description", "")
                            if "enum" in function["parameters"]["properties"][key].keys():
                                func_token_count += enum_init  # Add tokens if property has enum list
                                for item in function["parameters"]["properties"][key]["enum"]:
                                    func_token_count += enum_item
                                    func_token_count += len(encoding.encode(item))
                            if p_desc.endswith("."):
                                p_desc = p_desc[:-1]
                            line = f"{p_name}:{p_type}:{p_desc}"
                            func_token_count += len(encoding.encode(line))
                func_token_count += func_end
            return func_token_count

        return await asyncio.to_thread(_count_tokens)

    async def get_tokens(self, text: str, model: str = "gpt-5.1") -> list[int]:
        """Get token list from text"""
        if not text:
            log.debug("No text to get tokens from!")
            return []
        if isinstance(text, bytes):
            text = text.decode(encoding="utf-8")

        def _get_encoding():
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("o200k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding)

        return await asyncio.to_thread(encoding.encode, text)

    async def count_tokens(self, text: str, model: str) -> int:
        if not text:
            log.debug("No text to get token count from!")
            return 0
        try:
            tokens = await self.get_tokens(text, model)
            return len(tokens)
        except TypeError as e:
            log.error(f"Failed to count tokens for: {text}", exc_info=e)
            return 0

    async def can_call_llm(self, conf: GuildSettings, ctx: Optional[commands.Context] = None) -> bool:
        if not conf.api_key and not self.db.endpoint_override:
            if ctx:
                txt = _("No model API key or endpoint override is configured!\n")
                if ctx.author.id == ctx.guild.owner_id:
                    txt += _("- Set this server's API key with `{}`\n").format(f"{ctx.clean_prefix}assist openaikey")
                await ctx.send(txt)
            return False
        return True

    async def resync_embeddings(self, conf: GuildSettings, guild_id: int) -> int:
        """Re-embed all entries using the current embedding model.

        Handles dimension mismatches by recreating the collection.
        """
        all_data = await self.embedding_store.get_all_with_embeddings(guild_id)
        if not all_data:
            return 0

        first_name, first_meta = next(iter(all_data.items()))
        probe_text = first_meta.get("text", "")
        probe_embed, observed_model = await self.request_embedding_with_info(probe_text, conf)
        if not probe_embed:
            return 0

        current_dims = len(probe_embed)
        stored_dims = {len(meta.get("embedding", [])) for meta in all_data.values() if meta.get("embedding")}
        stored_models = {meta.get("model") for meta in all_data.values() if meta.get("model")}

        dimension_changed = bool(stored_dims) and (len(stored_dims) > 1 or current_dims not in stored_dims)
        model_changed = bool(stored_models) and observed_model not in stored_models

        if dimension_changed or model_changed:
            entries_to_sync = [(name, meta.get("text", "")) for name, meta in all_data.items()]
        else:
            entries_to_sync = []
            for name, meta in all_data.items():
                if not meta.get("embedding"):
                    entries_to_sync.append((name, meta.get("text", "")))
                    continue
                if len(meta.get("embedding", [])) != current_dims:
                    entries_to_sync.append((name, meta.get("text", "")))
                    continue
                if meta.get("model") != observed_model:
                    entries_to_sync.append((name, meta.get("text", "")))

        if not entries_to_sync:
            return 0

        # Re-embed in parallel
        results: dict[str, tuple[list[float], str]] = {first_name: (probe_embed, observed_model)} if first_name in dict(entries_to_sync) else {}

        async def _embed(name: str, text: str):
            vec, model = await self.request_embedding_with_info(text, conf)
            if vec:
                results[name] = (vec, model)

        await asyncio.gather(*[_embed(n, t) for n, t in entries_to_sync if n not in results])

        if not results:
            return 0

        if dimension_changed:
            # Recreate collection and re-add everything
            await self.embedding_store.recreate_collection(guild_id)
            for name, meta in all_data.items():
                vec, model = results.get(name, (meta.get("embedding", []), meta.get("model") or observed_model))
                if not vec:
                    continue
                await self.embedding_store.add(
                    guild_id,
                    name,
                    meta.get("text", ""),
                    vec,
                    model,
                    meta.get("ai_created", False),
                )
        else:
            # Just update the changed entries
            for name, (vec, model) in results.items():
                meta = all_data[name]
                await self.embedding_store.update(
                    guild_id,
                    name,
                    meta.get("text", ""),
                    vec,
                    model,
                )

        await self.save_conf()
        return len(results)

    def get_max_tokens(self, conf: GuildSettings, user: Optional[discord.Member]) -> int:
        user_max = conf.get_user_max_tokens(user)
        model = conf.get_user_model(user)
        max_model_tokens = MODELS.get(model)
        if max_model_tokens is None:
            if self.db.endpoint_override:
                return user_max
            max_model_tokens = 4000
        if not user_max or user_max > max_model_tokens:
            return max_model_tokens
        return user_max

    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, user: Optional[discord.Member] = None) -> str:
        if not text:
            log.debug("No text to cut by tokens!")
            return text
        tokens = await self.get_tokens(text, conf.get_user_model(user))
        return await self.get_text(tokens[: self.get_max_tokens(conf, user)], conf.get_user_model(user))

    async def get_text(self, tokens: list, model: str = "gpt-5.1") -> str:
        """Get text from token list"""

        def _get_encoding():
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("o200k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding)

        return await asyncio.to_thread(encoding.decode, tokens)

    # -------------------------------------------------------
    # -------------------------------------------------------
    # -------------------- FORMATTING -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------
    async def compact_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
        conversation: Optional[Conversation] = None,
        focus: str = "",
    ) -> bool:
        """Summarize older messages via LLM, falling back to degrade_conversation on failure"""
        model = conf.get_user_model(user)
        max_tokens = self.get_max_tokens(conf, user)
        threshold = conf.compaction_threshold or max_tokens
        convo_tokens = await self.count_payload_tokens(messages, model)
        func_tokens = await self.count_function_tokens(function_list, model)
        total_tokens = convo_tokens + func_tokens

        if total_tokens <= threshold:
            return False

        # If compaction is disabled, fall back to blind degradation
        if not conf.compaction_enabled:
            return await self.degrade_conversation(messages, function_list, conf, user)

        # Separate system/developer messages from conversation messages
        system_msgs = [m for m in messages if m.get("role") in ("system", "developer")]
        convo_msgs = [m for m in messages if m.get("role") not in ("system", "developer")]

        if len(convo_msgs) <= COMPACTION_KEEP_RECENT:
            # Too few messages to compact — fall back to degradation
            return await self.degrade_conversation(messages, function_list, conf, user)

        # Find the split point, respecting tool-call/result pairs
        split_idx = len(convo_msgs) - COMPACTION_KEEP_RECENT
        split_idx = self.find_safe_split(convo_msgs, split_idx)

        if split_idx <= 0:
            return await self.degrade_conversation(messages, function_list, conf, user)

        old_messages = convo_msgs[:split_idx]
        recent_messages = convo_msgs[split_idx:]

        # Build a text representation of old messages for the summarizer
        old_text = self.messages_to_text(old_messages)
        if not old_text.strip():
            return await self.degrade_conversation(messages, function_list, conf, user)

        # Call the LLM to summarize
        compaction_model = conf.compaction_model or model
        summary_prompt = COMPACTION_SYSTEM_PROMPT
        if focus:
            summary_prompt += f"\n\nFocus the summary on: {focus}"

        try:
            summary_messages = [
                {"role": "developer", "content": summary_prompt},
                {"role": "user", "content": old_text},
            ]
            if self.db.endpoint_override:
                for m in summary_messages:
                    if m["role"] == "developer":
                        m["role"] = "system"
            response = await request_chat_completion_raw(
                model=compaction_model,
                messages=summary_messages,
                temperature=0.0,
                api_key=self.get_api_key(conf),
                max_tokens=1000,
                functions=None,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                seed=None,
                base_url=self.db.endpoint_override,
            )
            summary_text = response.choices[0].message.content
            if response.usage:
                conf.update_usage(
                    response.model,
                    response.usage.total_tokens,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )
        except Exception as e:
            log.warning(f"Compaction LLM call failed, falling back to degradation: {e}")
            return await self.degrade_conversation(messages, function_list, conf, user)

        if not summary_text or not summary_text.strip():
            log.warning("Compaction returned empty summary, falling back to degradation")
            return await self.degrade_conversation(messages, function_list, conf, user)

        # Replace messages in-place: system msgs + summary + recent messages
        summary_msg = {
            "role": COMPACTION_SUMMARY_ROLE,
            "content": f"[Conversation Summary — compacted from {len(old_messages)} earlier messages]\n{summary_text}",
        }

        messages.clear()
        messages.extend(system_msgs)
        messages.append(summary_msg)
        messages.extend(recent_messages)

        if conversation:
            conversation.compaction_count += 1

        log.info(
            f"Compacted conversation for {user}: "
            f"removed {len(old_messages)} messages, "
            f"summary ~{len(summary_text)} chars, "
            f"kept {len(recent_messages)} recent messages"
        )
        return True

    async def flush_memory_before_compaction(
        self,
        messages: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
        guild: discord.Guild,
    ) -> None:
        """Extract and store important user facts from messages about to be compacted"""
        if not user or not conf.memory_flush_on_compaction:
            return
        if not conf.use_function_calls:
            return

        convo_msgs = [m for m in messages if m.get("role") not in ("system", "developer")]
        if len(convo_msgs) <= COMPACTION_KEEP_RECENT:
            return

        split_idx = len(convo_msgs) - COMPACTION_KEEP_RECENT
        split_idx = self.find_safe_split(convo_msgs, split_idx)
        if split_idx <= 0:
            return

        old_text = self.messages_to_text(convo_msgs[:split_idx])
        if not old_text.strip():
            return

        # Check existing memories so we don't duplicate
        memory_key = f"{guild.id}-{user.id}"
        existing = self.db.user_memories.get(memory_key)
        existing_facts = "\n".join(f"- {f}" for f in existing.facts) if existing and existing.facts else "None"

        flush_prompt = MEMORY_FLUSH_PROMPT.format(existing_facts=existing_facts)

        try:
            flush_model = conf.compaction_model or conf.get_user_model(user)
            flush_messages = [
                {"role": "developer", "content": flush_prompt},
                {"role": "user", "content": old_text},
            ]
            if self.db.endpoint_override:
                for m in flush_messages:
                    if m["role"] == "developer":
                        m["role"] = "system"
            response = await request_chat_completion_raw(
                model=flush_model,
                messages=flush_messages,
                temperature=0.0,
                api_key=self.get_api_key(conf),
                max_tokens=500,
                functions=None,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                seed=None,
                base_url=self.db.endpoint_override,
            )
            result_text = response.choices[0].message.content or ""
            if response.usage:
                conf.update_usage(
                    response.model,
                    response.usage.total_tokens,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )

            # Parse the JSON array of facts
            result_text = result_text.strip()
            # Handle markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            facts = orjson.loads(result_text)
            if not isinstance(facts, list):
                return

            if memory_key not in self.db.user_memories:
                self.db.user_memories[memory_key] = UserMemory(user_id=user.id, guild_id=guild.id)

            memory = self.db.user_memories[memory_key]
            added = 0
            for fact in facts:
                if not isinstance(fact, str) or not fact.strip():
                    continue
                # Avoid exact duplicates
                if fact.strip() not in memory.facts:
                    memory.facts.append(fact.strip())
                    added += 1

            if added:
                memory.updated_at = datetime.now(tz=timezone.utc)
                log.info(f"Memory flush stored {added} new facts for {user} before compaction")

            # If we're now over the cap, trigger consolidation
            max_facts = conf.get_user_max_memory_facts(user)
            if max_facts and len(memory.facts) > max_facts:
                await self.consolidate_user_memory(guild, user, conf)

        except Exception as e:
            log.debug(f"Memory flush failed (non-critical): {e}")

    async def consolidate_user_memory(
        self,
        guild: discord.Guild,
        user: discord.Member,
        conf: GuildSettings,
    ) -> bool:
        """Consolidate a user's facts via LLM when nearing the cap.

        Merges redundant facts, drops low-value ones, and targets ~75% of the cap.
        Returns True if consolidation was performed.
        """
        memory_key = f"{guild.id}-{user.id}"
        memory = self.db.user_memories.get(memory_key)
        if not memory or not memory.facts:
            return False

        max_facts = conf.get_user_max_memory_facts(user)
        if not max_facts or len(memory.facts) < max_facts:
            return False

        target_count = max(5, int(max_facts * 0.75))
        facts_list = "\n".join(f"{i + 1}. {fact}" for i, fact in enumerate(memory.facts))

        prompt = MEMORY_CONSOLIDATION_PROMPT.format(
            target_count=target_count,
            current_count=len(memory.facts),
            facts_list=facts_list,
        )

        try:
            model = conf.compaction_model or conf.get_user_model(user)
            consolidation_messages = [
                {"role": "developer", "content": prompt},
            ]
            if self.db.endpoint_override:
                for m in consolidation_messages:
                    if m["role"] == "developer":
                        m["role"] = "system"
            response = await request_chat_completion_raw(
                model=model,
                messages=consolidation_messages,
                temperature=0.0,
                api_key=self.get_api_key(conf),
                max_tokens=2000,
                functions=None,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                seed=None,
                base_url=self.db.endpoint_override,
            )
            result_text = response.choices[0].message.content or ""
            if response.usage:
                conf.update_usage(
                    response.model,
                    response.usage.total_tokens,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )

            result_text = result_text.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            new_facts = orjson.loads(result_text)
            if not isinstance(new_facts, list):
                return False

            # Validate all entries are non-empty strings
            new_facts = [f.strip() for f in new_facts if isinstance(f, str) and f.strip()]
            if not new_facts:
                return False

            before_count = len(memory.facts)
            memory.facts = new_facts
            memory.updated_at = datetime.now(tz=timezone.utc)

            log.info(f"Memory consolidation for {user} in {guild}: {before_count} -> {len(new_facts)} facts")
            return True

        except Exception as e:
            log.debug(f"Memory consolidation failed (non-critical): {e}")
            return False

    def find_safe_split(self, messages: List[dict], target_idx: int) -> int:
        """Walk backward from target_idx to avoid splitting tool-call/result pairs"""
        idx = target_idx
        while idx > 0:
            msg = messages[idx - 1]
            # If the message right before the split is an assistant with tool_calls,
            # the results are on the other side — move the split back
            if msg.get("role") == "assistant" and (msg.get("tool_calls") or msg.get("function_call")):
                idx -= 1
                continue
            # If the message right at the split is a tool/function result, its
            # associated assistant call is before the split — move back
            if idx < len(messages) and messages[idx].get("role") in ("tool", "function"):
                idx -= 1
                continue
            break
        return idx

    def messages_to_text(self, messages: List[dict]) -> str:
        """Convert message dicts to a plain-text transcript for summarization"""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if item.get("type") == "text":
                        parts.append(item["text"])
                    elif item.get("type") == "image_url":
                        parts.append("[image]")
                content = " ".join(parts)
            elif not isinstance(content, str):
                content = str(content)

            # Include tool call info if present
            if msg.get("tool_calls"):
                calls = msg["tool_calls"]
                call_names = []
                for c in calls:
                    if isinstance(c, dict) and "function" in c:
                        call_names.append(c["function"].get("name", "unknown"))
                if call_names:
                    content = f"[called: {', '.join(call_names)}] {content}"
            elif msg.get("function_call"):
                fc = msg["function_call"]
                if isinstance(fc, dict):
                    content = f"[called: {fc.get('name', 'unknown')}] {content}"

            name = msg.get("name", "")
            if name:
                lines.append(f"{role} ({name}): {content}")
            elif msg.get("tool_call_id"):
                lines.append(f"{role} [result]: {content}")
            else:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def degrade_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
    ) -> bool:
        """Last-resort fallback: remove oldest messages to fit within token limit"""
        model = conf.get_user_model(user)
        max_tokens = self.get_max_tokens(conf, user)
        convo_tokens = await self.count_payload_tokens(messages, model)
        function_tokens = await self.count_function_tokens(function_list, model)

        total_tokens = convo_tokens + function_tokens

        if total_tokens <= max_tokens:
            return False

        log.debug(f"Degrading messages for {user} (total: {total_tokens}/max: {max_tokens})")

        def count(role: str):
            return sum(1 for msg in messages if msg["role"] == role)

        async def pop_with_pair(role: str) -> int:
            """Remove the oldest message of the given role plus its paired tool results."""
            for idx, msg in enumerate(messages):
                if msg["role"] != role:
                    continue
                # If this is an assistant message with tool_calls, also remove
                # all immediately following tool/function result messages
                indices_to_remove = [idx]
                if role == "assistant" and (msg.get("tool_calls") or msg.get("function_call")):
                    # Collect paired tool results
                    tool_ids = set()
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            if isinstance(tc, dict) and "id" in tc:
                                tool_ids.add(tc["id"])
                    j = idx + 1
                    while j < len(messages):
                        next_msg = messages[j]
                        if next_msg.get("role") in ("tool", "function"):
                            indices_to_remove.append(j)
                            j += 1
                        else:
                            break

                reduction = 0
                for remove_idx in sorted(indices_to_remove, reverse=True):
                    removed = messages.pop(remove_idx)
                    reduction += 4
                    if "name" in removed:
                        reduction += 1
                    if content := removed.get("content"):
                        if isinstance(content, list):
                            for i in content:
                                if i["type"] == "text":
                                    reduction += await self.count_tokens(i["text"], model)
                                else:
                                    reduction += 2
                        else:
                            reduction += await self.count_tokens(str(content), model)
                    elif tool_calls := removed.get("tool_calls"):
                        reduction += await self.count_tokens(str(tool_calls), model)
                    elif function_call := removed.get("function_call"):
                        reduction += await self.count_tokens(str(function_call), model)
                return reduction
            return 0

        iters = 0
        while True:
            iters += 1
            break_conditions = [
                count("user") <= 1,
                count("assistant") <= 1,
                iters > 100,
            ]
            if any(break_conditions):
                break
            # 1. Remove oldest tool/function result (with paired assistant call)
            reduced = await pop_with_pair("tool")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            reduced = await pop_with_pair("function")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # 2. Remove oldest assistant message (with paired tool results)
            reduced = await pop_with_pair("assistant")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # 3. Remove oldest user message
            reduced = await pop_with_pair("user")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break

        log.debug(f"Convo degradation finished for {user} (total: {total_tokens}/max: {max_tokens})")
        return True

    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        """Pagify a long string by tokens rather than characters"""
        if not text:
            log.debug("No text to pagify!")
            return []
        token_chunks = []
        tokens = await self.get_tokens(text)
        current_chunk = []

        max_tokens = conf.max_tokens - 100
        if not self.db.endpoint_override or conf.model in MODELS:
            max_tokens = min(max_tokens, MODELS.get(conf.model, 4000))
        for token in tokens:
            current_chunk.append(token)
            if len(current_chunk) == max_tokens:
                token_chunks.append(current_chunk)
                current_chunk = []

        if current_chunk:
            token_chunks.append(current_chunk)

        text_chunks = []
        for chunk in token_chunks:
            text = await self.get_text(chunk)
            text_chunks.append(text)

        return text_chunks

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- EMBEDS ------------------------
    # -------------------------------------------------------
    # -------------------------------------------------------
    async def get_function_menu_embeds(self, user: discord.Member) -> List[discord.Embed]:
        func_dump = {}
        for k, v in self.db.functions.items():
            d = v.model_dump(exclude_defaults=False)
            d.setdefault("required_permissions", [])
            func_dump[k] = d
        registry = {"Assistant-Custom": func_dump}
        for cog_name, function_schemas in self.registry.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for function_name, data in function_schemas.items():
                function_schema = data["schema"]
                function_obj = getattr(cog, function_name, None)
                if function_obj is None:
                    continue
                if cog_name not in registry:
                    registry[cog_name] = {}
                registry[cog_name][function_name] = {
                    "code": inspect.getsource(function_obj),
                    "jsonschema": function_schema,
                    "permission_level": data["permission_level"],
                    "required_permissions": list(data.get("required_permissions", [])),
                }

        conf = self.db.get_conf(user.guild)
        model = conf.get_user_model(user)

        pages = sum(len(v) for v in registry.values())
        page = 1
        embeds = []
        for cog_name, functions in registry.items():
            for function_name, data in functions.items():
                embed = discord.Embed(
                    title=_("Custom Functions"),
                    description=function_name,
                    color=discord.Color.blue(),
                )
                if cog_name != "Assistant-Custom":
                    embed.add_field(
                        name=_("3rd Party"),
                        value=_("This function is managed by the `{}` cog").format(cog_name),
                        inline=False,
                    )
                elif cog_name == "Assistant":
                    embed.add_field(
                        name=_("Internal Function"),
                        value=_("This is a built-in function managed by the Assistant cog"),
                        inline=False,
                    )
                schema = json.dumps(data["jsonschema"], indent=2)
                tokens = await self.count_tokens(schema, model)

                schema_text = _("This function consumes `{}` input tokens each call\n").format(humanize_number(tokens))

                if user.id in self.bot.owner_ids:
                    if len(schema) > 900:
                        schema_text += box(schema[:900] + "...", "py")
                    else:
                        schema_text += box(schema, "py")

                    if len(data["code"]) > 900:
                        code_text = box(data["code"][:900] + "...", "py")
                    else:
                        code_text = box(data["code"], "py")

                else:
                    schema_text += box(data["jsonschema"]["description"], "json")
                    code_text = box(_("Hidden..."))

                perm_text = data["permission_level"].capitalize()
                if data.get("required_permissions"):
                    perm_text += _("\nRequired: {}").format(", ".join(f"`{p}`" for p in data["required_permissions"]))
                embed.add_field(name=_("Permission Level"), value=perm_text, inline=False)
                embed.add_field(name=_("Schema"), value=schema_text, inline=False)
                embed.add_field(name=_("Code"), value=code_text, inline=False)

                embed.set_footer(text=_("Page {}/{}").format(page, pages))
                embeds.append(embed)
                page += 1

        if not embeds:
            embeds.append(
                discord.Embed(
                    description=_("No custom code has been added yet!"),
                    color=discord.Color.purple(),
                )
            )
        return embeds

    async def get_embedding_menu_embeds(self, guild_id: int, conf: GuildSettings, place: int) -> List[discord.Embed]:
        all_meta = await self.embedding_store.get_all_metadata(guild_id)
        embeddings = sorted(all_meta.items(), key=lambda x: x[0])
        embeds = []
        pages = math.ceil(len(embeddings) / 5)
        model = conf.get_user_model()
        start = 0
        stop = 5
        for page in range(pages):
            stop = min(stop, len(embeddings))
            embed = discord.Embed(title=_("Embeddings"), color=discord.Color.blue())
            embed.set_footer(text=_("Page {}/{}").format(page + 1, pages))
            num = 0
            for i in range(start, stop):
                name, meta = embeddings[i]
                raw_text = meta.get("text", "")
                tokens = await self.count_tokens(raw_text, model)
                text = box(f"{raw_text[:30].strip()}...") if len(raw_text) > 33 else box(raw_text.strip())

                created_str = meta.get("created", "")
                modified_str = meta.get("modified", "")
                dimensions = meta.get("dimensions", 0)
                ai_created = meta.get("ai_created", False)
                emb_model = meta.get("model", conf.embed_model)

                # Format timestamps
                created_display = (
                    f"<t:{int(datetime.fromisoformat(created_str).timestamp())}:R>" if created_str else "Unknown"
                )
                modified_display = (
                    f"<t:{int(datetime.fromisoformat(modified_str).timestamp())}:R>" if modified_str else "Unknown"
                )

                val = (
                    f"`Created:    `{created_display}\n"
                    f"`Modified:   `{modified_display}\n"
                    f"`Tokens:     `{tokens}\n"
                    f"`Dimensions: `{dimensions}\n"
                    f"`AI Created: `{ai_created}\n"
                    f"`Model:      `{emb_model}\n"
                )
                val += text
                fieldname = f"➣ {name}" if place == num else name
                embed.add_field(
                    name=fieldname[:250],
                    value=val,
                    inline=False,
                )
                num += 1
            embeds.append(embed)
            start += 5
            stop += 5
        if not embeds:
            embeds.append(discord.Embed(description=_("No embeddings have been added!"), color=discord.Color.purple()))
        return embeds
