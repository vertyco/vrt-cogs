from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import Function

from assistant.common import calls
from assistant.common.chat import remember_reasoning
from assistant.common.responses import responses_to_chat_completion, to_responses_input

REASONING_ITEM = {"type": "reasoning", "id": "rs_1", "encrypted_content": "abc", "summary": []}


def make_response(output: list) -> SimpleNamespace:
    return SimpleNamespace(id="resp_1", model="gpt-5.5", created_at=0, usage=None, output=output)


def test_adapter_captures_encrypted_reasoning():
    reasoning = SimpleNamespace(type="reasoning", id="rs_1", encrypted_content="abc", summary=[])
    call = SimpleNamespace(type="function_call", call_id="call_1", id="fc_1", name="get_time", arguments="{}")
    result = responses_to_chat_completion(make_response([reasoning, call]), "gpt-5.5")
    message = result.choices[0].message
    assert message.reasoning_items == [REASONING_ITEM]
    assert getattr(message, "reasoning_content", None) is None


def test_adapter_keeps_summary_text_with_encrypted_reasoning():
    reasoning = SimpleNamespace(
        type="reasoning", id="rs_1", encrypted_content="abc", summary=[SimpleNamespace(text="thinking")]
    )
    result = responses_to_chat_completion(make_response([reasoning]), "gpt-5.5")
    message = result.choices[0].message
    assert message.reasoning_content == "thinking"
    assert message.reasoning_items[0]["summary"] == [{"type": "summary_text", "text": "thinking"}]


def test_adapter_skips_reasoning_without_encrypted_content():
    reasoning = SimpleNamespace(type="reasoning", id="rs_1", encrypted_content=None, summary=[])
    result = responses_to_chat_completion(make_response([reasoning]), "gpt-5.5")
    assert getattr(result.choices[0].message, "reasoning_items", None) is None


def test_to_responses_input_replays_reasoning_before_matching_call():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "x"},
        {"role": "tool", "tool_call_id": "call_2", "content": "y"},
    ]
    items = to_responses_input(messages, reasoning_items={"call_1": [REASONING_ITEM]})
    types = [(i.get("type"), i.get("call_id")) for i in items[1:4]]
    assert types == [("reasoning", None), ("function_call", "call_1"), ("function_call", "call_2")]
    assert items[1] == REASONING_ITEM


def test_to_responses_input_without_reasoning_is_unchanged():
    messages = [
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "function": {"name": "a"}}]},
    ]
    assert [i["type"] for i in to_responses_input(messages)] == ["function_call"]


class FakeStream:
    def __init__(self, events):
        self.events = events

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)


def completed_events():
    usage = SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2, input_tokens_details=None)
    completed = SimpleNamespace(id="r", model="gpt-5.5", created_at=0, usage=usage, output=[])
    return [SimpleNamespace(type="response.completed", response=completed)]


TOOL_MESSAGES = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "function": {"name": "a"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "x"},
]


@pytest.mark.asyncio
async def test_request_codex_raw_includes_and_replays_reasoning(monkeypatch):
    captured: dict = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return FakeStream(completed_events())

    monkeypatch.setattr(calls, "get_client", lambda *a, **k: SimpleNamespace(responses=FakeResponses()))
    auth = SimpleNamespace(access_token="t", account_id="a")
    monkeypatch.setattr(calls, "backend_headers", lambda auth: {})
    await calls.request_codex_raw(
        model="gpt-5.5", messages=TOOL_MESSAGES, auth=auth, reasoning_items={"call_1": [REASONING_ITEM]}
    )
    assert captured["include"] == ["reasoning.encrypted_content"]
    assert captured["store"] is False
    assert captured["input"][1] == REASONING_ITEM
    assert captured["input"][2]["type"] == "function_call"


@pytest.mark.asyncio
async def test_request_responses_raw_includes_and_replays_reasoning(monkeypatch):
    captured: dict = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="r", model="gpt-5.5", created_at=0, usage=None, output=[])

    monkeypatch.setattr(calls, "get_client", lambda *a, **k: SimpleNamespace(responses=FakeResponses()))
    await calls.request_responses_raw(
        model="gpt-5.5", messages=TOOL_MESSAGES, api_key="k", reasoning_items={"call_1": [REASONING_ITEM]}
    )
    assert captured["include"] == ["reasoning.encrypted_content"]
    assert captured["store"] is False
    assert captured["input"][1] == REASONING_ITEM


def make_tool_call(call_id: str) -> ChatCompletionMessageFunctionToolCall:
    return ChatCompletionMessageFunctionToolCall(
        id=call_id, type="function", function=Function(name="a", arguments="{}")
    )


def test_remember_reasoning_keys_by_first_tool_call():
    store: dict = {}
    message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[make_tool_call("call_1"), make_tool_call("call_2")],
        reasoning_items=[REASONING_ITEM],
    )
    remember_reasoning(store, message)
    assert store == {"call_1": [REASONING_ITEM]}


def test_remember_reasoning_ignores_messages_without_items_or_calls():
    store: dict = {}
    remember_reasoning(store, ChatCompletionMessage(role="assistant", content="hi"))
    remember_reasoning(store, ChatCompletionMessage(role="assistant", content=None, reasoning_items=[REASONING_ITEM]))
    assert store == {}
