import asyncio
import inspect
import json
import logging
import math
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import discord
import openai
import tiktoken
from aiocache import cached
from openai.error import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from openai.version import VERSION
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, humanize_number
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_delay,
    wait_random_exponential,
)

log = logging.getLogger("red.vrt.assistant.utils")
encoding = tiktoken.get_encoding("cl100k_base")


def get_attachments(message: discord.Message) -> List[discord.Attachment]:
    """Get all attachments from context"""
    attachments = []
    if message.attachments:
        direct_attachments = [a for a in message.attachments]
        attachments.extend(direct_attachments)
    if hasattr(message, "reference"):
        try:
            referenced_attachments = [a for a in message.reference.resolved.attachments]
            attachments.extend(referenced_attachments)
        except AttributeError:
            pass
    return attachments


async def wait_message(ctx: commands.Context) -> Optional[discord.Message]:
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        message = await ctx.bot.wait_for("message", timeout=600, check=check)
        if message.content == "cancel":
            await ctx.send("Canceled")
            return None
        return message
    except asyncio.TimeoutError:
        return None


async def can_use(message: discord.Message, blacklist: list, respond: bool = True) -> bool:
    allowed = True
    if message.author.id in blacklist:
        if respond:
            await message.channel.send("You have been blacklisted from using this command!")
        allowed = False
    elif any(role.id in blacklist for role in message.author.roles):
        if respond:
            await message.channel.send("You have a blacklisted role and cannot use this command!")
        allowed = False
    elif message.channel.id in blacklist:
        if respond:
            await message.channel.send("You cannot use that command in this channel!")
        allowed = False
    elif message.channel.category_id in blacklist:
        if respond:
            await message.channel.send(
                "You cannot use that command in any channels under this category"
            )
        allowed = False
    return allowed


def extract_code_blocks(content: str) -> List[str]:
    code_blocks = re.findall(r"```(?:\w+)(.*?)```", content, re.DOTALL)
    if not code_blocks:
        code_blocks = re.findall(r"```(.*?)```", content, re.DOTALL)
    return [block.strip() for block in code_blocks]


def extract_code_blocks_with_lang(content: str) -> List[Tuple[str, str]]:
    code_blocks = re.findall(r"```(\w+)(.*?)```", content, re.DOTALL)
    if not code_blocks:
        code_blocks = re.findall(r"```(.*?)```", content, re.DOTALL)
        return [("", block.strip()) for block in code_blocks]
    return [(block[0], block[1].strip()) for block in code_blocks]


def remove_code_blocks(content: str) -> str:
    content = re.sub(r"```(?:\w+)(.*?)```", "[Code Removed]", content, flags=re.DOTALL).strip()
    return re.sub(r"```(.*?)```", "[Code Removed]", content, flags=re.DOTALL).strip()


def code_string_valid(code: str) -> bool:
    # True if function is good
    if "*args, **kwargs" not in code:
        return False
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def compile_function(function_name: str, code: str) -> Callable:
    globals().update({"discord": discord})
    exec(code, globals())
    return globals()[function_name]


def json_schema_invalid(schema: dict) -> str:
    # String will be empty if function is good
    missing = ""
    if "name" not in schema:
        missing += "- `name`\n"
    if "description" not in schema:
        missing += "- `description`\n"
    if "parameters" not in schema:
        missing += "- `parameters`\n"
    if "parameters" in schema:
        if "type" not in schema["parameters"]:
            missing += "- `type` in **parameters**\n"
        if "properties" not in schema["parameters"]:
            missing = "- `properties` in **parameters**\n"
        if "required" in schema["parameters"].get("properties", []):
            missing += "- `required` key needs to be outside of properties!\n"
    return missing


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    if not string:
        return 0
    num_tokens = len(encoding.encode(string))
    return num_tokens


def function_list_tokens(functions: List[dict]) -> int:
    if not functions:
        return 0
    dumps = [json.dumps(i) for i in functions]
    joined = "".join(dumps)
    return num_tokens_from_string(joined)


