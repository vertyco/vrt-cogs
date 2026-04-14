import typing as t

import discord
from discord import ui

from .common.constants import (
    BELL,
    BELL_OFF,
    CALENDAR,
    CHECK,
    CROSS,
    DAY_LABELS,
    LEFT,
    PENCIL,
    PLUS,
    RIGHT,
    TRASH,
    TUTORIAL_PAGES,
)
from .common.models import DaySchedule, GuildSettings, TimeWindow, UserSchedule, Weekday
from .common.utils import discord_timestamp, get_user_time, window_discord_times

if t.TYPE_CHECKING:
    from .main import NoPing


def _text_view(text: str) -> ui.LayoutView:
    """Create a minimal LayoutView with a single text display."""
    view = ui.LayoutView()
    container = ui.Container()
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


# ──────────────────────────── Time Input Modal ────────────────────────────
class TimeWindowModal(ui.Modal, title="Add Availability Window"):
    start_time = ui.TextInput(
        label="Start Time (HH:MM, 24hr)",
        style=discord.TextStyle.short,
        placeholder="09:00",
        required=True,
        max_length=5,
        min_length=4,
    )
    end_time = ui.TextInput(
        label="End Time (HH:MM, 24hr)",
        style=discord.TextStyle.short,
        placeholder="17:00",
        required=True,
        max_length=5,
        min_length=4,
    )

    def __init__(self, schedule_view: "ScheduleView"):
        super().__init__()
        self.schedule_view = schedule_view

    def parse_time(self, value: str) -> t.Optional[tuple[int, int]]:
        value = value.strip().replace(".", ":")
        parts = value.split(":")
        if len(parts) != 2:
            return None
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h, m

    async def on_submit(self, interaction: discord.Interaction) -> None:
        start = self.parse_time(self.start_time.value)
        end = self.parse_time(self.end_time.value)
        if not start or not end:
            await interaction.response.send_message(
                "Invalid time format. Use HH:MM in 24-hour format (e.g., 09:00, 17:30).",
                ephemeral=True,
            )
            return

        if start[0] * 60 + start[1] >= end[0] * 60 + end[1]:
            await interaction.response.send_message(
                "Start time must be before end time.",
                ephemeral=True,
            )
            return

        window = TimeWindow(start_hour=start[0], start_minute=start[1], end_hour=end[0], end_minute=end[1])
        day_sched = self.schedule_view.user_schedule.get_day(self.schedule_view.selected_day)
        day_sched.enabled = True

        # Check for overlapping windows
        for existing in day_sched.windows:
            new_start = window.start_hour * 60 + window.start_minute
            new_end = window.end_hour * 60 + window.end_minute
            ex_start = existing.start_hour * 60 + existing.start_minute
            ex_end = existing.end_hour * 60 + existing.end_minute
            if new_start < ex_end and new_end > ex_start:
                await interaction.response.send_message(
                    f"This window overlaps with an existing window ({existing.format()}). Remove it first.",
                    ephemeral=True,
                )
                return

        day_sched.windows.append(window)
        day_sched.windows.sort(key=lambda w: w.start_hour * 60 + w.start_minute)

        self.schedule_view.rebuild()
        await interaction.response.edit_message(view=self.schedule_view)


# ──────────────────────────── All Days Modal ────────────────────────────
class AllDaysWindowModal(ui.Modal, title="Add Window to All Days"):
    start_time = ui.TextInput(
        label="Start Time (HH:MM, 24hr)",
        style=discord.TextStyle.short,
        placeholder="09:00",
        required=True,
        max_length=5,
        min_length=4,
    )
    end_time = ui.TextInput(
        label="End Time (HH:MM, 24hr)",
        style=discord.TextStyle.short,
        placeholder="17:00",
        required=True,
        max_length=5,
        min_length=4,
    )

    def __init__(self, schedule_view: "ScheduleView"):
        super().__init__()
        self.schedule_view = schedule_view

    def parse_time(self, value: str) -> t.Optional[tuple[int, int]]:
        value = value.strip().replace(".", ":")
        parts = value.split(":")
        if len(parts) != 2:
            return None
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h, m

    async def on_submit(self, interaction: discord.Interaction) -> None:
        start = self.parse_time(self.start_time.value)
        end = self.parse_time(self.end_time.value)
        if not start or not end:
            await interaction.response.send_message(
                "Invalid time format. Use HH:MM in 24-hour format (e.g., 09:00, 17:30).",
                ephemeral=True,
            )
            return

        if start[0] * 60 + start[1] >= end[0] * 60 + end[1]:
            await interaction.response.send_message(
                "Start time must be before end time.",
                ephemeral=True,
            )
            return

        window = TimeWindow(start_hour=start[0], start_minute=start[1], end_hour=end[0], end_minute=end[1])
        new_start = window.start_hour * 60 + window.start_minute
        new_end = window.end_hour * 60 + window.end_minute
        skipped = []

        for day_val in range(7):
            day_sched = self.schedule_view.user_schedule.get_day(day_val)
            overlaps = False
            for existing in day_sched.windows:
                ex_start = existing.start_hour * 60 + existing.start_minute
                ex_end = existing.end_hour * 60 + existing.end_minute
                if new_start < ex_end and new_end > ex_start:
                    overlaps = True
                    break
            if overlaps:
                skipped.append(DAY_LABELS[day_val])
                continue
            day_sched.enabled = True
            day_sched.windows.append(window.model_copy())
            day_sched.windows.sort(key=lambda w: w.start_hour * 60 + w.start_minute)

        self.schedule_view.rebuild()
        if skipped:
            await interaction.response.edit_message(view=self.schedule_view)
            await interaction.followup.send(
                f"Window added to most days. Skipped due to overlap: {', '.join(skipped)}",
                ephemeral=True,
            )
        else:
            await interaction.response.edit_message(view=self.schedule_view)


