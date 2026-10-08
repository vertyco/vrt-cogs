from types import SimpleNamespace

import discord
import pytest

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


@pytest.mark.asyncio
async def test_failed_instance_request_gets_none():
    error = discord.HTTPException(SimpleNamespace(status=404, reason="Not Found"), "x")
    bot = fake_bot(error=error)
    assert await discord_api.instance_location(bot, "i-3") is None
