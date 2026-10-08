from types import SimpleNamespace

from activityhub.common.sessions import LAUNCH_TTL, SESSION_TTL, LaunchMemory, ActivityContext, SessionStore


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