def degrade_conversation(
    messages: List[dict], function_list: List[dict], max_tokens: int
) -> Tuple[List[dict], List[dict], bool]:
    """Iteratively degrade a conversation payload, prioritizing more recent messages and critical context

    Args:
        messages (List[dict]): message entries sent to the api
        function_list (List[dict]): list of json function schemas for the model
        max_tokens (int): target tokens to keep conversation token count under

    Returns:
        Tuple[List[dict], List[dict], bool]: updated messages list, function list, and whether the conversation was degraded
    """
    # Calculate the initial total token count
    total_tokens = sum(num_tokens_from_string(msg["content"]) for msg in messages) + sum(
        num_tokens_from_string(json.dumps(func)) for func in function_list
    )
    # Check if the total token count is already under the max token limit
    if total_tokens <= max_tokens:
        return messages, function_list, False

    # Helper function to degrade a message
    def degrade_message(msg: str) -> str:
        words = msg.split()
        if len(words) > 1:
            return " ".join(words[:-1])
        else:
            return ""

    log.debug(f"Removing functions (total: {total_tokens}/max: {max_tokens})")
    # Degrade function_list first
    while total_tokens > max_tokens and len(function_list) > 0:
        popped = function_list.pop(0)
        total_tokens -= num_tokens_from_string(json.dumps(popped))
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

    log.debug(f"Degrading messages (total: {total_tokens}/max: {max_tokens})")
    # Degrade the conversation except for the most recent user and function messages
    i = 0
    while total_tokens > max_tokens and i < len(messages):
        if messages[i]["role"] == "system" or i == most_recent_user or i == most_recent_function:
            i += 1
            continue

        degraded_content = degrade_message(messages[i]["content"])
        if degraded_content:
            token_diff = num_tokens_from_string(messages[i]["content"]) - num_tokens_from_string(
                degraded_content
            )
            messages[i]["content"] = degraded_content
            total_tokens -= token_diff
        else:
            total_tokens -= num_tokens_from_string(messages[i]["content"])
            messages.pop(i)

        if total_tokens <= max_tokens:
            return messages, function_list, True

    # Degrade the most recent user and function messages as the last resort
    log.debug(f"Degrating user/function messages (total: {total_tokens}/max: {max_tokens})")
    for i in [most_recent_function, most_recent_user]:
        if total_tokens <= max_tokens:
            return messages, function_list, True
        while total_tokens > max_tokens:
            degraded_content = degrade_message(messages[i]["content"])
            if degraded_content:
                token_diff = num_tokens_from_string(
                    messages[i]["content"]
                ) - num_tokens_from_string(degraded_content)
                messages[i]["content"] = degraded_content
                total_tokens -= token_diff
            else:
                total_tokens -= num_tokens_from_string(messages[i]["content"])
                messages.pop(i)
                break

    return messages, function_list, True


def token_pagify(text: str, max_tokens: int = 2000):
    """Pagify a long string by tokens rather than characters"""
    token_chunks = []
    tokens = encoding.encode(text)
    current_chunk = []

    for token in tokens:
        current_chunk.append(token)
        if len(current_chunk) == max_tokens:
            token_chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        token_chunks.append(current_chunk)

    text_chunks = []
    for chunk in token_chunks:
        text_chunk = encoding.decode(chunk)
        text_chunks.append(text_chunk)

    return text_chunks


def token_cut(message: str, max_tokens: int):
    cut_tokens = encoding.encode(message)[:max_tokens]
    return encoding.decode(cut_tokens)


def compile_messages(messages: List[dict]) -> str:
    """Compile messages list into a single string"""
    text = ""
    for message in messages:
        role = message["role"]
        content = message["content"]
        text += f"{role}: {content}\n"
    text += "\n"
    return text


def function_embeds(
    functions: Dict[str, dict], registry: Dict[str, Dict[str, dict]], owner: bool, bot: Red
) -> List[discord.Embed]:
    main = {"Assistant": functions}
    for cog_name, function_schemas in registry.items():
        cog = bot.get_cog(cog_name)
        if not cog:
            continue
        for function_name, function_schema in function_schemas.items():
            function_obj = getattr(cog, function_name, None)
            if function_obj is None:
                continue
            if cog_name not in main:
                main[cog_name] = {}
            main[cog_name][function_name] = {
                "code": inspect.getsource(function_obj),
                "jsonschema": function_schema,
            }

    pages = sum(len(v) for v in main.values())
    page = 1
    embeds = []
    for cog_name, functions in main.items():
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
            tokens = num_tokens_from_string(schema)
            schema_text = (
                f"This function consumes `{humanize_number(tokens)}` input tokens each call\n"
            )

            if owner:
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


