from types import SimpleNamespace

import aiohttp
import discord
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from activityhub.common import discord_api
from activityhub.tests.fakes import APP_ID, GUILD_ID, MEMBER_ID, OUTSIDER_ID


class FakeHttp:
    def __init__(self, answer=None, error: Exception | None = None):
        self.answer = answer
        self.error = error

    async def request(self, route):
        if self.error:
            raise self.error
        return self.answer


def fake_bot(answer=None, error: Exception | None = None):
    return SimpleNamespace(application_id=APP_ID, http=FakeHttp(answer, error))


def instance(users: list[str], location: dict | None) -> dict:
    data = {"users": users}
    if location is not None:
        data["location"] = location
    return data


@pytest.mark.asyncio
async def test_instance_gives_the_server_channel_and_participants():
    bot = fake_bot(instance([str(MEMBER_ID), str(OUTSIDER_ID)], {"guild_id": str(GUILD_ID), "channel_id": "77"}))
    location = await discord_api.instance_location(bot, "i-1")
    assert location == {"guild_id": GUILD_ID, "channel_id": 77, "users": [str(MEMBER_ID), str(OUTSIDER_ID)]}


@pytest.mark.asyncio
async def test_dm_instance_has_no_server():
    bot = fake_bot(instance([str(MEMBER_ID)], {"channel_id": "5"}))
    location = await discord_api.instance_location(bot, "i-2")
    assert location == {"guild_id": None, "channel_id": 5, "users": [str(MEMBER_ID)]}


SLASH = {"name": "activities", "description": "Open the menu", "type": 1}
SAVED_ENTRY_POINT = {
    "id": "5",
    "application_id": str(APP_ID),
    "version": "9",
    "name": "play",
    "description": "Custom launch",
    "type": 4,
    "handler": 2,
}


class SyncHttp:
    """Global commands Discord already has, and what each bulk sync sent"""

    def __init__(self, current: list[dict]):
        self.current = current
        self.synced = []

    async def get_global_commands(self, application_id):
        return self.current

    async def bulk_upsert_global_commands(self, application_id, payload):
        self.synced.append(payload)
        return payload


def sync_bot(current: list[dict], embedded: bool = True):
    return SimpleNamespace(
        application_id=APP_ID, http=SyncHttp(current), application_flags=SimpleNamespace(embedded=embedded)
    )


@pytest.mark.asyncio
async def test_sync_carries_the_saved_entry_point_without_read_only_fields():
    bot = sync_bot([SLASH, SAVED_ENTRY_POINT])
    discord_api.keep_entry_point(bot)
    await bot.http.bulk_upsert_global_commands(APP_ID, [SLASH])
    entry = {"name": "play", "description": "Custom launch", "type": 4, "handler": 2}
    assert bot.http.synced == [[SLASH, entry]]


@pytest.mark.asyncio
async def test_sync_adds_a_default_entry_point_when_none_exists():
    bot = sync_bot([SLASH])
    discord_api.keep_entry_point(bot)
    await bot.http.bulk_upsert_global_commands(APP_ID, [SLASH])
    assert bot.http.synced == [[SLASH, discord_api.DEFAULT_ENTRY_POINT]]


@pytest.mark.asyncio
async def test_sync_adds_nothing_without_activities():
    bot = sync_bot([SLASH], embedded=False)

    async def info():
        return SimpleNamespace(flags=SimpleNamespace(embedded=False))

    bot.application_info = info
    discord_api.keep_entry_point(bot)
    await bot.http.bulk_upsert_global_commands(APP_ID, [SLASH])
    assert bot.http.synced == [[SLASH]]


@pytest.mark.asyncio
async def test_unload_restores_the_plain_sync():
    bot = sync_bot([])
    hook = discord_api.keep_entry_point(bot)
    discord_api.drop_entry_point_hook(bot, hook)
    assert "bulk_upsert_global_commands" not in bot.http.__dict__


@pytest.mark.asyncio
async def test_failed_instance_request_gets_none():
    error = discord.HTTPException(SimpleNamespace(status=404, reason="Not Found"), "x")
    bot = fake_bot(error=error)
    assert await discord_api.instance_location(bot, "i-3") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers, wait",
    [({"Retry-After": "12"}, 12.0), ({}, discord_api.DEFAULT_RETRY_AFTER), ({"Retry-After": "soon"}, 5.0)],
)
async def test_a_rate_limited_code_exchange_says_how_long_to_wait(monkeypatch, headers, wait):
    async def limited(request):
        return web.json_response({"message": "You are being rate limited."}, status=429, headers=headers)

    app = web.Application()
    app.router.add_post("/token", limited)
    server = TestServer(app)
    await server.start_server()
    monkeypatch.setattr(discord_api, "TOKEN_URL", str(server.make_url("/token")))
    try:
        async with aiohttp.ClientSession() as http:
            with pytest.raises(discord_api.RateLimited) as caught:
                await discord_api.exchange_code(http, str(APP_ID), "secret", "code")
    finally:
        await server.close()
    assert caught.value.retry_after == wait
