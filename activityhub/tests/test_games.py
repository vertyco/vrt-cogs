import pytest

from activityhub.common.games import GameError, GameRegistry, validate_game

REMOVE = object()


class GameCog:
    """A stand-in game cog whose description can be bent per test"""

    def __init__(self, folder, cog_name="FakeGame", **changes):
        self.qualified_name = cog_name
        self.folder = folder
        self.changes = changes

    async def act(self, ctx, data):
        return {}

    async def join(self, ctx, conn):
        return None

    async def upload(self, request, ctx):
        return None

    async def activityhub_game(self):
        desc = {"key": "fake", "name": "Fake Game", "web_dir": self.folder, "actions": {"act": self.act}}
        desc.update(self.changes)
        return {k: v for k, v in desc.items() if v is not REMOVE}


class PlainCog:
    qualified_name = "Plain"


@pytest.fixture
def web_dir(tmp_path):
    (tmp_path / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
    (tmp_path / "icon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "wide.png").write_bytes(b"png")
    return tmp_path


@pytest.mark.asyncio
async def test_valid_description_becomes_a_game(web_dir):
    cog = GameCog(
        web_dir,
        icon="icon.svg",
        thumbnail="wide.png",
        socket={"join": None},
        routes={"POST /upload/": None},
        scopes=["guilds.members.read"],
    )
    cog.changes["socket"] = {"join": cog.join}
    cog.changes["routes"] = {"POST /upload/": cog.upload}
    game = await validate_game(cog)
    assert game.key == "fake" and game.name == "Fake Game" and game.cog is cog
    assert game.description == "" and game.icon == "icon.svg" and game.thumbnail == "wide.png"
    assert game.actions == {"act": cog.act}
    assert game.socket == {"join": cog.join}
    assert game.routes == {("POST", "upload"): cog.upload}
    assert game.scopes == ["guilds.members.read"]


@pytest.mark.asyncio
async def test_optional_fields_default(web_dir):
    game = await validate_game(GameCog(web_dir, actions=REMOVE))
    assert game.actions == {} and game.socket == {} and game.routes == {} and game.scopes == [] and game.icon is None
    assert game.thumbnail is None


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"action": {}}, "Unknown fields: action"),
        ({"web_dir": REMOVE}, "Missing fields: web_dir"),
        ({"key": "BB"}, "key"),
        ({"key": "a"}, "key"),
        ({"key": "x" * 33}, "key"),
        ({"key": "has space"}, "key"),
        ({"key": 5}, "key"),
        ({"name": "  "}, "name"),
        ({"description": 3}, "description"),
        ({"icon": "missing.png"}, "icon"),
        ({"icon": "../outside.svg"}, "icon"),
        ({"thumbnail": "missing.png"}, "thumbnail"),
        ({"thumbnail": "../outside.png"}, "thumbnail"),
        ({"thumbnail": 5}, "thumbnail"),
        ({"actions": []}, "actions must be a dict"),
        ({"socket": {"connect": None}}, "socket"),
        ({"routes": {"FETCH data": None}}, "routes"),
        ({"routes": {"GET /": None}}, "routes"),
        ({"scopes": "identify"}, "scopes"),
    ],
)
@pytest.mark.asyncio
async def test_bad_descriptions_are_refused(web_dir, changes, reason):
    with pytest.raises(GameError, match=reason):
        await validate_game(GameCog(web_dir, **changes))


@pytest.mark.asyncio
async def test_web_dir_needs_an_index(tmp_path):
    with pytest.raises(GameError, match="index.html"):
        await validate_game(GameCog(tmp_path))


@pytest.mark.asyncio
async def test_action_names_are_checked(web_dir):
    for name in ("has space", "a/b", "x" * 65, ""):
        cog = GameCog(web_dir)
        cog.changes["actions"] = {name: cog.act}
        with pytest.raises(GameError, match="invalid name"):
            await validate_game(cog)


