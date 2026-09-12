import logging
import typing as t
import uuid
from datetime import datetime, timezone

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box

from ..abc import MixinMeta
from ..common.dynamic_menu import DynamicMenu
from ..common.jobs import (
    NAMED_EVENTS,
    build_trigger,
    describe_trigger,
    parse_interval,
    validate_event_name,
)
from ..common.models import GuildSettings, Job
from .admin import Admin

log = logging.getLogger("red.vrt.assistant.jobs.commands")
_ = Translator("Assistant", __file__)

FilterChannel = t.Union[discord.TextChannel, discord.VoiceChannel, discord.ForumChannel]
JOBS_PER_PAGE = 10


def find_job(conf: GuildSettings, name: str) -> t.Optional[Job]:
    lowered = name.lower()
    for job in conf.jobs.values():
        if job.name.lower() == lowered:
            return job
    return None


def job_embed(job: Job, prefix: str) -> discord.Embed:
    status = _("Enabled") if job.enabled else _("Paused")
    embed = discord.Embed(
        title=_("Job: {}").format(job.name),
        description=f"**{status}**",
        color=discord.Color.blurple(),
    )
    embed.add_field(name=_("Trigger"), value=describe_trigger(job))
    embed.add_field(name=_("Output channel"), value=f"<#{job.channel_id}>")
    if job.event_channel_id:
        embed.add_field(name=_("Event filter"), value=f"<#{job.event_channel_id}>")
    embed.add_field(name=_("Silent"), value=str(job.silent))
    embed.add_field(name=_("Remembers runs"), value=str(job.remember))
    embed.add_field(name=_("Runs"), value=str(job.run_count))
    last_run = f"<t:{int(job.last_run.timestamp())}:R>" if job.last_run else _("never")
    embed.add_field(name=_("Last run"), value=last_run)
    embed.add_field(name=_("Created by"), value=f"<@{job.created_by}>")
    if job.last_error:
        embed.add_field(name=_("Last error"), value=job.last_error[:1000], inline=False)
    embed.add_field(name=_("Prompt"), value=job.prompt[:1000], inline=False)
    embed.set_footer(text=f"{prefix}assistant jobs view {job.name}")
    return embed


def job_line(job: Job) -> str:
    icon = "🟢" if job.enabled else "⏸️"
    last = f"<t:{int(job.last_run.timestamp())}:R>" if job.last_run else _("never")
    return (
        f"{icon} **{job.name}** · {describe_trigger(job)} · <#{job.channel_id}> · "
        + _("{} runs").format(job.run_count)
        + f" · {last}"
    )


