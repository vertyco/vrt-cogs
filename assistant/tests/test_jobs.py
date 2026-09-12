# assistant/tests/test_jobs.py
# pyright: reportAbstractUsage=false
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import discord

from assistant.commands.jobs import Jobs, find_job, job_embed
from assistant.common import jobs
from assistant.common.chat import ChatHandler
from assistant.common.jobs import JobRunner
from assistant.common.models import DB, Conversation, GuildSettings, Job


def make_job(**overrides) -> Job:
    fields = dict(
        id="abc123",
        name="ping",
        guild_id=1,
        channel_id=10,
        prompt="Say hi",
        trigger_type="interval",
        trigger="30m",
        created_by=5,
        created_at=datetime.now(tz=timezone.utc),
    )
    fields.update(overrides)
    return Job(**fields)


@pytest.mark.parametrize("text,seconds", [("30m", 1800), ("1h30m", 5400), ("2d", 172800), ("45s", 45), ("1H", 3600)])
def test_parse_interval(text, seconds):
    assert jobs.parse_interval(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "30", "5x", "m30"])
def test_parse_interval_rejects(text):
    with pytest.raises(ValueError):
        jobs.parse_interval(text)


def test_build_trigger_interval():
    assert isinstance(jobs.build_trigger(make_job()), IntervalTrigger)


def test_build_trigger_cron():
    job = make_job(trigger_type="cron", trigger="0 9 * * 1-5")
    assert isinstance(jobs.build_trigger(job), CronTrigger)


def test_build_trigger_bad_cron():
    with pytest.raises(ValueError):
        jobs.build_trigger(make_job(trigger_type="cron", trigger="not a cron"))


def test_validate_event_name():
    assert jobs.validate_event_name("Member_Join") == "member_join"
    assert jobs.validate_event_name("raw:on_member_ban") == "raw:on_member_ban"
    with pytest.raises(ValueError):
        jobs.validate_event_name("nope")
    with pytest.raises(ValueError):
        jobs.validate_event_name("raw:member_ban")
    with pytest.raises(ValueError):
        jobs.validate_event_name("raw:on_member ban")


def test_job_round_trip():
    conf = GuildSettings(jobs={"abc123": make_job()}, job_log_channel=99)
    dumped = conf.model_dump()
    loaded = GuildSettings.model_validate(dumped)
    assert loaded.jobs["abc123"].name == "ping"
    assert loaded.job_log_channel == 99
    db = DB()
    assert (db.max_jobs_per_guild, db.min_job_interval, db.job_error_pause) == (10, 300, 5)


class FakeChat(ChatHandler):
    def __init__(self, db: DB):
        self.db = db
        self.bot = Mock()
        self.registry = {}
        self.saved: list[str] = []

    async def save_conversation(self, key: str):
        self.saved.append(key)


FakeChat.__abstractmethods__ = frozenset()


@pytest.mark.asyncio
async def test_conversation_key_override(monkeypatch):
    conf = GuildSettings(use_function_calls=False)
    chat = FakeChat(DB(configs={1: conf}))
    guild = Mock(id=1)
    inner = AsyncMock(return_value="ok")
    monkeypatch.setattr(chat, "_get_chat_response", inner)
    await chat.get_chat_response(
        message="hi", author=5, guild=guild, channel=10, conf=conf, conversation_key="job-abc-1"
    )
    await asyncio.sleep(0)
    assert "job-abc-1" in chat.db.conversations
    assert "5-10-1" not in chat.db.conversations
    assert chat.saved == ["job-abc-1"]


