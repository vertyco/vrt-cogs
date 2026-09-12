import asyncio
import logging
import re
import typing as t
from datetime import datetime, timezone

import discord
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.models import GuildSettings, Job

log = logging.getLogger("red.vrt.assistant.jobs")

INTERVAL_RE = re.compile(r"(\d+)\s*([smhd])", re.IGNORECASE)
INTERVAL_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
EVENT_NAME_RE = re.compile(r"^on_[a-z_]+$")

NAMED_EVENTS: dict[str, str] = {
    "member_join": "A member joins the server",
    "member_leave": "A member leaves the server",
    "message": "A non-bot message is posted in the filter channel (filter required)",
    "reaction_add": "A reaction is added to a message (optional channel filter)",
    "thread_create": "A thread or forum post is created (optional parent channel filter)",
    "role_change": "A member's roles change",
    "voice_join": "A member joins a voice channel (optional channel filter)",
    "ticket_opened": "A ticket is opened through the Tickets cog",
}


def parse_interval(text: str) -> int:
    """Turn '1h30m' style text into seconds. Raises ValueError on anything else."""
    cleaned = text.strip().lower()
    matches = INTERVAL_RE.findall(cleaned)
    if not matches or "".join(f"{n}{u}" for n, u in matches) != cleaned.replace(" ", ""):
        raise ValueError(f"'{text}' is not an interval like 30m, 2h, 1h30m, or 1d")
    total = sum(int(n) * INTERVAL_UNITS[u] for n, u in matches)
    if total <= 0:
        raise ValueError("Interval must be greater than zero")
    return total


def build_trigger(job: Job):
    if job.trigger_type == "interval":
        return IntervalTrigger(seconds=parse_interval(job.trigger))
    if job.trigger_type == "cron":
        try:
            return CronTrigger.from_crontab(job.trigger, timezone=timezone.utc)
        except ValueError as e:
            raise ValueError(f"Invalid cron string '{job.trigger}': {e}") from e
    raise ValueError(f"Job {job.name} has no schedule trigger")


def describe_trigger(job: Job) -> str:
    if job.trigger_type == "interval":
        return f"every {job.trigger}"
    if job.trigger_type == "cron":
        return f"on cron `{job.trigger}` (UTC)"
    return f"on event `{job.trigger}`"


def validate_event_name(name: str) -> str:
    cleaned = name.strip().lower()
    if cleaned in NAMED_EVENTS:
        return cleaned
    if cleaned.startswith("raw:"):
        event = cleaned[4:]
        if EVENT_NAME_RE.match(event):
            return f"raw:{event}"
        raise ValueError(f"'{event}' is not a discord.py event name (must look like on_member_ban)")
    raise ValueError(f"Unknown event '{name}'. Use one of: {', '.join(NAMED_EVENTS)} or raw:on_<event>")


def describe_object(obj: t.Any) -> str:
    if isinstance(obj, (discord.Member, discord.User)):
        return f"{obj} ({obj.id})"
    if isinstance(obj, discord.Message):
        return f"message by {obj.author} ({obj.author.id}) in #{obj.channel}: {obj.content[:500]}"
    if isinstance(obj, (discord.abc.GuildChannel, discord.Thread, discord.Role, discord.Guild)):
        return f"{type(obj).__name__} {obj.name} ({obj.id})"
    return str(obj)[:300]


def describe_event_args(args: tuple) -> str:
    return "\n".join(f"- {describe_object(arg)}" for arg in args)


def actor_is_bot(arg: t.Any) -> bool:
    """True when the event object is a bot, or a message written by a bot."""
    if getattr(arg, "bot", False) is True:
        return True
    return getattr(getattr(arg, "author", None), "bot", False) is True


