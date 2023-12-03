import logging
import typing as t
from typing import List, Optional

import aiohttp
import httpx
import openai
from aiocache import cached
from perftracker import perf
from sentry_sdk import add_breadcrumb
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .constants import MODELS_1106, SUPPORTS_FUNCTIONS, SUPPORTS_TOOLS

log = logging.getLogger("red.vrt.assistant.calls")


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            openai.BadRequestError,
            httpx.ReadTimeout,
        ]
    ),
    wait=wait_random_exponential(min=5, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
@perf()
async def request_chat_completion_raw(
    model: str,
    messages: List[dict],
    temperature: float,
    api_key: str,
    max_tokens: int,
    api_base: Optional[str] = None,
    functions: Optional[List[dict]] = None,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    seed: int = None,
):
    log.debug(f"request_chat_completion_raw: {model}")
    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=api_base,
        max_retries=5,
        timeout=240,
    )
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    if seed and model in MODELS_1106:
        kwargs["seed"] = seed
    if functions and model in SUPPORTS_FUNCTIONS:
        if model in SUPPORTS_TOOLS:
            tools = []
            for func in functions:
                function = {"type": "function", "function": func, "name": func["name"]}
                tools.append(function)
            if tools:
                kwargs["tools"] = tools
        else:
            kwargs["functions"] = functions

    add_breadcrumb(
        category="api",
        message=f"Calling request_chat_completion_raw: {model}",
        level="info",
        data=kwargs,
    )
    response = await client.chat.completions.create(**kwargs)
    # log.debug(f"CHAT RESPONSE TYPE: {type(response)}")
    return response


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            openai.BadRequestError,
            httpx.ReadTimeout,
        ]
    ),
    wait=wait_random_exponential(min=5, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
@perf()
async def request_completion_raw(
    model: str,
    prompt: str,
    temperature: float,
    api_key: str,
    max_tokens: int,
    api_base: Optional[str] = None,
) -> str:
    log.debug(f"request_completion_raw: {model}")
    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=api_base,
        max_retries=5,
        timeout=240,
    )
    kwargs = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    add_breadcrumb(
        category="api",
        message=f"Calling request_completion_raw: {model}",
        level="info",
        data=kwargs,
    )
    response = await client.completions.create(**kwargs)
    # log.debug(f"COMPLETION RESPONSE TYPE: {type(response)}")
    return response


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            openai.BadRequestError,
            httpx.ReadTimeout,
        ]
    ),
    wait=wait_random_exponential(min=5, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
@perf()
@cached(ttl=3600)
async def request_embedding_raw(
    text: str,
    api_key: str,
    api_base: Optional[str] = None,
) -> List[float]:
    log.debug("request_embedding_raw")
    client = openai.AsyncOpenAI(
        api_key=api_key,
        base_url=api_base,
        max_retries=5,
        timeout=15,
    )
    add_breadcrumb(
        category="api",
        message="Calling request_embedding_raw",
        level="info",
        data={"text": text},
    )
    response = await client.embeddings.create(
        input=text,
        model="text-embedding-ada-002",
    )
    # log.debug(f"EMBED RESPONSE TYPE: {type(response)}")
    return response


@perf()
@cached(ttl=30)
async def request_tokens_raw(text: str, url: str):
    payload = {"text": text, "tokens": None}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            res = await response.json()
            return res["tokens"]


@perf()
@cached(ttl=30)
async def request_text_raw(tokens: list, url: str):
    payload = {"text": None, "tokens": tokens}
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            res = await response.json()
            return res["text"]


@perf()
@cached(ttl=1800)
async def request_model(url: str):
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            return await response.json()