@pytest.mark.asyncio
async def test_handlers_must_be_async(web_dir):
    def sync_handler(ctx, data):
        return {}

    with pytest.raises(GameError, match="async def"):
        await validate_game(GameCog(web_dir, actions={"act": sync_handler}))


@pytest.mark.asyncio
async def test_plain_def_hook_is_refused(web_dir):
    class PlainHookCog(GameCog):
        def activityhub_game(self):
            return {}

    with pytest.raises(GameError, match="must be an async def"):
        await validate_game(PlainHookCog(web_dir))


@pytest.mark.asyncio
async def test_hook_must_return_a_dict(web_dir):
    class ListHookCog(GameCog):
        async def activityhub_game(self):
            return []

    with pytest.raises(GameError, match="must return a dict"):
        await validate_game(ListHookCog(web_dir))


@pytest.mark.asyncio
async def test_registry_adds_games_and_ignores_plain_cogs(web_dir):
    registry = GameRegistry()
    assert await registry.add(PlainCog()) is None
    assert registry.failed == {}
    game = await registry.add(GameCog(web_dir, scopes=["b.scope", "a.scope"]))
    assert registry.games == {"fake": game}
    assert registry.scopes() == ["a.scope", "b.scope"]


@pytest.mark.asyncio
async def test_registry_records_refusals(web_dir):
    registry = GameRegistry()
    cog = GameCog(web_dir, key="NOPE")
    assert await registry.add(cog) is None
    assert registry.failed["FakeGame"][0] is cog
    assert "key" in registry.failed["FakeGame"][1]


@pytest.mark.asyncio
async def test_registry_records_a_raising_hook(web_dir, caplog):
    class BrokenCog(GameCog):
        async def activityhub_game(self):
            raise RuntimeError("boom")

    registry = GameRegistry()
    assert await registry.add(BrokenCog(web_dir)) is None
    assert registry.failed["FakeGame"][1] == "activityhub_game() raised RuntimeError: boom"
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_first_cog_keeps_a_duplicate_key(web_dir):
    registry = GameRegistry()
    first = await registry.add(GameCog(web_dir, cog_name="First"))
    assert await registry.add(GameCog(web_dir, cog_name="Second")) is None
    assert registry.games["fake"] is first
    assert "already used by First" in registry.failed["Second"][1]


@pytest.mark.asyncio
async def test_reload_remove_then_add(web_dir):
    registry = GameRegistry()
    old, new = GameCog(web_dir), GameCog(web_dir)
    await registry.add(old)
    registry.remove(old)
    await registry.add(new)
    assert registry.games["fake"].cog is new


@pytest.mark.asyncio
async def test_reload_add_before_remove_keeps_new_copy(web_dir):
    registry = GameRegistry()
    old, new = GameCog(web_dir), GameCog(web_dir)
    await registry.add(old)
    await registry.add(new)
    registry.remove(old)
    assert registry.games["fake"].cog is new


@pytest.mark.asyncio
async def test_reload_with_a_new_key_drops_the_old_key(web_dir):
    registry = GameRegistry()
    await registry.add(GameCog(web_dir))
    await registry.add(GameCog(web_dir, key="renamed"))
    assert list(registry.games) == ["renamed"]


@pytest.mark.asyncio
async def test_failed_new_copy_survives_old_copy_removal(web_dir):
    registry = GameRegistry()
    old, broken = GameCog(web_dir), GameCog(web_dir, key="BAD")
    await registry.add(old)
    await registry.add(broken)
    registry.remove(old)
    assert registry.games == {}
    assert registry.failed["FakeGame"][0] is broken


@pytest.mark.asyncio
async def test_removing_a_cog_clears_its_failure(web_dir):
    registry = GameRegistry()
    broken = GameCog(web_dir, key="BAD")
    await registry.add(broken)
    registry.remove(broken)
    assert registry.failed == {}
