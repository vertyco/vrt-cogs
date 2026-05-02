import logging
import typing as t
from typing import List, Optional

import httpx
import openai
import orjson
from aiocache import cached
from openai.types import CreateEmbeddingResponse, Image, ImagesResponse
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, ValidationError
from sentry_sdk import add_breadcrumb
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .constants import NO_DEVELOPER_ROLE, OLD_TOOL_SCHEMA, PRICES, SUPPORTS_SEED

log = logging.getLogger("red.vrt.assistant.calls")


def get_custom_endpoint_image_error() -> str:
    return (
        "The configured custom endpoint does not support OpenAI image generation endpoints. "
        "Many OpenAI-compatible backends support chat and embeddings but do not implement /v1/images."
    )


def get_request_messages(messages: List[dict], use_legacy_functions: bool) -> list[dict]:
    """Return a request-safe copy of the chat payload.

    The low-level API helper should never mutate the caller's conversation state.
    When targeting the legacy ``functions`` schema, modern tool-call history is
    downgraded to the older assistant/function message format where possible.
    """
    payload: list[dict] = []
    for message in messages:
        copied = message.copy()

        if use_legacy_functions:
            if copied.get("role") == "tool":
                copied["role"] = "function"
                copied.pop("tool_call_id", None)

            tool_calls = copied.pop("tool_calls", None)
            if tool_calls:
                if len(tool_calls) == 1:
                    function = tool_calls[0].get("function", {})
                    name = function.get("name")
                    arguments = function.get("arguments")
                    if name and arguments is not None:
                        copied["function_call"] = {"name": name, "arguments": arguments}
                else:
                    log.debug("Dropping parallel tool call metadata for legacy functions payload")
        else:
            copied.pop("function_call", None)

        payload.append(copied)

    return payload


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
    max_tokens: Optional[int] = None,
    functions: Optional[List[dict]] = None,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    seed: int = None,
    base_url: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    verbosity: Optional[str] = None,
) -> ChatCompletion:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    use_legacy_functions = bool(functions and model not in NO_DEVELOPER_ROLE and base_url is None and model in OLD_TOOL_SCHEMA)

    kwargs = {"model": model, "messages": get_request_messages(messages, use_legacy_functions)}

    if base_url is not None:
        # Custom endpoint: send standard params, skip OpenAI-specific ones
        kwargs["temperature"] = temperature
        kwargs["frequency_penalty"] = frequency_penalty
        kwargs["presence_penalty"] = presence_penalty
        if max_tokens and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
    elif model in PRICES:
        # Using an OpenAI model
        if not model.startswith("o") and "gpt-5" not in model:
            kwargs["temperature"] = temperature
            kwargs["frequency_penalty"] = frequency_penalty
            kwargs["presence_penalty"] = presence_penalty

        if (model.startswith("o") or "gpt-5" in model) and reasoning_effort is not None:
            if "gpt-5.4" in model:
                # gpt-5.4 supports: none, low, medium, high, xhigh (not minimal)
                # Chat Completions does not support reasoning_effort + tools together for gpt-5.4
                if reasoning_effort == "minimal":
                    reasoning_effort = "low"
                if not functions:
                    kwargs["reasoning_effort"] = reasoning_effort
            elif "gpt-5" in model:
                # gpt-5 (non-5.4) supports: minimal, low, medium, high (not none/xhigh)
                if reasoning_effort == "none":
                    reasoning_effort = "minimal"
                elif reasoning_effort == "xhigh":
                    reasoning_effort = "high"
                kwargs["reasoning_effort"] = reasoning_effort
            else:
                # o-series supports: low, medium, high
                if reasoning_effort in ("none", "minimal"):
                    reasoning_effort = "low"
                elif reasoning_effort == "xhigh":
                    reasoning_effort = "high"
                kwargs["reasoning_effort"] = reasoning_effort

        if "gpt-5" in model and verbosity is not None:
            kwargs["verbosity"] = verbosity

        if max_tokens and max_tokens > 0:
            kwargs["max_completion_tokens"] = max_tokens

        if seed and model in SUPPORTS_SEED:
            kwargs["seed"] = seed

    if functions and model not in NO_DEVELOPER_ROLE:
        if use_legacy_functions:
            kwargs["functions"] = functions
        else:
            # Custom endpoints and modern OpenAI models use the tools schema
            tools = [{"type": "function", "function": func} for func in functions]
            if tools:
                kwargs["tools"] = tools

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
    size: t.Literal["1024x1024", "1792x1024", "1024x1792", "1024x1536", "1536x1024"] = "1024x1024",
    quality: t.Literal["standard", "hd", "low", "medium", "high"] = "standard",
    style: t.Optional[t.Literal["natural", "vivid"]] = "vivid",
    model: t.Literal["dall-e-3", "gpt-image-1.5"] = "dall-e-3",
    base_url: Optional[str] = None,
) -> Image:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    kwargs = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
    }

    # Handle model-specific parameters
    if model == "dall-e-3":
        kwargs["quality"] = quality if quality in ["standard", "hd"] else "standard"
        kwargs["style"] = style
        kwargs["response_format"] = "b64_json"
    elif model == "gpt-image-1.5":
        if quality in ["low", "medium", "high"]:
            kwargs["quality"] = quality
        else:
            kwargs["quality"] = "medium"
        kwargs["response_format"] = "b64_json"
        # gpt-image-1.5 doesn't support style parameter

    response: ImagesResponse = await client.images.generate(**kwargs)
    images: list[Image] = response.data
    return images[0]


async def request_image_edit_raw(
    prompt: str,
    api_key: str,
    images: t.List[t.Tuple[str, t.Any, str]],  # list[(filename, BytesIO, mime_type)]
    base_url: Optional[str] = None,
) -> Image:
    assert all(isinstance(image, tuple) and len(image) == 3 for image in images), (
        "All images must be tuples of (filename, file_data, mime_type)."
    )
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    response: ImagesResponse = await client.images.edit(
        model="gpt-image-1.5",
        prompt=prompt,
        image=images,
    )
    images: list[Image] = response.data
    return images[0]


class CreateMemoryResponse(BaseModel):
    memory_name: str
    memory_content: str


async def create_memory_call(
    messages: t.List[dict],
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> t.Union[CreateMemoryResponse, None]:
    if not model:
        raise ValueError("A model is required for memory calls")

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    if base_url is None:
        response = await client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=CreateMemoryResponse,
        )
        return response.choices[0].message.parsed

    response: ChatCompletion = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.0,
        max_tokens=300,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        return None
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        return CreateMemoryResponse.model_validate(orjson.loads(content))
    except (orjson.JSONDecodeError, ValidationError) as e:
        log.warning("Failed to parse memory response from custom endpoint", exc_info=e)
        return None
