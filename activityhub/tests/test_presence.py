import asyncio
import json

import pytest
import pytest_asyncio

from activityhub.common import presence as presence_module
from activityhub.common.presence import Presence, clean_data, clean_status
from activityhub.common.sockets import Connection
from activityhub.tests.fakes import ADMIN_ID, MANAGER_ID, MEMBER_ID, context_for, make_hub
from activityhub.tests.test_sockets import FakeWebSocket, delivered

ON = {"snake", "tanks"}


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(presence_module, "SEND_EVERY", 0)
    monkeypatch.setattr(presence_module, "GRACE_SECONDS", 0.05)


@pytest.fixture
def hub():
    return make_hub()


@pytest_asyncio.fixture
async def presence():
    async def game_on(guild_id, key):
        return key in ON

    made = Presence(game_on)
    yield made
    links = made.links()
    # Inside the test's loop, so the cancelled sends and graces belong to a loop that is still running
    made.stop()
    await asyncio.sleep(0)
    # A list that went out just as the test ended is still on its way to its links
    await delivered(*links)


def link(hub, user_id=MEMBER_ID, instance="i-1", guild=True):
    ctx = context_for(hub, user_id=user_id, instance_id=instance, guild_id=500 if guild else None)
    return Connection(FakeWebSocket(), ctx, None, None)


async def settle(*conns):
    # Lets the merged send run, then waits for what it queued to go out
    await asyncio.sleep(0.01)
    await delivered(*conns)


def last(conn) -> dict:
    return conn.ws.sent[-1]


def ids(snapshot) -> list[str]:
    return [person["id"] for person in snapshot["people"]]


def test_status_and_data_are_cleaned():
    assert clean_status("  Wave 4\x00\n · 1,230  ") == "Wave 4 · 1,230"
    assert clean_status("x" * 100) == "x" * 60
    assert clean_status(7) == ""
    assert clean_status("Hi \ud83d") == "Hi"
    assert clean_data({"score": 5}) == {"score": 5}
    assert clean_data("x" * 2000) is None
    assert clean_data(2**70) is None


@pytest.mark.asyncio
async def test_joining_sends_everyone_the_list(hub, presence):
    ann, bo = link(hub), link(hub, MANAGER_ID)
    await presence.connect(ann)
    await presence.connect(bo)
    await settle(ann, bo)
    assert ids(last(ann)) == [str(MEMBER_ID), str(MANAGER_ID)]
    assert last(ann) == last(bo)
    person = last(ann)["people"][0]
    assert person == {
        "id": str(MEMBER_ID),
        "name": "Member",
        "avatar": person["avatar"],
        "game": None,
        "status": "",
        "data": None,
        "busy": False,
        "away": False,
    }


@pytest.mark.asyncio
async def test_messages_are_cleaned(hub, presence):
    ann = link(hub)
    await presence.connect(ann)
    await presence.update(ann, {"where": "snake", "status": "Playing · 9", "data": {"score": 9}, "busy": True})
    await settle(ann)
    me = last(ann)["people"][0]
    assert (me["game"], me["status"], me["data"], me["busy"], me["away"]) == (
        "snake",
        "Playing · 9",
        {"score": 9},
        True,
        False,
    )
    await presence.update(ann, {"where": "vegas", "status": ["x"], "data": "y" * 5000, "busy": "yes", "away": 1})
    await settle(ann)
    me = last(ann)["people"][0]
    assert (me["game"], me["status"], me["data"], me["busy"], me["away"]) == (None, "", None, False, False)


@pytest.mark.asyncio
async def test_odd_messages_are_ignored(hub, presence):
    ann = link(hub)
    await presence.connect(ann)
    await presence.update(ann, {"where": "snake"})
    for junk in [None, [], "snake", {"where": "tanks", "admin": True}]:
        await presence.update(ann, junk)
    await settle(ann)
    assert last(ann)["people"][0]["game"] == "snake"
    stranger = link(hub, ADMIN_ID)
    await presence.update(stranger, {"where": "tanks"})
    await settle(ann)
    assert ids(last(ann)) == [str(MEMBER_ID)]


@pytest.mark.asyncio
async def test_two_devices_count_once(hub, presence):
    desk, phone, bo = link(hub), link(hub), link(hub, MANAGER_ID)
    for conn in (desk, phone, bo):
        await presence.connect(conn)
    await presence.update(phone, {"where": "tanks"})
    await settle(bo)
    assert ids(last(bo)) == [str(MEMBER_ID), str(MANAGER_ID)]
    assert last(bo)["people"][0]["game"] == "tanks"
    presence.disconnect(phone)
    await asyncio.sleep(0.1)
    await settle(bo)
    assert ids(last(bo)) == [str(MEMBER_ID), str(MANAGER_ID)] and not last(bo)["people"][0]["away"]