def find_guild_id(args: tuple) -> t.Optional[int]:
    for arg in args:
        if isinstance(arg, discord.Guild):
            return arg.id
    for arg in args:
        guild = getattr(arg, "guild", None)
        if isinstance(guild, discord.Guild):
            return guild.id
    for arg in args:
        guild_id = getattr(arg, "guild_id", None)
        if isinstance(guild_id, int):
            return guild_id
    return None


class JobRunner(MixinMeta):
    def job_key(self, guild_id: int, job_id: str) -> str:
        return f"job_{guild_id}_{job_id}"

    def schedule_job(self, job: Job) -> None:
        if job.trigger_type == "event" or not job.enabled:
            return
        self.scheduler.add_job(
            self.run_job,
            build_trigger(job),
            args=[job.guild_id, job.id],
            id=self.job_key(job.guild_id, job.id),
            replace_existing=True,
        )

    def unschedule_job(self, job: Job) -> None:
        try:
            self.scheduler.remove_job(self.job_key(job.guild_id, job.id))
        except Exception as e:
            log.debug(f"Job {job.name} was not scheduled: {e}")

    def schedule_jobs(self) -> None:
        count = 0
        for guild_id, conf in self.db.configs.items():
            for job in conf.jobs.values():
                try:
                    self.schedule_job(job)
                    if job.trigger_type != "event" and job.enabled:
                        count += 1
                except ValueError as e:
                    log.error(f"Cannot schedule job {job.name} in server {guild_id}", exc_info=e)
        self.sync_raw_listeners()
        if count:
            log.info(f"Scheduled {count} assistant jobs")

    def sync_raw_listeners(self) -> None:
        wanted = {
            job.trigger[4:]
            for conf in self.db.configs.values()
            for job in conf.jobs.values()
            if job.enabled and job.trigger_type == "event" and job.trigger.startswith("raw:")
        }
        for event_name in wanted - set(self.raw_listeners):

            async def listener(*args, event_name=event_name):
                await self.handle_raw_event(event_name, *args)

            self.raw_listeners[event_name] = listener
            self.bot.add_listener(listener, event_name)
        for event_name in set(self.raw_listeners) - wanted:
            self.bot.remove_listener(self.raw_listeners.pop(event_name), event_name)

    async def handle_raw_event(self, event_name: str, *args) -> None:
        if any(actor_is_bot(arg) for arg in args):
            return
        guild_id = find_guild_id(args)
        if guild_id is None:
            return
        text = f"Event: {event_name}\n{describe_event_args(args)}"
        self.dispatch_event_jobs(guild_id, f"raw:{event_name}", text)

    def dispatch_event_jobs(
        self, guild_id: int, trigger: str, event_text: str, channel_id: t.Optional[int] = None
    ) -> int:
        conf = self.db.get_conf(guild_id)
        started = 0
        for job in conf.jobs.values():
            if not job.enabled or job.trigger_type != "event" or job.trigger != trigger:
                continue
            if job.event_channel_id and channel_id is not None and job.event_channel_id != channel_id:
                continue
            try:
                asyncio.create_task(self.run_job(guild_id, job.id, event_text))
                started += 1
            except Exception as e:
                log.error(f"Could not start event job {job.name}", exc_info=e)
        return started

    @commands.Cog.listener("on_member_join")
    async def on_job_member_join(self, member: discord.Member):
        if member.bot:
            return
        self.dispatch_event_jobs(
            member.guild.id,
            "member_join",
            f"Event: member joined. Member: {member} ({member.id}), account created {member.created_at:%Y-%m-%d}.",
        )

    @commands.Cog.listener("on_member_remove")
    async def on_job_member_remove(self, member: discord.Member):
        if member.bot:
            return
        roles = ", ".join(r.name for r in member.roles if r.name != "@everyone") or "none"
        joined = f"{member.joined_at:%Y-%m-%d}" if member.joined_at else "unknown"
        self.dispatch_event_jobs(
            member.guild.id,
            "member_leave",
            f"Event: member left. Member: {member} ({member.id}), joined {joined}, roles: {roles}.",
        )

    @commands.Cog.listener("on_message_without_command")
    async def on_job_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        text = (
            f"Event: message in #{message.channel} by {message.author} ({message.author.id}): "
            f"{message.content[:1500]}, attachments: {len(message.attachments)}"
        )
        self.dispatch_event_jobs(message.guild.id, "message", text, channel_id=message.channel.id)

    @commands.Cog.listener("on_raw_reaction_add")
    async def on_job_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or (payload.member and payload.member.bot):
            return
        url = f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}"
        who = f"{payload.member} ({payload.user_id})" if payload.member else str(payload.user_id)
        self.dispatch_event_jobs(
            payload.guild_id,
            "reaction_add",
            f"Event: reaction {payload.emoji} added by {who} to message {url}",
            channel_id=payload.channel_id,
        )

    @commands.Cog.listener("on_thread_create")
    async def on_job_thread_create(self, thread: discord.Thread):
        owner = thread.owner or thread.guild.get_member(thread.owner_id)
        if owner and owner.bot:
            return
        who = f"{owner} ({owner.id})" if owner else "unknown"
        self.dispatch_event_jobs(
            thread.guild.id,
            "thread_create",
            f"Event: thread created: {thread.name} in #{thread.parent} by {who}",
            channel_id=thread.parent_id,
        )

    @commands.Cog.listener("on_member_update")
    async def on_job_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or before.roles == after.roles:
            return
        added = ", ".join(r.name for r in after.roles if r not in before.roles) or "none"
        removed = ", ".join(r.name for r in before.roles if r not in after.roles) or "none"
        self.dispatch_event_jobs(
            after.guild.id,
            "role_change",
            f"Event: roles changed for {after} ({after.id}). Added: {added}. Removed: {removed}.",
        )

    @commands.Cog.listener("on_voice_state_update")
    async def on_job_voice_state_update(self, member: discord.Member, before, after):
        if member.bot or before.channel is not None or after.channel is None:
            return
        self.dispatch_event_jobs(
            member.guild.id,
            "voice_join",
            f"Event: {member} ({member.id}) joined voice channel {after.channel.name}",
            channel_id=after.channel.id,
        )

    @commands.Cog.listener("on_ticket_opened")
    async def on_job_ticket_opened(self, guild: discord.Guild, member: discord.Member, channel, panel_name: str):
        self.dispatch_event_jobs(
            guild.id,
            "ticket_opened",
            f"Event: ticket opened by {member} ({member.id}) in #{channel} (panel: {panel_name})",
        )

    async def pause_job(self, conf: GuildSettings, guild: discord.Guild, job: Job, reason: str) -> None:
        job.enabled = False
        job.last_error = reason[:500]
        self.unschedule_job(job)
        self.sync_raw_listeners()
        channel = guild.get_channel(job.channel_id) if guild else None
        if channel and hasattr(channel, "send"):
            prefix = (await self.bot.get_valid_prefixes(guild))[0]
            try:
                await channel.send(
                    f"⚠️ Job `{job.name}` was paused. {reason}\n"
                    f"Re-enable it with `{prefix}assistant jobs enable {job.name}`."
                )
            except discord.HTTPException as e:
                log.warning(f"Could not post pause warning for job {job.name}", exc_info=e)
        await self.save_conf()

    async def run_job(self, guild_id: int, job_id: str, event_text: str = "") -> None:
        conf = self.db.get_conf(guild_id)
        job = conf.jobs.get(job_id)
        if not job or not job.enabled:
            return
        guild = self.bot.get_guild(guild_id)
        if not guild:
            log.warning(f"Job {job.name}: server {guild_id} not found")
            return
        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        channel = guild.get_channel(job.channel_id)
        if not channel or not hasattr(channel, "send"):
            await self.pause_job(conf, guild, job, "Its output channel no longer exists.")
            return
        creator = guild.get_member(job.created_by)
        if not creator:
            await self.pause_job(conf, guild, job, "Its creator is no longer in the server.")
            return
        lock = self.job_locks.setdefault(self.job_key(guild_id, job_id), asyncio.Lock())
        if lock.locked():
            log.debug(f"Job {job.name} is still running, skipping this firing")
            return
        async with lock:
            await self.execute_job(conf, guild, channel, creator, job, event_text)

    def build_job_prompt(self, job: Job, event_text: str) -> str:
        prompt = f"[JOB {job.name}] This is an automated job configured by a server admin. It runs {describe_trigger(job)}.\n"
        if event_text:
            prompt += f"{event_text}\n"
        return prompt + f"Instruction: {job.prompt}"

    async def execute_job(self, conf, guild, channel, creator, job: Job, event_text: str) -> None:
        key = f"job-{job.id}-{guild.id}"
        started = datetime.now(tz=timezone.utc)
        reply, error, deferred_files = "", "", []
        try:
            if not await self.can_call_llm(conf):
                raise RuntimeError("No API key, endpoint, or Codex login is configured")
            reply = await self.get_chat_response(
                message=self.build_job_prompt(job, event_text),
                author=creator,
                guild=guild,
                channel=channel,
                conf=conf,
                deferred_files=deferred_files,
                conversation_key=key,
            ) or ""
            if not job.silent:
                await self.send_job_reply(channel, creator, reply, deferred_files)
            job.run_count += 1
            job.last_run = started
            job.consecutive_errors = 0
            job.last_error = ""
        except Exception as e:
            log.error(f"Job {job.name} in server {guild.id} failed", exc_info=e)
            error = str(e)[:500]
            job.consecutive_errors += 1
            job.last_error = error
        finally:
            if not job.remember:
                self.db.conversations.pop(key, None)
                # get_chat_response schedules a save for this key, so clear the stored file too.
                try:
                    await self.save_conversation(key)
                except Exception as e:
                    log.warning(f"Could not drop conversation for job {job.name}", exc_info=e)
        duration = (datetime.now(tz=timezone.utc) - started).total_seconds()
        await self.log_job_run(conf, guild, job, not error, duration, reply, error)
        if error and job.consecutive_errors >= self.db.job_error_pause:
            await self.pause_job(conf, guild, job, f"{job.consecutive_errors} errors in a row. Last error: {error}")
            return
        await self.save_conf()

    async def send_job_reply(self, channel, creator, reply: str, deferred_files: list) -> None:
        allowed_mentions = await self.get_mention_permissions(creator)
        pages = list(pagify(reply, delims=["\n", " "], page_length=2000)) if reply else []
        if not pages and deferred_files:
            await channel.send(files=deferred_files, allowed_mentions=allowed_mentions)
        for i, page in enumerate(pages):
            kwargs = {"allowed_mentions": allowed_mentions}
            if i == 0 and deferred_files:
                kwargs["files"] = deferred_files
            await channel.send(page, **kwargs)

    async def log_job_run(self, conf, guild, job: Job, ok: bool, duration: float, reply: str, error: str) -> None:
        if not conf.job_log_channel:
            return
        channel = guild.get_channel(conf.job_log_channel)
        if not channel or not hasattr(channel, "send"):
            return
        embed = discord.Embed(
            title=f"Job: {job.name}",
            color=discord.Color.green() if ok else discord.Color.red(),
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.add_field(name="Trigger", value=describe_trigger(job))
        embed.add_field(name="Duration", value=f"{duration:.1f}s")
        embed.add_field(name="Status", value="OK" if ok else f"Error: {error[:200]}")
        if reply and not job.silent:
            embed.add_field(name="Reply", value=reply[:1000], inline=False)
        try:
            await channel.send(embed=embed)
            if reply and job.silent:
                for page in pagify(reply, page_length=2000):
                    await channel.send(page)
        except discord.HTTPException as e:
            log.warning(f"Could not write job log for {job.name}", exc_info=e)
