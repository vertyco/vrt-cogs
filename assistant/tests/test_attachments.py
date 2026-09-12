# pyright: reportAbstractUsage=false
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant.common.api import API, get_encoding
from assistant.common.chat import ChatHandler
from assistant.common.constants import ATTACHMENT_FILE_CONTEXT_SHARE, ATTACHMENT_TOTAL_CONTEXT_SHARE
from assistant.common.models import GuildSettings

FIXTURES = Path(__file__).parent / "fixtures"


class FakeChat(ChatHandler, API):
    """Chat mixin plus the token helpers from the API mixin, with a fixed context size."""

    def __init__(self, max_tokens: int):
        self.max_tokens = max_tokens

    def get_max_tokens(self, conf, member):
        return self.max_tokens


FakeChat.__abstractmethods__ = frozenset()


class FakeAttachment:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self.data = data

    async def read(self) -> bytes:
        return self.data


def make_message(*attachments: FakeAttachment) -> SimpleNamespace:
    return SimpleNamespace(attachments=list(attachments), reference=None)


def count(text: str) -> int:
    return len(get_encoding().encode(text))


@pytest.mark.asyncio
async def test_short_text_is_not_truncated():
    chat = FakeChat(1000)
    text = "one two three four"
    assert await chat.cap_attachment_text(text, 50) == text


@pytest.mark.asyncio
async def test_long_text_keeps_head_and_tail_within_limit():
    chat = FakeChat(1000)
    text = " ".join(f"word{i}" for i in range(500))
    capped = await chat.cap_attachment_text(text, 100)
    assert capped.startswith("word0 word1")
    assert capped.rstrip().endswith("word499")
    assert "truncated" in capped
    # The marker adds a few tokens on top of the 100 kept tokens
    assert count(capped) < 130


@pytest.mark.asyncio
async def test_read_attachments_separates_images_and_text():
    chat = FakeChat(10_000)
    log_bytes = (FIXTURES / "sample.log").read_bytes()
    message = make_message(
        FakeAttachment("shot.png", b"\x89PNG"),
        FakeAttachment("sample.log", log_bytes),
        FakeAttachment("archive.zip", b"PK"),
    )
    images, text = await chat.read_attachments(message, GuildSettings(), None)
    assert images == ["data:image/png;base64,iVBORw=="]
    assert "### Uploaded File (sample.log):" in text
    assert "ERROR crashed: out of memory" in text
    assert "archive.zip" not in text


@pytest.mark.asyncio
async def test_read_attachments_extracts_pdf():
    chat = FakeChat(10_000)
    pdf_bytes = (FIXTURES / "sample.pdf").read_bytes()
    message = make_message(FakeAttachment("sample.pdf", pdf_bytes))
    images, text = await chat.read_attachments(message, GuildSettings(), None)
    assert images == []
    assert "### Uploaded Document (sample.pdf):" in text
    assert "Dinos are cool" in text


@pytest.mark.asyncio
async def test_read_attachments_caps_each_file_to_its_share():
    max_tokens = 400
    chat = FakeChat(max_tokens)
    big = " ".join(f"line{i}" for i in range(2000)).encode()
    message = make_message(FakeAttachment("big.log", big))
    _, text = await chat.read_attachments(message, GuildSettings(), None)
    per_file = int(max_tokens * ATTACHMENT_FILE_CONTEXT_SHARE)
    assert "truncated" in text
    assert count(text) < per_file + 60


@pytest.mark.asyncio
async def test_read_attachments_stops_when_total_budget_is_used():
    max_tokens = 400
    chat = FakeChat(max_tokens)
    big = " ".join(f"line{i}" for i in range(2000)).encode()
    message = make_message(
        FakeAttachment("a.log", big),
        FakeAttachment("b.log", big),
        FakeAttachment("c.log", big),
    )
    _, text = await chat.read_attachments(message, GuildSettings(), None)
    total = int(max_tokens * ATTACHMENT_TOTAL_CONTEXT_SHARE)
    assert "### Uploaded File (a.log):" in text
    assert "### Uploaded File (b.log):" in text
    assert "c.log" in text and "skipped" in text
    assert count(text) < total + 120


@pytest.mark.asyncio
async def test_undecodable_file_is_reported():
    chat = FakeChat(1000)
    message = make_message(FakeAttachment("data.txt", b"\xff\xfe\x00\x01\x80"))
    _, text = await chat.read_attachments(message, GuildSettings(), None)
    assert "[Unable to decode file: data.txt]" in text
