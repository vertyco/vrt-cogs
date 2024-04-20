from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
import discord
import typing

_ = Translator("LevelUp", __file__)


def dashboard_page(*args, **kwargs):
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator


class DashboardIntegration:
    bot: Red

    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

    async def get_dashboard_leaderboard(self, user: discord.User, guild: discord.Guild, lbtype: typing.Literal["normal", "weekly"], stat: typing.Literal["exp", "messages", "voice", "stars"]="exp", **kwargs):
        conf = self.data[guild.id]
        if lbtype == "weekly":
            if not conf["weekly"]["on"]:
                return {"status": 1, "error_title": _("Weekly stats disabled"), "error_message": _("Weekly stats are disabled for this guild.")}
            if not conf["weekly"]["users"]:
                return {"status": 1, "error_title": _("No Weekly stats available"), "error_message": _("There is no data for the weekly leaderboard yet, please chat a bit first.")}
        payload = await self.get_leaderboard_for_dash(guild, conf, stat, lbtype, is_global=False, use_displayname=True, member=guild.get_member(user.id))
        if not payload["stats"]:
            return {"status": 1, "error_title": _("No stats available"), "error_message": _("There is no data for the leaderboard yet, please chat a bit first.")}

        source = """
            <div class="d-flex justify-content-between">
                <h5>{{ total }}</h5>
                <div class="dropdown">
                    <a class="btn btn-secondary" role="button" id="sort_by_dropdown" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
                        Sort by <i class="ni ni-bold-down"></i>
                    </a>
                    <div class="dropdown-menu" aria-labelledby="sort_by_dropdown">
                        <a class="dropdown-item" href="{{ url_for_query(stat=None) }}">{% if stat == "exp" %}<i class="ni ni-check-bold me-2" style="vertical-align: -1.5px;"></i>{% endif %}Exp</a>
                        <a class="dropdown-item" href="{{ url_for_query(stat="messages") }}">{% if stat == "messages" %}<i class="ni ni-check-bold me-2" style="vertical-align: -1.5px;"></i>{% endif %}Messages</a>
                        <a class="dropdown-item" href="{{ url_for_query(stat="voice") }}">{% if stat == "voice" %}<i class="ni ni-check-bold me-2" style="vertical-align: -1.5px;"></i>{% endif %}Voice</a>
                        <a class="dropdown-item" href="{{ url_for_query(stat="stars") }}">{% if stat == "stars" %}<i class="ni ni-check-bold me-2" style="vertical-align: -1.5px;"></i>{% endif %}Stars</a>
                    </div>
                </div>
            </div>
            <div id="users-container" class="table-responsive p-0">
                <table class="table align-items-center mb-0">
                    <thead>
                        <tr>
                            <td class="medium"><b>#</b></td>
                            <td class="large"><b>Name:</b></th>
                            <td class="medium"><b>{{ statname }}:</b></td>
                        </tr>
                    </thead>
                    <tbody>
                        {% for user in users %}
                            <tr{% if user.id == current_user.id|string %} class="text-{{ variables["meta"]["color"] }}"{% endif %}>
                                <td class="medium">{{ user.position }}</td>
                                <td class="large" title="{{ user.id }}">{{ user.name }}</td>
                                <td class="medium">{{ user.stat }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        """
        return {
            "status": 0,
            "web_content": {
                "source": source,
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
    async def leaderboard_page(self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs) -> typing.Dict[str, typing.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "normal", stat, **kwargs)

    @dashboard_page(name="weekly", description="Display the guild weekly leaderboard.")
    async def weekly_page(self, user: discord.User, guild: discord.Guild, stat: str = None, **kwargs) -> typing.Dict[str, typing.Any]:
        stat = stat if stat is not None and stat in {"exp", "messages", "voice", "stars"} else "exp"
        return await self.get_dashboard_leaderboard(user, guild, "weekly", stat, **kwargs)
