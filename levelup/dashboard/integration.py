import asyncio
import logging
import typing as t
from pathlib import Path

import discord
import pydantic
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common import formatter, models

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
        )
        data = {
            "user_id": user.id,
            "users": res["stats"],
            "stat": stat,
            "total": res["description"].replace("`", ""),
            "type": lbtype,
            "page": int(kwargs["extra_kwargs"].get("page", 1)),
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

    async def save_settings(self, user: discord.User, guild: discord.Guild, data: dict, **kwargs):
        member = guild.get_member(user.id)
        if not member:
            return {
                "status": 1,
                "error_title": _("Member not found"),
                "error_message": _("You are not a member of this guild."),
            }
        if not await self.bot.is_admin(member):
            return {
                "status": 1,
                "error_title": _("Insufficient permissions"),
                "error_message": _("You need to be an admin to access this page."),
            }

        try:
            new_conf = models.GuildSettings.model_validate(data)
        except pydantic.ValidationError as e:
            return {
                "status": 1,
                "error_title": _("Validation error"),
                "error_message": str(e),
            }

        conf = self.db.get_conf(guild)
        for k, v in data.items():
            setattr(conf, k, getattr(new_conf, k, v))
        self.save()
        return {
            "status": 0,
            "success_title": _("Settings saved"),
            "success_message": _("The settings have been saved."),
        }

    # @dashboard_page(name="settings", description="Configure the leveling system.")
    async def get_cog_settings(self, user: discord.User, guild: discord.Guild, **kwargs):
        if kwargs.get("save") and (data := kwargs.get("new_data")):
            log.info(f"Saving settings for {guild.name} by {user.name}")
            return await self.save_settings(user, guild, data, **kwargs)
        log.info(f"Getting settings for {guild.name} by {user.name}")
        member = guild.get_member(user.id)
        if not member:
            return {
                "status": 1,
                "error_title": _("Member not found"),
                "error_message": _("You are not a member of this guild."),
            }
        if not await self.bot.is_admin(member):
            return {
                "status": 1,
                "error_title": _("Insufficient permissions"),
                "error_message": _("You need to be an admin to access this page."),
            }

        conf = self.db.get_conf(guild)
        settings = conf.model_dump(mode="json", exclude=["users", "users_weekly"])

        users = []
        for user in guild.members:
            users.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "avatar": user.display_avatar.url,
                }
            )

        emojis = []
        for emoji in guild.emojis:
            emojis.append(
                {
                    "id": emoji.id,
                    "name": emoji.name,
                    "url": emoji.url,
                }
            )

        # Add roles data for the settings page
        roles = []
        for role in sorted(guild.roles, reverse=True):
            if role.is_default():
                continue
            roles.append(
                {
                    "id": role.id,
                    "name": role.name,
                    "color": str(role.color),
                    "position": role.position,
                }
            )

        parent = Path(__file__).parent
        source_path = parent / "templates" / "settings.html"
        static_dir = parent / "static"
        js_path = static_dir / "js" / "settings.js"
        css_path = static_dir / "css" / "settings.css"

        # Inject JS and CSS into the HTML source for full page loads
        source = (
            f"<style>\n{css_path.read_text() if css_path.exists() else ''}\n</style>\n\n"
            + source_path.read_text().strip()
            + f"\n\n<script>\n{js_path.read_text()}\n</script>"
        )

        payload = {
            "status": 0,
            "web_content": {
                "source": source,
                "expanded": True,
                "settings": settings,
                "users": users,
                "emojis": emojis,
                "roles": roles,
            },
        }
        return payload
