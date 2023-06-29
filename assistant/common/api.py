import asyncio
import inspect
import json
import logging
import math
from typing import List, Optional, Tuple, Union

import discord
import openai
import orjson
from aiocache import cached
from openai.error import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from openai.version import VERSION
from redbot.core.utils.chat_formatting import box, humanize_number
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_delay,
    wait_random_exponential,
)

from ..abc import MixinMeta
from .constants import MODELS, SELF_HOSTED, SUPPORTS_FUNCTIONS
from .models import Conversation, GuildSettings

log = logging.getLogger("red.vrt.assistant.api")


class API(MixinMeta):
    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        if conf.use_local_embedder or not conf.api_key:
            log.debug("Local embed requested")
            embeddings = await self._local_embed(text)
            log.debug(f"Embed length: {len(embeddings)}")
            return embeddings.tolist()
        return await self._openai_embed(text, conf)

    @cached(ttl=1800)
    async def _local_embed(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.local_llm.embedder.encode, text)

    @retry(
        retry=retry_if_exception_type(
            Union[Timeout, APIConnectionError, RateLimitError, ServiceUnavailableError]
        ),
        wait=wait_random_exponential(min=1, max=5),
        stop=stop_after_delay(15),
        reraise=True,
    )
    @cached(ttl=1800)
    async def _openai_embed(self, text: str, conf: GuildSettings) -> List[float]:
        response = await openai.Embedding.acreate(
            input=text, model="text-embedding-ada-002", api_key=conf.api_key, timeout=30
        )
        return response["data"][0]["embedding"]

    @retry(
        retry=retry_if_exception_type(
            Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
        ),
        wait=wait_random_exponential(min=1, max=5),
        stop=stop_after_delay(60),
        reraise=True,
    )
    @cached(ttl=30)
    async def request_chat_response(
        self, messages: List[dict], conf: GuildSettings, functions: List[dict] = []
    ) -> dict:
        if functions and VERSION >= "0.27.6" and conf.model in SUPPORTS_FUNCTIONS:
            response = await openai.ChatCompletion.acreate(
                model=conf.model,
                messages=messages,
                temperature=conf.temperature,
                api_key=conf.api_key,
                timeout=60,
                functions=functions,
            )
        else:
            response = await openai.ChatCompletion.acreate(
                model=conf.model,
                messages=messages,
                temperature=conf.temperature,
                api_key=conf.api_key,
                timeout=60,
            )
        return response["choices"][0]["message"]

    @retry(
        retry=retry_if_exception_type(
            Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
        ),
        wait=wait_random_exponential(min=1, max=5),
        stop=stop_after_delay(60),
        reraise=True,
    )
    @cached(ttl=30)
    async def request_completion_response(
        self, prompt: str, conf: GuildSettings, max_response_tokens: int
    ) -> str:
        response = await openai.Completion.acreate(
            model=conf.model,
            prompt=prompt,
            temperature=conf.temperature,
            api_key=conf.api_key,
            max_tokens=max_response_tokens,
        )
        return response["choices"][0]["text"]

    async def request_local_response(
        self, prompt: str, context: str, min_confidence: float
    ) -> str:
        def _run():
            result = self.local_llm.pipe(question=prompt, context=context)
            if not result:
                return ""

            log.debug(f"Response: {result}")
            score = result.get("score", 0)
            if score < min_confidence:
                return ""
            return result.get("answer", "")

        if not context:
            return ""
        return await asyncio.to_thread(_run)

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- HELPERS -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------
    def get_llm_type(self, conf: GuildSettings, embeds: bool = False) -> str:
        check = conf.use_local_embedder if embeds else conf.use_local_llm
        if conf.api_key and not check:
            return "api"
        elif self.local_llm is not None:
            return "local"
        else:
            # Either api model is selected but no api key, or self hosted is selected but its not enabled
            if not conf.api_key:
                log.info("No API key!")
            elif self.local_llm is None:
                log.info("Local LLM not running!")
            return "none"

    async def sync_embeddings(self, conf: GuildSettings) -> bool:
        synced = False

        for name, em in conf.embeddings.items():
            if conf.use_local_embedder and em.openai_tokens:
                log.debug(f"Converting OpenAI embedding '{name}' to Local version")
                em.embedding = await self.request_embedding(em.text, conf)
                em.openai_tokens = False
                synced = True
            elif not conf.use_local_embedder and not em.openai_tokens:
                log.debug(f"Converting Local embedding '{name}' to OpenAI version")
                em.embedding = await self.request_embedding(em.text, conf)
                em.openai_tokens = True
                synced = True

        if synced:
            await self.save_conf()
        return synced

    def get_max_tokens(self, conf: GuildSettings, user: Optional[discord.Member]) -> int:
        return min(conf.get_user_max_tokens(user), MODELS[conf.get_user_model(user)] - 96)

    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, max_tokens: int) -> str:
        tokens = await self.get_tokens(text, conf)
        return await self.get_text(tokens[:max_tokens])

    async def get_token_count(self, text: str, conf: GuildSettings) -> int:
        return len(await self.get_tokens(text, conf))

    async def get_tokens(self, text: str, conf: GuildSettings) -> list:
        """Get token list from text"""

        def _run():
            if conf.model in SELF_HOSTED and self.local_llm is not None:
                return self.local_llm.pipe.tokenizer.encode(text)
            else:
                return self.openai_tokenizer.encode(text)

        if not text:
            return []
        return await asyncio.to_thread(_run)

    async def get_text(self, tokens: list, conf: GuildSettings) -> str:
        """Get text from token list"""

        def _run():
            if conf.model in SELF_HOSTED and self.local_llm is not None:
                return self.local_llm.pipe.tokenizer.convert_tokens_to_string(tokens)
            else:
                return self.openai_tokenizer.decode(tokens)

        return await asyncio.to_thread(_run)

    async def convo_token_count(self, conf: GuildSettings, convo: Conversation) -> int:
        """Fetch token count of stored messages"""
        return sum([(await self.get_token_count(i["content"], conf)) for i in convo.messages])

    async def prompt_token_count(self, conf: GuildSettings) -> int:
        """Fetch token count of system and initial prompts"""
        return (await self.get_token_count(conf.prompt, conf)) + (
            await self.get_token_count(conf.system_prompt, conf)
        )

    async def function_token_count(self, conf: GuildSettings, functions: List[dict]) -> int:
        if not functions:
            return 0
        dumped = "".join(orjson.dumps(i) for i in functions)
        return await self.get_token_count(dumped, conf)

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
    ) -> Tuple[List[dict], List[dict], bool]:
        """Iteratively degrade a conversation payload, prioritizing more recent messages and critical context

        Args:
            messages (List[dict]): message entries sent to the api
            function_list (List[dict]): list of json function schemas for the model
            conf: (GuildSettings): current settings

        Returns:
            Tuple[List[dict], List[dict], bool]: updated messages list, function list, and whether the conversation was degraded
        """
        # Calculate the initial total token count
        total_tokens = 0
        for message in messages:
            count = await self.get_token_count(message["content"], conf)
            total_tokens += count

        for function in function_list:
            count = await self.get_token_count(orjson.dumps(function), conf)
            total_tokens += count

        # Check if the total token count is already under the max token limit
        max_tokens = self.get_max_tokens(conf, user)
        if total_tokens <= max_tokens:
            return messages, function_list, False

        # Helper function to degrade a message
        def _degrade_message(msg: str) -> str:
            words = msg.split()
            if len(words) > 1:
                return " ".join(words[:-1])
            else:
                return ""

        log.debug(f"Removing functions (total: {total_tokens}/max: {max_tokens})")
        # Degrade function_list first
        while total_tokens > max_tokens and len(function_list) > 0:
            popped = function_list.pop(0)
            total_tokens -= await self.get_token_count(orjson.dumps(popped), conf)
            if total_tokens <= max_tokens:
                return messages, function_list, True

        # Find the indices of the most recent messages for each role
        most_recent_user = most_recent_function = most_recent_assistant = -1
        for i, msg in enumerate(reversed(messages)):
            if most_recent_user == -1 and msg["role"] == "user":
                most_recent_user = len(messages) - 1 - i
            if most_recent_function == -1 and msg["role"] == "function":
                most_recent_function = len(messages) - 1 - i
            if most_recent_assistant == -1 and msg["role"] == "assistant":
                most_recent_assistant = len(messages) - 1 - i
            if (
                most_recent_user != -1
                and most_recent_function != -1
                and most_recent_assistant != -1
            ):
                break

        log.debug(f"Degrading messages (total: {total_tokens}/max: {max_tokens})")
        # Degrade the conversation except for the most recent user and function messages
        i = 0
        while total_tokens > max_tokens and i < len(messages):
            if (
                messages[i]["role"] == "system"
                or i == most_recent_user
                or i == most_recent_function
            ):
                i += 1
                continue

            degraded_content = _degrade_message(messages[i]["content"])
            if degraded_content:
                token_diff = (await self.get_token_count(messages[i]["content"], conf)) - (
                    await self.get_token_count(degraded_content, conf)
                )
                messages[i]["content"] = degraded_content
                total_tokens -= token_diff
            else:
                total_tokens -= await self.get_token_count(messages[i]["content"], conf)
                messages.pop(i)

            if total_tokens <= max_tokens:
                return messages, function_list, True

        # Degrade the most recent user and function messages as the last resort
        log.debug(f"Degrating user/function messages (total: {total_tokens}/max: {max_tokens})")
        for i in [most_recent_function, most_recent_user]:
            if total_tokens <= max_tokens:
                return messages, function_list, True
            while total_tokens > max_tokens:
                degraded_content = _degrade_message(messages[i]["content"])
                if degraded_content:
                    token_diff = (await self.get_token_count(messages[i]["content"], conf)) - (
                        await self.get_token_count(degraded_content, conf)
                    )
                    messages[i]["content"] = degraded_content
                    total_tokens -= token_diff
                else:
                    total_tokens -= await self.get_token_count(messages[i]["content"], conf)
                    messages.pop(i)
                    break

        return messages, function_list, True

    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        """Pagify a long string by tokens rather than characters"""
        token_chunks = []
        tokens = await self.get_tokens(text, conf)
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
        func_dump = {k: v.dict() for k, v in self.db.functions.items()}
        registry = {"Assistant": func_dump}
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

        pages = sum(len(v) for v in registry.values())
        page = 1
        embeds = []
        for cog_name, functions in registry.items():
            for function_name, func in functions.items():
                embed = discord.Embed(
                    title="Custom Functions", description=function_name, color=discord.Color.blue()
                )
                if cog_name != "Assistant":
                    embed.add_field(
                        name="3rd Party",
                        value=f"This function is managed by the `{cog_name}` cog",
                        inline=False,
                    )
                schema = json.dumps(func["jsonschema"], indent=2)
                tokens = await self.get_token_count(schema, conf)
                schema_text = (
                    f"This function consumes `{humanize_number(tokens)}` input tokens each call\n"
                )

                if user.id in self.bot.owner_ids:
                    if len(schema) > 1000:
                        schema_text += box(schema[:1000], "py") + "..."
                    else:
                        schema_text += box(schema, "py")

                    if len(func["code"]) > 1000:
                        code_text = box(func["code"][:1000], "py") + "..."
                    else:
                        code_text = box(func["code"], "py")

                else:
                    schema_text += box(func["jsonschema"]["description"], "json")
                    code_text = box("Hidden...")

                embed.add_field(name="Schema", value=schema_text, inline=False)
                embed.add_field(name="Code", value=code_text, inline=False)

                embed.set_footer(text=f"Page {page}/{pages}")
                embeds.append(embed)
                page += 1

        if not embeds:
            embeds.append(
                discord.Embed(
                    description="No custom code has been added yet!", color=discord.Color.purple()
                )
            )
        return embeds

    async def get_embbedding_menu_embeds(
        self, conf: GuildSettings, place: int
    ) -> List[discord.Embed]:
        embeddings = sorted(conf.embeddings.items(), key=lambda x: x[0])
        embeds = []
        pages = math.ceil(len(embeddings) / 5)
        start = 0
        stop = 5
        for page in range(pages):
            stop = min(stop, len(embeddings))
            embed = discord.Embed(title="Embeddings", color=discord.Color.blue())
            embed.set_footer(text=f"Page {page + 1}/{pages}")
            num = 0
            for i in range(start, stop):
                name, embedding = embeddings[i]
                tokens = await self.get_token_count(embedding.text, conf)
                encoder = "OpenAI" if embedding.openai_tokens else "Local LLM"
                text = (
                    box(f"{embedding.text[:30].strip()}...")
                    if len(embedding.text) > 33
                    else box(embedding.text.strip())
                )
                val = f"`Tokens:     `{tokens}\n" f"`Encoded by: `{encoder}\n" f"{text}"
                embed.add_field(
                    name=f"➣ {name}" if place == num else name,
                    value=val,
                    inline=False,
                )
                num += 1
            embeds.append(embed)
            start += 5
            stop += 5
        if not embeds:
            embeds.append(
                discord.Embed(
                    description="No embeddings have been added!", color=discord.Color.purple()
                )
            )
        return embeds
