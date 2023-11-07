import logging
from typing import List, Optional

import aiohttp
from aiocache import cached
from openai import AsyncOpenAI

from .constants import MODELS_1106, SUPPORTS_FUNCTIONS, SUPPORTS_TOOLS

log = logging.getLogger("red.vrt.assistant.calls")


async def request_chat_completion_raw(
    model: str,
    messages: List[dict],
    temperature: float,
    api_key: str,
    max_tokens: int,
    api_base: Optional[str] = None,
    functions: Optional[List[dict]] = None,
    timeout: int = 60,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    seed: int = None,
):
    log.debug(f"request_chat_completion_raw: {model}")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=api_base,
        max_retries=5,
    )
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "timeout": timeout,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    if model in MODELS_1106:
        kwargs["seed"] = seed
    if functions and model in SUPPORTS_FUNCTIONS:
        log.debug(f"Calling model with {len(functions)} functions")
        if model in SUPPORTS_TOOLS:
            tools = []
            for func in functions:
                function = {"type": "function", "function": func, "name": func["name"]}
                tools.append(function)
            if tools:
                kwargs["tools"] = tools
        else:
            kwargs["functions"] = functions
    response = await client.chat.completions.create(**kwargs)
    log.debug(f"CHAT RESPONSE TYPE: {type(response)}")
    return response


async def request_completion_raw(
    model: str,
    prompt: str,
    temperature: float,
    api_key: str,
    max_tokens: int,
    api_base: Optional[str] = None,
    timeout: int = 60,
) -> str:
    log.debug(f"request_completion_raw: {model}")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=api_base,
        max_retries=5,
    )
    kwargs = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "timeout": timeout,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    response = await client.completions.create(**kwargs)
    log.debug(f"COMPLETION RESPONSE TYPE: {type(response)}")
    return response


@cached(ttl=3600)
async def request_embedding_raw(
    text: str,
    api_key: str,
    api_base: Optional[str] = None,
) -> List[float]:
    log.debug("request_embedding_raw")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=api_base,
        max_retries=5,
    )
    response = await client.embeddings.create(
        input=text,
        model="text-embedding-ada-002",
        timeout=30,
    )
    log.debug(f"EMBED RESPONSE TYPE: {type(response)}")
    return response


@cached(ttl=30)
async def request_tokens_raw(text: str, url: str):
    payload = {"text": text, "tokens": None}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            res = await response.json()
            return res["tokens"]


@cached(ttl=30)
async def request_text_raw(tokens: list, url: str):
    payload = {"text": None, "tokens": tokens}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            res = await response.json()
            return res["text"]


@cached(ttl=1800)
async def request_model(url: str):
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            return await response.json()
