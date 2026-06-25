from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tickets.common.models import GuildSettings, OpenedTicket, Panel
from tickets.common.utils import can_close


def make_conf(locked: bool, user_can_close: bool = True) -> GuildSettings:
    conf = GuildSettings(user_can_close=user_can_close)
    conf.panels["support"] = Panel()
    ticket = OpenedTicket(panel="support", opened="2026-06-25T00:00:00+00:00", locked=locked)
    conf.opened[111] = {222: ticket}
    return conf


def fake_actor(member_id: int, role_ids: list[int]):
    roles = [SimpleNamespace(id=rid) for rid in role_ids]
    return SimpleNamespace(id=member_id, roles=roles)


def test_opened_ticket_locked_defaults_false():
    ticket = OpenedTicket(panel="support", opened="2026-06-25T00:00:00+00:00")
    assert ticket.locked is False


@pytest.mark.asyncio
async def test_owner_cannot_close_when_locked():
    conf = make_conf(locked=True)
    guild = SimpleNamespace(owner_id=999)
    channel = SimpleNamespace(id=222)
    author = fake_actor(111, [])  # owner, no support roles
    with patch("tickets.common.utils.is_admin_or_superior", new=AsyncMock(return_value=False)):
        result = await can_close(None, guild, channel, author, 111, conf)
    assert result is False


@pytest.mark.asyncio
async def test_owner_can_close_when_unlocked():
    conf = make_conf(locked=False)
    guild = SimpleNamespace(owner_id=999)
    channel = SimpleNamespace(id=222)
    author = fake_actor(111, [])
    with patch("tickets.common.utils.is_admin_or_superior", new=AsyncMock(return_value=False)):
        result = await can_close(None, guild, channel, author, 111, conf)
    assert result is True


@pytest.mark.asyncio
async def test_support_can_close_locked_ticket():
    conf = make_conf(locked=True)
    conf.support_roles = [(500, False)]
    guild = SimpleNamespace(owner_id=999)
    channel = SimpleNamespace(id=222)
    author = fake_actor(333, [500])  # staff, not owner
    with patch("tickets.common.utils.is_admin_or_superior", new=AsyncMock(return_value=False)):
        result = await can_close(None, guild, channel, author, 111, conf)
    assert result is True