# ──────────────────────────── Window Select Row ────────────────────────────
class WindowSelectRow(ui.ActionRow["ScheduleView"]):
    def __init__(self, day_schedule: DaySchedule, selected_day: int):
        super().__init__()
        self.day_schedule = day_schedule
        self.selected_day = selected_day
        self.setup_options()

    def setup_options(self):
        options = []
        for i, window in enumerate(self.day_schedule.windows):
            options.append(
                discord.SelectOption(
                    label=window.format(),
                    value=str(i),
                    description=f"Window {i + 1} on {DAY_LABELS[self.selected_day]}",
                )
            )
        if not options:
            options.append(discord.SelectOption(label="No windows", value="none"))
        self.remove_window_select.options = options
        self.remove_window_select.disabled = not self.day_schedule.windows

    @ui.select(placeholder="Select a window to remove", max_values=1, min_values=1)
    async def remove_window_select(self, interaction: discord.Interaction, select: ui.Select) -> None:
        if select.values[0] == "none":
            await interaction.response.defer()
            return
        idx = int(select.values[0])
        if idx < len(self.day_schedule.windows):
            self.day_schedule.windows.pop(idx)
            if not self.day_schedule.windows:
                self.day_schedule.enabled = False
        view: ScheduleView = self.view
        view.rebuild()
        await interaction.response.edit_message(view=view)


# ──────────────────────────── Day Select Row ────────────────────────────
class DaySelectRow(ui.ActionRow["ScheduleView"]):
    def __init__(self, selected_day: int, user_schedule: UserSchedule):
        super().__init__()
        self.user_schedule = user_schedule
        options = []
        for day_val in range(7):
            day_sched = user_schedule.days.get(day_val)
            has_windows = day_sched and day_sched.enabled and day_sched.windows
            count = len(day_sched.windows) if has_windows else 0
            desc = f"{count} window(s)" if count else "No windows set"
            options.append(
                discord.SelectOption(
                    label=DAY_LABELS[day_val],
                    value=str(day_val),
                    description=desc,
                    default=day_val == selected_day,
                )
            )
        self.day_select.options = options

    @ui.select(placeholder="Select a day to edit")
    async def day_select(self, interaction: discord.Interaction, select: ui.Select) -> None:
        view: ScheduleView = self.view
        view.selected_day = int(select.values[0])
        view.rebuild()
        await interaction.response.edit_message(view=view)


