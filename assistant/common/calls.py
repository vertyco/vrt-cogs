import logging
import typing as t
from typing import List, Optional

import httpx
import openai
from openai.types import CreateEmbeddingResponse
from openai.types.chat import ChatCompletion
from sentry_sdk import add_breadcrumb
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .constants import SUPPORTS_SEED, SUPPORTS_TOOLS

log = logging.getLogger("red.vrt.assistant.calls")


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            openai.BadRequestError,
            httpx.ReadTimeout,
            openai.InternalServerError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def request_chat_completion_raw(
    model: str,
    messages: List[dict],
    temperature: float,
    api_key: str,
    max_tokens: int,
    functions: Optional[List[dict]] = None,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    seed: int = None,
) -> ChatCompletion:
    client = openai.AsyncOpenAI(api_key=api_key)
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
    }
    if max_tokens > 0:
        kwargs["max_tokens"] = max_tokens
    if seed and model in SUPPORTS_SEED:
        kwargs["seed"] = seed
    if functions:
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
    response: ChatCompletion = await client.chat.completions.create(**kwargs)

    log.debug(f"request_chat_completion_raw: {model} -> {response.model}")
    return response


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            openai.BadRequestError,
            httpx.ReadTimeout,
            openai.InternalServerError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=15),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def request_embedding_raw(
    text: str,
    api_key: str,
    model: str,
) -> CreateEmbeddingResponse:
    client = openai.AsyncOpenAI(api_key=api_key)
    add_breadcrumb(
        category="api",
        message="Calling request_embedding_raw",
        level="info",
        data={"text": text},
    )
    response: CreateEmbeddingResponse = await client.embeddings.create(input=text, model=model)
    log.debug(f"request_embedding_raw: {model} -> {response.model}")
    return response
