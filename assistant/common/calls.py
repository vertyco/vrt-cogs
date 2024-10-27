import logging
import typing as t
from typing import List, Optional

import httpx
import openai
from openai.types import CreateEmbeddingResponse, Image, ImagesResponse
from openai.types.chat import ChatCompletion
from pydantic import BaseModel
from sentry_sdk import add_breadcrumb
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .constants import NO_SYSTEM_MESSAGES, SUPPORTS_SEED, SUPPORTS_TOOLS

log = logging.getLogger("red.vrt.assistant.calls")


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            httpx.ReadTimeout,
            openai.InternalServerError,
        ]
    ),
    wait=wait_random_exponential(min=1, max=30),
    stop=stop_after_attempt(5),
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

    kwargs = {"model": model, "messages": messages}

    if model not in NO_SYSTEM_MESSAGES:
        kwargs["temperature"] = temperature
        kwargs["frequency_penalty"] = frequency_penalty
        kwargs["presence_penalty"] = presence_penalty

    if max_tokens > 0:
        if model in NO_SYSTEM_MESSAGES:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

    if seed and model in SUPPORTS_SEED:
        kwargs["seed"] = seed

    if functions and model not in NO_SYSTEM_MESSAGES:
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
            httpx.ReadTimeout,
            openai.InternalServerError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=30),
    stop=stop_after_attempt(5),
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


@retry(
    retry=retry_if_exception_type(
        t.Union[
            httpx.TimeoutException,
            httpx.ReadTimeout,
            openai.InternalServerError,
        ]
    ),
    wait=wait_random_exponential(min=5, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def request_image_raw(
    prompt: str,
    api_key: str,
    size: t.Literal["1024x1024", "1792x1024", "1024x1792"] = "1024x1024",
    quality: t.Literal["standard", "hd"] = "standard",
    style: t.Literal["natural", "vivid"] = "vivid",
) -> Image:
    client = openai.AsyncOpenAI(api_key=api_key)
    response: ImagesResponse = await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,
        quality=quality,
        style=style,
        response_format="b64_json",
        n=1,
    )
    return response.data[0]


class CreateMemoryResponse(BaseModel):
    memory_name: str
    memory_content: str


async def create_memory_call(messages: t.List[dict], api_key: str) -> t.Union[CreateMemoryResponse, None]:
    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=messages,
        response_format=CreateMemoryResponse,
    )
    return response.choices[0].message.parsed
