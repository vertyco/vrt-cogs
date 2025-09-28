import typing as t

from pydantic import BaseModel, Field


class CronDataResponse(BaseModel):
    interval: t.Optional[int] = Field(description="[INTERVAL]: for the schedule (e.g. every N units)")
    interval_unit: t.Optional[str] = Field(
        description="[INTERVAL]: seconds, minutes, hours, days, weeks, months, years"
    )

    hour: t.Optional[str] = Field(description="[CRON]: ex: *, */a, a-b, a-b/c, a,b,c")
    minute: t.Optional[str] = Field(description="[CRON]: ex: *, */a, a-b, a-b/c, a,b,c")
    second: t.Optional[str] = Field(description="[CRON]: ex: *, */a, a-b, a-b/c, a,b,c")
    days_of_week: t.Optional[str] = Field(description="[CRON]: ex: 'mon', 'tue', '1-4', '1,2,3' etc.")
    days_of_month: t.Optional[str] = Field(
        description="[CRON]: ex: *, */a, a-b, a-b/c, a,b,c, xth y, last, last x, etc."
    )
    months_of_year: t.Optional[str] = Field(description="[CRON]: ex: '1', '1-12/3', '1/2', '1,7', etc.")
    start_date: t.Optional[str] = Field(description="[CRON]: Start date for the schedule (ISOFORMAT)")
    end_date: t.Optional[str] = Field(description="[CRON]: End date for the schedule (ISOFORMAT)")
    between_time_start: t.Optional[str] = Field(description="[CRON]: HH:MM")
    between_time_end: t.Optional[str] = Field(description="[CRON]: HH:MM")


class CommandCreationResponse(CronDataResponse):
    name: str = Field(description="The name of the scheduled command")
    channel_id: t.Optional[int] = Field(
        description="The channel ID to run the command in, default to current channel if not provided in request"
    )
    author_id: t.Optional[int] = Field(
        description="The author ID to run the command as, default to current user if not provided in request"
    )
    command: str = Field(description="The command to run")