class FakeRunner(JobRunner):
    def __init__(self, db: DB):
        self.db = db
        self.bot = Mock()
        self.bot.owner_ids = set()
        self.bot.get_valid_prefixes = AsyncMock(return_value=["!"])
        self.bot.cog_disabled_in_guild = AsyncMock(return_value=False)
        self.scheduler = Mock()
        self.job_locks = {}
        self.raw_listeners = {}
        self.sent: list[tuple[int, str]] = []
        self.saved_keys: list[str] = []
        self.reply = "the reply"
        self.raise_error: Exception | None = None

    async def save_conf(self):
        pass

    async def save_conversation(self, key: str):
        self.saved_keys.append(key)

    async def can_call_llm(self, conf, ctx=None):
        return True

    async def get_mention_permissions(self, member):
        return discord.AllowedMentions.none()

    async def get_chat_response(self, **kwargs):
        if self.raise_error:
            raise self.raise_error
        self.db.conversations.setdefault(kwargs["conversation_key"], Conversation())
        return self.reply


FakeRunner.__abstractmethods__ = frozenset()


def make_channel(cid: int, sink: list):
    channel = Mock(id=cid)

    async def send(content=None, **kwargs):
        sink.append((cid, content if content is not None else kwargs.get("embed")))
        return Mock()

    channel.send = send
    return channel


def make_runner(job: Job, log_channel: int = 0):
    conf = GuildSettings(jobs={job.id: job}, job_log_channel=log_channel)
    runner = FakeRunner(DB(configs={1: conf}))
    channels = {10: make_channel(10, runner.sent)}
    if log_channel:
        channels[log_channel] = make_channel(log_channel, runner.sent)
    guild = Mock(id=1, owner_id=5)
    guild.get_channel = lambda cid: channels.get(cid)
    member = Mock(id=5, bot=False)
    member.guild = guild
    guild.get_member = lambda uid: member if uid == 5 else None
    runner.bot.get_guild = lambda gid: guild if gid == 1 else None
    return runner, conf


@pytest.mark.asyncio
async def test_run_job_posts_reply_and_updates_counters():
    job = make_job()
    runner, conf = make_runner(job)
    await runner.run_job(1, job.id)
    assert runner.sent == [(10, "the reply")]
    assert job.run_count == 1 and job.consecutive_errors == 0 and job.last_run is not None
    assert "job-abc123-1" not in runner.db.conversations  # fresh job forgets
    assert "job-abc123-1" in runner.saved_keys  # and the stored file is cleared


@pytest.mark.asyncio
async def test_run_job_remember_keeps_conversation():
    job = make_job(remember=True)
    runner, conf = make_runner(job)
    await runner.run_job(1, job.id)
    assert "job-abc123-1" in runner.db.conversations


@pytest.mark.asyncio
async def test_run_job_silent_only_logs():
    job = make_job(silent=True)
    runner, conf = make_runner(job, log_channel=20)
    await runner.run_job(1, job.id)
    assert all(cid == 20 for cid, _ in runner.sent)
    assert len(runner.sent) >= 1


@pytest.mark.asyncio
async def test_run_job_error_pauses_at_threshold():
    job = make_job()
    runner, conf = make_runner(job, log_channel=20)
    runner.db.job_error_pause = 2
    runner.raise_error = RuntimeError("boom")
    await runner.run_job(1, job.id)
    assert job.enabled and job.consecutive_errors == 1 and job.last_error == "boom"
    await runner.run_job(1, job.id)
    assert not job.enabled
    warnings = [c for cid, c in runner.sent if cid == 10 and isinstance(c, str) and "paused" in c]
    assert warnings
    runner.scheduler.remove_job.assert_called()


@pytest.mark.asyncio
async def test_run_job_skips_while_locked():
    job = make_job()
    runner, conf = make_runner(job)
    lock = asyncio.Lock()
    await lock.acquire()
    runner.job_locks[runner.job_key(1, job.id)] = lock
    await runner.run_job(1, job.id)
    assert runner.sent == []


@pytest.mark.asyncio
async def test_run_job_missing_creator_pauses():
    job = make_job(created_by=999)
    runner, conf = make_runner(job)
    await runner.run_job(1, job.id)
    assert not job.enabled and "creator" in job.last_error


