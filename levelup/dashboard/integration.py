import asyncio
import logging
import typing as t
from pathlib import Path

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common import formatter

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.levelup.dashboard")


def dashboard_page(*args, **kwargs):
    def decorator(func: t.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func

    return decorator


class DashboardIntegration(MixinMeta):
    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        log.info("Dashboard cog added, registering third party.")
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

    async def get_dashboard_leaderboard(
        self,
        user: discord.User,
        guild: discord.Guild,
        lbtype: t.Literal["lb", "weekly"],
        stat: t.Literal["exp", "messages", "voice", "stars"] = "exp",
        query: t.Optional[str] = None,
        **kwargs,
    ):
        """
        kwargs = {
            "user_id": int,
            "guild_id": int,
            "method": str,  # GET or POST
            "request_url": str,
            "cxrf_token": str,
            "wtf_csrf_secret_key": bytes,
            "extra_kwargs": MultiDict,
            "data": {
                "form": ImmutableMultiDict,
                "json": ImmutableMultiDict,
            }
            "lang_code": str,
            "Form": FlaskForm,
            "DpyObjectConverter": DpyObjectConverter,
            "get_sorted_channels": Callable,
            "get_sorted_roles": Callable,
            "Pagination": Pagination,
        }
        """
        log.warning("Kwargs")
        for k, v in kwargs.items():
            log.warning(f"{k}: {v}")
        conf = self.db.get_conf(guild)
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

        parent = Path(__file__).parent

        source_path = parent / "templates" / "leaderboard.html"
        static_dir = parent / "static"
        js_path = static_dir / "js" / "leaderboard.js"
        css_path = static_dir / "css" / "leaderboard.css"

        # Inject JS and CSS into the HTML source for full page loads
        source = (
            f"<style>\n{css_path.read_text()}\n</style>\n\n"
            + source_path.read_text().strip()
            + f"\n\n<script>\n{js_path.read_text()}\n</script>"
        )

        """
        {
            "title": str,
            "description": str,
            "stat": str,
            "stats": [{"position": int, "name": str, "id": int, "stat": str}]
            "total": str,
            "type": leaderboard type,  // lb or weekly
            "user_position": int, // Index of the user in the leaderboard
        }
        """
        res: dict = await asyncio.to_thread(
            formatter.get_leaderboard,
            bot=self.bot,
            guild=guild,
            db=self.db,
            stat=stat,
            lbtype=lbtype,
            is_global=False,
            member=guild.get_member(user.id),
            use_displayname=True,
            dashboard=True,
            query=query,
        )
        data = {
            "user_id": user.id,
            "users": res["stats"],
            "stat": stat,
            "total": res["description"].replace("`", ""),
            "type": lbtype,
            "statname": res["stat"],
            "query": query if query is not None else "",  # Changed to prevent None
            "page": int(kwargs["extra_kwargs"].get("page", 1)),  # Ensure it's an integer
        }
        content = {
            "status": 0,
            "web_content": {
                "source": source,
                "data": data,
                "stat": stat,
                "total": res["description"].replace("`", ""),
                "statname": res["stat"],
                "query": query,
                "current_user": user,
            },
        }
        return content

    @dashboard_page(name="leaderboard", description="Display the guild leaderboard.")
    async def leaderboard_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, query: t.Optional[str] = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "lb", stat, query, **kwargs)

    @dashboard_page(name="weekly", description="Display the guild weekly leaderboard.")
    async def weekly_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, query: t.Optional[str] = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "weekly", stat, query, **kwargs)
