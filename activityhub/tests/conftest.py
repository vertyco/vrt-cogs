import pytest
import pytest_asyncio
from aiohttp.test_utils import TestClient, TestServer

from activityhub.common.server import HubServer
from activityhub.tests.fakes import GUILD_ID, MEMBER_ID, DemoCog, make_hub, register, write_demo_web


@pytest.fixture
def hub():
    return make_hub()


@pytest.fixture
def hub_web(tmp_path):
    """A small stand-in for activityhub/web, plus a file outside it that must never be served"""
    folder = tmp_path / "hubweb"
    folder.mkdir()
    menu = "<!doctype html><html><head><title>Menu</title></head><body>menu</body></html>"
    (folder / "index.html").write_text(menu, encoding="utf-8")
    (folder / "sdk.js").write_text("export function connect() {}\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    return folder


@pytest.fixture
def demo(hub, tmp_path):
    cog = DemoCog(write_demo_web(tmp_path / "demo"))
    assert register(hub, cog) is not None
    return cog


@pytest.fixture
def second(hub, tmp_path):
    cog = DemoCog(write_demo_web(tmp_path / "second"), key="second", name="Alpha Game", cog_name="Second")
    assert register(hub, cog) is not None
    return cog


@pytest.fixture
def server(hub, hub_web):
    return HubServer(hub, web_dir=hub_web)


@pytest.fixture
def discord_answers(server):
    """What the fake Discord says about logins and activity instances. Tests change it as needed"""
    answers = {"login": ("access-token", MEMBER_ID), "location": {"guild_id": GUILD_ID, "channel_id": 77}}

    async def exchange_code(code):
        return answers["login"]

    async def locate(instance_id):
        if answers["location"] is None:
            return None
        # By default whoever logs in is one of the instance's participants
        joined = [str(answers["login"][1])] if answers["login"] else []
        return {**answers["location"], "users": answers.get("users", joined)}

    server.exchange_code = exchange_code
    server.locate = locate
    return answers


@pytest_asyncio.fixture
async def client(server):
    test_client = TestClient(TestServer(server.make_app()))
    await test_client.start_server()
    yield test_client
    await test_client.close()