@pytest.mark.asyncio
async def test_dispatch_event_jobs_filters_and_counts():
    a = make_job(id="a", name="a", trigger_type="event", trigger="message", event_channel_id=10)
    b = make_job(id="b", name="b", trigger_type="event", trigger="message", event_channel_id=11)
    c = make_job(id="c", name="c", trigger_type="event", trigger="member_join")
    runner, conf = make_runner(a)
    conf.jobs.update({"b": b, "c": c})
    runner.run_job = AsyncMock()
    started = runner.dispatch_event_jobs(1, "message", "Event: x", channel_id=10)
    assert started == 1
    assert runner.dispatch_event_jobs(1, "member_join", "Event: y") == 1
    assert runner.dispatch_event_jobs(1, "role_change", "Event: z") == 0


@pytest.mark.asyncio
async def test_member_join_listener_ignores_bots():
    job = make_job(trigger_type="event", trigger="member_join")
    runner, conf = make_runner(job)
    runner.dispatch_event_jobs = Mock(return_value=0)
    bot_member = Mock(bot=True, guild=Mock(id=1))
    await runner.on_job_member_join(bot_member)
    runner.dispatch_event_jobs.assert_not_called()
    human = Mock(bot=False, id=7, guild=Mock(id=1), created_at=datetime.now(tz=timezone.utc))
    human.__str__ = lambda self: "human"
    await runner.on_job_member_join(human)
    trigger = runner.dispatch_event_jobs.call_args.args[1]
    assert trigger == "member_join"


@pytest.mark.asyncio
async def test_message_listener_passes_channel_for_filter():
    job = make_job(trigger_type="event", trigger="message", event_channel_id=10)
    runner, conf = make_runner(job)
    runner.dispatch_event_jobs = Mock(return_value=0)
    message = Mock(author=Mock(bot=False, id=7), guild=Mock(id=1), channel=Mock(id=10), content="hello", attachments=[])
    await runner.on_job_message(message)
    assert runner.dispatch_event_jobs.call_args.kwargs["channel_id"] == 10
    assert "hello" in runner.dispatch_event_jobs.call_args.args[2]


def test_describe_event_args():
    member = Mock(spec=discord.Member, id=1, bot=False)
    member.__str__ = lambda self: "vert"
    channel = Mock(spec=discord.TextChannel, id=2)
    channel.name = "general"
    text = jobs.describe_event_args((member, channel, "plain"))
    assert "vert (1)" in text and "general (2)" in text and "plain" in text


def test_sync_raw_listeners_reconciles():
    a = make_job(id="a", name="a", trigger_type="event", trigger="raw:on_member_ban")
    b = make_job(id="b", name="b", trigger_type="event", trigger="raw:on_member_ban")
    runner, conf = make_runner(a)
    conf.jobs["b"] = b
    runner.sync_raw_listeners()
    assert list(runner.raw_listeners) == ["on_member_ban"]
    runner.bot.add_listener.assert_called_once()
    del conf.jobs["a"]
    runner.sync_raw_listeners()
    assert "on_member_ban" in runner.raw_listeners
    del conf.jobs["b"]
    runner.sync_raw_listeners()
    assert runner.raw_listeners == {}
    runner.bot.remove_listener.assert_called_once()


def test_find_guild_id():
    guild = Mock(spec=discord.Guild, id=4)
    assert jobs.find_guild_id((Mock(guild=guild),)) == 4
    assert jobs.find_guild_id((Mock(spec=[], guild_id=6),)) == 6
    assert jobs.find_guild_id((guild,)) == 4
    assert jobs.find_guild_id(("text",)) is None


@pytest.mark.asyncio
async def test_handle_raw_event_dispatches_and_skips_bots():
    job = make_job(trigger_type="event", trigger="raw:on_member_ban")
    runner, conf = make_runner(job)
    runner.dispatch_event_jobs = Mock(return_value=0)
    guild = Mock(spec=discord.Guild, id=1)
    await runner.handle_raw_event("on_member_ban", guild, Mock(bot=True))
    runner.dispatch_event_jobs.assert_not_called()
    await runner.handle_raw_event("on_member_ban", guild, Mock(bot=False, id=9))
    assert runner.dispatch_event_jobs.call_args.args[1] == "raw:on_member_ban"


