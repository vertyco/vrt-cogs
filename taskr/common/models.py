import typing as t
from datetime import datetime, time, timezone
from io import StringIO
from uuid import uuid4

import discord
import pytz
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import Field
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box

from . import Base

_ = Translator("Taskr", __file__)
DAYS_OF_WEEK = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}
MONTHS_OF_YEAR = {
    "1": "January",
    "2": "February",
    "3": "March",
    "4": "April",
    "5": "May",
    "6": "June",
    "7": "July",
    "8": "August",
    "9": "September",
    "10": "October",
    "11": "November",
    "12": "December",
}


def make_id() -> str:
    return str(uuid4())


def default_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class ScheduledCommand(Base):
    id: str = Field(default_factory=make_id)
    created_on: datetime = Field(default_factory=default_now)
    last_run: t.Optional[datetime] = Field(default=None)

    name: str

    # Used to mock the command
    guild_id: int
    channel_id: int = 0
    author_id: int
    command: str

    # Settings
    enabled: bool = Field(default=False)

    # ----------------- Advanced scheduling options -----------------
    # For interval-based scheduling
    interval: t.Optional[int] = Field(default=None)  # The interval for the schedule (e.g., every N units)
    interval_unit: t.Optional[str] = Field(default=None)  # 'minutes', 'hours', 'days', 'weeks', 'months', 'years'

    # For cron-based scheduling
    # ex: *, */a, a-b, a-b/c, a,b,c
    hour: t.Optional[str] = Field(default=None)  # ex: '1', '1-12/3', '1/2', '1,7', etc.
    minute: t.Optional[str] = Field(default=None)  # ex: '1', '1-30/2', '1/2', '1,7', etc.
    second: t.Optional[str] = Field(default=None)  # ex: '1', '1-30/2', '1/2', '1,7', etc.

    # Change to accept strings for advanced expressions
    days_of_week: t.Optional[str] = Field(default=None)  # ex: 'mon', 'tue', '1-4', '1,2,3' etc.
    days_of_month: t.Optional[str] = Field(default=None)  # ex: *, */a, a-b, a-b/c, a,b,c, xth y, last, last x, etc.
    months_of_year: t.Optional[str] = Field(default=None)  # ex: '1', '1-12/3', '1/2', '1,7', etc.

    # Optional start and end times/dates
    start_date: t.Optional[datetime] = Field(default=None)  # uses dateparser to parse
    end_date: t.Optional[datetime] = Field(default=None)  # uses dateparser to parse

    # Time range for interval scheduling
    between_time_start: t.Optional[time] = Field(default=None)
    between_time_end: t.Optional[time] = Field(default=None)

    def humanize(self) -> str:
        """
        Returns a humanized explanation of the current scheduled task.
        """
        if self.interval and self.interval_unit:
            return self._humanize_interval()
        else:
            return self._humanize_cron()

    def _humanize_interval(self) -> str:
        parts = []

        # Handle the interval and interval_unit
        interval = self.interval
        unit = self.interval_unit.lower()

        if interval == 1:
            if unit.endswith("s"):
                unit_singular = unit[:-1]
            else:
                unit_singular = unit
            parts.append(f"Every {unit_singular}")
        elif interval == 2:
            if unit.endswith("s"):
                unit_singular = unit[:-1]
            else:
                unit_singular = unit
            parts.append(f"Every other {unit_singular}")
        else:
            parts.append(f"Every {interval} {unit}")

        # Handle time ranges
        if self.between_time_start and self.between_time_end:
            start_time = self.between_time_start.strftime("%I:%M %p").lstrip("0")
            end_time = self.between_time_end.strftime("%I:%M %p").lstrip("0")
            parts.append(f"between {start_time} and {end_time}")

        # Handle t.Optional time specifications
        if self.hour and self.minute:
            time_str = self._format_time(self.hour, self.minute)
            parts.append(time_str)
        elif self.hour:
            time_str = self._format_time(self.hour, "0")
            parts.append(time_str)
        elif self.minute:
            time_str = f"{self.minute} minutes past every hour"
            parts.append(time_str)

        # Handle days of week, days of month, and months of year
        days_of_week_phrase = self._parse_days_of_week(self.days_of_week)
        days_of_month_phrase = self._parse_days_of_month(self.days_of_month)
        months_of_year_phrase = self._parse_months_of_year(self.months_of_year)

        if days_of_week_phrase:
            parts.append(f"on {days_of_week_phrase}")
        if days_of_month_phrase:
            parts.append(f"on {days_of_month_phrase}")
        if months_of_year_phrase:
            parts.append(f"in {months_of_year_phrase}")

        if self.start_date:
            parts.append(f"starting from {self.start_date.strftime('%B %d, %Y %I:%M %p')}")
        if self.end_date:
            parts.append(f"until {self.end_date.strftime('%B %d, %Y')}")

        return " ".join(parts)

    def _humanize_cron(self) -> str:
        parts = []

        # Handle time
        if self.hour or self.minute:
            time_str = self._format_time(self.hour or "*", self.minute or "0")
            parts.append(time_str)
        else:
            parts.append("At every hour")

        # Handle months of year
        months_of_year_phrase = self._parse_months_of_year(self.months_of_year)
        if months_of_year_phrase:
            parts.append(f"on {months_of_year_phrase}")

        # Handle days of month and days of week
        days_parts = []
        days_of_month_phrase = self._parse_days_of_month(self.days_of_month)
        days_of_week_phrase = self._parse_days_of_week(self.days_of_week)
        if days_of_month_phrase:
            days_parts.append(days_of_month_phrase)
        if days_of_week_phrase:
            days_parts.append(days_of_week_phrase)
        if days_parts:
            parts.append("on " + " and ".join(days_parts))
        else:
            parts.append("every day")

        if self.start_date:
            parts.append(f"starting from {self.start_date.strftime('%B %d, %Y %I:%M %p')}")
        if self.end_date:
            parts.append(f"until {self.end_date.strftime('%B %d, %Y')}")

        return " ".join(parts)

    def _format_time(self, hour: str, minute: str) -> str:
        def parse_field(field_str) -> str | list[int]:
            if field_str == "*":
                return "*"
            elif "," in field_str:
                values = []
                for part in field_str.split(","):
                    if "-" in part:
                        start, end = map(int, part.split("-"))
                        values.extend(range(start, end + 1))
                    else:
                        values.append(int(part))
                return sorted(set(values))
            elif "-" in field_str and "/" in field_str:
                range_part, step = field_str.split("/")
                start, end = map(int, range_part.split("-"))
                step = int(step)
                return list(range(start, end + 1, step))
            elif "-" in field_str:
                start, end = map(int, field_str.split("-"))
                return list(range(start, end + 1))
            elif "/" in field_str:
                start, step = map(int, field_str.split("/"))
                return list(range(start, 60, step))
            else:
                return [int(field_str)]

        def get_step(lst):
            if len(lst) < 2:
                return None
            step = lst[1] - lst[0]
            for i in range(2, len(lst)):
                if lst[i] - lst[i - 1] != step:
                    return None
            return step

        hour_parsed = parse_field(hour)
        minute_parsed = parse_field(minute)

        # Case when both hour and minute are wildcards
        if hour_parsed == "*" and minute_parsed == "*":
            return "every minute"

        # Handling when minute is a wildcard
        if minute_parsed == "*":
            if hour_parsed == "*":
                return "every minute"
            elif isinstance(hour_parsed, list):
                if len(hour_parsed) == 1:
                    h = hour_parsed[0] % 24
                    time_str = time(hour=h).strftime("%I %p").lstrip("0")
                    return f"every minute at {time_str}"
                else:
                    step = get_step(hour_parsed)
                    start_hour = hour_parsed[0] % 24
                    end_hour = hour_parsed[-1] % 24
                    start_time_str = time(hour=start_hour).strftime("%I %p").lstrip("0")
                    end_time_str = time(hour=end_hour).strftime("%I %p").lstrip("0")
                    if step and step > 1:
                        if step == 2:
                            every_str = "every other hour"
                        else:
                            every_str = f"every {step} hours"
                        return f"{every_str} between {start_time_str} and {end_time_str}"
                    else:
                        return f"every minute between {start_time_str} and {end_time_str}"
        # Handling when hour is a wildcard
        if hour_parsed == "*":
            if isinstance(minute_parsed, list):
                if len(minute_parsed) == 1:
                    m = minute_parsed[0] % 60
                    return f"every hour at {m} minute(s) past the hour"
                else:
                    step = get_step(minute_parsed)
                    if step and step > 1:
                        if step == 2:
                            every_str = "every other minute"
                        else:
                            every_str = f"every {step} minutes"
                        return f"every hour, {every_str}"
                    else:
                        minutes_str = ", ".join(str(m % 60) for m in minute_parsed)
                        return f"every hour at minutes {minutes_str}"
        # Handling when both hour and minute are specified
        if isinstance(hour_parsed, list):
            if len(hour_parsed) == 1:
                h = hour_parsed[0] % 24
                if isinstance(minute_parsed, list):
                    if len(minute_parsed) == 1:
                        m = minute_parsed[0] % 60
                        time_str = time(hour=h, minute=m).strftime("%I:%M %p").lstrip("0")
                        return f"at {time_str}"
                    else:
                        step = get_step(minute_parsed)
                        time_str = time(hour=h).strftime("%I %p").lstrip("0")
                        if step and step > 1:
                            if step == 2:
                                every_str = "every other minute"
                            else:
                                every_str = f"every {step} minutes"
                            return f"{every_str} at {time_str}"
                        else:
                            minutes_str = ", ".join(str(m % 60) for m in minute_parsed)
                            return f"at {minutes_str} minutes past {time_str}"
            else:
                step_hour = get_step(hour_parsed)
                if minute_parsed == "*":
                    start_hour = hour_parsed[0] % 24
                    end_hour = hour_parsed[-1] % 24
                    start_time_str = time(hour=start_hour).strftime("%I %p").lstrip("0")
                    end_time_str = time(hour=end_hour).strftime("%I %p").lstrip("0")
                    if step_hour and step_hour > 1:
                        if step_hour == 2:
                            every_str = "every other hour"
                        else:
                            every_str = f"every {step_hour} hours"
                        return f"{every_str} between {start_time_str} and {end_time_str}"
                    else:
                        return f"every minute between {start_time_str} and {end_time_str}"
                elif isinstance(minute_parsed, list):
                    step_minute = get_step(minute_parsed)
                    if len(minute_parsed) == 1:
                        m = minute_parsed[0] % 60
                        start_hour = hour_parsed[0] % 24
                        end_hour = hour_parsed[-1] % 24
                        start_time_str = time(hour=start_hour).strftime("%I %p").lstrip("0")
                        end_time_str = time(hour=end_hour).strftime("%I %p").lstrip("0")
                        if m == 0:
                            time_desc = "on the hour"
                        else:
                            time_desc = f"at {m} minute(s) past the hour"
                        if step_hour and step_hour > 1:
                            if step_hour == 2:
                                every_str = "every other hour"
                            else:
                                every_str = f"every {step_hour} hours"
                            return f"{every_str} {time_desc} between {start_time_str} and {end_time_str}"
                        else:
                            return f"{time_desc} between {start_time_str} and {end_time_str}"
                    else:
                        if step_minute and step_minute > 1:
                            # Use step_minute to describe the pattern
                            start_hour = hour_parsed[0] % 24
                            end_hour = hour_parsed[-1] % 24
                            start_time_str = time(hour=start_hour).strftime("%I %p").lstrip("0")
                            end_time_str = time(hour=end_hour).strftime("%I %p").lstrip("0")
                            return f"every {step_minute} minutes between {start_time_str} and {end_time_str}"
                        else:
                            # List all specific times if no clear step is found
                            times = []
                            for h in hour_parsed:
                                for m in minute_parsed:
                                    time_str = time(hour=h % 24, minute=m % 60).strftime("%I:%M %p").lstrip("0")
                                    times.append(time_str)
                            times_str = ", ".join(times)
                            return f"at {times_str}"
        # Default fallback
        return "Invalid time format."

    def _parse_days_of_week(self, days_of_week: str) -> str | None:
        if not days_of_week or days_of_week == "*":
            return None

        days = []
        tokens = days_of_week.lower().split(",")
        for token in tokens:
            token = token.strip()
            if "-" in token:
                # Handle ranges (e.g., mon-fri)
                start_day, end_day = token.split("-")
                ordered_days = list(DAYS_OF_WEEK.keys())
                start_index = ordered_days.index(start_day)
                end_index = ordered_days.index(end_day)
                if start_index <= end_index:
                    days_range = ordered_days[start_index : end_index + 1]
                else:
                    days_range = ordered_days[start_index:] + ordered_days[: end_index + 1]
                days.extend([DAYS_OF_WEEK[day] for day in days_range])
            elif "/" in token:
                # Handle steps (e.g., mon/2)
                day, step = token.split("/")
                day_name = DAYS_OF_WEEK.get(day, day.capitalize())
                step = int(step)
                if step == 2:
                    days.append(f"every other {day_name}")
                else:
                    days.append(f"every {step} {day_name}")
            else:
                day_name = DAYS_OF_WEEK.get(token, token.capitalize())
                days.append(day_name)

        if len(days) == 7:
            return None  # Every day
        elif len(days) > 1:
            return ", ".join(days[:-1]) + f" and {days[-1]}"
        else:
            return days[0]

    def _parse_days_of_month(self, days_of_month: str) -> str | None:
        if not days_of_month or days_of_month == "*":
            return None
        days = []
        tokens = days_of_month.lower().split(",")
        for token in tokens:
            token = token.strip()
            if token == "last":
                days.append("the last day of the month")
            elif any(i in token for i in ("th", "st", "nd", "rd")):
                # Handle ordinal days, e.g., "1st fri"
                ordinal, day = token.split(" ")
                ordinal = ordinal.lower()
                day = day.lower()
                day_name = day.capitalize()
                day_name = DAYS_OF_WEEK.get(day, day_name)
                if ordinal == "last":
                    days.append(f"the last {day_name} of the month")
                else:
                    days.append(f"the {ordinal} {day_name} of the month")
            elif "-" in token:
                # Handle ranges, e.g., '1-7'
                start_day, end_day = token.split("-")
                start_day = int(start_day)
                end_day = int(end_day)
                days.append(
                    f"every day from the {self._ordinal(start_day)} to the {self._ordinal(end_day)} of the month"
                )
            elif "/" in token:
                # Handle steps, e.g., '1/2'
                base, step = token.split("/")
                base = int(base)
                step = int(step)
                if step == 2:
                    days.append(f"every other day starting from the {self._ordinal(base)}")
                else:
                    days.append(f"every {step} days starting from the {self._ordinal(base)}")
            else:
                day = int(token)
                days.append(f"the {self._ordinal(day)} day of the month")
        if len(days) > 1:
            return ", ".join(days[:-1]) + f" and {days[-1]}"
        else:
            return days[0]

    def _parse_months_of_year(self, months_of_year: str) -> str | None:
        if not months_of_year or months_of_year == "*":
            return None

        months = []
        tokens = months_of_year.split(",")
        for token in tokens:
            token = token.strip()
            if "-" in token and "/" in token:
                # e.g., '1-12/3'
                range_part, step = token.split("/")
                start_month, end_month = range_part.split("-")
                step = int(step)
                start_index = int(start_month)
                end_index = int(end_month)
                month_nums = list(range(start_index, end_index + 1, step))
                months.extend([MONTHS_OF_YEAR[str(m)] for m in month_nums])
            elif "/" in token:
                # e.g., '1/2'
                base, step = token.split("/")
                base = int(base)
                step = int(step)
                months_in_year = 12
                month_nums = list(range(base, months_in_year + 1, step))
                months.extend([MONTHS_OF_YEAR[str(m)] for m in month_nums])
            elif "-" in token:
                # e.g., '1-3'
                start_month, end_month = token.split("-")
                start_index = int(start_month)
                end_index = int(end_month)
                month_nums = list(range(start_index, end_index + 1))
                months.extend([MONTHS_OF_YEAR[str(m)] for m in month_nums])
            else:
                month_name = MONTHS_OF_YEAR.get(token, f"Month {token}")
                months.append(month_name)

        if len(months) == 12:
            return None  # Every month
        elif len(months) > 1:
            return ", ".join(months[:-1]) + f" and {months[-1]}"
        else:
            return months[0]

    def _ordinal(self, n: int) -> str:
        suffix = [
            "th",
            "st",
            "nd",
            "rd",
        ] + ["th"] * 6
        if 10 <= n % 100 <= 20:
            return f"{n}th"
        else:
            return f"{n}{suffix[n % 10]}"

    def embed(self, timezone: str) -> discord.Embed:
        embed = discord.Embed(title=self.name, description=box(self.command), color=discord.Color.blurple())
        value = _("• Channel: {}\n• Author: {}\n").format(
            f"<#{self.channel_id}>" if self.channel_id else _("**DM**"),
            f"<@{self.author_id}>",
        )
        embed.add_field(name="Target Info", value=value, inline=False)

        ts = int(self.created_on.timestamp())
        value = _(
            "This command will run: {} ({})\n"
            "• Timezone: **{}**\n"
            "• Created: <t:{}:F> (<t:{}:R>)\n"
            "• Last run: {}\n"
            "Next 3 runtimes:\n{}"
        ).format(
            self.humanize(),
            str(self.trigger(timezone)),
            timezone,
            ts,
            ts,
            self.last_run_discord(),
            self.next_x_runs(3, timezone),
        )
        embed.add_field(
            name="Runtime Info",
            value=value,
            inline=False,
        )
        embed.add_field(
            name="Interval",
            value=("• Interval: **{}**\n• Unit: **{}**").format(self.interval, self.interval_unit),
            inline=True,
        )
        embed.add_field(
            name="Cron",
            value=("• Hour: **{}**\n• Minute: **{}**\n• Second: **{}**").format(self.hour, self.minute, self.second),
            inline=True,
        )
        embed.add_field(
            name="Advanced",
            value=("• Days of Week: **{}**\n• Days of Month: **{}**\n• Months of Year: **{}**").format(
                self.days_of_week, self.days_of_month, self.months_of_year
            ),
            inline=True,
        )
        if self.start_date:
            ts = int(self.start_date.timestamp())
            start = f"<t:{ts}:F> (<t:{ts}:R>)"
        else:
            start = "**None**"
        if self.end_date:
            ts = int(self.end_date.timestamp())
            end = f"<t:{ts}:F> (<t:{ts}:R>)"
        else:
            end = "**None**"
        embed.add_field(
            name="Time Boudaries",
            value=("• Start Date: {}\n• End Date: {}\n• Between Time Start: {}\n• Between Time End: {}").format(
                start,
                end,
                self.between_time_start.strftime("%I:%M %p").lstrip("0") if self.between_time_start else "**None**",
                self.between_time_end.strftime("%I:%M %p").lstrip("0") if self.between_time_end else "**None**",
            ),
            inline=True,
        )
        return embed

    def next_x_runs(self, x: int, timezone: str) -> str:
        if not self.next_run(timezone):
            return "**Never**"
        trigger = self.trigger(timezone)
        next_run: datetime | None = self.next_run(timezone)
        last_run: datetime | None = self.last_run
        if next_run:
            next_run = next_run.astimezone(pytz.timezone(timezone))
        if last_run:
            last_run = last_run.astimezone(pytz.timezone(timezone))
        buffer = StringIO()
        for idx in range(x):
            if not next_run:
                break
            ts = int(next_run.timestamp())
            buffer.write(f"{idx + 1}. <t:{ts}:F> (<t:{ts}:R>)\n")
            last_run = next_run
            next_run = trigger.get_next_fire_time(last_run, next_run)
        return buffer.getvalue()

    def trigger(self, timezone: str) -> IntervalTrigger | CronTrigger:
        """
        Return the appropriate APScheduler trigger based on the scheduling options

        Can handle the following examples:
        1. "the first friday of every 3 months at 3:00 PM"
        2. "every 2 weeks at 8:00 PM"
        3. "every other day at 6:00 AM"
        4. "january and july on the 1st at 12:00 PM"
        5. "every 30 minutes"
        6. "every 2 hours between 10am and 10pm"
        """
        tz = pytz.timezone(timezone)
        if self.interval and self.interval_unit:
            if self.between_time_start and self.between_time_end:
                # Use CronTrigger to handle intervals within a time range
                cron_kwargs = {"timezone": tz}
                if self.interval_unit == "hours":
                    start_hour = self.between_time_start.hour
                    end_hour = self.between_time_end.hour - 1  # Make it inclusive
                    cron_kwargs["hour"] = f"{start_hour}-{end_hour}/{self.interval}"
                    cron_kwargs["minute"] = self.between_time_start.minute
                    cron_kwargs["second"] = "0"
                elif self.interval_unit == "minutes":
                    start_minute = self.between_time_start.minute
                    end_minute = self.between_time_end.minute - 1
                    cron_kwargs["minute"] = f"{start_minute}-{end_minute}/{self.interval}"
                    cron_kwargs["hour"] = "*"
                    cron_kwargs["second"] = "0"
                else:
                    raise ValueError("When using between times, the interval unit must be 'hours' or 'minutes'.")

                if self.days_of_week:
                    cron_kwargs["day_of_week"] = self.days_of_week
                if self.days_of_month:
                    cron_kwargs["day"] = self.days_of_month
                if self.months_of_year:
                    cron_kwargs["month"] = self.months_of_year
                if self.start_date:
                    cron_kwargs["start_date"] = self.start_date.astimezone(tz)
                if self.end_date:
                    cron_kwargs["end_date"] = self.end_date.astimezone(tz)

                return CronTrigger(**cron_kwargs)
            else:
                # Use IntervalTrigger when there's no time range
                interval_kwargs = {self.interval_unit: self.interval, "timezone": tz}
                if self.hour and self.hour.isdigit():
                    interval_kwargs["hours"] = int(self.hour)
                if self.minute and self.minute.isdigit():
                    interval_kwargs["minutes"] = int(self.minute)
                if self.second and self.second.isdigit():
                    interval_kwargs["seconds"] = int(self.second)
                if self.start_date:
                    interval_kwargs["start_date"] = self.start_date.astimezone(tz)
                if self.end_date:
                    interval_kwargs["end_date"] = self.end_date.astimezone(tz)
                return IntervalTrigger(**interval_kwargs)
        else:
            # Use CronTrigger for more advanced scheduling options
            cron_kwargs = {
                "hour": self.hour or "*",
                "minute": self.minute or "0",
                "second": self.second or "0",
                "timezone": tz,
            }
            if self.days_of_week:
                cron_kwargs["day_of_week"] = self.days_of_week
            if self.days_of_month:
                cron_kwargs["day"] = self.days_of_month
            if self.months_of_year:
                cron_kwargs["month"] = self.months_of_year
            if self.start_date:
                cron_kwargs["start_date"] = self.start_date.astimezone(tz)
            if self.end_date:
                cron_kwargs["end_date"] = self.end_date.astimezone(tz)
            return CronTrigger(**cron_kwargs)

    def is_safe(self, timezone: str, minimum_interval: int) -> bool:
        """Ensure that the scheduled task will not run more frequently than every 5 minutes."""
        trigger: IntervalTrigger | CronTrigger = self.trigger(timezone)

        if isinstance(trigger, IntervalTrigger):
            # For IntervalTrigger, check if the interval is at least 5 minutes
            interval_seconds = trigger.interval.total_seconds()
            return interval_seconds >= minimum_interval
        elif isinstance(trigger, CronTrigger):
            # For CronTrigger, calculate the interval between the next two fire times
            now = default_now()
            next_run = trigger.get_next_fire_time(None, now)
            if next_run is None:
                return True
            following_run = trigger.get_next_fire_time(next_run, next_run)

            if next_run and following_run:
                delta = (following_run - next_run).total_seconds()
                return delta >= minimum_interval
            else:
                # If we cannot determine the interval, assume it's safe
                return True
        else:
            # For unknown triggers, assume it's safe
            return True

    def update_run(self):
        self.last_run = default_now()

    def last_run_discord(self) -> str:
        if not self.last_run:
            return "**Never**"
        ts = int(self.last_run.timestamp())
        return f"<t:{ts}:F> (<t:{ts}:R>)"

    def next_run(self, timezone: str) -> datetime | None:
        now = default_now()
        trigger = self.trigger(timezone)
        next_run = trigger.get_next_fire_time(self.last_run, now)
        if next_run and next_run < now:
            # If the next run is in the past, get the next one
            next_run = trigger.get_next_fire_time(None, now)
        return next_run

    def next_run_discord(self, timezone: str) -> str:
        next_run = self.next_run(timezone)
        if not next_run:
            return "**Never**"
        ts = int(next_run.timestamp())
        return f"<t:{ts}:F> (<t:{ts}:R>)"

    def __str__(self):
        return f"Scheduled Command: {self.name} ({self.command})"

    def __eq__(self, other) -> bool:
        if not isinstance(other, ScheduledCommand):
            return False
        attributes_to_compare = [
            "id",
            "enabled",
            "name",
            "guild_id",
            "channel_id",
            "author_id",
            "command",
            "interval",
            "interval_unit",
            "hour",
            "minute",
            "second",
            "days_of_week",
            "days_of_month",
            "months_of_year",
            "start_date",
            "end_date",
            "between_time_start",
            "between_time_end",
        ]
        return all(getattr(self, attr) == getattr(other, attr) for attr in attributes_to_compare)


