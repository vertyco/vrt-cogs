from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tickets.common.models import GuildSettings, OpenedTicket, Panel
from tickets.common.utils import can_escalate


def make_conf(user_can_escalate: bool, locked: bool = False) -> GuildSettings:
    conf = GuildSettings(user_can_escalate=user_can_escalate)
    conf.panels["support"] = Panel()
    ticket = OpenedTicket(panel="support", opened="2026-06-25T00:00:00+00:00", locked=locked)
    conf.opened[111] = {222: ticket}
    return conf


def fake_actor(member_id: int, manage_guild: bool = False):
    return SimpleNamespace(id=member_id, guild_permissions=SimpleNamespace(manage_guild=manage_guild))


async def check(conf: GuildSettings, author, is_admin: bool = False) -> bool:
    guild = SimpleNamespace(owner_id=999)
    channel = SimpleNamespace(id=222)
    with patch("tickets.common.utils.is_admin_or_superior", new=AsyncMock(return_value=is_admin)):
        return await can_escalate(None, guild, channel, author, 111, conf)


@pytest.mark.asyncio
async def test_owner_cannot_escalate_when_disabled():
    assert await check(make_conf(user_can_escalate=False), fake_actor(111)) is False


@pytest.mark.asyncio
async def test_owner_can_escalate_when_enabled():
    assert await check(make_conf(user_can_escalate=True), fake_actor(111)) is True


@pytest.mark.asyncio
async def test_owner_cannot_escalate_locked_ticket():
    assert await check(make_conf(user_can_escalate=True, locked=True), fake_actor(111)) is False


@pytest.mark.asyncio
async def test_other_user_cannot_escalate_when_enabled():
    assert await check(make_conf(user_can_escalate=True), fake_actor(333)) is False


@pytest.mark.asyncio
async def test_admin_can_escalate_when_disabled():
    assert await check(make_conf(user_can_escalate=False), fake_actor(333), is_admin=True) is True


@pytest.mark.asyncio
async def test_manage_guild_can_escalate_when_disabled():
    assert await check(make_conf(user_can_escalate=False), fake_actor(333, manage_guild=True)) is True
