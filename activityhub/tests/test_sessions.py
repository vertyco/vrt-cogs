from types import SimpleNamespace

import pytest

from activityhub.common.sessions import LAUNCH_TTL, SESSION_TTL, LaunchMemory, ActivityContext, SessionStore
from activityhub.tests.fakes import (
    ADMIN_ID,
    GUILD_ID,
    GUILD_OWNER_ID,
    MANAGER_ID,
    MEMBER_ID,
    MOD_ID,
    OWNER_ID,
    context_for,
    make_hub,
)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def player(user_id=1, guild_id=None):
    guild = SimpleNamespace(id=guild_id) if guild_id else None
    return ActivityContext(author=SimpleNamespace(id=user_id), guild=guild, channel_id=5, instance_id="i-1")


def test_guild_id():
    assert player(guild_id=9).guild_id == 9
    assert player().guild_id is None


def test_create_and_get():
    store = SessionStore(Clock())
    token = store.create(player())
    assert len(token) == 43
    assert store.get(token).ctx.author.id == 1
    assert store.get("nope") is None
    assert store.get(None) is None
    assert store.create(player()) != token


def test_sessions_expire_after_twelve_hours():
    clock = Clock()
    store = SessionStore(clock)
    token = store.create(player())
    clock.now += SESSION_TTL - 1
    assert store.get(token) is not None
    clock.now += 1
    assert store.get(token) is None
    assert token not in store.sessions


def test_creating_prunes_expired_sessions():
    clock = Clock()
    store = SessionStore(clock)
    old = store.create(player())
    clock.now += SESSION_TTL
    store.create(player(2))
    assert old not in store.sessions


def test_forget_user_drops_only_their_sessions():
    store = SessionStore(Clock())
    mine, theirs = store.create(player(1)), store.create(player(2))
    store.forget_user(1)
    assert store.get(mine) is None
    assert store.get(theirs) is not None


def test_launch_memory_is_taken_once():
    memory = LaunchMemory(Clock())
    memory.remember(1, "brickbreaker")
    assert memory.take(1) == "brickbreaker"
    assert memory.take(1) is None


def test_launch_memory_expires_after_two_minutes():
    clock = Clock()
    memory = LaunchMemory(clock)
    memory.remember(1, "brickbreaker")
    clock.now += LAUNCH_TTL + 1
    assert memory.take(1) is None


def test_launch_memory_keeps_the_latest_choice_and_forgets_users():
    memory = LaunchMemory(Clock())
    memory.remember(1, "a")
    memory.remember(1, "b")
    memory.remember(2, "c")
    memory.forget_user(2)
    assert memory.take(1) == "b"
    assert memory.take(2) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id, admin, mod",
    [
        (OWNER_ID, True, True),
        (GUILD_OWNER_ID, True, True),
        (MANAGER_ID, True, True),
        (ADMIN_ID, True, True),
        (MOD_ID, False, True),
        (MEMBER_ID, False, False),
    ],
)
async def test_who_counts_as_a_server_admin_or_mod(user_id, admin, mod):
    ctx = context_for(make_hub(), user_id=user_id)
    assert await ctx.is_admin() is admin
    assert await ctx.is_mod() is mod


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [OWNER_ID, MANAGER_ID, ADMIN_ID, MOD_ID])
async def test_nobody_is_an_admin_or_mod_outside_a_server(user_id):
    ctx = context_for(make_hub(), user_id=user_id, guild_id=None)
    assert await ctx.is_admin() is False
    assert await ctx.is_mod() is False


@pytest.mark.asyncio
async def test_a_member_who_left_loses_their_rights_but_the_owners_keep_theirs():
    hub = make_hub()
    everyone = (MANAGER_ID, ADMIN_ID, MOD_ID, OWNER_ID, GUILD_OWNER_ID)
    contexts = {user_id: context_for(hub, user_id=user_id) for user_id in everyone}
    hub.bot.guilds[GUILD_ID].members.clear()
    for user_id in (MANAGER_ID, ADMIN_ID, MOD_ID):
        assert await contexts[user_id].is_admin() is False
        assert await contexts[user_id].is_mod() is False
    for user_id in (OWNER_ID, GUILD_OWNER_ID):
        assert await contexts[user_id].is_admin() is True
        assert await contexts[user_id].is_mod() is True


def test_the_bot_stays_out_of_the_ctx_repr():
    assert "bot=" not in repr(context_for(make_hub()))


def test_the_bot_doesnt_change_whether_two_contexts_are_equal():
    ctx = context_for(make_hub())
    assert ctx == ActivityContext(ctx.author, ctx.guild, ctx.channel_id, ctx.instance_id, bot=object())


@pytest.mark.asyncio
async def test_no_discord_permission_makes_a_mod_on_its_own():
    # Only Red's mod and admin roles, and Manage Server through is_admin, count
    hub = make_hub()
    member = hub.bot.guilds[GUILD_ID].members[MEMBER_ID]
    member.guild_permissions = SimpleNamespace(
        manage_guild=False, kick_members=True, ban_members=True, manage_messages=True, moderate_members=True
    )
    ctx = context_for(hub, user_id=MEMBER_ID)
    assert await ctx.is_mod() is False
