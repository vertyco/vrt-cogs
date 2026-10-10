import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, pagify

from ..abc import MixinMeta
from ..common.server import DEFAULT_HOST, DEFAULT_PORT
from ..common.setup_check import ICONS, run_checks
from ..common.setup_guide import setup_pages
from ..views.dynamic_menu import DynamicMenu
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
        The default is `127.0.0.1` port `8742`. `[p]activityhub view` shows the current address.
        """
        await self.config.host.set(host)
        await self.config.port.set(port)
        await self.start_server()
        if self.server.running:
            await ctx.send(_("The web server is listening on {}:{}.").format(host, port))
        else:
            await ctx.send(_("The web server couldn't start on {}:{}. Check the bot's logs.").format(host, port))

    @activityhub_group.command(name="view")
    @commands.bot_has_permissions(embed_links=True)
    async def view_settings(self, ctx: commands.Context):
        """Show where the web server listens, whether it is running, and the rest of the setup"""
        prefix = ctx.clean_prefix
        host, port = await self.config.host(), await self.config.port()
        if self.server.running:
            state = _("Running")
        else:
            state = _(
                "**Not running.** Check the bot's logs, or pick another address with "
                "`{}activityhub webserver <host> <port>`."
            ).format(prefix)
        embed = discord.Embed(title=_("ActivityHub settings"), color=await ctx.embed_color())
        embed.add_field(
            name=_("Web server"),
            value=_("Listens on `{}:{}`\n{}\nThe default is `{}:{}`.").format(
                host, port, state, DEFAULT_HOST, DEFAULT_PORT
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Public address"),
            value=_(
                "The bot doesn't store it. It's the HTTPS address your tunnel or proxy serves, and the one set in the "
                "Developer Portal under Activities > URL Mappings. Test it with `{}activityhub check`."
            ).format(prefix),
            inline=False,
        )
        if (await self.bot.get_shared_api_tokens("activityhub")).get("client_secret"):
            secret = _("Saved")
        else:
            secret = _("Not set. Run `{}activityhub secret`.").format(prefix)
        embed.add_field(name=_("Client secret"), value=secret, inline=False)
        blocked = await self.config.disabled()
        off = sum(1 for key in self.registry.games if key in blocked)
        embed.add_field(
            name=_("Activities"),
            value=_("{} installed, {} turned off for every server. `{}activityhub games` lists them.").format(
                len(self.registry.games), off, prefix
            ),
            inline=False,
        )
        embed.add_field(
            name=_("Setting it up"),
            value=_("`{}activityhub setup` walks through every step.").format(prefix),
            inline=False,
        )
        await ctx.send(embed=embed)

    @activityhub_group.command(name="setup", aliases=["setuphelp"])
    @commands.bot_has_permissions(embed_links=True)
    async def setup_guide(self, ctx: commands.Context):
        """
        Walk through the whole setup, step by step

        Covers the Developer Portal, the client secret, and giving the web server a public HTTPS address with
        Cloudflare Tunnel, Caddy or nginx. The steps use this bot's own address.
        """
        has_secret = bool((await self.bot.get_shared_api_tokens("activityhub")).get("client_secret"))
        pages = setup_pages(
            prefix=ctx.clean_prefix,
            host=await self.config.host(),
            port=await self.config.port(),
            running=self.server.running,
            has_secret=has_secret,
            app_id=self.bot.application_id,
            color=await ctx.embed_color(),
        )
        await DynamicMenu(ctx, pages).refresh()

    @activityhub_group.command(name="secret")
    async def set_secret(self, ctx: commands.Context):
        """
        Set the client secret used to log players in

        Find it in the Discord Developer Portal, under this bot's OAuth2 page.
        """
        await SetSecretView(self, ctx).start()

    @activityhub_group.command(name="check")
    async def check_setup(self, ctx: commands.Context, public_host: str | None = None):
        """
        Check every setup step and say which one is missing

        Tests the URL mapping through Discord's own proxy, the way players load the activities.
        `public_host` is optional: the address your tunnel or proxy serves, like `games.example.com`. When given, the
        bot also tests it directly and says why it can't reach it.
        """
        async with ctx.typing():
            results = await run_checks(self, public_host, ctx.clean_prefix)
        lines = [f"{ICONS[status]} {text}" for status, text in results]
        for page in pagify("\n".join(lines)):
            await ctx.send(page)

    @activityhub_group.command(name="games")
    async def list_games(self, ctx: commands.Context):
        """List the installed activities with the Discord scopes each asks for, and any game cog that was refused"""
        games = sorted(self.registry.games.values(), key=lambda game: game.key)
        blocked = await self.config.disabled()
        lines = []
        for game in games:
            line = f"{game.key}: {game.name} ({game.cog.qualified_name})"
            if game.key in blocked:
                line += _(" [turned off]")
            # Every game's scopes go into one login, so this is how the owner finds the game behind a bad one
            if game.scopes:
                line += _(" scopes: {}").format(", ".join(game.scopes))
            lines.append(line)
        if not lines:
            lines = [_("No activities installed yet.")]
        if self.registry.failed:
            lines += ["", _("Refused:")]
            lines += [f"{name}: {reason}" for name, (cog, reason) in sorted(self.registry.failed.items())]
        for page in pagify("\n".join(lines), page_length=1900):
            await ctx.send(box(page))
