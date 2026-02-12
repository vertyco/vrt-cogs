import asyncio
import logging
import typing as t
from pathlib import Path

import discord
from pydantic import BaseModel, Field, ValidationError
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common import formatter

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.levelup.dashboard")
root = Path(__file__).parent
static = root / "static"
templates = root / "templates"


class LeaderboardQueryParams(BaseModel):
    page: int = Field(default=1, ge=1)


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

    async def get_dashboard_leaderboard(
        self,
        user: discord.User,
        guild: discord.Guild,
        lbtype: t.Literal["lb", "weekly"],
        stat: t.Literal["exp", "messages", "voice", "stars"] = "exp",
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

        source_path = templates / "leaderboard.html"
        js_path = static / "js" / "leaderboard.js"
        css_path = static / "css" / "leaderboard.css"

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
        content = {
            "status": 0,
            "web_content": {
                "source": source,
                "data": data,
                "stat": stat,
                "statname": res["stat"],
                "expanded": True,
            },
        }
        return content

    @dashboard_page(name="leaderboard", description="Display the guild leaderboard.")
    async def leaderboard_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "lb", stat, **kwargs)

    @dashboard_page(name="weekly", description="Display the guild weekly leaderboard.")
    async def weekly_page(
        self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs
    ) -> t.Dict[str, t.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "weekly", stat, **kwargs)

    # @dashboard_page(name="settings", description="Configure the leveling system.", methods=("GET", "POST"))
    async def cog_settings(self, user: discord.User, guild: discord.Guild, **kwargs):
        import wtforms  # pip install WTForms
        from flask_wtf import FlaskForm  # pip install Flask-WTF

        log.info(f"Getting settings for {guild.name} by {user.name}")
        member = guild.get_member(user.id)
        if not member:
            log.warning(f"Member {user.name} not found in guild {guild.name}")
            return {
                "status": 1,
                "error_title": _("Member not found"),
                "error_message": _("You are not a member of this guild."),
            }
        if not await self.bot.is_admin(member):
            log.warning(f"Member {user.name} is not an admin in guild {guild.name}")
            return {
                "status": 1,
                "error_title": _("Insufficient permissions"),
                "error_message": _("You need to be an admin to access this page."),
            }

        conf = self.db.get_conf(guild)

        class SettingsForm(kwargs["Form"]):
            def __init__(self):
                super().__init__(prefix="levelup_settings_form_")

            # General settings
            enabled = wtforms.BooleanField(_("Enabled:"), default=conf.enabled)
            algo_base = wtforms.IntegerField(
                _("Algorithm Base:"), default=conf.algorithm.base, validators=[wtforms.validators.InputRequired()]
            )
            algo_multiplier = wtforms.FloatField(
                _("Algorithm Multiplier:"), default=conf.algorithm.exp, validators=[wtforms.validators.InputRequired()]
            )

            # Submit button
            submit = wtforms.SubmitField(_("Save Settings"))

        form: FlaskForm = SettingsForm()

        # Handle form submission
        if form.validate_on_submit() and await form.validate_dpy_converters():
            log.info(f"Form validated for {guild.name} by {user.name}")
            conf.enabled = form.enabled.data
            conf.algorithm.base = form.algo_base.data or 100
            conf.algorithm.exp = form.algo_multiplier.data or 2.0
            self.save()
            return {
                "status": 0,
                "notifications": [{"message": _("Settings saved"), "category": "success"}],
                "redirect_url": kwargs["request_url"],
            }
        source = (templates / "settings.html").read_text()
        return {
            "status": 0,
            "web_content": {"source": source, "settings_form": form},
        }
