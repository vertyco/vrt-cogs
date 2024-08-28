from redbot.core import commands

from ..abc import MixinMeta
from ..db.tables import Click, SavedView
from ..views.postgres_creds import SetConnectionView


class Admin(MixinMeta):
    @commands.group(name="clickerset", aliases=["cowclicker"])
    @commands.is_owner()
    async def clickerset(self, ctx: commands.Context):
        """Cow Clicker settings"""

    @clickerset.command(name="postgres")
    async def whosaltset_postgres(self, ctx: commands.Context):
        """Set the Postgres connection info"""
        await SetConnectionView(self, ctx).start()

    @clickerset.command(name="view")
    async def whosaltset_view(self, ctx: commands.Context):
        """View the Postgres connection info"""
        clicks = await Click.count()
        views = await SavedView.count()
        await ctx.send(f"Clicks: {clicks}, Menus saved: {views}")