@pytest.mark.asyncio
async def test_handle_raw_event_skips_bot_authored_messages():
    job = make_job(trigger_type="event", trigger="raw:on_message")
    runner, conf = make_runner(job)
    runner.dispatch_event_jobs = Mock(return_value=0)
    guild = Mock(spec=discord.Guild, id=1)
    bot_message = Mock(spec=discord.Message, author=Mock(bot=True), guild=guild, content="hi", channel="general")
    await runner.handle_raw_event("on_message", bot_message)
    runner.dispatch_event_jobs.assert_not_called()
    human_message = Mock(
        spec=discord.Message, author=Mock(bot=False, id=9), guild=guild, content="hi", channel="general"
    )
    await runner.handle_raw_event("on_message", human_message)
    assert runner.dispatch_event_jobs.call_args.args[1] == "raw:on_message"


def test_schedule_jobs_registers_only_enabled_schedule_jobs():
    a = make_job(id="a", name="a")
    b = make_job(id="b", name="b", enabled=False)
    c = make_job(id="c", name="c", trigger_type="event", trigger="member_join")
    runner, conf = make_runner(a)
    conf.jobs.update({"b": b, "c": c})
    runner.schedule_jobs()
    ids = [call.kwargs["id"] for call in runner.scheduler.add_job.call_args_list]
    assert ids == ["job_1_a"]


def test_find_job_case_insensitive():
    job = make_job(name="Daily")
    conf = GuildSettings(jobs={job.id: job})
    assert find_job(conf, "daily") is job
    assert find_job(conf, "nope") is None


def test_job_embed_lists_fields():
    job = make_job(last_error="boom", enabled=False)
    embed = job_embed(job, "!")
    names = [f.name for f in embed.fields]
    assert "Trigger" in names and "Last error" in names
    assert "Paused" in embed.description


class FakeJobs(Jobs):
    def __init__(self, db: DB):
        self.db = db
        self.schedule_job = Mock()
        self.sync_raw_listeners = Mock()

    async def save_conf(self):
        pass


FakeJobs.__abstractmethods__ = frozenset()


def make_jobs_cog(**db_kwargs):
    cog = FakeJobs(DB(configs={1: GuildSettings()}, **db_kwargs))
    ctx = Mock(guild=Mock(id=1), author=Mock(id=5))
    ctx.send = AsyncMock()
    return cog, ctx, Mock(id=10)


@pytest.mark.asyncio
async def test_create_job_respects_max_jobs():
    cog, ctx, channel = make_jobs_cog(max_jobs_per_guild=1)
    conf = cog.db.get_conf(1)
    conf.jobs["abc123"] = make_job()
    assert await cog.create_job(ctx, "second", channel, "do it", "interval", "30m") is None
    assert "maximum" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
async def test_create_job_rejects_duplicate_name():
    cog, ctx, channel = make_jobs_cog()
    cog.db.get_conf(1).jobs["abc123"] = make_job(name="Ping")
    assert await cog.create_job(ctx, "ping", channel, "do it", "interval", "30m") is None
    assert "already exists" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
async def test_create_job_rejects_multi_word_name():
    cog, ctx, channel = make_jobs_cog()
    assert await cog.create_job(ctx, "two words", channel, "do it", "interval", "30m") is None
    assert "one word" in ctx.send.call_args.args[0]


@pytest.mark.asyncio
async def test_create_job_stores_and_schedules():
    cog, ctx, channel = make_jobs_cog()
    job = await cog.create_job(ctx, "daily", channel, "do it", "interval", "30m")
    assert job is not None
    assert cog.db.get_conf(1).jobs[job.id] is job
    assert job.created_by == 5 and job.channel_id == 10
    cog.schedule_job.assert_called_once_with(job)
