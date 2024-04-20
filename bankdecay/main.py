import asyncio
import logging
import math
import typing as t
from datetime import datetime, timedelta
from io import StringIO

import discord
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import humanize_number, text_to_file

from .abc import CompositeMetaClass
from .commands.admin import Admin
from .common.listeners import Listeners
from .common.models import DB
from .common.scheduler import scheduler

log = logging.getLogger("red.vrt.bankdecay")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]

_ = Translator("BankDecay", __file__)
# redgettext -D main.py commands/admin.py --command-docstring


@cog_i18n(_)
class BankDecay(Admin, Listeners, commands.Cog, metaclass=CompositeMetaClass):
    """
    Economy decay!

    Periodically reduces users' red currency based on inactivity, encouraging engagement.
    Server admins can configure decay parameters, view settings, and manually trigger decay cycles.
    User activity is tracked via messages and reactions.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.3.11"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})

        self.db: DB = DB()
        self.saving = False

    async def cog_load(self) -> None:
        scheduler.start()
        scheduler.remove_all_jobs()
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        scheduler.remove_all_jobs()
        scheduler.shutdown(wait=False)

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        await self.start_jobs()

    async def start_jobs(self):
        kwargs = {
            "func": self.autodecay_guilds,
            "trigger": "cron",
            "minute": 0,
            "hour": 0,
            "id": "BankDecay.autodecay_guilds",
            "replace_existing": True,
            "misfire_grace_time": 3600,  # 1 hour grace time for missed job
        }
        # If it has been more than 24 hours since the last run, schedule it to run now
        if self.db.last_run is not None and (datetime.now() - self.db.last_run) > timedelta(hours=24):
            kwargs["next_run_time"] = datetime.now() + timedelta(seconds=5)

        # Schedule decay job
        scheduler.add_job(**kwargs)

    async def autodecay_guilds(self):
        if await bank.is_global():
            log.error("This cog cannot be used with a global bank!")
            return

        log.info("Running decay_guilds!")
        total_affected = 0
        total_decayed = 0
        for guild_id in self.db.configs.copy():
            guild = self.bot.get_guild(guild_id)
            if not guild:
                # Remove guids that the bot is no longer a part of
                del self.db.configs[guild_id]
                continue
            decayed = await self.decay_guild(guild)
            total_affected += len(decayed)
            total_decayed += sum(decayed.values())

        if total_affected or total_decayed:
            log.info(f"Decayed {total_affected} users balances for a total of {total_decayed} credits!")
        self.db.last_run = datetime.now()
        await self.save()

    async def decay_guild(self, guild: discord.Guild, check_only: bool = False) -> t.Dict[str, int]:
        now = datetime.now()
        conf = self.db.get_conf(guild)
        if not conf.enabled and not check_only:
            return {}

        _bank_members = await bank._config.all_members(guild)
        bank_members: t.Dict[int, int] = {int(k): v["balance"] for k, v in _bank_members.items()}

        # Decayed users: dict[username, amount]
        decayed: t.Dict[str, int] = {}
        uids = [i for i in conf.users]
        for user_id in uids:
            user = guild.get_member(user_id)
            if not user:
                # User no longer in guild
                continue

            if any(r.id in conf.ignored_roles for r in user.roles):
                # Don't decay user balances with roles in the ignore list
                continue

            last_active = conf.get_user(user).last_active

            delta = now - last_active
            if delta.days <= conf.inactive_days:
                continue

            bal = bank_members.get(user_id)
            # bal = await bank.get_balance(user)
            if not bal:
                continue

            credits_to_remove = math.ceil(bal * conf.percent_decay)
            new_bal = bal - credits_to_remove
            if not check_only:
                await bank.set_balance(user, new_bal)

            decayed[user.name] = credits_to_remove

        if check_only:
            return decayed

        conf.total_decayed += sum(decayed.values())
        log.info(f"Decayed guild {guild.name}.\nUsers decayed: {len(decayed)}\nTotal: {sum(decayed.values())}")

        log_channel = guild.get_channel(conf.log_channel)
        if not log_channel:
            return decayed
        if not log_channel.permissions_for(guild.me).embed_links:
            return decayed

        title = _("Bank Decay Cycle")
        if decayed:
            txt = _("- User Balances Decayed: {}\n- Total Amount Decayed: {}").format(
                f"`{humanize_number(len(decayed))}`", f"`{humanize_number(sum(decayed.values()))}`"
            )
            color = discord.Color.yellow()
        else:
            txt = _("No user balances were decayed during this cycle.")
            color = discord.Color.blue()

        embed = discord.Embed(
            title=title,
            description=txt,
            color=color,
            timestamp=datetime.now(),
        )
        # Create a text file with the list of users and how much they will lose
        buffer = StringIO()
        for user, amount in sorted(decayed.items(), key=lambda x: x[1], reverse=True):
            buffer.write(f"{user}: {amount}\n")

        file = text_to_file(buffer.getvalue(), filename="decay.txt")
        perms = [
            log_channel.permissions_for(guild.me).attach_files,
            log_channel.permissions_for(guild.me).embed_links,
        ]
        if not any(perms):
            return decayed

        try:
            if perms[0] and perms[1]:
                await log_channel.send(embed=embed, file=file)
            elif perms[1]:
                await log_channel.send(embed=embed)
        except Exception as e:
            log.error(f"Failed to send decay log to {log_channel.name} in {guild.name}", exc_info=e)

        return decayed

    async def save(self) -> None:
        if self.saving:
            return
        try:
            self.saving = True
            dump = self.db.model_dump(mode="json")
            await self.config.db.set(dump)
        except Exception as e:
            log.exception("Failed to save config", exc_info=e)
        finally:
            self.saving = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        """No data to delete"""