def embedding_embeds(embeddings: Dict[str, Any], place: int) -> List[discord.Embed]:
    embeddings = sorted(embeddings.items(), key=lambda x: x[0])
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
            em = embeddings[i]
            text = em[1].text
            token_length = num_tokens_from_string(text)
            val = f"`Tokens: `{token_length}\n```\n{text[:30]}...\n```"
            embed.add_field(
                name=f"➣ {em[0]}" if place == num else em[0],
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


@retry(
    retry=retry_if_exception_type(
        Union[Timeout, APIConnectionError, RateLimitError, ServiceUnavailableError]
    ),
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_delay(120),
    reraise=True,
)
@cached(ttl=1800)
async def request_embedding(text: str, api_key: str) -> List[float]:
    response = await openai.Embedding.acreate(
        input=text, model="text-embedding-ada-002", api_key=api_key, timeout=30
    )
    return response["data"][0]["embedding"]


@retry(
    retry=retry_if_exception_type(
        Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
    ),
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_delay(120),
    reraise=True,
)
@cached(ttl=30)
async def request_chat_response(
    model: str,
    messages: List[dict],
    api_key: str,
    temperature: float,
    functions: Optional[List[dict]] = [],
) -> dict:
    # response = await asyncio.to_thread(_chat, model, messages, api_key, temperature, functions)
    function_able_models = [
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    ]
    if VERSION >= "0.27.6" and model in function_able_models and functions:
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=messages,
            temperature=temperature,
            api_key=api_key,
            timeout=60,
            functions=functions,
        )
    else:
        response = await openai.ChatCompletion.acreate(
            model=model, messages=messages, temperature=temperature, api_key=api_key, timeout=60
        )
    return response["choices"][0]["message"]


def _chat(
    model: str,
    messages: List[dict],
    api_key: str,
    temperature: float,
    functions: Optional[List[dict]] = [],
):
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
        api_key=api_key,
        timeout=60,
        functions=functions,
        function_call="auto" if functions else "none",
    )
    return response["choices"][0]["message"]


@retry(
    retry=retry_if_exception_type(
        Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
    ),
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_delay(120),
    reraise=True,
)
@cached(ttl=30)
async def request_completion_response(
    model: str, message: str, api_key: str, temperature: float, max_tokens: int
) -> str:
    response = await openai.Completion.acreate(
        model=model,
        prompt=message,
        temperature=temperature,
        api_key=api_key,
        max_tokens=max_tokens,
    )
    return response["choices"][0]["text"]


@retry(
    retry=retry_if_exception_type(
        Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
    ),
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_delay(120),
    reraise=True,
)
async def request_image_create(prompt: str, api_key: str, size: str, user_id: str) -> str:
    response = await openai.Image.acreate(api_key=api_key, prompt=prompt, size=size, user=user_id)
    return response["data"][0]["url"]


@retry(
    retry=retry_if_exception_type(
        Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
    ),
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_delay(120),
    reraise=True,
)
async def request_image_edit(
    prompt: str, api_key: str, size: str, user_id: str, image: bytes, mask: Optional[bytes]
) -> str:
    response = await openai.Image.create_edit(
        api_key=api_key, prompt=prompt, size=size, user=user_id, image=image, mask=mask
    )
    return response["data"][0]["url"]


@retry(
    retry=retry_if_exception_type(
        Union[Timeout, APIConnectionError, RateLimitError, APIError, ServiceUnavailableError]
    ),
    wait=wait_random_exponential(min=1, max=5),
    stop=stop_after_delay(120),
    reraise=True,
)
async def request_image_variant(
    prompt: str, api_key: str, size: str, user_id: str, image: bytes
) -> str:
    response = await openai.Image.create_variation(
        api_key=api_key, prompt=prompt, size=size, user=user_id, image=image
    )
    return response["data"][0]["url"]
