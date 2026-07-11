"""Adapter between Chat Completions and the Responses API.

The gpt-5.4/5.5/5.6 reasoning family cannot use a configurable ``reasoning_effort``
alongside function tools on ``/v1/chat/completions``. That combination is only
supported on ``/v1/responses``. To keep the rest of the cog (conversation storage,
``chat.py`` parsing, usage/cache accounting) unchanged, this module translates a
Chat-Completions-shaped request into a Responses request and translates the
Responses result back into a ``ChatCompletion`` object.

The conversation store stays in Chat Completions format. Translation is stateless
and per-call (``store=False``), so switching models mid-conversation still works.
"""

import typing as t

from openai.types.chat.chat_completion import ChatCompletion, Choice
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails


def _text_part_type(role: str) -> str:
    return "output_text" if role == "assistant" else "input_text"


def _convert_content(content: t.Any, role: str) -> t.Any:
    """Translate a Chat Completions message ``content`` into Responses form.

    Plain strings pass through untouched. Multi-part content (text + images) is
    remapped: ``text`` -> ``input_text``/``output_text`` and ``image_url`` ->
    ``input_image``.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    parts: list[dict] = []
    for item in content:
        if not isinstance(item, dict):
            parts.append({"type": _text_part_type(role), "text": str(item)})
            continue
        itype = item.get("type")
        if itype in ("text", "input_text", "output_text"):
            parts.append({"type": _text_part_type(role), "text": item.get("text", "")})
        elif itype in ("image_url", "input_image"):
            img = item.get("image_url")
            if isinstance(img, dict):
                url = img.get("url")
                detail = img.get("detail")
            else:
                url = img
                detail = item.get("detail")
            new_part: dict = {"type": "input_image", "image_url": url}
            if detail:
                new_part["detail"] = detail
            parts.append(new_part)
        else:
            # Unknown part (e.g. a cache_control marker) -> coerce to text so the
            # payload stays valid rather than being rejected by the API.
            parts.append({"type": _text_part_type(role), "text": item.get("text", "")})
    return parts


def _stringify(content: t.Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict) and part.get("text")
        )
    return "" if content is None else str(content)


def to_responses_input(messages: list[dict]) -> list[dict]:
    """Translate Chat Completions ``messages`` into Responses ``input`` items."""
    items: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id"),
                    "output": _stringify(content),
                }
            )
            continue

        if role == "assistant":
            if content:
                items.append({"role": "assistant", "content": _convert_content(content, role)})
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": tc.get("id"),
                            "name": fn.get("name"),
                            "arguments": fn.get("arguments") or "{}",
                        }
                    )
            elif msg.get("function_call"):
                fc = msg["function_call"]
                # Legacy single function_call has no id; reuse the name as call_id.
                items.append(
                    {
                        "type": "function_call",
                        "call_id": fc.get("name"),
                        "name": fc.get("name"),
                        "arguments": fc.get("arguments") or "{}",
                    }
                )
            continue

        # system / developer / user
        items.append({"role": role, "content": _convert_content(content, role)})

    return items


def to_responses_tools(functions: list[dict]) -> list[dict]:
    """Flatten Chat Completions function schemas into Responses ``tools`` form."""
    tools: list[dict] = []
    for func in functions:
        tools.append(
            {
                "type": "function",
                "name": func.get("name"),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            }
        )
    return tools


def responses_to_chat_completion(resp: t.Any, model: str) -> ChatCompletion:
    """Rebuild a ``ChatCompletion`` from a Responses ``Response`` object."""
    content_text: t.Optional[str] = None
    refusal: t.Optional[str] = None
    reasoning_text: t.Optional[str] = None
    tool_calls: list[ChatCompletionMessageToolCall] = []

    for item in getattr(resp, "output", None) or []:
        itype = getattr(item, "type", None)
        if itype == "message":
            for part in getattr(item, "content", None) or []:
                ptype = getattr(part, "type", None)
                if ptype == "output_text":
                    content_text = (content_text or "") + (getattr(part, "text", "") or "")
                elif ptype == "refusal":
                    refusal = getattr(part, "refusal", None)
        elif itype == "function_call":
            tool_calls.append(
                ChatCompletionMessageToolCall(
                    id=getattr(item, "call_id", None) or getattr(item, "id", "") or "",
                    type="function",
                    function=Function(
                        name=getattr(item, "name", "") or "",
                        arguments=getattr(item, "arguments", None) or "{}",
                    ),
                )
            )
        elif itype == "reasoning":
            summary = getattr(item, "summary", None) or []
            joined = " ".join(
                getattr(s, "text", "") for s in summary if getattr(s, "text", "")
            ).strip()
            if joined:
                reasoning_text = joined

    message_kwargs: dict = {
        "role": "assistant",
        "content": content_text,
        "refusal": refusal,
        "tool_calls": tool_calls or None,
    }
    if reasoning_text:
        # openai's BaseModel allows extra fields; chat.py reads this via getattr and
        # strips it from the persisted dump.
        message_kwargs["reasoning_content"] = reasoning_text
    message = ChatCompletionMessage(**message_kwargs)

    usage: t.Optional[CompletionUsage] = None
    ru = getattr(resp, "usage", None)
    if ru is not None:
        cached = 0
        itd = getattr(ru, "input_tokens_details", None)
        if itd is not None:
            cached = getattr(itd, "cached_tokens", 0) or 0
        usage = CompletionUsage(
            prompt_tokens=getattr(ru, "input_tokens", 0) or 0,
            completion_tokens=getattr(ru, "output_tokens", 0) or 0,
            total_tokens=getattr(ru, "total_tokens", 0) or 0,
            prompt_tokens_details=PromptTokensDetails(cached_tokens=cached),
        )

    choice = Choice(
        index=0,
        finish_reason="tool_calls" if tool_calls else "stop",
        message=message,
        logprobs=None,
    )
    return ChatCompletion(
        id=getattr(resp, "id", None) or "responses",
        choices=[choice],
        created=int(getattr(resp, "created_at", 0) or 0),
        model=getattr(resp, "model", None) or model,
        object="chat.completion",
        usage=usage,
    )
