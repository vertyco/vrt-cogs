import logging
import typing as t
from typing import List, Optional

import httpx
import openai
from aiocache import cached
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

from .constants import NO_DEVELOPER_ROLE, PRICES, SUPPORTS_SEED, SUPPORTS_TOOLS

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
    base_url: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
) -> ChatCompletion:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    kwargs = {"model": model, "messages": messages}

    if model in PRICES and base_url is None:
        # Using an OpenAI model
        if not model.startswith("o"):
            kwargs["temperature"] = temperature
            kwargs["frequency_penalty"] = frequency_penalty
            kwargs["presence_penalty"] = presence_penalty

        if model.startswith("o") and reasoning_effort is not None:
            kwargs["reasoning_effort"] = reasoning_effort

        if max_tokens > 0:
            kwargs["max_completion_tokens"] = max_tokens

        if seed and model in SUPPORTS_SEED:
            kwargs["seed"] = seed

    if functions and model not in NO_DEVELOPER_ROLE:
        if model in SUPPORTS_TOOLS:
            tools = []
            for func in functions:
                function = {"type": "function", "function": func, "name": func["name"]}
                tools.append(function)
            if tools:
                kwargs["tools"] = tools
                # If passing tools, make sure the messages payload has no "function_call" key
                for idx, message in enumerate(messages):
                    if "function_call" in message:
                        # Remove the message from the payload
                        del kwargs["messages"][idx]

        else:
            kwargs["functions"] = functions
            # If passing functions, make sure the messages payload has no tool calls
            for idx, message in enumerate(messages):
                if "tool_calls" in message:
                    # Remove the message from the payload
                    del kwargs["messages"][idx]

    add_breadcrumb(
        category="api",
        message=f"Calling request_chat_completion_raw: {model}",
        level="info",
        data=kwargs,
    )
    response: ChatCompletion = await client.chat.completions.create(**kwargs)

    log.debug(f"request_chat_completion_raw: {model} -> {response.model}")
    return response


@cached(ttl=60)
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
    base_url: Optional[str] = None,
) -> CreateEmbeddingResponse:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
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
    base_url: Optional[str] = None,
) -> Image:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
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


async def create_memory_call(
    messages: t.List[dict],
    api_key: str,
    base_url: Optional[str] = None,
) -> t.Union[CreateMemoryResponse, None]:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-2024-11-20",
        messages=messages,
        response_format=CreateMemoryResponse,
    )
    return response.choices[0].message.parsed
