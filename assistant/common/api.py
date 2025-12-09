import asyncio
import inspect
import json
import logging
import math
from typing import List, Optional

import aiohttp
import discord
import tiktoken
import openai
import ollama
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.create_embedding_response import CreateEmbeddingResponse
from ollama import ChatResponse as OllamaChatResponse
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from .calls import request_chat_completion_raw, request_embedding_raw
from .constants import MODELS, VISION_COSTS
from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.api")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class API(MixinMeta):
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
        model = model_override or conf.get_user_model(member)

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
            log.error(f"This model is no longer supported: {model}. Switching to gpt-5.1")
            model = "gpt-5.1"
            await self.save_conf()

        try:
            response = await request_chat_completion_raw(
                model=model,
                messages=messages,
                temperature=temperature_override if temperature_override is not None else conf.temperature,
                api_key=conf.api_key or "unprotected" if self.db.endpoint_override else conf.api_key,
                max_tokens=response_tokens,
                functions=functions,
                frequency_penalty=conf.frequency_penalty,
                presence_penalty=conf.presence_penalty,
                seed=conf.seed,
                base_url=self.db.endpoint_override,
                reasoning_effort=conf.reasoning_effort,
                verbosity=conf.verbosity,
            )
        except openai.OpenAIError as e:
            log.error("OpenAI chat completion failed", exc_info=e)
            raise commands.UserFeedbackCheckFailure(_("OpenAI request failed: {}").format(e)) from e
        except ollama.ResponseError as e:
            log.error("Ollama chat completion failed", exc_info=e)
            raise commands.UserFeedbackCheckFailure(_("Ollama request failed: {}").format(e)) from e
        except ollama.RequestError as e:
            log.error("Ollama chat request failed", exc_info=e)
            raise commands.UserFeedbackCheckFailure(_("Ollama request failed: {}").format(e)) from e

        if isinstance(response, ChatCompletion):
            message: ChatCompletionMessage = response.choices[0].message
            conf.update_usage(
                response.model,
                response.usage.total_tokens,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        elif isinstance(response, OllamaChatResponse):
            response_message = getattr(response, "message", {}) or {}
            role = getattr(response_message, "role", None)
            content = getattr(response_message, "content", None)
            if isinstance(response_message, dict):
                role = role or response_message.get("role")
                content = content or response_message.get("content")
            message = ChatCompletionMessage(
                role=role or "assistant",
                content=content,
            )
            prompt_tokens = getattr(response, "prompt_eval_count", 0) or 0
            completion_tokens = getattr(response, "eval_count", 0) or 0
            conf.update_usage(
                response.model,
                prompt_tokens + completion_tokens,
                prompt_tokens,
                completion_tokens,
            )
        else:
            raise commands.UserFeedbackCheckFailure(_("Unsupported response type from AI client."))

        log.debug(f"MESSAGE TYPE: {type(message)}")
        return message

    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        embed_model = conf.get_embed_model(self.db.endpoint_override)
        try:
            response = await request_embedding_raw(
                text=text,
                api_key=conf.api_key or "unprotected" if self.db.endpoint_override else conf.api_key,
                model=embed_model,
                base_url=self.db.endpoint_override,
            )
        except openai.OpenAIError as e:
            log.error("OpenAI embedding request failed", exc_info=e)
            raise commands.UserFeedbackCheckFailure(_("OpenAI embedding failed: {}").format(e)) from e
        except ollama.ResponseError as e:
            log.error("Ollama embedding request failed", exc_info=e)
            raise commands.UserFeedbackCheckFailure(_("Ollama embedding failed: {}").format(e)) from e
        except ollama.RequestError as e:
            log.error("Ollama embedding request failed", exc_info=e)
            raise commands.UserFeedbackCheckFailure(_("Ollama embedding failed: {}").format(e)) from e

        if isinstance(response, CreateEmbeddingResponse):
            conf.update_usage(
                response.model,
                response.usage.total_tokens,
                response.usage.prompt_tokens,
                0,
            )
            return response.data[0].embedding

        if hasattr(response, "embeddings"):
            embedding = response.embeddings[0] if response.embeddings else []
            conf.update_usage(response.model, 0, 0, 0)
            return embedding

        raise commands.UserFeedbackCheckFailure(_("Unsupported embedding response type from AI client."))

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
            # Custom endpoints (e.g., Ollama) can use arbitrary model names; avoid noisy warnings.
            if self.db.endpoint_override:
                log.debug(f"Incompatible model for custom endpoint: {model}")
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
        if self.db.endpoint_override:
            return True
        if not conf.api_key:
            if ctx:
                txt = _("There are no API keys set!\n")
                if ctx.author.id == ctx.guild.owner_id:
                    txt += _("- Set your OpenAI key with `{}`\n").format(f"{ctx.clean_prefix}assist openaikey")
                await ctx.send(txt)
            return False
        return True

    async def resync_embeddings(self, conf: GuildSettings, guild_id: int) -> int:
        """Update embeds to match current dimensions

        Takes a sample using current embed method, the updates the rest to match dimensions
        """
        if not conf.embeddings:
            return 0

        sample = list(conf.embeddings.values())[0]
        sample_embed = await self.request_embedding(sample.text, conf)
        target_model = conf.get_embed_model(self.db.endpoint_override)

        async def update_embedding(name: str, text: str):
            conf.embeddings[name].embedding = await self.request_embedding(text, conf)
            conf.embeddings[name].update()
            conf.embeddings[name].model = target_model
            log.debug(f"Updated embedding: {name}")

        synced = 0
        tasks = []
        for name, em in conf.embeddings.items():
            if target_model != em.model or len(em.embedding) != len(sample_embed):
                synced += 1
                tasks.append(update_embedding(name, em.text))

        if synced:
            await asyncio.gather(*tasks)
            await asyncio.to_thread(conf.sync_embeddings, guild_id)
            await self.save_conf()
        return synced

    def get_max_tokens(self, conf: GuildSettings, user: Optional[discord.Member]) -> int:
        user_max = conf.get_user_max_tokens(user)
        model = conf.get_user_model(user)
        max_model_tokens = MODELS.get(model, 4000)
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
    async def degrade_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
    ) -> bool:
        """
        Iteratively degrade a conversation payload in-place to fit within the max token limit, prioritizing more recent messages and critical context.

        Order of importance:
        - System messages
        - Function calls available to model
        - Most recent user message
        - Most recent assistant message
        - Most recent function/tool message

        System messages are always ignored.

        Args:
            messages (List[dict]): message entries sent to the api
            function_list (List[dict]): list of json function schemas for the model
            conf: (GuildSettings): current settings

        Returns:
            bool: whether the conversation was degraded
        """
        # Fetch the current model the user is using
        model = conf.get_user_model(user)
        # Fetch the max token limit for the current user
        max_tokens = self.get_max_tokens(conf, user)
        # Token count of current conversation
        convo_tokens = await self.count_payload_tokens(messages, model)
        # Token count of function calls available to model
        function_tokens = await self.count_function_tokens(function_list, model)

        total_tokens = convo_tokens + function_tokens

        # Check if the total token count is already under the max token limit
        if total_tokens <= max_tokens:
            return False

        log.debug(f"Degrading messages for {user} (total: {total_tokens}/max: {max_tokens})")

        def count(role: str):
            return sum(1 for msg in messages if msg["role"] == role)

        async def pop(role: str) -> int:
            for idx, msg in enumerate(messages):
                if msg["role"] != role:
                    continue
                removed = messages.pop(idx)
                reduction = 4
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

        # We will NOT remove the most recent user message or assistant message
        # We will also not touch system messages
        # We will also not touch function calls available to model (yet)
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
            # First we will iterate through the messages and remove in the following sweep order:
            # 1. Remove oldest tool call or response
            reduced = await pop("tool")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            reduced = await pop("function")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # 2. Remove oldest assistant message
            reduced = await pop("assistant")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # 3. Remove oldest user message
            reduced = await pop("user")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # Then we will repeat the process until we are under the max token limit

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

        max_tokens = min(conf.max_tokens - 100, MODELS.get(conf.model, 4000))
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
        func_dump = {k: v.model_dump(exclude_defaults=False) for k, v in self.db.functions.items()}
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
                        value=_("This is an internal command that can only be used when interacting with a tutor"),
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

                embed.add_field(name=_("Permission Level"), value=data["permission_level"].capitalize(), inline=False)
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

    async def get_embbedding_menu_embeds(self, conf: GuildSettings, place: int) -> List[discord.Embed]:
        embeddings = sorted(conf.embeddings.items(), key=lambda x: x[0])
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
                name, embedding = embeddings[i]
                tokens = await self.count_tokens(embedding.text, model)
                text = (
                    box(f"{embedding.text[:30].strip()}...")
                    if len(embedding.text) > 33
                    else box(embedding.text.strip())
                )
                val = _(
                    "`Created:    `{}\n"
                    "`Modified:   `{}\n"
                    "`Tokens:     `{}\n"
                    "`Dimensions: `{}\n"
                    "`AI Created: `{}\n"
                    "`Model:      `{}\n"
                ).format(
                    embedding.created_at(),
                    embedding.modified_at(relative=True),
                    tokens,
                    len(embedding.embedding),
                    embedding.ai_created,
                    conf.get_embed_model(self.db.endpoint_override),
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
