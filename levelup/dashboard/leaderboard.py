import asyncio
import typing as t

import discord
from pydantic import BaseModel, Field, ValidationError
from redbot.core.i18n import Translator

from ..common import formatter

if t.TYPE_CHECKING:
    from ..abc import MixinMeta

_ = Translator("LevelUp", __file__)


class LeaderboardQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)


async def get_dashboard_leaderboard(
    cog: "MixinMeta",
    user: discord.User,
    guild: discord.Guild,
    lbtype: t.Literal["lb", "weekly"],
    source: str,
    stat: t.Literal["exp", "messages", "voice", "stars"] = "exp",
    **kwargs: t.Any,
) -> t.Dict[str, t.Any]:
    conf = cog.db.get_conf(guild)
    if lbtype == "weekly":
        if not conf.weeklysettings.on:
            return {
                "status": 1,
                "error_title": _("Weekly stats disabled"),
                "error_message": _("Weekly stats are disabled for this guild."),
            }
        if not conf.users_weekly:
            return {
                "status": 1,
                "error_title": _("No Weekly stats available"),
                "error_message": _("There is no data for the weekly leaderboard yet, please chat a bit first."),
            }

    res: dict = await asyncio.to_thread(
        formatter.get_leaderboard,
        bot=cog.bot,
        guild=guild,
        db=cog.db,
        stat=stat,
        lbtype=lbtype,
        is_global=False,
        member=guild.get_member(user.id),
        use_displayname=True,
        dashboard=True,
    )
    try:
        query_params = LeaderboardQueryParams.model_validate(kwargs.get("extra_kwargs", {}))
        page = query_params.page
    except ValidationError:
        page = 1

    data = {
        "user_id": user.id,
        "users": res["stats"],
        "stat": stat,
        "total": res["description"].replace("`", ""),
        "type": lbtype,
        "page": page,
    }
    return {
        "status": 0,
        "web_content": {
            "source": source,
            "data": data,
            "stat": stat,
            "statname": res["stat"],
            "expanded": True,
        },
    }