# ──────────────────────────── Schedule View (LayoutView) ────────────────────────────
class ScheduleView(ui.LayoutView):
    action_row = ui.ActionRow()

    def __init__(
        self,
        cog: "NoPing",
        user: discord.Member,
        user_schedule: UserSchedule,
        conf: GuildSettings,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.user_schedule = user_schedule
        self.conf = conf
        self.selected_day: int = 0
        self.message: t.Optional[discord.Message] = None

        self.rebuild()

    def rebuild(self):
        """Rebuild all components from current state."""
        self.clear_items()

        tz_display = self.user_schedule.timezone or self.conf.timezone
        now = get_user_time(self.user_schedule, self.conf.timezone)
        container = ui.Container(accent_colour=discord.Colour.blurple())

        # Header
        status = (
            f"{BELL_OFF} Ping Protection: **ON**" if self.user_schedule.enabled else f"{BELL} Ping Protection: **OFF**"
        )
        container.add_item(
            ui.TextDisplay(
                f"# {self.user.display_name}'s Schedule\n"
                f"-# {status} | Timezone: {tz_display} | Now: {discord_timestamp(now, 'T')}"
            )
        )
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))

        # Day overview with Discord timestamps
        day_name = DAY_LABELS[self.selected_day]
        day_sched = self.user_schedule.days.get(self.selected_day)

        if day_sched and day_sched.enabled and day_sched.windows:
            window_lines = []
            for i, w in enumerate(day_sched.windows):
                start_ts, end_ts = window_discord_times(self.user_schedule, self.conf.timezone, self.selected_day, i)
                window_lines.append(f"- {w.format()} ({start_ts} → {end_ts})")
            windows_text = "\n".join(window_lines)
            container.add_item(
                ui.TextDisplay(
                    f"## {day_name}\n-# Availability windows (pings allowed during these times):\n{windows_text}"
                )
            )
        else:
            container.add_item(
                ui.TextDisplay(f"## {day_name}\n-# No availability windows set \u2014 pings blocked all day")
            )

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Weekly overview
        overview_lines = []
        for d in range(7):
            ds = self.user_schedule.days.get(d)
            marker = CHECK if ds and ds.enabled and ds.windows else CROSS
            count = len(ds.windows) if ds and ds.windows else 0
            overview_lines.append(f"{marker} **{Weekday(d).short}**: {count} window(s)")
        container.add_item(ui.TextDisplay("-# " + " | ".join(overview_lines)))

        self.add_item(container)

        # Day selection dropdown
        self.add_item(DaySelectRow(self.selected_day, self.user_schedule))

        # Window removal dropdown (if windows exist on selected day)
        if day_sched and day_sched.windows:
            self.add_item(WindowSelectRow(day_sched, self.selected_day))

        # Action buttons
        self.remove_item(self.action_row)
        self.add_item(self.action_row)

    @action_row.button(label="Add Window", style=discord.ButtonStyle.green, emoji=PLUS)
    async def add_window_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(TimeWindowModal(self))

    @action_row.button(label="Add to All Days", style=discord.ButtonStyle.green, emoji=CALENDAR)
    async def add_all_days_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(AllDaysWindowModal(self))

    @action_row.button(label="Toggle Day", style=discord.ButtonStyle.secondary, emoji=PENCIL)
    async def toggle_day_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        day_sched = self.user_schedule.get_day(self.selected_day)
        day_sched.enabled = not day_sched.enabled
        self.rebuild()
        await interaction.response.edit_message(view=self)

    @action_row.button(label="Clear Day", style=discord.ButtonStyle.danger, emoji=TRASH)
    async def clear_day_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        day_sched = self.user_schedule.get_day(self.selected_day)
        day_sched.windows.clear()
        day_sched.enabled = False
        self.rebuild()
        await interaction.response.edit_message(view=self)

    @action_row.button(label="Save & Close", style=discord.ButtonStyle.green, emoji=CHECK)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        # Auto-enable noping if the user has any schedule windows configured
        if self.user_schedule.has_schedule():
            self.user_schedule.enabled = True
        self.cog.save()
        await self.cog.sync_automod_rules(interaction.guild.id)
        view = _text_view(f"{CHECK} Schedule saved and ping protection is now active!")
        await interaction.response.edit_message(view=view)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.cog.save()
        if self.message:
            try:
                await self.message.edit(view=_text_view("Schedule editor timed out. Changes were saved."))
            except discord.HTTPException:
                pass


# ──────────────────────────── Tutorial View ────────────────────────────
class TutorialView(ui.LayoutView):
    action_row = ui.ActionRow()

    def __init__(self, user: discord.Member):
        super().__init__(timeout=180)
        self.user = user
        self.page = 0
        self.pages = TUTORIAL_PAGES
        self.message: t.Optional[discord.Message] = None
        self.rebuild()

    def rebuild(self):
        self.clear_items()

        page_data = self.pages[self.page]
        container = ui.Container(accent_colour=discord.Colour.blue())
        container.add_item(
            ui.TextDisplay(
                f"# {page_data['title']}\n-# Page {self.page + 1}/{len(self.pages)}\n\n{page_data['description']}"
            )
        )
        self.add_item(container)

        self.remove_item(self.action_row)
        self.add_item(self.action_row)

    @action_row.button(label="Previous", style=discord.ButtonStyle.secondary, emoji=LEFT)
    async def prev_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.page = (self.page - 1) % len(self.pages)
        self.rebuild()
        await interaction.response.edit_message(view=self)

    @action_row.button(label="Next", style=discord.ButtonStyle.primary, emoji=RIGHT)
    async def next_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        self.page = (self.page + 1) % len(self.pages)
        self.rebuild()
        await interaction.response.edit_message(view=self)

    @action_row.button(label="Close", style=discord.ButtonStyle.danger, emoji=CROSS)
    async def close_button(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.edit_message(view=_text_view("Tutorial closed."))
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=_text_view("Tutorial timed out."))
            except discord.HTTPException:
                pass