@pytest.mark.asyncio
async def test_reconnect_keeps_the_person_through_the_grace(hub, presence):
    ann, bo = link(hub), link(hub, MANAGER_ID)
    await presence.connect(ann)
    await presence.connect(bo)
    presence.disconnect(ann)
    await settle(bo)
    assert last(bo)["people"][0]["away"] is True
    again = link(hub)
    await presence.connect(again)
    await asyncio.sleep(0.1)
    await settle(bo)
    assert ids(last(bo)) == [str(MEMBER_ID), str(MANAGER_ID)] and last(bo)["people"][0]["away"] is False


@pytest.mark.asyncio
async def test_a_person_leaves_after_the_grace(hub, presence):
    ann, bo = link(hub), link(hub, MANAGER_ID)
    await presence.connect(ann)
    await presence.connect(bo)
    presence.disconnect(ann)
    await asyncio.sleep(0.1)
    await settle(bo)
    assert ids(last(bo)) == [str(MANAGER_ID)]


@pytest.mark.asyncio
async def test_other_channels_are_counted_per_server(hub, presence):
    here, there, dm = link(hub), link(hub, MANAGER_ID, instance="i-2"), link(hub, ADMIN_ID, instance="i-3", guild=False)
    for conn in (here, there, dm):
        await presence.connect(conn)
    await settle(here, there, dm)
    await presence.update(there, {"where": "snake"})
    await presence.update(dm, {"where": "tanks"})
    await settle(here, there, dm)
    assert last(here)["elsewhere"] == {"snake": 1}
    assert last(there)["elsewhere"] == {}
    assert last(dm)["elsewhere"] == {}


@pytest.mark.asyncio
async def test_a_status_change_stays_in_its_own_window(hub, presence):
    here, there = link(hub), link(hub, MANAGER_ID, instance="i-2")
    for conn in (here, there):
        await presence.connect(conn)
    await presence.update(there, {"where": "snake"})
    await settle(here, there)
    sent = len(here.ws.sent)
    await presence.update(there, {"where": "snake", "status": "Wave 2"})
    await settle(here, there)
    assert last(there)["people"][0]["status"] == "Wave 2"
    assert len(here.ws.sent) == sent


@pytest.mark.asyncio
async def test_sends_are_merged(hub, presence, monkeypatch):
    monkeypatch.setattr(presence_module, "SEND_EVERY", 0.2)
    ann = link(hub)
    await presence.connect(ann)
    await settle(ann)
    sent = len(ann.ws.sent)
    for score in range(10):
        await presence.update(ann, {"where": "snake", "status": f"Playing · {score}"})
    await asyncio.sleep(0.3)
    await delivered(ann)
    assert len(ann.ws.sent) == sent + 1 and last(ann)["people"][0]["status"] == "Playing · 9"


@pytest.mark.asyncio
async def test_follow_targets(hub, presence):
    ann, bo, far = link(hub), link(hub, MANAGER_ID), link(hub, ADMIN_ID, instance="i-2")
    for conn in (ann, bo, far):
        await presence.connect(conn)
    assert presence.follow_target(ann.ctx, str(MANAGER_ID)) == MANAGER_ID
    assert presence.follow_target(ann.ctx, str(ADMIN_ID)) is None
    assert presence.follow_target(ann.ctx, str(MEMBER_ID)) is None
    assert presence.follow_target(ann.ctx, MANAGER_ID) is None
    assert presence.follow_target(ann.ctx, "12x") is None
    assert presence.follow_target(ann.ctx, "\u00b2") is None
    assert presence.follow_target(ann.ctx, "9" * 5000) is None
    assert presence.follow_target(ann.ctx, "") is None


@pytest.mark.asyncio
async def test_the_list_is_json(hub, presence):
    ann = link(hub)
    await presence.connect(ann)
    await presence.update(ann, {"where": "snake", "data": {"nested": [1, {"a": None}]}})
    window = presence.windows["i-1"]
    assert json.loads(json.dumps(presence.snapshot(window)))["people"][0]["data"] == {"nested": [1, {"a": None}]}


@pytest.mark.asyncio
async def test_half_an_emoji_does_not_stop_the_list(hub, presence):
    ann, bo = link(hub), link(hub, MANAGER_ID)
    await presence.connect(ann)
    await presence.connect(bo)
    await presence.update(ann, {"where": "snake", "status": "Playing \ud83d"})
    await settle(ann, bo)
    assert last(bo)["people"][0]["status"] == "Playing"
    await presence.update(bo, {"where": "tanks"})
    await settle(ann, bo)
    assert last(ann)["people"][1]["game"] == "tanks"


@pytest.mark.asyncio
async def test_a_list_that_cant_be_built_is_logged_and_the_next_one_goes_out(hub, presence, monkeypatch, caplog):
    real_dumps = presence_module.dumps

    def broken(data):
        raise ValueError("bad field")

    monkeypatch.setattr(presence_module, "dumps", broken)
    ann = link(hub)
    await presence.connect(ann)
    await settle(ann)
    assert "bad field" in caplog.text and "i-1" in caplog.text and ann.ws.sent == []
    monkeypatch.setattr(presence_module, "dumps", real_dumps)
    await presence.update(ann, {"where": "snake"})
    await settle(ann)
    assert last(ann)["people"][0]["game"] == "snake"
