from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from tickets.common.models import GuildSettings, Panel
from tickets.common.utils import can_optin, format_optin_list, get_optin_mentions


def fake_guild(member_ids: list[int], roles: dict[int, list[int]] | None = None):
    roles = roles or {}
    members = {
        i: SimpleNamespace(id=i, mention=f"<@{i}>", roles=[SimpleNamespace(id=r) for r in roles.get(i, [])])
        for i in member_ids
    }
    return SimpleNamespace(get_member=members.get)


def fake_thread(manage_thread_ids: list[int]):
    """Thread whose parent channel everyone can see; only some members can manage threads"""
    thread = MagicMock(spec=discord.Thread)
    thread.permissions_for = lambda m: SimpleNamespace(view_channel=True, manage_threads=m.id in manage_thread_ids)
    return thread


def fake_channel(visible_ids: list[int]):
    return SimpleNamespace(permissions_for=lambda m: SimpleNamespace(view_channel=m.id in visible_ids))


def test_mentions_member_who_can_view():
    conf = GuildSettings(ping_optins=[1])
    assert get_optin_mentions(conf, fake_guild([1]), fake_channel([1]), Panel(), opener_id=99) == ["<@1>"]


def test_skips_member_who_cannot_view():
    conf = GuildSettings(ping_optins=[1, 2])
    assert get_optin_mentions(conf, fake_guild([1, 2]), fake_channel([2]), Panel(), opener_id=99) == ["<@2>"]


def test_skips_opener():
    conf = GuildSettings(ping_optins=[1])
    assert get_optin_mentions(conf, fake_guild([1]), fake_channel([1]), Panel(), opener_id=1) == []


def test_skips_member_not_in_server():
    conf = GuildSettings(ping_optins=[1, 2])
    assert get_optin_mentions(conf, fake_guild([2]), fake_channel([1, 2]), Panel(), opener_id=99) == ["<@2>"]


def test_nobody_opted_in():
    conf = GuildSettings()
    assert get_optin_mentions(conf, fake_guild([1]), fake_channel([1]), Panel(), opener_id=99) == []


def fake_member(member_id: int, role_ids: list[int]):
    return SimpleNamespace(id=member_id, roles=[SimpleNamespace(id=r) for r in role_ids])


async def check_optin(conf: GuildSettings, member, is_admin: bool = False) -> bool:
    with patch("tickets.common.utils.is_admin_or_superior", new=AsyncMock(return_value=is_admin)):
        return await can_optin(None, conf, member)


@pytest.mark.asyncio
async def test_global_support_role_can_opt_in():
    conf = GuildSettings(support_roles=[(10, False)])
    assert await check_optin(conf, fake_member(1, [10])) is True


@pytest.mark.asyncio
async def test_panel_role_can_opt_in():
    conf = GuildSettings()
    conf.panels["ase"] = Panel(roles=[(20, False)])
    assert await check_optin(conf, fake_member(1, [20])) is True


@pytest.mark.asyncio
async def test_admin_can_opt_in():
    assert await check_optin(GuildSettings(), fake_member(1, []), is_admin=True) is True


@pytest.mark.asyncio
async def test_regular_member_cannot_opt_in():
    conf = GuildSettings(support_roles=[(10, False)])
    assert await check_optin(conf, fake_member(1, [30])) is False


@pytest.mark.asyncio
async def test_can_always_opt_out():
    conf = GuildSettings(ping_optins=[1])
    assert await check_optin(conf, fake_member(1, [])) is True


def test_thread_mentions_panel_staff_only():
    conf = GuildSettings(ping_optins=[1, 2])
    panel = Panel(roles=[(20, False)])
    guild = fake_guild([1, 2], roles={1: [20], 2: [30]})
    assert get_optin_mentions(conf, guild, fake_thread([]), panel, opener_id=99) == ["<@1>"]


def test_thread_mentions_global_support_staff():
    conf = GuildSettings(ping_optins=[1], support_roles=[(10, False)])
    guild = fake_guild([1], roles={1: [10]})
    assert get_optin_mentions(conf, guild, fake_thread([]), Panel(), opener_id=99) == ["<@1>"]


def test_thread_mentions_thread_managers():
    conf = GuildSettings(ping_optins=[1])
    assert get_optin_mentions(conf, fake_guild([1]), fake_thread([1]), Panel(), opener_id=99) == ["<@1>"]


def test_optin_list_short():
    assert format_optin_list(["<@1>", "<@2>"]) == "<@1>, <@2>"


def test_optin_list_empty():
    assert format_optin_list([]) == "None"


def test_optin_list_fits_embed_field():
    mentions = [f"<@{100000000000000000 + i}>" for i in range(100)]
    text = format_optin_list(mentions)
    assert len(text) <= 1024
    assert text.endswith("more")
