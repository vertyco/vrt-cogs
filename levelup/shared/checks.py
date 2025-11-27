import logging
import bisect
import typing as t

import discord
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import warning
from redbot.core import commands

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.levelup.shared.checks")
_ = Translator("LevelUp", __file__)


class Checks(MixinMeta):
    def __init__(self):
        self.last_invoked: t.Dict[t.Tuple[int, str], float] = {}  # (member id, command) -> last usage time

    async def level_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return True
        member = ctx.author
        if isinstance(member, discord.User):
            return True
        conf = self.db.get_conf(member.guild)
        command = ctx.command.qualified_name
        if command not in conf.cmd_requirements:
            return True

        # allow help command
        if ctx.command.name == "help" or ctx.invoked_with == "help":
            return True

        # check bypasses
        bypass_roles = set([r.id for r in member.roles]) & set(conf.cmd_bypass_roles)
        if member.id in conf.cmd_bypass_member or len(bypass_roles) >= 1:
            return True

        profile = conf.get_profile(member)
        level = profile.level
        req_level = conf.cmd_requirements[command]
        if level < req_level:
            await ctx.reply(
                warning(f"You need level `{req_level}` to use `{ctx.command}`. (current level: {level})"),
                delete_after=30,
                mention_author=False,
            )
            raise commands.CheckFailure()
        return True

    async def cooldown_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return True
        member = ctx.author
        if isinstance(member, discord.User):
            return True
        conf = self.db.get_conf(member.guild)
        command = ctx.command.qualified_name
        if command not in conf.cmd_cooldowns:
            return True

        # check bypasses
        bypass_roles = set([r.id for r in member.roles]) & set(conf.cmd_bypass_roles)
        if member.id in conf.cmd_bypass_member or len(bypass_roles) >= 1:
            return True

        cooldowns = conf.cmd_cooldowns[command]
        levels = sorted(cooldowns.keys())
        profile = conf.get_profile(member)
        level = profile.level

        cooldown_level = bisect.bisect_left(levels, level)
        if cooldown_level == len(
            levels
        ):  # user has a higher level then all of the specified cooldowns, so no cooldown is applied
            return True
        cooldown = cooldowns[levels[cooldown_level]]

        key = (member.id, command)
        now = ctx.message.created_at.timestamp()
        last = self.last_invoked.get(key, 0)
        retry_after = last + cooldown - now

        if retry_after > 0:
            bucket_cooldown = commands.Cooldown(1, cooldown)
            raise commands.CommandOnCooldown(bucket_cooldown, retry_after, commands.BucketType.member)
        self.last_invoked[key] = now
        # override any built in cooldowns for the command
        ctx.command.reset_cooldown(ctx)

        return True
