import json
import logging
import math
import typing as t
from contextlib import suppress
from datetime import datetime

import discord
import orjson
from pydantic import ValidationError
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, pagify, text_to_file

from ..abc import MixinMeta
from ..common import utils
from ..common.models import DB, GuildSettings
from ..views.dynamic_menu import DynamicMenu

_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.commands.data")


@cog_i18n(_)
class DataAdmin(MixinMeta):
    @commands.group(name="leveldata", aliases=["lvldata", "ldata"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def lvldata(self, ctx: commands.Context):
        """Admin Only Data Commands"""

    @lvldata.command(name="cleanup")
    async def cleanup_data(self, ctx: commands.Context):
        """Cleanup the database

        Performs the following actions:
        - Delete data for users no longer in the server
        - Removes channels and roles that no longer exist
        """
        conf = self.db.get_conf(ctx.guild)
        txt = ""
        pruned = 0
        for user_id in list(conf.users.keys()):
            member = ctx.guild.get_member(user_id)
            if not member:
                del conf.users[user_id]
                pruned += 1
                continue
            if member.bot and self.db.ignore_bots:
                del conf.users[user_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} users from the database\n").format(pruned)
        pruned = 0
        for user_id in list(conf.users_weekly.keys()):
            if not ctx.guild.get_member(user_id):
                del conf.users_weekly[user_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} users from the weekly database\n").format(pruned)
        pruned = 0
        for level in list(conf.levelroles.keys()):
            if not ctx.guild.get_role(conf.levelroles[level]):
                del conf.levelroles[level]
                pruned += 1
        if pruned:
            txt += _("Pruned {} level roles from the database\n").format(pruned)
        pruned = 0
        for role_id in list(conf.role_groups.keys()):
            if not ctx.guild.get_role(role_id):
                del conf.role_groups[role_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} role groups from the database\n").format(pruned)
        pruned = 0
        for channel_id in list(conf.ignoredchannels):
            if not ctx.guild.get_channel(channel_id):
                conf.ignoredchannels.remove(channel_id)
                pruned += 1
        if pruned:
            txt += _("Pruned {} ignored channels from the database\n").format(pruned)
        pruned = 0
        for role_id in list(conf.ignoredroles):
            if not ctx.guild.get_role(role_id):
                conf.ignoredroles.remove(role_id)
                pruned += 1
        if pruned:
            txt += _("Pruned {} ignored roles from the database\n").format(pruned)
        pruned = 0
        for role_id in list(conf.rolebonus.msg.keys()):
            if not ctx.guild.get_role(role_id):
                del conf.rolebonus.msg[role_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} role bonuses from the database\n").format(pruned)
        pruned = 0
        for role_id in list(conf.rolebonus.voice.keys()):
            if not ctx.guild.get_role(role_id):
                del conf.rolebonus.voice[role_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} voice role bonuses from the database\n").format(pruned)
        pruned = 0
        for channel_id in list(conf.channelbonus.msg.keys()):
            if not ctx.guild.get_channel(channel_id):
                del conf.channelbonus.msg[channel_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} channel bonuses from the database\n").format(pruned)
        pruned = 0
        for channel_id in list(conf.channelbonus.voice.keys()):
            if not ctx.guild.get_channel(channel_id):
                del conf.channelbonus.voice[channel_id]
                pruned += 1
        if pruned:
            txt += _("Pruned {} voice channel bonuses from the database\n").format(pruned)
        if not txt:
            await ctx.send(_("No data to prune!"))
        self.save()

    @lvldata.command(name="resetglobal")
    @commands.is_owner()
    async def reset_global(self, ctx: commands.Context):
        """Reset user data for all servers"""
        msg = await ctx.send(_("This will reset all user data for all servers. Are you sure?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Reset cancelled!"))
        for guild_id in list(self.db.configs.keys()):
            self.db.configs[guild_id].users = {}
            self.db.configs[guild_id].users_weekly = {}
        self.save()
        await msg.edit(content=_("Global data reset!"))

    @lvldata.command(name="reset")
    async def reset_user(self, ctx: commands.Context):
        """Reset all user data in this server"""
        msg = await ctx.send(_("This will reset all user data for this server. Are you sure?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Reset cancelled!"))
        conf = self.db.get_conf(ctx.guild)
        conf.users = {}
        conf.users_weekly = {}
        self.save()
        await msg.edit(content=_("Server data reset!"))

    @lvldata.command(name="resetcog")
    @commands.is_owner()
    async def reset_cog(self, ctx: commands.Context):
        """Reset the ENTIRE cog's data"""
        msg = await ctx.send(_("This will reset all data for this cog. Are you sure?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Reset cancelled!"))
        self.db = DB()
        self.save()
        await msg.edit(content=_("Cog data reset!"))

    @lvldata.command(name="backupcog")
    @commands.is_owner()
    @commands.bot_has_permissions(attach_files=True)
    async def backup_cog(self, ctx: commands.Context):
        """Backup the cog's data"""
        dump = self.db.dumpjson(pretty=True)
        now = datetime.now().strftime("%m-%d-%Y-%H-%M-%S")
        filename = f"LevelUp {now}.json"
        file = text_to_file(dump, filename=filename)
        await ctx.send(file=file)

    @lvldata.command(name="backup")
    async def backup_server(self, ctx: commands.Context):
        """Backup this server's data"""
        server_name = ctx.guild.name
        # Make sure the server name is safe for a filename
        server_name = "".join([c for c in server_name if c.isalnum() or c in " -_"])
        conf = self.db.get_conf(ctx.guild)
        dump = conf.dumpjson(pretty=True)
        now = datetime.now().strftime("%m-%d-%Y-%H-%M-%S")
        filename = f"LevelUp {server_name} {now}.json"
        file = text_to_file(dump, filename=filename)
        await ctx.send(file=file)

    @lvldata.command(name="restore")
    async def restore_server(self, ctx: commands.Context):
        """Restore this server's data"""
        attachments = utils.get_attachments(ctx)
        if not attachments:
            return await ctx.send(_("Please attach a backup file to the command message"))
        att = attachments[0]
        if not att.filename.endswith(".json"):
            return await ctx.send(_("Backup file must be a JSON file"))
        try:
            conf = GuildSettings.loadjson(await att.read())
        except ValidationError as e:
            pages = [f"Errors\n{box(i, lang='json')}" for i in pagify(e.json(indent=2), page_length=1900)]
            await ctx.send(_("Failed to restore data!"))
            await DynamicMenu(ctx, pages).refresh()
            return
        self.db.configs[ctx.guild.id] = conf
        self.save()
        await ctx.send(_("Server data restored!"))

    @lvldata.command(name="restorecog")
    @commands.is_owner()
    async def restore_cog(self, ctx: commands.Context):
        """Restore the cog's data"""
        attachments = utils.get_attachments(ctx)
        if not attachments:
            return await ctx.send(_("Please attach a backup file to the command message"))
        att = attachments[0]
        if not att.filename.endswith(".json"):
            return await ctx.send(_("Backup file must be a JSON file"))
        try:
            self.db = DB.loadjson(await att.read())
        except ValidationError as e:
            pages = [f"Errors\n{box(i, lang='json')}" for i in pagify(e.json(indent=2), page_length=1900)]
            await ctx.send(_("Failed to restore data!"))
            await DynamicMenu(ctx, pages).refresh()
            return
        self.save()
        await ctx.send(_("Cog data restored!"))

    @lvldata.command(name="importamari")
    @commands.guildowner()
    async def import_amari_data(
        self,
        ctx: commands.Context,
        import_by: t.Literal["level", "exp"],
        replace: bool,
        api_key: str,
        all_users: bool,
    ):
        """Import levels and exp from AmariBot
        **Arguments**
        ➣ `import_by` - Import by level or exp
        • If `level`, it will import their level and calculate exp from that.
        • If `exp`, it will import their exp directly and calculate level from that.
        ➣ `replace` - Replace existing data (True/False)
        • If True, it will replace existing data.
        ➣ `api_key` - Your [AmariBot API key](https://docs.google.com/forms/d/e/1FAIpQLScQDCsIqaTb1QR9BfzbeohlUJYA3Etwr-iSb0CRKbgjA-fq7Q/viewform?usp=send_form)
        ➣ `all_users` - Import all users regardless of if they're in the server (True/False)
        """
        with suppress(discord.HTTPException):
            await ctx.message.delete()
        msg = await ctx.send(_("Are you sure you want to import data from Amari bot's API?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Import cancelled!"))
        await msg.edit(content=_("Fetching AmariBot leaderboard data, this could take a while..."))
        # player_schema = {
        #     "id": int,
        #     "level": int,
        #     "exp": int,
        #     "weeklyExp": int,
        #     "username": str,
        # }
        players: t.List[t.Dict[str, t.Union[int, str]]] = []
        pages = math.ceil(len(ctx.guild.members) / 1000)
        failed_pages = 0
        async with ctx.typing():
            for i in range(pages):
                try:
                    data, status = await utils.fetch_amari_payload(ctx.guild.id, i, api_key)
                except Exception as e:
                    log.warning(
                        f"Failed to import page {i} of AmariBot leaderboard data in {ctx.guild}",
                        exc_info=e,
                    )
                    await ctx.send(f"Failed to import page {i} of AmariBot leaderboard data: {e}")
                    failed_pages += 1
                    if isinstance(e, json.JSONDecodeError):
                        await msg.edit(content=_("AmariBot is rate limiting too heavily! Import Failed!"))
                        return
                    continue
                error_msg = data.get("error", None)
                if status == 501:
                    # No more users
                    break
                if status != 200:
                    if error_msg:
                        return await ctx.send(error_msg)
                    else:
                        return await ctx.send(_("No data found!"))
                player_data = data.get("data")
                if not player_data:
                    break
                players.extend(player_data)
        if failed_pages:
            await ctx.send(
                _("{} pages failed to fetch from AmariBot api, check logs for more info").format(str(failed_pages))
            )
        if not players:
            return await ctx.send(_("No leaderboard data found!"))
        await msg.edit(content=_("Data retrieved, importing..."))
        conf = self.db.get_conf(ctx.guild)
        imported = 0
        failed = 0
        async with ctx.typing():
            for player in players:
                uid = player["id"]
                xp = player["exp"]
                level = player["level"]
                weekly_xp = player["weeklyExp"]
                member = ctx.guild.get_member(int(uid))
                if not member and not all_users:
                    failed += 1
                    continue
                profile = conf.get_profile(int(uid))

                weekly = conf.get_weekly_profile(int(uid)) if conf.weeklysettings.on else None

                if replace:
                    if import_by == "level":
                        profile.level = level
                        profile.xp = conf.algorithm.get_xp(level)
                    else:
                        profile.xp = xp
                        profile.level = conf.algorithm.get_level(xp)

                    if weekly:
                        weekly.xp = weekly_xp
                else:
                    if import_by == "level":
                        if level:
                            profile.level += level
                            profile.xp = conf.algorithm.get_xp(profile.level)
                    else:
                        if xp:
                            profile.xp += xp
                            profile.level = conf.algorithm.get_level(profile.xp)

                    if weekly:
                        weekly.xp += weekly_xp

                imported += 1

        if not imported and not failed:
            await msg.edit(content=_("No AmariBot stats were found"))
        else:
            txt = _("Imported {} User(s)").format(str(imported))
            if failed:
                txt += _(" ({} skipped since they are no longer in the discord)").format(str(failed))
            await msg.edit(content=txt)
            await ctx.tick()
            self.save()

    @lvldata.command(name="importfixator")
    @commands.is_owner()
    async def import_from_fixator(self, ctx: commands.Context):
        """
        Import data from Fixator's Leveler cog

        This will overwrite existing LevelUp level data and stars
        It will also import XP range level roles, and ignored channels

        *Obviously you will need MongoDB running while you run this command*
        """
        path = self.cog_path / "Leveler" / "settings.json"
        if not path.exists():
            return await ctx.send(_("No config found for Fixator's Leveler cog!"))
        data = orjson.loads(path.read_text())
        # Get the first key in the dict
        # Usually 78008101945374987542543513523680608657
        config_id = list(data.keys())[0]
        data = data[config_id]
        default_mongo_config = {
            "host": "localhost",
            "port": 27017,
            "username": None,
            "password": None,
            "db_name": "leveler",
        }
        mongo_config = data.get("MONGODB", default_mongo_config)
        global_config = data["GLOBAL"]
        guild_config = data["GUILD"]
        # If leveler is installed then libs should import fine
        try:
            from motor.motor_asyncio import AsyncIOMotorClient  # type: ignore
            from pymongo import errors as mongoerrors  # type: ignore
        except Exception as e:
            log.warning(f"pymongo Import Error: {e}")
            txt = _(
                "Failed to import `pymongo` and `motor` libraries. Run `{}pipinstall pymongo` and `{}pipinstall motor`"
            ).format(ctx.clean_prefix, ctx.clean_prefix)
            return await ctx.send(txt)

        msg = await ctx.send(_("Are you sure you want to import data from Fixator's Leveler cog?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Import cancelled!"))
        await msg.edit(content=_("Importing data..."))

        try:
            client = AsyncIOMotorClient(**{k: v for k, v in mongo_config.items() if k != "db_name"})
            await client.server_info()
            db = client[mongo_config["db_name"]]
        except (
            mongoerrors.ServerSelectionTimeoutError,
            mongoerrors.ConfigurationError,
            mongoerrors.OperationFailure,
        ) as e:
            log.error(f"Failed to connect to MongoDB: {e}")
            return await ctx.send(_("Failed to connect to MongoDB. Check your connection and try again."))

        imported = 0
        async with ctx.typing():
            min_message_length = global_config.get("message_length", 0)
            mention = global_config.get("mention", False)
            xp_range = global_config.get("xp", [1, 5])
            for guild in self.bot.guilds:
                guild_id = str(guild.id)
                conf = self.db.get_conf(guild)
                conf.min_length = min_message_length
                conf.mention = mention
                conf.xp_range = xp_range
                conf.ignoredchannels = guild_config.get(guild_id, {}).get("ignored_channels", [])

                if server_roles := await db.roles.find_one({"guild_id": guild_id}):
                    for rolename, data in server_roles["roles"].items():
                        role = guild.get_role(int(rolename))
                        if not role:
                            continue
                        conf.levelroles[int(data["level"])] = role.id
                for user in guild.members:
                    user_id = str(user.id)
                    try:
                        userinfo = await db.users.find_one({"user_id": user_id})
                    except Exception as e:
                        log.info(f"No data found for {user_id}: {e}")
                        continue
                    if not userinfo:
                        continue
                    profile = conf.get_profile(user)
                    if guild_id in userinfo["servers"]:
                        profile.level = userinfo["servers"][guild_id]["level"]
                        profile.xp = conf.algorithm.get_xp(profile.level)

                    profile.stars = int(userinfo["rep"]) if userinfo["rep"] else 0
                    imported += 1

            if not imported:
                return await msg.edit(content=_("There was no data to import!"))

            self.save()
            await msg.edit(content=_("Imported data for {} users from Fixator's Leveler cog!").format(imported))

    @lvldata.command(name="importmalarne")
    @commands.is_owner()
    async def import_from_malarne(
        self,
        ctx: commands.Context,
        import_by: t.Literal["level", "exp"],
        replace: bool,
        all_users: bool,
    ):
        """Import levels and exp from Malarne's Leveler cog

        **Arguments**
        ➣ `import_by` - Import by level or exp
        • If `level`, it will import their level and calculate exp from that.
        • If `exp`, it will import their exp directly and calculate level from that.
        ➣ `replace` - Replace existing data (True/False)
        • If True, it will replace existing data.
        ➣ `all_users` - Import all users regardless of if they're in the server (True/False)
        """
        path = self.cog_path / "UserProfile" / "settings.json"
        if not path.exists():
            return await ctx.send(_("No config found for Malarne's Leveler cog!"))

        msg = await ctx.send(_("Are you sure you want to import data from Malarne's Leveler cog?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Import cancelled!"))
        await msg.edit(content=_("Fetching Mee6 leaderboard data, this could take a while..."))

        data = orjson.loads(path.read_text())["1099710897114110101"]["MEMBER"]
        imported = 0
        async with ctx.typing():
            for guild_id, profiles in data.items():
                guild = self.bot.get_guild(int(guild_id))
                if not guild and not all_users:
                    continue
                conf = self.db.get_conf(int(guild_id))
                for user_id, data in profiles.items():
                    user = guild.get_member(int(user_id)) if guild else None
                    if not user and not all_users:
                        continue
                    level = data.get("level", 0)
                    xp = data.get("exp", 0)
                    if not level and not xp:
                        continue
                    profile = conf.get_profile(int(user_id))
                    if replace:
                        if import_by == "level" and level:
                            profile.level = level
                            profile.xp = conf.algorithm.get_xp(level)
                        elif xp:
                            profile.xp = xp
                            profile.level = conf.algorithm.get_level(xp)
                    else:
                        if import_by == "level" and level:
                            profile.level += level
                            profile.xp = conf.algorithm.get_xp(profile.level)
                        elif xp:
                            profile.xp += xp
                            profile.level = conf.algorithm.get_level(profile.xp)
                    imported += 1
        if not imported:
            return await ctx.send(_("There were no profiles to import"))
        txt = _("Imported {} profile(s)").format(imported)
        await ctx.send(txt)
        self.save()

    @lvldata.command(name="importmee6")
    @commands.guildowner()
    async def import_from_mee6(
        self,
        ctx: commands.Context,
        import_by: t.Literal["level", "exp"],
        replace: bool,
        include_settings: bool,
        all_users: bool,
    ):
        """Import levels and exp from MEE6

        **Arguments**
        ➣ `import_by` - Import by level or exp
        • If `level`, it will import their level and calculate exp from that.
        • If `exp`, it will import their exp directly and calculate level from that.
        ➣ `replace` - Replace existing data (True/False)
        ➣ `include_settings` - Include MEE6 settings (True/False)
        ➣ `all_users` - Import all users regardless of if they're in the server (True/False)
        """
        msg = await ctx.send(_("Are you sure you want to import data from Mee6?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Import cancelled!"))
        await msg.edit(content=_("Fetching Mee6 leaderboard data, this could take a while..."))

        pages = math.ceil(len(ctx.guild.members) / 1000)
        # player_schema = {"id": int, "exp": int}
        players: t.List[t.Dict[str, t.Union[int, str]]] = []
        failed_pages = 0
        settings_imported = False
        conf = self.db.get_conf(ctx.guild)

        async with ctx.typing():
            for i in range(pages):
                try:
                    data, status = await utils.fetch_mee6_payload(ctx.guild.id, i)
                except Exception as e:
                    log.warning(
                        f"Failed to import page {i} of Mee6 leaderboard data in {ctx.guild}",
                        exc_info=e,
                    )
                    await ctx.send(f"Failed to import page {i} of Mee6 leaderboard data: {e}")
                    failed_pages += 1
                    if isinstance(e, json.JSONDecodeError):
                        await msg.edit(content=_("Mee6 is rate limiting too heavily! Import Failed!"))
                        return
                    continue

                error = data.get("error", {})
                error_msg = error.get("message", None)
                if status != 200:
                    if status == 401:
                        return await ctx.send(_("Your leaderboard needs to be set to public!"))
                    elif error_msg:
                        return await ctx.send(error_msg)
                    else:
                        return await ctx.send(_("No data found!"))

                if include_settings and not settings_imported:
                    settings_imported = True
                    if xp_rate := data.get("xp_rate"):
                        conf.algorithm.base = round(xp_rate * 100)
                    if xp_per_message := data.get("xp_per_message"):
                        conf.xp = xp_per_message
                    if role_rewards := data.get("role_rewards"):
                        for entry in role_rewards:
                            role_id = int(entry["role_id"])
                            if not ctx.guild.get_role(role_id):
                                continue
                            conf.levelroles[int(entry["rank"])] = role_id
                    await ctx.send("Settings imported!")
                player_data = data.get("players")
                if not player_data:
                    break

                players.extend(player_data)
        if failed_pages:
            await ctx.send(
                _("{} pages failed to fetch from mee6 api, check logs for more info").format(str(failed_pages))
            )
        if not players:
            return await ctx.send(_("No leaderboard data found!"))

        await msg.edit(content=_("Data retrieved, importing..."))
        imported = 0
        failed = 0
        async with ctx.typing():
            for user in players:
                uid = str(user["id"])
                lvl = int(user["level"])
                xp = float(user["xp"])
                member = ctx.guild.get_member(int(uid))
                if not member and not all_users:
                    failed += 1
                    continue
                if replace:
                    if import_by == "level":
                        profile = conf.get_profile(int(uid))
                        profile.level = lvl
                        profile.xp = conf.algorithm.get_xp(lvl)
                    else:
                        profile = conf.get_profile(int(uid))
                        profile.xp = xp
                        profile.level = conf.algorithm.get_level(xp)
                else:
                    if import_by == "level":
                        profile = conf.get_profile(int(uid))
                        profile.level += lvl
                        profile.xp = conf.algorithm.get_xp(profile.level)
                    else:
                        profile = conf.get_profile(int(uid))
                        profile.xp += xp
                        profile.level = conf.algorithm.get_level(profile.xp)
                imported += 1
        if not imported and not failed:
            await msg.edit(content=_("No MEE6 stats were found"))
        else:
            txt = _("Imported {} User(s)").format(str(imported))
            if failed:
                txt += _(" ({} skipped since they are no longer in the discord)").format(str(failed))
            await msg.edit(content=txt)
            await ctx.tick()
            self.save()

    @lvldata.command(name="importpolaris")
    @commands.guildowner()
    async def import_from_polaris(
        self,
        ctx: commands.Context,
        replace: bool,
        include_settings: bool,
        all_users: bool,
    ):
        """
        Import levels and exp from Polaris

        **Make sure your guild's leaderboard is public!**

        **Arguments**
        ➣ `replace` - Replace existing data (True/False)
        ➣ `include_settings` - Include Polaris settings (True/False)
        ➣ `all_users` - Import all users regardless of if they're in the server (True/False)

        [Polaris](https://gdcolon.com/polaris/)
        """
        msg = await ctx.send(_("Are you sure you want to import data from Polaris?"))
        yes = await utils.confirm_msg(ctx)
        if not yes:
            return await msg.edit(content=_("Import cancelled!"))
        await msg.edit(content=_("Fetching Polaris leaderboard data, this could take a while..."))

        # player_schema = {"id": int, "exp": int}
        players: t.List[t.Dict[str, t.Union[int, str]]] = []
        failed_pages = 0
        settings_imported = False
        conf = self.db.get_conf(ctx.guild)
        async with ctx.typing():
            for page in range(10):
                try:
                    data, status = await utils.fetch_polaris_payload(ctx.guild.id, page)
                except Exception as e:
                    log.warning(
                        f"Failed to import page {page} of Polaris leaderboard data in {ctx.guild}",
                        exc_info=e,
                    )
                    await ctx.send(f"Failed to import page {page} of Polaris leaderboard data: {e}")
                    failed_pages += 1
                    if isinstance(e, json.JSONDecodeError):
                        await msg.edit(content=_("Polaris is rate limiting too heavily! Import Failed!"))
                        return
                    continue
                error = data.get("error", {})
                error_msg = error.get("message", None)
                if status != 200:
                    if status == 401:
                        return await ctx.send(_("Your leaderboard needs to be set to public!"))
                    elif error_msg:
                        return await ctx.send(error_msg)
                    else:
                        return await ctx.send(_("No data found!"))

                if include_settings and not settings_imported:
                    settings_imported = True
                    if settings := data.get("settings"):
                        if gain := settings.get("gain"):
                            conf.xp = [gain["min"], gain["max"]]
                            conf.cooldown = gain["time"]
                        if curve := settings.get("curve"):
                            # The cubic curve doesn't translate to quadratic easily, so we won't import this
                            # cubed = curve["3"]
                            # squared = curve["2"]
                            # base = curve["1"]
                            conf.algorithm.base = curve["1"]

                    if role_rewards := data.get("rewards"):
                        for entry in role_rewards:
                            role = ctx.guild.get_role(int(entry["id"]))
                            if not role:
                                continue
                            conf.levelroles[int(entry["level"])] = role.id
                    await ctx.send(_("Settings Imported!"))

                player_data = data.get("leaderboard")
                if not player_data:
                    break

                players.extend(player_data)

        if failed_pages:
            await ctx.send(
                _("{} pages failed to fetch from Polaris api, check logs for more info").format(str(failed_pages))
            )
        if not players:
            return await ctx.send(_("No leaderboard data found!"))

        await msg.edit(content=_("Data retrieved, importing..."))
        imported = 0
        failed = 0
        async with ctx.typing():
            for user in players:
                uid = str(user["id"])
                xp = float(user["xp"])
                member = ctx.guild.get_member(int(user["id"]))
                if not member and not all_users:
                    failed += 1
                    continue
                profile = conf.get_profile(int(uid))
                if replace:
                    profile.xp = xp
                    profile.level = conf.algorithm.get_level(xp)
                elif xp:
                    profile.xp += xp
                    profile.level = conf.algorithm.get_level(profile.xp)
                imported += 1

        if not imported and not failed:
            await msg.edit(content=_("No Polaris stats were found"))
        else:
            txt = _("Imported {} User(s)").format(str(imported))
            if failed:
                txt += _(" ({} skipped since they are no longer in the discord)").format(str(failed))
            await msg.edit(content=txt)
            await ctx.tick()
            self.save()
