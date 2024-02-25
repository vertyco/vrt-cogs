import asyncio
import inspect
import json
import logging
import math
from typing import List, Optional

import aiohttp
import discord
import tiktoken
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.create_embedding_response import CreateEmbeddingResponse
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from .calls import request_chat_completion_raw, request_embedding_raw
from .constants import MODELS
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
    ) -> ChatCompletionMessage:
        model = conf.get_user_model(member)

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

        max_model_tokens = MODELS[model]

        # Ensure that user doesn't set max response tokens higher than model can handle
        if response_token_override:
            response_tokens = response_token_override
        else:
            response_tokens = 0  # Dynamic
            if max_response_tokens:
                # Calculate max response tokens
                response_tokens = max(max_convo_tokens - current_convo_tokens, 0)
                # If current convo exceeds the max convo tokens for that user, use max model tokens
                if not response_tokens:
                    response_tokens = max(max_model_tokens - current_convo_tokens, 0)
                # Use the lesser of caculated vs set response tokens
                response_tokens = min(response_tokens, max_response_tokens)

        if model not in MODELS:
            log.error(f"This model is not longer supported: {model}. Switching to gpt-3.5-turbo")
            model = "gpt-3.5-turbo"
            await self.save_conf()

        response: ChatCompletion = await request_chat_completion_raw(
            model=model,
            messages=messages,
            temperature=conf.temperature,
            api_key=conf.api_key,
            max_tokens=response_tokens,
            functions=functions,
            frequency_penalty=conf.frequency_penalty,
            presence_penalty=conf.presence_penalty,
            seed=conf.seed,
        )
        message: ChatCompletionMessage = response.choices[0].message

        conf.update_usage(
            response.model,
            response.usage.total_tokens,
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
        )
        log.debug(f"MESSAGE TYPE: {type(message)}")
        return message

    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        response: CreateEmbeddingResponse = await request_embedding_raw(text, conf.api_key, conf.embed_model)

        conf.update_usage(
            response.model,
            response.usage.total_tokens,
            response.usage.prompt_tokens,
            0,
        )
        return response.data[0].embedding

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- HELPERS -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    async def count_payload_tokens(self, messages: List[dict], model: str = "gpt-3.5-turbo"):
        if not messages:
            return 0

        def _get_encoding():
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("cl100k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding)

        num_tokens = 0
        for message in messages:
            num_tokens += 4  # every message follows <im_start>{role/name}\n{content}<im_end>\n
            for key, value in message.items():
                if not value:
                    continue
                if isinstance(value, list):
                    for i in value:
                        if i["type"] == "image_url":
                            num_tokens += 65
                            if i.get("detail", "") == "high":
                                num_tokens += 65
                            continue
                        try:
                            encoded = await asyncio.to_thread(encoding.encode, i.get("text") or str(i))
                        except Exception as e:
                            log.error(f"Failed to encode: {i.get('text') or str(i)}", exc_info=e)
                            encoded = []
                        num_tokens += len(encoded)
                else:
                    try:
                        encoded = await asyncio.to_thread(encoding.encode, str(value))
                    except Exception as e:
                        log.error(f"Failed to encode: {value}", exc_info=e)
                        encoded = []
                    num_tokens += len(encoded)
                if key == "name":  # if there's a name, the role is omitted
                    num_tokens += -1  # role is always required and always 1 token
        num_tokens += 2  # every reply is primed with <im_start>assistant
        return num_tokens

    async def count_function_tokens(self, functions: List[dict], model: str = "gpt-3.5-turbo"):
        def _get_encoding():
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("cl100k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding)

        num_tokens = 0
        for func in functions:
            dump = json.dumps(func)
            encoded = await asyncio.to_thread(encoding.encode, dump)
            num_tokens += len(encoded)
        return num_tokens

    async def get_tokens(self, text: str, model: str = "gpt-3.5-turbo") -> list:
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
                enc = tiktoken.get_encoding("cl100k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding)

        return await asyncio.to_thread(encoding.encode, text)

    async def count_tokens(self, text: str, model: str) -> int:
        if not text:
            log.debug("No text to get token count from!")
            return 0
        tokens = await self.get_tokens(text, model)
        return len(tokens)

    async def can_call_llm(self, conf: GuildSettings, ctx: Optional[commands.Context] = None) -> bool:
        if not conf.api_key:
            if ctx:
                txt = _("There are no API keys set!\n")
                if ctx.author.id == ctx.guild.owner_id:
                    txt += _("- Set your OpenAI key with `{}`\n").format(f"{ctx.clean_prefix}assist openaikey")
                await ctx.send(txt)
            return False
        return True

    async def resync_embeddings(self, conf: GuildSettings) -> int:
        """Update embeds to match current dimensions

        Takes a sample using current embed method, the updates the rest to match dimensions
        """
        if not conf.embeddings:
            return 0

        sample = list(conf.embeddings.values())[0]
        sample_embed = await self.request_embedding(sample.text, conf)

        async def update_embedding(name: str, text: str):
            conf.embeddings[name].embedding = await self.request_embedding(text, conf)
            conf.embeddings[name].update()
            conf.embeddings[name].model = conf.embed_model
            log.debug(f"Updated embedding: {name}")

        synced = 0
        tasks = []
        for name, em in conf.embeddings.items():
            if conf.embed_model != em.model or len(em.embedding) != len(sample_embed):
                synced += 1
                tasks.append(update_embedding(name, em.text))

        if synced:
            await asyncio.gather(*tasks)
            await self.save_conf()
        return synced

    def get_max_tokens(self, conf: GuildSettings, user: Optional[discord.Member]) -> int:
        user_max = conf.get_user_max_tokens(user)
        return min(user_max, MODELS[conf.get_user_model(user)] - 96)

    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, user: Optional[discord.Member]) -> str:
        if not text:
            log.debug("No text to cut by tokens!")
            return text
        tokens = await self.get_tokens(text, conf.get_user_model(user))
        return await self.get_text(tokens[: self.get_max_tokens(conf, user)], conf.get_user_model(user))

    async def get_text(self, tokens: list, model: str = "gpt-3.5-turbo") -> str:
        """Get text from token list"""

        def _get_encoding():
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("cl100k_base")
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

        def _degrade_text(txt: str) -> str:
            words = txt.split()
            if len(words) > 1:
                return " ".join(words[:-1])
            else:
                return ""

        def _most_recent():
            most_recent_user = most_recent_assistant = most_recent_tool = None
            for idx, msg in enumerate(reversed(messages)):
                if msg["role"] in ["tool", "function"] and not most_recent_tool:
                    most_recent_tool = len(messages) - 1 - idx
                elif msg["role"] == "assistant" and not most_recent_assistant:
                    most_recent_assistant = len(messages) - 1 - idx
                elif msg["role"] == "user" and not most_recent_user:
                    most_recent_user = len(messages) - 1 - idx
                elif most_recent_user and most_recent_assistant and most_recent_tool:
                    break
            return most_recent_user, most_recent_assistant, most_recent_tool

        # Fetch the current model
        model = conf.get_user_model(user)
        # Fetch the max response tokens for the current user
        conf.get_user_max_response_tokens(user)
        # Fetch the max token limit for the current user
        max_tokens = self.get_max_tokens(conf, user)

        # Token count of current conversation
        convo_tokens = await self.count_payload_tokens(messages, model)
        # Token count of function calls available to model
        function_tokens = await self.count_function_tokens(function_list, model)
        total_tokens_used = convo_tokens + function_tokens

        # Check if the total token count is already under the max token limit
        if total_tokens_used <= max_tokens:
            return False

        log.debug(f"Degrading messages for {user} (total: {total_tokens_used}/max: {max_tokens})")
        # First we will iterate through the messages and remove in the following sweep order:
        # 1. Remove oldest tool call or response
        # 2. Remove oldest assistant message
        # 3. Remove oldest user message
        # Then we will repeat the process until we are under the max token limit
        # We will NOT remove the most recent user message or assistant message
        # We will also not touch system messages
        # We will also not touch function calls available to model (yet)

        most_recent_user, most_recent_assistant, most_recent_tool = _most_recent()

        # Start degrading the conversation except for system messages and most recent messages
        messages_to_purge = set()
        token_reduction = 0
        for idx, msg in enumerate(messages):
            skip_conditions = [
                msg["role"] == "system",
                idx == most_recent_user,
                idx == most_recent_assistant,
                idx == most_recent_tool,
            ]
            if any(skip_conditions):
                continue

            # This message will get popped
            token_reduction += 4  # Default count
            if "name" in msg:
                token_reduction += 1

            content_to_tokenize = msg["content"] or msg.get("tool_calls", "") or msg.get("function_call", "")
            token_reduction += await self.count_tokens(content_to_tokenize, model)
            messages_to_purge.add(idx)

            # Check if we are under the max token limit
            if total_tokens_used - token_reduction <= max_tokens:
                break

        # Remove messages
        total_tokens_used -= token_reduction
        for idx in sorted(messages_to_purge, reverse=True):
            messages.pop(idx)

        # Check if we are under the max token limit
        if total_tokens_used <= max_tokens:
            log.debug(f"First sweep successful for {user} (total: {total_tokens_used}/max: {max_tokens})")
            return True

        # # If still not under the max token limit, we will now remove function calls available to model
        # function_indexes_to_purge = set()
        # token_reduction = 0
        # for idx, func in enumerate(function_list):
        #     token_reduction += await self.count_tokens(json.dumps(func), model)
        #     function_indexes_to_purge.add(idx)
        #     if total_tokens_used - token_reduction <= max_tokens:
        #         break

        # # Remove function calls
        # total_tokens_used -= token_reduction
        # for idx in sorted(function_indexes_to_purge, reverse=True):
        #     function_list.pop(idx)

        # # Check if we are under the max token limit
        # if total_tokens_used <= max_tokens:
        #     log.debug(f"Second sweep successful for {user} (total: {total_tokens_used}/max: {max_tokens})")
        #     return True

        # # If still not under the max token limit, we will now DEGRADE the most recent user and assistant messages
        # # We will also remove the most recent function/tool message if it exists
        # messages_to_purge = set()
        # token_reduction = 0
        # # Just start degrading from the first onward
        # for idx, msg in enumerate(messages):
        #     if msg["role"] == "system":
        #         continue
        #     # This message will get popped
        #     token_reduction += 4
        #     if "name" in msg:
        #         token_reduction += 1

        #     content_to_tokenize = msg["content"] or msg.get("tool_calls", "") or msg.get("function_call", "")
        #     token_reduction += await self.count_tokens(content_to_tokenize, model)
        #     messages_to_purge.add(idx)

        #     # Check if we are under the max token limit
        #     if total_tokens_used - token_reduction <= max_tokens:
        #         break

        # # Remove messages
        # total_tokens_used -= token_reduction
        # for idx in sorted(messages_to_purge, reverse=True):
        #     messages.pop(idx)

        # # Check if we are under the max token limit
        # if total_tokens_used <= max_tokens:
        #     log.debug(f"Third sweep successful for {user} (total: {total_tokens_used}/max: {max_tokens})")
        #     return True

        # Check if we destroyed the whole convo somehow
        messages_without_system = sum(1 for msg in messages if msg["role"] != "system")
        if messages_without_system == 0:
            # We failed or the admins are trying their damn best to configure stupid settings
            raise ValueError(f"Failed to degrade conversation for {user}, guild owner needs to check settings")

        # Chances are we are still over the limit, so lets just check if we're not over the model's context window
        if total_tokens_used > MODELS[model] - 96:
            raise ValueError(f"Failed to degrade conversation for {user}, guild owner needs to check settings")

        log.debug(f"Convo degradation finished for {user} (total: {total_tokens_used}/max: {max_tokens})")
        return True

    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        """Pagify a long string by tokens rather than characters"""
        if not text:
            log.debug("No text to pagify!")
            return []
        token_chunks = []
        tokens = await self.get_tokens(text)
        current_chunk = []

        max_tokens = min(conf.max_tokens - 100, MODELS[conf.model])
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
        func_dump = {k: v.model_dump() for k, v in self.db.functions.items()}
        registry = {"Assistant-Custom": func_dump}
        for cog_name, function_schemas in self.registry.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for function_name, function_schema in function_schemas.items():
                function_obj = getattr(cog, function_name, None)
                if function_obj is None:
                    continue
                if cog_name not in registry:
                    registry[cog_name] = {}
                registry[cog_name][function_name] = {
                    "code": inspect.getsource(function_obj),
                    "jsonschema": function_schema,
                }

        conf = self.db.get_conf(user.guild)
        model = conf.get_user_model(user)

        pages = sum(len(v) for v in registry.values())
        page = 1
        embeds = []
        for cog_name, functions in registry.items():
            for function_name, func in functions.items():
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
                schema = json.dumps(func["jsonschema"], indent=2)
                tokens = await self.count_tokens(schema, model)

                schema_text = _("This function consumes `{}` input tokens each call\n").format(humanize_number(tokens))

                if user.id in self.bot.owner_ids:
                    if len(schema) > 900:
                        schema_text += box(schema[:900] + "...", "py")
                    else:
                        schema_text += box(schema, "py")

                    if len(func["code"]) > 900:
                        code_text = box(func["code"][:900] + "...", "py")
                    else:
                        code_text = box(func["code"], "py")

                else:
                    schema_text += box(func["jsonschema"]["description"], "json")
                    code_text = box(_("Hidden..."))

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
                    conf.embed_model,
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
