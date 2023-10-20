import logging
from typing import Dict, List, Optional, Union

import aiohttp
import openai
from aiocache import cached
from openai.error import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from openai.version import VERSION
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .constants import SUPPORTS_FUNCTIONS

log = logging.getLogger("red.vrt.assistant.calls")


@retry(
    retry=retry_if_exception_type(
        Union[
            APIError,
            Timeout,
            APIConnectionError,
            RateLimitError,
            ServiceUnavailableError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
@cached(ttl=21600)
async def request_embedding_raw(
    text: str,
    api_key: str,
    api_base: Optional[str] = None,
) -> List[float]:
    log.debug("request_embedding_raw")
    return await openai.Embedding.acreate(
        input=text,
        model="text-embedding-ada-002",
        api_key=api_key,
        api_base=api_base,
        timeout=30,
    )


@retry(
    retry=retry_if_exception_type(
        Union[
            Timeout,
            APIConnectionError,
            RateLimitError,
            ServiceUnavailableError,
            APIError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def request_chat_completion_raw(
    model: str,
    messages: List[dict],
    temperature: float,
    api_key: str,
    max_tokens: int,
    api_base: Optional[str] = None,
    functions: Optional[List[dict]] = None,
    timeout: int = 60,
) -> Dict[str, str]:
    log.debug(f"request_chat_completion_raw: {model}")
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "api_key": api_key,
        "api_base": api_base,
        "timeout": timeout,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    if functions and VERSION >= "0.27.6" and model in SUPPORTS_FUNCTIONS:
        log.debug(f"Calling model with {len(functions)} functions")
        kwargs["functions"] = functions
    return await openai.ChatCompletion.acreate(**kwargs)


@retry(
    retry=retry_if_exception_type(
        Union[
            Timeout,
            APIConnectionError,
            RateLimitError,
            APIError,
            ServiceUnavailableError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
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
    kwargs = {
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "api_key": api_key,
        "api_base": api_base,
        "timeout": timeout,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    return await openai.Completion.acreate(**kwargs)


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
