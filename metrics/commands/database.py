import asyncpg
import redbot_orm
from piccolo.engine.postgres import PostgresEngine
from redbot.core import commands
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, pagify
from redbot_orm.common import get_root

from ..abc import MixinMeta
from ..db.tables import ensure_db_connection
from ..views.postgres_creds import SetConnectionView


class DatabaseCommands(MixinMeta):
    @commands.group(name="metricsdb")
    @commands.is_owner()
    async def dbsetgroup(self, ctx: commands.Context):
        """Database Commands"""

    @dbsetgroup.command(name="postgres")
    async def dbsetgroup_postgres(self, ctx: commands.Context):
        """Set the Postgres connection info"""
        await SetConnectionView(self, ctx).start()

    @dbsetgroup.command(name="nukedb")
    @ensure_db_connection()
    async def dbsetgroup_nukedb(self, ctx: commands.Context, confirm: bool):
        """Delete the database for this cog and reinitialize it

        THIS CANNOT BE UNDONE!"""
        if not confirm:
            return await ctx.send(f"You must confirm this action with `{ctx.clean_prefix}metricsdb nukedb True`")
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            cogpath = cog_data_path(self) / "db.sqlite3"
            if cogpath.exists():
                cogpath.unlink()
                return await ctx.send("Deleted the sqlite database file. Reload the cog.")

            return await ctx.send(f"Postgres credentials not set! Use `{ctx.clean_prefix}metricsdb postgres` command!")
        if self.db and isinstance(self.db, PostgresEngine):
            tmp = self.db
            self.db = None
            tmp.pool.terminate()
        conn = None
        try:
            # Connect to the 'postgres' maintenance database to drop the target database
            config_copy = dict(config)
            config_copy["database"] = "postgres"
            try:
                conn = await asyncpg.connect(**config_copy)
            except asyncpg.InvalidPasswordError:
                return await ctx.send("Invalid password!")
            except asyncpg.InvalidCatalogNameError:
                return await ctx.send("Invalid database name!")
            except asyncpg.InvalidAuthorizationSpecificationError:
                return await ctx.send("Invalid user!")

            await conn.execute(f"DROP DATABASE IF EXISTS {get_root(self).stem};")
        finally:
            if conn:
                await conn.close()

        await ctx.send("Database has been nuked, please reload the cog.")

    @dbsetgroup.command(name="diagnose")
    async def dbsetgroup_diagnose(self, ctx: commands.Context):
        """Check the database connection"""
        config = await self.bot.get_shared_api_tokens("postgres")
        issues = await redbot_orm.diagnose_issues(self, config=config)
        for p in pagify(issues, page_length=1980):
            await ctx.send(box(p, lang="python"))