class DB(Base):
    tasks: dict[str, ScheduledCommand] = {}  # {task_id: ScheduledCommand}
    timezones: dict[int, str] = {}  # {guild_id: timezone}
    last_cleanup: datetime = Field(default_factory=default_now)  # Last time invalid tasks were pruned
    max_tasks: int = 30  # Max scheduled commands a guild can have if premium (or premium is disabled)
    minimum_interval: int = 60  # Minimum interval between tasks in seconds (default: 1 minute)

    # Premium Settings
    premium_enabled: bool = False
    main_guild: int = 0
    premium_role: int = 0
    free_tasks: int = 5  # Task limit for free guilds
    premium_interval: int = 30  # Minimum interval between tasks for premium guilds in seconds (default: 30 seconds)

    def timezone(self, guild: discord.Guild | int) -> str:
        guild_id = guild if isinstance(guild, int) else guild.id
        return self.timezones.get(guild_id, "UTC")

    def get_tasks(self, guild: discord.Guild | int) -> list[ScheduledCommand]:
        guild_id = guild if isinstance(guild, int) else guild.id
        return sorted([task for task in self.tasks.values() if task.guild_id == guild_id], key=lambda x: x.name)

    def task_count(self, guild: discord.Guild | int) -> int:
        guild_id = guild if isinstance(guild, int) else guild.id
        return len([task for task in self.tasks.values() if task.guild_id == guild_id])

    def add_task(self, task: ScheduledCommand, overwrite: bool = False) -> None:
        if not overwrite and task.id in self.tasks:
            raise ValueError("Task with the same ID already exists.")
        self.tasks[task.id] = task

    def remove_task(self, task: str | ScheduledCommand) -> ScheduledCommand | None:
        task_id = task if isinstance(task, str) else task.id
        return self.tasks.pop(task_id)

    def refresh_task(self, task: str | ScheduledCommand) -> None:
        task_id = task if isinstance(task, str) else task.id
        if task_id in self.tasks:
            self.tasks[task_id].last_run = default_now()
