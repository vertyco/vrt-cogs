import asyncio
import inspect
import json
import logging
import math
from typing import Dict, List, Optional, Tuple

import discord
from aiohttp import ClientConnectionError
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from .calls import (
    request_chat_completion_raw,
    request_completion_raw,
    request_embedding_raw,
    request_text_raw,
    request_tokens_raw,
)
from .constants import CHAT, MODELS
from .models import Conversation, GuildSettings
from .utils import compile_messages

log = logging.getLogger("red.vrt.assistant.api")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class API(MixinMeta):
    async def request_response(
        self,
        messages: List[dict],
        conf: GuildSettings,
        functions: Optional[List[dict]] = None,
        member: Optional[discord.Member] = None,
        response_token_override: int = None,
    ) -> Dict[str, str]:
        api_base = conf.endpoint_override or self.db.endpoint_override
        api_key = "unset"
        if conf.api_key:
            api_base = None
            api_key = conf.api_key

        max_convo_tokens = self.get_max_tokens(conf, member)
        max_response_tokens = conf.get_user_max_response_tokens(member)

        # Overestimate by 5%
        current_convo_tokens = await self.payload_token_count(conf, messages)
        current_convo_tokens = round(current_convo_tokens * 1.05)

        model = conf.get_user_model(member)
        # Dynamically adjust to lower model to save on cost
        if "-16k" in model and current_convo_tokens < 2000:
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

        if model in CHAT:
            response = await request_chat_completion_raw(
                model=model,
                messages=messages,
                temperature=conf.temperature,
                api_key=api_key,
                max_tokens=response_tokens,
                api_base=api_base,
                functions=functions,
            )
            message = response["choices"][0]["message"]
        else:
            compiled = compile_messages(messages)
            prompt = await self.cut_text_by_tokens(compiled, conf, self.get_max_tokens(conf, member))
            response = await request_completion_raw(
                model=model,
                prompt=prompt,
                temperature=conf.temperature,
                api_key=api_key,
                max_tokens=response_tokens,
                api_base=api_base,
            )
            text = response["choices"][0]["text"]
            for i in ["Assistant:", "assistant:", "System:", "system:", "User:", "user:"]:
                text = text.replace(i, "").strip()
            message = {"content": text, "role": "assistant"}

        total_tokens = response["usage"].get("total_tokens", 0)
        prompt_tokens = response["usage"].get("prompt_tokens", 0)
        completion_tokens = response["usage"].get("completion_tokens", 0)
        conf.update_usage(response["model"], total_tokens, prompt_tokens, completion_tokens)

        return message

    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        if conf.api_key:
            api_base = None
            api_key = conf.api_key
        else:
            log.debug("Using external embedder")
            api_base = conf.endpoint_override or self.db.endpoint_override
            api_key = "unset"

        response = await request_embedding_raw(text, api_key, api_base)

        prompt_tokens = response["usage"].get("prompt_tokens", 0)
        total_tokens = response["usage"].get("total_tokens", 0)
        conf.update_usage(response["model"], total_tokens, prompt_tokens, 0)
        return response["data"][0]["embedding"]

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- HELPERS -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    async def can_call_llm(self, conf: GuildSettings, ctx: Optional[commands.Context] = None) -> bool:
        cant = [
            not conf.api_key,
            conf.endpoint_override is None,
            self.db.endpoint_override is None,
        ]
        if all(cant):
            if ctx:
                txt = _("There are no API keys set!\n")
                if ctx.author.id == ctx.guild.owner_id:
                    txt += _("- Set your OpenAI key with `{}`\n").format(f"{ctx.clean_prefix}assist openaikey")
                    txt += _("- Or set an endpoint override to your self-hosted LLM with `{}`\n").format(
                        f"{ctx.clean_prefix}assist endpoint"
                    )
                if ctx.author.id in self.bot.owner_ids:
                    txt += _("- Alternatively you can set a global endpoint with `{}`").format(
                        f"{ctx.clean_prefix}assist globalendpoint"
                    )
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

        synced = 0
        for name, em in conf.embeddings.items():
            if len(em.embedding) != len(sample_embed):
                em.embedding = await self.request_embedding(em.text, conf)
                synced += 1
                log.debug(f"Updating embedding {name}")

        if synced:
            await self.save_conf()
        return synced

    def get_max_tokens(self, conf: GuildSettings, user: Optional[discord.Member]) -> int:
        user_max = conf.get_user_max_tokens(user)
        return min(user_max, MODELS[conf.get_user_model(user)] - 96)

    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, max_tokens: int) -> str:
        if not text:
            log.debug("No text to cut by tokens!")
            return text
        tokens = await self.get_tokens(text, conf)
        return await self.get_text(tokens[:max_tokens], conf)

    async def get_token_count(self, text: str, conf: GuildSettings) -> int:
        if not text:
            log.debug("No text to get token count from!")
            # raise Exception("No text to get token count from!")
            return 0
        tokens = await self.get_tokens(text, conf)
        return len(tokens)

    async def get_tokens(self, text: str, conf: GuildSettings) -> list:
        """Get token list from text"""
        if not text:
            log.debug("No text to get tokens from!")
            return []
        if isinstance(text, bytes):
            text = text.decode(encoding="utf-8")

        if not conf.api_key and (conf.endpoint_override or self.db.endpoint_override):
            log.debug("Using external tokenizer")
            endpoint = conf.endpoint_override or self.db.endpoint_override
            try:
                return await request_tokens_raw(text, f"{endpoint}/tokenize")
            except (KeyError, ClientConnectionError):  # API probably old or bad endpoint
                pass

        return await asyncio.to_thread(self.tokenizer.encode, text)

    async def get_text(self, tokens: list, conf: GuildSettings) -> str:
        """Get text from token list"""

        if not conf.api_key and (conf.endpoint_override or self.db.endpoint_override):
            log.debug("Using external tokenizer")
            endpoint = conf.endpoint_override or self.db.endpoint_override
            return await request_text_raw(tokens, f"{endpoint}/untokenize")

        return await asyncio.to_thread(self.tokenizer.decode, tokens)

    async def convo_token_count(self, conf: GuildSettings, convo: Conversation) -> int:
        """Fetch token count of stored messages"""
        return sum([(await self.get_token_count(i["content"], conf)) for i in convo.messages if i["content"]])

    async def payload_token_count(self, conf: GuildSettings, messages: List[dict]):
        total = 0
        for message in messages:
            total += await self.get_token_count(json.dumps(message), conf)
        return total

    async def prompt_token_count(self, conf: GuildSettings) -> int:
        """Fetch token count of system and initial prompts"""
        return (await self.get_token_count(conf.prompt, conf)) + (await self.get_token_count(conf.system_prompt, conf))

    async def function_token_count(self, conf: GuildSettings, functions: List[dict]) -> int:
        if not functions:
            return 0
        dumpped = []
        for i in functions:
            dumpped.append(json.dumps(i))
        joined = "".join(dumpped)
        return await self.get_token_count(joined, conf)

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
        total_tokens = await self.get_token_count(json.dumps(messages), conf)
        total_tokens += await self.get_token_count(json.dumps(function_list), conf)

        # Check if the total token count is already under the max token limit
        max_response_tokens = conf.get_user_max_response_tokens(user)
        max_tokens = self.get_max_tokens(conf, user)
        if max_tokens > max_response_tokens:
            max_tokens = max_tokens - max_response_tokens

        if total_tokens <= max_tokens:
            return messages, function_list, False

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
            total_tokens -= await self.get_token_count(json.dumps(popped), conf)
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
            if most_recent_user != -1 and most_recent_function != -1 and most_recent_assistant != -1:
                break

        # Clear out function calls (not the result, just the message of it being called)
        i = 0
        while total_tokens > max_tokens and i < len(messages):
            if messages[i]["content"]:
                i += 1
                continue
            messages.pop(i)

        log.debug(f"Degrading messages (total: {total_tokens}/max: {max_tokens})")
        # Degrade the conversation except for the most recent user, assistant, and function messages
        i = 0
        while total_tokens > max_tokens and i < len(messages):
            if (
                messages[i]["role"] == "system"
                or i == most_recent_user
                or i == most_recent_function
                or i == most_recent_assistant
            ):
                i += 1
                continue

            if not messages[i]["content"]:
                if "function_call" not in messages[i]:
                    messages.pop(i)
                else:
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
        if not text:
            log.debug("No text to pagify!")
            return []
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
                tokens = await self.get_token_count(schema, conf)

                schema_text = _("This function consumes `{}` input tokens each call\n").format(humanize_number(tokens))

                if user.id in self.bot.owner_ids:
                    if len(schema) > 1000:
                        schema_text += box(schema[:1000] + "...", "py")
                    else:
                        schema_text += box(schema, "py")

                    if len(func["code"]) > 1000:
                        code_text = box(func["code"][:1000] + "...", "py")
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
        start = 0
        stop = 5
        for page in range(pages):
            stop = min(stop, len(embeddings))
            embed = discord.Embed(title=_("Embeddings"), color=discord.Color.blue())
            embed.set_footer(text=_("Page {}/{}").format(page + 1, pages))
            num = 0
            for i in range(start, stop):
                name, embedding = embeddings[i]
                tokens = await self.get_token_count(embedding.text, conf)
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
                ).format(
                    embedding.created_at(),
                    embedding.modified_at(relative=True),
                    tokens,
                    len(embedding.embedding),
                    embedding.ai_created,
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
