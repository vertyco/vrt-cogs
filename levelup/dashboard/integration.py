import logging
import typing as t
from pathlib import Path

import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from .leaderboard import get_dashboard_leaderboard
from .settings import handle_settings_page

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.levelup.dashboard")
root = Path(__file__).parent
static = root / "static"
templates = root / "templates"


def dashboard_page(*args: t.Any, **kwargs: t.Any) -> t.Callable[[t.Any], t.Any]:
    def decorator(func: t.Callable) -> t.Callable[[t.Any], t.Any]:
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func

    return decorator


class DashboardIntegration(MixinMeta):
    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        log.info("Dashboard cog added, registering third party.")
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

    def _build_leaderboard_source(self) -> str:
        source_path = templates / "leaderboard.html"
        js_path = static / "js" / "leaderboard.js"
        css_path = static / "css" / "leaderboard.css"
        return (
            f"<style>\n{css_path.read_text(encoding='utf-8')}\n</style>\n\n"
            + source_path.read_text(encoding="utf-8").strip()
            + f"\n\n<script>\n{js_path.read_text(encoding='utf-8')}\n</script>"
        )

    @dashboard_page(name="leaderboard", description="Display the guild leaderboard.")
    async def leaderboard_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        source = self._build_leaderboard_source()
        return await get_dashboard_leaderboard(self, user, guild, "lb", source, stat, **kwargs)

    @dashboard_page(name="weekly", description="Display the guild weekly leaderboard.")
    async def weekly_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        source = self._build_leaderboard_source()
        return await get_dashboard_leaderboard(self, user, guild, "weekly", source, stat, **kwargs)

    @dashboard_page(name="settings", description="Configure the leveling system.", methods=("GET", "POST"))
    async def cog_settings(self, user: discord.User, guild: discord.Guild, **kwargs) -> t.Dict[str, t.Any]:
        return await handle_settings_page(self, user, guild, **kwargs)
