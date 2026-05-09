import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

import discord
from discord import ui
from redbot.core import commands
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.serverlimits")

ROLE_LIMIT = 250
CATEGORY_LIMIT = 50
CHANNEL_LIMIT = 500
CHANNELS_PER_CATEGORY_LIMIT = 50
THREAD_MEMBER_LIMIT = 1_000
THREAD_ROLE_MENTION_LIMIT = 250
GO_LIVE_MEMBER_LIMIT = 50
VIDEO_SCREEN_SHARE_LIMIT = 50
VOICE_VIDEO_LIMIT = 25
STAGE_AUDIENCE_LIMIT = 10_000
SHARED_STAGE_SCREEN_LIMIT = 1
MOBILE_PUSH_THRESHOLD = 2_500
OFFLINE_VISIBLE_THRESHOLD = 1_000
OFFLINE_REAPPEAR_THRESHOLD = 800
MEMBER_CAP = 25_000_000
ROLE_NAME_LIMIT = 100
INVITE_LIMIT = 999
AUDIT_LOG_RETENTION_DAYS = 45
FOLLOWED_ANNOUNCEMENT_LIMIT = 10
RTC_CONNECT_TIMEOUT_MINUTES = 3
THREAD_DEFAULT_ARCHIVE = "3 days"

SOUNDBOARD_LIMITS = {0: 8, 1: 24, 2: 36, 3: 48}
STREAM_QUALITY = {
    0: "720p @ 30fps",
    1: "720p @ 60fps",
    2: "720p @ 60fps",
    3: "720p @ 60fps",
}
GO_LIVE_STREAMS = {
    0: "720p @ 60fps",
    1: "720p @ 60fps",
    2: "1080p @ 60fps",
    3: "1080p @ 60fps",
}


def format_number(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value:,}"


def format_size(value: int) -> str:
    size = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}PB"


def format_bitrate(value: int) -> str:
    return f"{value / 1000:.0f}kbps"


def format_state(enabled: bool) -> str:
    return "Yes" if enabled else "No"


def get_bar(progress: int | float, total: int | float, width: int) -> str:
    if total <= 0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(float(progress) / float(total), 1.0))
    fill = "▰"
    space = "▱"
    filled = round(ratio * width)
    bar = fill * filled + space * (width - filled)
    return f"{bar} {round(100 * ratio, 1)}%"


def get_stage_video_seat_limit(tier: int, boosts: int) -> int:
    if tier <= 1:
        return 50
    if tier == 2:
        return 150
    extra_boosts = max(boosts - 14, 0)
    return 300 + (extra_boosts * 30)


def get_server_banner_cap(tier: int) -> str:
    if tier >= 3:
        return "Animated"
    if tier >= 2:
        return "Static"
    return "No"


@dataclass(slots=True)
class Metric:
    name: str
    current: str
    limit: str | None = None
    bar: str | None = None
    note: str | None = None

    def render(self) -> str:
        line = f"-# **{self.name}** `{self.current}"
        if self.limit is not None:
            line += f"/{self.limit}`"
        else:
            line += "`"
        if self.bar is not None:
            line += f"\n-# {self.bar}"
        if self.note is not None:
            line += f"\n-# {self.note}"
        return line


@dataclass(slots=True)
class GuildSnapshot:
    guild_name: str
    tier: int
    boosts: int
    member_count: int
    static_emoji_count: int
    animated_emoji_count: int
    sticker_count: int
    soundboard_count: int
    role_count: int
    channel_count: int
    category_count: int
    max_channels_in_category: int
    longest_role_name: int
    invite_count: int | None
    filesize_limit: int
    bitrate_limit: int
    emoji_limit: int
    sticker_limit: int
    soundboard_limit: int
    stream_quality: str
    go_live_streams: str
    stage_video_seats: int
    stage_channel_count: int
    thread_count: int
    animated_icon: bool
    server_banner: str
    role_icons: bool
    custom_invite_link: bool
    vanity_url_length: int | None


def make_progress_metric(
    name: str,
    current: int,
    limit: int,
    formatter: Callable[[int | None], str] = format_number,
    bar_width: int = 12,
    note: str | None = None,
) -> Metric:
    return Metric(
        name=name,
        current=formatter(current),
        limit=formatter(limit),
        bar=get_bar(current, limit, width=bar_width),
        note=note,
    )


def render_section(title: str, metrics: list[Metric]) -> str:
    body = "\n".join(metric.render() for metric in metrics)
    return f"## {title}\n{body}".strip()


