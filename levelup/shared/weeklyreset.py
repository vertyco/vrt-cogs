import logging
import typing as t
from contextlib import suppress

import discord
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import humanize_number

from ..abc import MixinMeta
from ..common import utils
from ..common.models import ProfileWeekly

log = logging.getLogger("red.vrt.levelup.shared.weeklyreset")
_ = Translator("LevelUp", __file__)


class WeeklyReset(MixinMeta):
    async def reset_weekly(self, guild: discord.Guild, ctx: commands.Context = None) -> None:
        """Announce and reset weekly stats

        Args:
            guild (discord.Guild): The guild where the weekly stats are being reset.
            ctx (commands.Context, optional): Sends the announcement embed in the current channel. Defaults to None.
        """
        if ctx:
            await ctx.send(_("Weekly stats have been reset."))
        conf = self.db.get_conf(guild)
        if not conf.users_weekly:
            if ctx:
                await ctx.send(_("There are no users in the weekly data yet"))
            conf.weeklysettings.refresh()
            self.save()
            return
        valid_users: t.Dict[discord.Member, ProfileWeekly] = {}
        for user_id, stats in conf.users_weekly.items():
            user = guild.get_member(user_id)
            if user and stats.xp > 0:
                valid_users[user] = stats
        if not valid_users:
            if ctx:
                await ctx.send(_("There are no users with XP in the weekly data yet"))
            conf.weeklysettings.refresh()
            self.save()
            return

        channel = guild.get_channel(conf.weeklysettings.channel) if conf.weeklysettings.channel else None

        total_xp = 0
        total_messages = 0
        total_voicetime = 0
        total_stars = 0
        for stats in valid_users.values():
            total_xp += stats.xp
            total_messages += stats.messages
            total_voicetime += stats.voice
            total_stars += stats.stars
        total_xp = humanize_number(int(total_xp))
        total_messages = humanize_number(total_messages)
        total_voicetime = utils.humanize_delta(total_voicetime)
        total_stars = humanize_number(total_stars)

        embed = discord.Embed(
            description=_(
                "`Total Exp:       `{}\n"
                "`Total Messages:  `{}\n"
                "`Total Stars:     `{}\n"
                "`Total Voicetime: `{}\n"
                "`Next Reset:      `{}"
            ).format(
                total_xp,
                total_messages,
                total_stars,
                total_voicetime,
                f"<t:{conf.weeklysettings.next_reset}:R>",
            ),
            color=await self.bot.get_embed_color(channel or ctx),
        )
        embed.set_author(
            name=_("Top Weekly Exp Earners"),
            icon_url=guild.icon,
        )
        embed.set_thumbnail(url=guild.icon)
        place_emojis = ["🥇", "🥈", "🥉"]
        sorted_users = sorted(valid_users.items(), key=lambda x: x[1].xp, reverse=True)
        top_user_ids = []
        for idx, (user, stats) in enumerate(sorted_users):
            place = idx + 1
            if place > conf.weeklysettings.count:
                break
            top_user_ids.append(user.id)
            position = place_emojis[idx] if idx < 3 else f"#{place}."
            embed.add_field(
                name=f"{position} {user.display_name}",
                value=_("`Experience: `{}\n" "`Messages:   `{}\n" "`Stars:      `{}\n" "`Voicetime:  `{}").format(
                    humanize_number(round(stats.xp)),
                    humanize_number(stats.messages),
                    humanize_number(stats.stars),
                    utils.humanize_delta(round(stats.voice)),
                ),
                inline=False,
            )
        if ctx:
            with suppress(discord.HTTPException):
                await ctx.send(embed=embed)
        elif channel:
            with suppress(discord.HTTPException):
                await channel.send(embed=embed)

        top = sorted_users[: conf.weeklysettings.count]
        if conf.weeklysettings.role_all:
            winners = [user[0] for user in top]
        else:
            winners = [top[0][0]]

        role = guild.get_role(conf.weeklysettings.role) if conf.weeklysettings.role else None
        if role:
            last_winners = [guild.get_member(uid) for uid in conf.weeklysettings.last_winners if guild.get_member(uid)]
            if conf.weeklysettings.remove:
                for last in last_winners:
                    if last in winners or role not in last.roles:
                        continue
                    try:
                        await last.remove_roles(role, reason=_("Weekly winner role removal"))
                    except discord.Forbidden:
                        log.warning(f"Missing permissions to apply role {role} to {last}")
                    except discord.HTTPException:
                        pass

            for winner in winners:
                if winner in last_winners or role in winner.roles:
                    # No need to add the role again
                    continue
                try:
                    await winner.add_roles(role, reason=_("Weekly winner role addition"))
                except discord.Forbidden:
                    log.warning(f"Missing permissions to apply role {role} to {winner}")
                except discord.HTTPException:
                    pass

        conf.weeklysettings.last_winners = [user.id for user in winners]
        if bonus := conf.weeklysettings.bonus:
            for uid in winners:
                profile = conf.get_profile(uid)
                profile.xp += bonus

        conf.weeklysettings.refresh()
        conf.users_weekly.clear()
        conf.weeklysettings.last_embed = embed.to_dict()
        self.save()
