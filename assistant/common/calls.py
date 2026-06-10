import logging
import re
import typing as t
from typing import List, Optional

import httpx
import openai
from aiocache import cached
from openai.types import CreateEmbeddingResponse, Image, ImagesResponse
from openai.types.chat import ChatCompletion
from sentry_sdk import add_breadcrumb
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from .constants import MODELS, NO_DEVELOPER_ROLE, OLD_TOOL_SCHEMA, SUPPORTS_SEED

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
    tool_choice: Optional[t.Union[str, dict]] = None,
    # ----- Prompt-caching params -----
    # OpenRouter response caching (Mode A).
    openrouter_cache: bool = False,
    openrouter_cache_ttl: int = 300,
    # OpenRouter session routing (sticky provider).
    session_id: Optional[str] = None,
    # OpenRouter provider prompt cache TTL (Mode B). One of None,
    # "off", "5m", "1h". Applies to Anthropic / Gemini / Qwen models.
    openrouter_prompt_cache_ttl: Optional[str] = None,
    # OpenAI prompt_cache_key for direct-OpenAI routing stickiness.
    guild_id: Optional[int] = None,
    # OpenRouter provider routing preferences dict (injected as extra_body["provider"]).
    openrouter_provider: Optional[dict] = None,
) -> ChatCompletion:
    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    use_legacy_functions = bool(
        functions and model not in NO_DEVELOPER_ROLE and base_url is None and model in OLD_TOOL_SCHEMA
    )

    kwargs = {"model": model, "messages": get_request_messages(messages, use_legacy_functions)}

    if base_url is not None:
        # Custom endpoint: send standard params, skip OpenAI-specific ones
        kwargs["temperature"] = temperature
        kwargs["frequency_penalty"] = frequency_penalty
        kwargs["presence_penalty"] = presence_penalty
        if max_tokens and max_tokens > 0:
            kwargs["max_tokens"] = max_tokens
    elif model in MODELS:
        # Using an OpenAI model
        if not model.startswith("o") and "gpt-5" not in model:
            kwargs["temperature"] = temperature
            kwargs["frequency_penalty"] = frequency_penalty
            kwargs["presence_penalty"] = presence_penalty

        if (model.startswith("o") or "gpt-5" in model) and reasoning_effort is not None:
            if "gpt-5.4" in model or "gpt-5.5" in model:
                # gpt-5.4/5.5 support: none, low, medium, high, xhigh (not minimal)
                # Chat Completions does not support reasoning_effort + tools together for these
                if reasoning_effort == "minimal":
                    reasoning_effort = "low"
                if not functions:
                    kwargs["reasoning_effort"] = reasoning_effort
            elif "gpt-5" in model:
                # gpt-5 (non-5.4/5.5) supports: minimal, low, medium, high (not none/xhigh)
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
                if tool_choice is not None:
                    kwargs["tool_choice"] = tool_choice

    # ------------------------------------------------------------------
    # OpenRouter cache controls.
    # ------------------------------------------------------------------
    is_openrouter = bool(base_url and "openrouter.ai" in base_url.lower())
    extra_headers: dict = {}
    extra_body: dict = {}

    if is_openrouter:
        # Mode A - response caching at the OpenRouter network layer.
        if openrouter_cache:
            extra_headers["X-OpenRouter-Cache"] = "true"
            ttl = max(1, min(int(openrouter_cache_ttl or 300), 86400))
            extra_headers["X-OpenRouter-Cache-TTL"] = str(ttl)

        # Sticky session routing.
        if session_id:
            extra_body["session_id"] = session_id

        # Mode B - provider-level prompt cache via cache_control.
        ttl_setting = (openrouter_prompt_cache_ttl or "").lower()
        if ttl_setting in ("5m", "1h"):
            model_prefix = model.split("/", 1)[0].lower() if "/" in model else ""

            def build_cc() -> dict:
                cc: dict = {"type": "ephemeral"}
                if ttl_setting == "1h":
                    cc["ttl"] = "1h"
                return cc

            # Qwen snapshot endpoints (e.g. qwen3.5-plus-02-15,
            # qwen2.5-vl-72b-instruct-2024-09-19) reject cache_control.
            # Detect a trailing -MM-DD or -YYYY-MM-DD date suffix and skip
            # the breakpoint so we don't surface a hard error to admins.
            qwen_supports_cc = model_prefix != "qwen" or not re.search(
                r"-(?:\d{4}-)?\d{2}-\d{2}$", model.lower()
            )

            if model_prefix == "anthropic":
                # Anthropic supports automatic caching via top-level
                # cache_control on the request body. The openai-python SDK
                # rejects unknown kwargs, so we route it through extra_body.
                extra_body["cache_control"] = build_cc()
            elif model_prefix in ("google", "deepseek") or (model_prefix == "qwen" and qwen_supports_cc):
                # Gemini / Qwen / DeepSeek require explicit content-block
                # breakpoints. Place one in the last system/developer
                # message so the system prompt and tool defs are cached.
                messages_payload = kwargs["messages"]
                for idx in range(len(messages_payload) - 1, -1, -1):
                    msg = messages_payload[idx]
                    if msg.get("role") in ("system", "developer"):
                        content = msg.get("content")
                        if isinstance(content, str) and content.strip():
                            msg["content"] = [
                                {"type": "text", "text": content},
                                {"type": "text", "text": "", "cache_control": build_cc()},
                            ]
                        elif isinstance(content, list) and content:
                            # Append a cache_control marker to the last text block.
                            content[-1] = {**content[-1], "cache_control": build_cc()}
                        break

        if openrouter_provider:
            extra_body["provider"] = openrouter_provider

    # ------------------------------------------------------------------
    # OpenAI prompt_cache_key for direct OpenAI calls.
    # Improves routing stickiness so per-guild traffic lands on the same
    # inference machine more often, raising cache hit rate.
    # ------------------------------------------------------------------
    if base_url is None and guild_id is not None and model in MODELS:
        kwargs["prompt_cache_key"] = f"guild-{guild_id}"

    if extra_headers:
        kwargs["extra_headers"] = extra_headers
    if extra_body:
        kwargs["extra_body"] = extra_body

    add_breadcrumb(
        category="api",
        message=f"Calling request_chat_completion_raw: {model}",
        level="info",
        data=kwargs,
    )
    # Final wire-gate sanitation: some reasoning models emit an assistant turn
    # with null content and no tool_calls; providers like qwen via OpenRouter
    # reject it with 400 'Provider returned error'. Salvage reasoning into
    # content (or drop to a stub) so the payload is always valid.
    def sanitize_messages_for_wire(payload):
        if not isinstance(payload, list):
            return
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            if entry.get("role") != "assistant":
                continue
            if entry.get("content") or entry.get("tool_calls") or entry.get("function_call"):
                continue
            salvaged = entry.get("reasoning_content") or entry.get("reasoning") or ""
            if not salvaged and isinstance(entry.get("reasoning_details"), list):
                salvaged = " ".join(
                    d.get("text", "") for d in entry["reasoning_details"] if isinstance(d, dict)
                ).strip()
            entry["content"] = salvaged or "Continuing."
            entry.pop("reasoning_content", None)
            entry.pop("reasoning", None)
            entry.pop("reasoning_details", None)

    sanitize_messages_for_wire(kwargs.get("messages"))

    try:
        response: ChatCompletion = await client.chat.completions.create(**kwargs)
    except openai.NotFoundError as exc:
        # Some OpenRouter provider endpoints for the routed model do not support a
        # forced tool_choice value and reply 404 "No endpoints found that support
        # the provided 'tool_choice' value". Drop tool_choice and retry once.
        # exc.body may be the inner error dict ({"message": ...}) or the full
        # envelope ({"error": {"message": ...}}); fall back to str(exc) either way.
        body = getattr(exc, "body", None)
        message_text = str(exc)
        if isinstance(body, dict):
            inner = body.get("error") if isinstance(body.get("error"), dict) else body
            message_text = f"{message_text} {inner.get('message', '')}"
        if "tool_choice" in message_text and "tool_choice" in kwargs:
            kwargs.pop("tool_choice", None)
            response = await client.chat.completions.create(**kwargs)
        else:
            raise
    except TypeError as exc:
        # Sentry SDK bug: its OpenAI integration iterates response.choices without
        # a null guard.  Some OpenRouter models return HTTP 200 with choices=null
        # (e.g. when the provider is warming up or the response is malformed).
        # The TypeError surfaces here instead of from our code.
        raise RuntimeError(
            f"Model {model!r} returned an empty response (choices=null). "
            "The provider may be temporarily unavailable — try again or switch models."
        ) from exc

    if not response.choices:
        raise RuntimeError(
            f"Model {model!r} returned an empty choices list. "
            "The provider may be temporarily unavailable — try again or switch models."
        )

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
    text: t.Union[str, list[str]],
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
