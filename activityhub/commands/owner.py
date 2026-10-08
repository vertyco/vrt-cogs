from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.setup_check import ICONS, normalize_host, run_checks
from ..views.secret import SetSecretView

_ = Translator("ActivityHub", __file__)


class OwnerCommands(MixinMeta):
    @commands.group(name="activityhub")
    @commands.is_owner()
    async def activityhub_group(self, ctx: commands.Context):
        """Set up the activities web server and the Discord login"""

    @activityhub_group.command(name="webserver")
    async def set_webserver(self, ctx: commands.Context, host: str, port: commands.Range[int, 1, 65535]):
        """
        Set where the activities web server listens, then restart it

        Point your reverse proxy or tunnel at this address, and the Activity's URL mapping at the proxy.
        Use `127.0.0.1` when the proxy runs on the same machine, `0.0.0.0` to listen on every network.
        """
        await self.config.host.set(host)
        await self.config.port.set(port)
        await self.start_server()
        if self.server.running:
            await ctx.send(_("The web server is listening on {}:{}.").format(host, port))
        else:
            await ctx.send(_("The web server couldn't start on {}:{}. Check the bot's logs.").format(host, port))

    @activityhub_group.command(name="secret")
    async def set_secret(self, ctx: commands.Context):
        """
        Set the client secret used to log players in

        Find it in the Discord Developer Portal, under this bot's OAuth2 page.
        """
        await SetSecretView(self, ctx).start()

    @activityhub_group.command(name="check")
    async def check_setup(self, ctx: commands.Context, public_host: str):
        """
        Check every setup step and say which one is missing

        `public_host` is the address Discord loads the activities from, like `games.example.com`.
        """
        async with ctx.typing():
            results = await run_checks(self, public_host, ctx.clean_prefix)
        lines = [f"{ICONS[status]} {text}" for status, text in results]
        lines.append(
            _(
                "Last step, which bots can't check: in the Developer Portal under Activities > URL Mappings, "
                "the root mapping `/` must point to `{}`."
            ).format(normalize_host(public_host))
        )
        for page in pagify("\n".join(lines)):
            await ctx.send(page)

    @activityhub_group.command(name="games")
    async def list_games(self, ctx: commands.Context):
        """List the installed activities, and any game cog that was refused with the reason"""
        games = sorted(self.registry.games.values(), key=lambda game: game.key)
        blocked = await self.config.disabled()
        off = _(" [turned off]")
        lines = [f"{g.key}: {g.name} ({g.cog.qualified_name}){off if g.key in blocked else ''}" for g in games]
        if not lines:
            lines = [_("No activities installed yet.")]
        if self.registry.failed:
            lines += ["", _("Refused:")]
            lines += [f"{name}: {reason}" for name, (cog, reason) in sorted(self.registry.failed.items())]
        for page in pagify("\n".join(lines), page_length=1900):
            await ctx.send(box(page))