def build_utilization_metrics(snapshot: GuildSnapshot) -> list[Metric]:
    metrics = [
        make_progress_metric("Static Emojis", snapshot.static_emoji_count, snapshot.emoji_limit),
        make_progress_metric("Animated Emojis", snapshot.animated_emoji_count, snapshot.emoji_limit),
        make_progress_metric("Stickers", snapshot.sticker_count, snapshot.sticker_limit),
        make_progress_metric("Soundboard", snapshot.soundboard_count, snapshot.soundboard_limit),
        make_progress_metric("Roles", snapshot.role_count, ROLE_LIMIT),
        make_progress_metric("Channels", snapshot.channel_count, CHANNEL_LIMIT),
        make_progress_metric("Categories", snapshot.category_count, CATEGORY_LIMIT),
        make_progress_metric("Largest Category", snapshot.max_channels_in_category, CHANNELS_PER_CATEGORY_LIMIT),
        make_progress_metric("Role Name Len", snapshot.longest_role_name, ROLE_NAME_LIMIT),
    ]
    if snapshot.invite_count is None:
        metrics.append(
            Metric(
                name="Invite Codes",
                current="Unavailable",
                limit=format_number(INVITE_LIMIT),
                note="⚠️ needs Manage Server permissions",
            )
        )
    else:
        metrics.append(make_progress_metric("Invite Codes", snapshot.invite_count, INVITE_LIMIT))
    return metrics


def build_server_cap_metrics(snapshot: GuildSnapshot) -> list[Metric]:
    return [
        Metric(name="Upload", current=format_size(snapshot.filesize_limit)),
        Metric(name="Audio", current=format_bitrate(snapshot.bitrate_limit)),
        Metric(name="Stream Quality", current=snapshot.stream_quality),
        Metric(name="Go Live Streams", current=snapshot.go_live_streams),
        Metric(name="Go Live Audience", current=f"{format_number(GO_LIVE_MEMBER_LIMIT)} members"),
        Metric(name="Video Screenshare", current=f"{format_number(VIDEO_SCREEN_SHARE_LIMIT)} members"),
        Metric(name="Voice + Video", current=f"{format_number(VOICE_VIDEO_LIMIT)} members"),
        Metric(
            name="Vanity URL",
            current=(
                f"{snapshot.vanity_url_length} chars" if snapshot.vanity_url_length is not None else "Unavailable"
            ),
        ),
        Metric(name="Animated Server Icon", current=format_state(snapshot.animated_icon)),
        Metric(name="Server Banner", current=snapshot.server_banner),
        Metric(name="Custom Role Icons", current=format_state(snapshot.role_icons)),
        Metric(name="Custom Invite Link", current=format_state(snapshot.custom_invite_link)),
        Metric(
            name="Member Cap",
            current=format_number(snapshot.member_count),
            limit=format_number(MEMBER_CAP),
        ),
        Metric(name="Mobile Push All Msgs", current=f"under {format_number(MOBILE_PUSH_THRESHOLD)} members"),
        Metric(name="Offline List Visible", current=f"under {format_number(OFFLINE_VISIBLE_THRESHOLD)} members"),
        Metric(name="Offline List Reappears", current=f"under {format_number(OFFLINE_REAPPEAR_THRESHOLD)} members"),
        Metric(name="RTC Connect Timeout", current=f"{RTC_CONNECT_TIMEOUT_MINUTES} minutes"),
        Metric(name="Audit Log Retention", current=f"{AUDIT_LOG_RETENTION_DAYS} days"),
        Metric(name="Follows / Channel", current=format_number(FOLLOWED_ANNOUNCEMENT_LIMIT)),
    ]


def build_stage_thread_metrics(snapshot: GuildSnapshot) -> list[Metric]:
    return [
        Metric(name="Stage Audience", current=format_number(STAGE_AUDIENCE_LIMIT)),
        Metric(
            name="Video Stage Seats",
            current=format_number(snapshot.stage_video_seats),
            note=("+30 / boost past 14" if snapshot.tier >= 3 else None),
        ),
        Metric(
            name="Stage Channels", current="No limit", note=f"current {format_number(snapshot.stage_channel_count)}"
        ),
        Metric(name="Hands Raised", current="No limit"),
        Metric(name="Shared Screens", current=format_number(SHARED_STAGE_SCREEN_LIMIT)),
        Metric(name="Stage Activities", current="None"),
        Metric(name="Stage Msg Rate", current="No limit unless slowmode"),
        Metric(name="Thread Archive Default", current=THREAD_DEFAULT_ARCHIVE),
        Metric(name="Thread Members", current=format_number(THREAD_MEMBER_LIMIT)),
        Metric(name="Private Thread Role Mentions", current=format_number(THREAD_ROLE_MENTION_LIMIT)),
        Metric(name="Threads Cached", current=format_number(snapshot.thread_count)),
    ]


def build_dashboard_text(snapshot: GuildSnapshot) -> str:
    sections = [
        "# Server Limits",
        discord.utils.escape_markdown(snapshot.guild_name),
        (
            f"Tier {snapshot.tier} | "
            f"Boosts {format_number(snapshot.boosts)} | "
            f"Members {format_number(snapshot.member_count)}"
        ),
        render_section("Usage", build_utilization_metrics(snapshot)),
        render_section("Server Caps", build_server_cap_metrics(snapshot)),
        render_section("Stage + Threads", build_stage_thread_metrics(snapshot)),
    ]
    return "\n".join(sections)