@cog_i18n(_)
class Jobs(MixinMeta):
    async def create_job(
        self,
        ctx: commands.Context,
        name: str,
        channel: discord.TextChannel,
        prompt: str,
        trigger_type: str,
        trigger: str,
        enabled: bool = True,
    ) -> t.Optional[Job]:
        conf = self.db.get_conf(ctx.guild)
        if len(conf.jobs) >= self.db.max_jobs_per_guild:
            txt = _("This server already has the maximum of {} jobs.").format(self.db.max_jobs_per_guild)
            await ctx.send(txt)
            return None
        if " " in name or len(name) > 32:
            await ctx.send(_("Job names are one word, up to 32 characters."))
            return None
        if find_job(conf, name):
            await ctx.send(_("A job named `{}` already exists.").format(name))
            return None
        job = Job(
            id=uuid.uuid4().hex[:8],
            name=name,
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            prompt=prompt,
            trigger_type=trigger_type,
            trigger=trigger,
            enabled=enabled,
            created_by=ctx.author.id,
            created_at=datetime.now(tz=timezone.utc),
        )
        conf.jobs[job.id] = job
        self.schedule_job(job)
        self.sync_raw_listeners()
        await self.save_conf()
        return job

    @Admin.jobs.command(name="interval")
    async def jobs_interval(
        self, ctx: commands.Context, name: str, every: str, channel: discord.TextChannel, *, prompt: str
    ):
        """Add a job that runs every N seconds/minutes/hours/days (e.g. 30m, 6h, 1d)"""
        try:
            seconds = parse_interval(every)
        except ValueError as e:
            log.debug(f"Bad interval '{every}' in server {ctx.guild.id}", exc_info=e)
            return await ctx.send(str(e))
        if seconds < self.db.min_job_interval:
            return await ctx.send(_("The minimum interval is {} seconds.").format(self.db.min_job_interval))
        job = await self.create_job(ctx, name, channel, prompt, "interval", every)
        if job:
            await ctx.send(_("Job `{}` added, running {}.").format(job.name, describe_trigger(job)))

    @Admin.jobs.command(name="cron")
    async def jobs_cron(
        self, ctx: commands.Context, name: str, cron: str, channel: discord.TextChannel, *, prompt: str
    ):
        """
        Add a job on a 5-field cron schedule (UTC)

        Quote the cron string, for example: "0 9 * * 1-5"
        """
        probe = Job(
            id="x",
            name=name,
            guild_id=0,
            channel_id=0,
            prompt="",
            trigger_type="cron",
            trigger=cron,
            created_by=0,
            created_at=datetime.now(tz=timezone.utc),
        )
        try:
            build_trigger(probe)
        except ValueError as e:
            log.debug(f"Bad cron '{cron}' in server {ctx.guild.id}", exc_info=e)
            return await ctx.send(str(e))
        job = await self.create_job(ctx, name, channel, prompt, "cron", cron)
        if job:
            await ctx.send(_("Job `{}` added, running {}.").format(job.name, describe_trigger(job)))

    @Admin.jobs.command(name="event")
    async def jobs_event(
        self, ctx: commands.Context, name: str, event: str, channel: discord.TextChannel, *, prompt: str
    ):
        """Add a job that runs on a Discord event. See `[p]assistant jobs events`"""
        try:
            trigger = validate_event_name(event)
        except ValueError as e:
            log.debug(f"Bad event '{event}' in server {ctx.guild.id}", exc_info=e)
            return await ctx.send(str(e))
        needs_filter = trigger == "message"
        job = await self.create_job(ctx, name, channel, prompt, "event", trigger, enabled=not needs_filter)
        if not job:
            return
        if needs_filter:
            txt = _(
                "Job `{name}` added but paused. Set the channel to watch with "
                "`{prefix}assistant jobs filter {name} #channel`, then `{prefix}assistant jobs enable {name}`."
            ).format(name=job.name, prefix=ctx.clean_prefix)
            await ctx.send(txt)
        else:
            await ctx.send(_("Job `{}` added, running {}.").format(job.name, describe_trigger(job)))

    @Admin.jobs.command(name="filter")
    async def jobs_filter(self, ctx: commands.Context, name: str, channel: t.Optional[FilterChannel] = None):
        """Set or clear the channel an event job watches (leave the channel off to clear)"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        if not channel and job.trigger_type == "event" and job.trigger == "message":
            txt = _(
                "Message jobs need a channel to watch first. Run `{prefix}assistant jobs filter {name} #channel`."
            ).format(prefix=ctx.clean_prefix, name=job.name)
            return await ctx.send(txt)
        job.event_channel_id = channel.id if channel else None
        await self.save_conf()
        if channel:
            await ctx.send(_("Job `{}` now only fires for events in {}.").format(job.name, channel.mention))
        else:
            await ctx.send(_("Job `{}` no longer filters by channel.").format(job.name))

    @Admin.jobs.command(name="list")
    async def jobs_list(self, ctx: commands.Context):
        """List every job on this server"""
        conf = self.db.get_conf(ctx.guild)
        if not conf.jobs:
            return await ctx.send(_("No jobs on this server."))
        jobs = sorted(conf.jobs.values(), key=lambda j: j.name.lower())
        chunks = [jobs[i : i + JOBS_PER_PAGE] for i in range(0, len(jobs), JOBS_PER_PAGE)]
        pages = []
        for idx, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=_("Assistant jobs"),
                description="\n".join(job_line(job) for job in chunk),
                color=discord.Color.blurple(),
            )
            embed.set_footer(text=_("Page {}/{}").format(idx + 1, len(chunks)))
            pages.append(embed)
        await DynamicMenu(ctx, pages).refresh()

    @Admin.jobs.command(name="view")
    async def jobs_view(self, ctx: commands.Context, name: str):
        """Show everything about one job"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        await ctx.send(embed=job_embed(job, ctx.clean_prefix))

    @Admin.jobs.command(name="remove", aliases=["delete", "del"])
    async def jobs_remove(self, ctx: commands.Context, name: str):
        """Delete a job"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        self.unschedule_job(job)
        del conf.jobs[job.id]
        key = f"job-{job.id}-{ctx.guild.id}"
        self.db.conversations.pop(key, None)
        await self.save_conversation(key)
        self.job_locks.pop(self.job_key(ctx.guild.id, job.id), None)
        self.sync_raw_listeners()
        await self.save_conf()
        await ctx.send(_("Job `{}` deleted.").format(job.name))

    @Admin.jobs.command(name="enable")
    async def jobs_enable(self, ctx: commands.Context, name: str):
        """Enable (or un-pause) a job"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        if job.trigger_type == "event" and job.trigger == "message" and not job.event_channel_id:
            txt = _(
                "Message jobs need a channel to watch first. Run `{prefix}assistant jobs filter {name} #channel`."
            ).format(prefix=ctx.clean_prefix, name=job.name)
            return await ctx.send(txt)
        job.enabled = True
        job.consecutive_errors = 0
        job.last_error = ""
        self.unschedule_job(job)
        self.schedule_job(job)
        self.sync_raw_listeners()
        await self.save_conf()
        await ctx.send(_("Job `{}` is enabled.").format(job.name))

    @Admin.jobs.command(name="disable", aliases=["pause"])
    async def jobs_disable(self, ctx: commands.Context, name: str):
        """Pause a job without deleting it"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        job.enabled = False
        self.unschedule_job(job)
        self.sync_raw_listeners()
        await self.save_conf()
        await ctx.send(_("Job `{}` is paused.").format(job.name))

    @Admin.jobs.command(name="run")
    async def jobs_run(self, ctx: commands.Context, name: str):
        """Run a job right now, even if it is paused"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        await ctx.send(_("Running `{}` now.").format(job.name))
        was_enabled = job.enabled
        job.enabled = True
        async with ctx.typing():
            await self.run_job(ctx.guild.id, job.id)
        if job.enabled:
            job.enabled = was_enabled
        await self.save_conf()

    @Admin.jobs.command(name="silent")
    async def jobs_silent(self, ctx: commands.Context, name: str):
        """Toggle whether the job posts its reply in the output channel"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        job.silent = not job.silent
        await self.save_conf()
        if job.silent:
            await ctx.send(_("Job `{}` will not post its reply in the channel.").format(job.name))
        else:
            await ctx.send(_("Job `{}` will post its reply in the channel.").format(job.name))

    @Admin.jobs.command(name="memory")
    async def jobs_memory(self, ctx: commands.Context, name: str):
        """Toggle whether the job remembers what happened on previous runs"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        job.remember = not job.remember
        if not job.remember:
            key = f"job-{job.id}-{ctx.guild.id}"
            self.db.conversations.pop(key, None)
            await self.save_conversation(key)
        await self.save_conf()
        if job.remember:
            await ctx.send(_("Job `{}` will remember previous runs.").format(job.name))
        else:
            await ctx.send(_("Job `{}` will start fresh every run.").format(job.name))

    @Admin.jobs.command(name="prompt")
    async def jobs_prompt(self, ctx: commands.Context, name: str, *, prompt: str):
        """Change what the job asks the assistant to do"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        job.prompt = prompt
        await self.save_conf()
        await ctx.send(_("Prompt updated for job `{}`.").format(job.name))

    @Admin.jobs.command(name="channel")
    async def jobs_channel(self, ctx: commands.Context, name: str, channel: discord.TextChannel):
        """Change the channel a job posts to"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        job.channel_id = channel.id
        await self.save_conf()
        await ctx.send(_("Job `{}` now posts to {}.").format(job.name, channel.mention))

    @Admin.jobs.command(name="rename")
    async def jobs_rename(self, ctx: commands.Context, name: str, new_name: str):
        """Rename a job"""
        conf = self.db.get_conf(ctx.guild)
        job = find_job(conf, name)
        if not job:
            return await ctx.send(_("No job named `{}`.").format(name))
        if " " in new_name or len(new_name) > 32:
            return await ctx.send(_("Job names are one word, up to 32 characters."))
        existing = find_job(conf, new_name)
        if existing and existing is not job:
            return await ctx.send(_("A job named `{}` already exists.").format(new_name))
        job.name = new_name
        await self.save_conf()
        await ctx.send(_("Job renamed to `{}`.").format(job.name))

    @Admin.jobs.command(name="events")
    async def jobs_events(self, ctx: commands.Context):
        """List the events a job can be triggered by"""
        embed = discord.Embed(
            title=_("Job event triggers"),
            description="\n".join(f"`{name}` - {desc}" for name, desc in NAMED_EVENTS.items()),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name=_("Anything else"),
            value=_(
                "`raw:on_<event>` runs on any discord.py event, with the event's objects summarised into the prompt."
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @Admin.jobs.command(name="logchannel")
    async def jobs_logchannel(self, ctx: commands.Context, channel: t.Optional[discord.TextChannel] = None):
        """Set the channel that gets a log embed for every job run (leave it off to disable)"""
        conf = self.db.get_conf(ctx.guild)
        conf.job_log_channel = channel.id if channel else 0
        await self.save_conf()
        if channel:
            await ctx.send(_("Job runs will be logged in {}.").format(channel.mention))
        else:
            await ctx.send(_("Job run logging is off."))

    @Admin.jobs.group(name="limits", invoke_without_command=True)
    @commands.is_owner()
    async def jobs_limits(self, ctx: commands.Context):
        """Bot owner limits for jobs"""
        txt = _("Max jobs per server: {}\nMinimum interval: {} seconds\nErrors before pause: {}").format(
            self.db.max_jobs_per_guild, self.db.min_job_interval, self.db.job_error_pause
        )
        await ctx.send(box(txt, lang="python"))

    @jobs_limits.command(name="maxjobs")
    @commands.is_owner()
    async def jobs_limits_maxjobs(self, ctx: commands.Context, amount: int):
        """Set how many jobs a single server can have"""
        if amount < 1:
            return await ctx.send(_("That must be at least 1."))
        self.db.max_jobs_per_guild = amount
        await self.save_conf()
        await ctx.send(_("Servers can now have up to {} jobs.").format(amount))

    @jobs_limits.command(name="mininterval")
    @commands.is_owner()
    async def jobs_limits_mininterval(self, ctx: commands.Context, seconds: int):
        """Set the shortest interval a job can run on, in seconds"""
        if seconds < 1:
            return await ctx.send(_("That must be at least 1."))
        self.db.min_job_interval = seconds
        await self.save_conf()
        await ctx.send(_("The minimum job interval is now {} seconds.").format(seconds))

    @jobs_limits.command(name="errorpause")
    @commands.is_owner()
    async def jobs_limits_errorpause(self, ctx: commands.Context, amount: int):
        """Set how many errors in a row pause a job"""
        if amount < 1:
            return await ctx.send(_("That must be at least 1."))
        self.db.job_error_pause = amount
        await self.save_conf()
        await ctx.send(_("Jobs pause after {} errors in a row.").format(amount))
