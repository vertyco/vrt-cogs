import typing as t
from pathlib import Path

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

_ = Translator("LevelUp", __file__)


def dashboard_page(*args, **kwargs):
    def decorator(func: t.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func

    return decorator


class DashboardIntegration:
    bot: Red

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    async def get_dashboard_leaderboard(
        self,
        user: discord.User,
        guild: discord.Guild,
        lbtype: t.Literal["normal", "weekly"],
        stat: t.Literal["exp", "messages", "voice", "stars"] = "exp",
        **kwargs,
    ):
        conf = self.data[guild.id]
        if lbtype == "weekly":
            if not conf["weekly"]["on"]:
                return {
                    "status": 1,
                    "error_title": _("Weekly stats disabled"),
                    "error_message": _("Weekly stats are disabled for this guild."),
                }
            if not conf["weekly"]["users"]:
                return {
                    "status": 1,
                    "error_title": _("No Weekly stats available"),
                    "error_message": _("There is no data for the weekly leaderboard yet, please chat a bit first."),
                }
        payload = await self.get_leaderboard_for_dash(
            guild, conf, stat, lbtype, is_global=False, use_displayname=True, member=guild.get_member(user.id)
        )
        if not payload["stats"]:
            return {
                "status": 1,
                "error_title": _("No stats available"),
                "error_message": _("There is no data for the leaderboard yet, please chat a bit first."),
            }

        source_path = Path(__file__).parent / "templates" / "leaderboard.html"

        return {
            "status": 0,
            "web_content": {
                "source": source_path.read_text(),
                "users": kwargs["Pagination"].from_list(
                    payload["stats"],
                    per_page=kwargs["extra_kwargs"].get("per_page"),
                    page=kwargs["extra_kwargs"].get("page"),
                    default_per_page=100,
                ),
                "stat": stat,
                "total": payload["description"].replace("`", ""),
                "statname": payload["stat"],
            },
        }

    @dashboard_page(name="leaderboard", description="Display the guild leaderboard.")
    async def leaderboard_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "normal", stat, **kwargs)

    @dashboard_page(name="weekly", description="Display the guild weekly leaderboard.")
    async def weekly_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "weekly", stat, **kwargs)