async def build_snapshot(guild: discord.Guild) -> GuildSnapshot:
    tier = int(guild.premium_tier)
    boosts = guild.premium_subscription_count or 0
    features = set(guild.features)
    member_count = guild.member_count or len(guild.members)
    static_emoji_count = len([emoji for emoji in guild.emojis if not emoji.animated])
    animated_emoji_count = len([emoji for emoji in guild.emojis if emoji.animated])

    soundboard_count = len(guild.soundboard_sounds)
    if soundboard_count == 0:
        try:
            soundboard_count = len(await guild.fetch_soundboard_sounds())
        except (AttributeError, discord.Forbidden, discord.HTTPException):
            soundboard_count = len(guild.soundboard_sounds)

    invite_count = None
    me = guild.me
    if me is not None and me.guild_permissions.manage_guild:
        try:
            invite_count = len(await guild.invites())
        except (discord.Forbidden, discord.HTTPException):
            invite_count = None

    return GuildSnapshot(
        guild_name=guild.name,
        tier=tier,
        boosts=boosts,
        member_count=member_count,
        static_emoji_count=static_emoji_count,
        animated_emoji_count=animated_emoji_count,
        sticker_count=len(guild.stickers),
        soundboard_count=soundboard_count,
        role_count=len(guild.roles),
        channel_count=len(guild.channels),
        category_count=len(guild.categories),
        max_channels_in_category=max((len(category.channels) for category in guild.categories), default=0),
        longest_role_name=max((len(role.name) for role in guild.roles), default=0),
        invite_count=invite_count,
        filesize_limit=guild.filesize_limit,
        bitrate_limit=int(guild.bitrate_limit),
        emoji_limit=guild.emoji_limit,
        sticker_limit=guild.sticker_limit,
        soundboard_limit=SOUNDBOARD_LIMITS.get(tier, SOUNDBOARD_LIMITS[3]),
        stream_quality=STREAM_QUALITY.get(tier, STREAM_QUALITY[3]),
        go_live_streams=GO_LIVE_STREAMS.get(tier, GO_LIVE_STREAMS[3]),
        stage_video_seats=get_stage_video_seat_limit(tier, boosts),
        stage_channel_count=len(guild.stage_channels),
        thread_count=len(guild.threads),
        animated_icon=tier >= 1,
        server_banner=get_server_banner_cap(tier),
        role_icons="ROLE_ICONS" in features,
        custom_invite_link="VANITY_URL" in features,
        vanity_url_length=25 if "VANITY_URL" in features else None,
    )


class DashboardControls(ui.ActionRow["ServerLimitsView"]):
    @ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction[Red], button: ui.Button) -> None:
        assert self.view is not None
        await self.view.refresh(interaction)

    @ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction[Red], button: ui.Button) -> None:
        assert self.view is not None
        self.view.stop()
        await interaction.response.defer()
        try:
            if interaction.message is not None:
                await interaction.message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass


class ServerLimitsView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, snapshot: GuildSnapshot):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.snapshot = snapshot
        self.message: discord.Message | None = None
        self.build_layout()

    async def interaction_check(self, interaction: discord.Interaction[Red]) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your dashboard.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
            for nested in getattr(child, "children", []):
                if hasattr(nested, "disabled"):
                    setattr(nested, "disabled", True)
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return

    def build_layout(self) -> None:
        self.clear_items()
        self.add_item(ui.TextDisplay(build_dashboard_text(self.snapshot)))
        self.add_item(DashboardControls())

    async def refresh(self, interaction: discord.Interaction[Red]) -> None:
        guild = self.ctx.guild
        if guild is None:
            await interaction.response.send_message("Guild context missing.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            self.snapshot = await build_snapshot(guild)
        except Exception as e:
            log.exception("Failed to refresh snapshot", exc_info=e)
            await interaction.followup.send("Failed to refresh server limits.", ephemeral=True)
            return
        self.build_layout()
        await interaction.edit_original_response(view=self)


class ServerLimits(commands.Cog):
    """Show current Discord server caps.

    Info taken from https://support.discord.com/hc/en-us/articles/33694251638295-Discord-Account-Caps-Server-Caps-and-More
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.1.3"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self._init_task: asyncio.Task[None] | None = None

    def format_help_for_context(self, ctx: commands.Context) -> str:
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        return

    async def red_get_data_for_user(self, *, requester: str, user_id: int) -> None:
        return

    async def cog_load(self) -> None:
        self._init_task = asyncio.create_task(self.initialize())

    def cog_unload(self) -> None:
        if self._init_task is not None:
            self._init_task.cancel()

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()

    @commands.command(name="serverlimits")
    @commands.guild_only()
    async def serverlimits(self, ctx: commands.Context) -> None:
        """Show current server limits for this guild."""
        guild = ctx.guild
        if guild is None:
            await ctx.send("Guild only.")
            return
        snapshot = await build_snapshot(guild)
        view = ServerLimitsView(ctx, snapshot)
        view.message = await ctx.send(view=view)
