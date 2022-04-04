# author: github.com/mikeshardmind
# Contact: discord: Sinbad#0001(<@78631113035100160>)| https://cogboard.red/u/Sinbad
#
# commissioned work for: https://cogboard.red/u/chnaski | <@107937406132420608>
# If this is public, thank them for releasing it.
from datetime import date, datetime
import pathlib
import re

import discord
from discord.ext import commands
from cogs.utils.dataIO import dataIO
from cogs.utils import checks

import typing
if typing.TYPE_CHECKING:
    from typing import List, Dict
    RoleSettings = Dict[str, int]


PATH = 'data/selectiveroleedit'

MEMBERS = 1
NAME = 2
COLOR = 4
MENTION = 8

MASS_MENTION_RE = re.compile(r"(@)(?=everyone|here)")

DATE_RES = [re.compile(p) for p in (
    r"(?x)(?P<y>(?:19|20)\d{2})(?P<m>1[012]|0\d)(?P<d>[012]\d|3[01])",
    r"(?x)(?P<y>(?:19|20)\d{2}) (-|/) (?P<m>1[012]|0?\d) \2 (?P<d>[012]?\d|3[01])",
    r"(?x)(?P<m>1[012]|0?\d) (/|-) (?P<d>[012]?\d|3[01]) \2 (?P<y>(?:19|20)\d{2})",
    r"(?x)(?P<m>1[012]|0\d) (?P<d>[012]\d|3[01]) (?P<y>(?:19|20)\d{2})"
)]


def has_set_role(ctx):
    try:
        srv = ctx.message.channel.server
    except Exception:
        return False

    rids = ctx.bot.get_cog("SelectiveRoleEdit").server_settings.get(srv.id, [])
    return any(
        idx in rids for idx in [r.id for r in ctx.message.author.roles]
    )


class SelectiveRoleEdit:

    __version__ = "2.2.0"

    def __init__(self, bot):
        self.bot = bot
        self.settings = None  # type: RoleSettings
        self.server_settings = None
        self.log_settings = None

        try:
            self.settings = dataIO.load_json(PATH + '/settings.json')
        except Exception:
            self.settings = {}

        try:
            self.server_settings = dataIO.load_json(PATH + '/server_settings.json')
        except Exception:
            self.server_settings = {}
        else:
            to_update = {}

            for k, v in self.server_settings.items():
                if not isinstance(v, list):
                    to_update[k] = [v]

            self.server_settings.update(to_update)
            self.save_settings()

        try:
            self.log_settings = dataIO.load_json(PATH + '/log_settings.json')
        except Exception:
            self.log_settings = {}

    def save_roles(self):
        dataIO.save_json(PATH + '/settings.json', self.settings)

    def save_log_settings(self):
        dataIO.save_json(PATH + '/log_settings.json', self.log_settings)

    def op_valid_on_role(self, role: discord.Role, op: int) -> bool:
        return bool(self.settings.get(role.id, 0) & op)

    def rem_op(self, role: discord.Role, op: int):
        try:
            self.settings[role.id] ^= op
        except KeyError:
            pass  # still default 0, skip write.
        else:
            self.save_roles()

    def add_op(self, role: discord.Role, op: int):
        self.settings[role.id] = self.settings.get(role.id, 0) | op
        self.save_roles()

    def save_settings(self):
        dataIO.save_json(PATH + '/server_settings.json', self.server_settings)

    @staticmethod
    def _parse_dob(instr: str) -> typing.Optional[date]:
        if not instr:
            return

        for pattern in DATE_RES:
            match = pattern.match(instr)

            if match:
                data = match.groupdict()
                return date(int(data["y"]), int(data["m"]), int(data["d"]))

    async def log_event(self, ctx, member: discord.Member, title: str, dob: date):
        channel_id = self.log_settings.get(ctx.message.server.id)
        channel = self.bot.get_channel(channel_id)

        if not channel:
            return

        body = '\n'.join((
            "Member: " + member.mention,
            "Date of Birth: " + dob.strftime("%m/%d/%Y"),
            "Verified by: " + ctx.message.author.mention
        ))
        em = discord.Embed(title=title, timestamp=datetime.now(), description=body)
        return await self.bot.send_message(channel, embed=em)

    @checks.serverowner_or_permissions(administrator=True)
    @commands.group(name="sreset", pass_context=True, no_pm=True)
    async def sreset(self, ctx: commands.Context):
        """
        Selective Role Edit settings
        """
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @sreset.command(name="modrole", pass_context=True)
    async def modrole(self, ctx, *roles: discord.Role):
        """
        Sets the role(s) required to use the restricted role editing.

        Multiword roles require quotes.

        Removes existing setting.
        """
        server = ctx.message.server
        self.server_settings[server.id] = [r.id for r in roles]
        self.save_settings()

        if not roles:
            message = "Roles cleared."
        elif len(roles) == 1:
            message = "Role set to {}".format(roles[0].name)
        else:
            message = "Roles set to {}".format(", ".join([r.name for r in roles]))

        await self.bot.say(message)

    @sreset.command(pass_context=True)
    async def allowcolor(self, ctx, *, role: discord.Role):
        """
        Allow mods to edit the color of a role
        """
        self.add_op(role, COLOR)
        await self.bot.say("Color of role {0.name} changeable.".format(role))

    @sreset.command(pass_context=True)
    async def allowname(self, ctx, *, role: discord.Role):
        """
        Allow mods to edit the name of a role
        """
        self.add_op(role, NAME)
        await self.bot.say("Name of role {0.name} changeable.".format(role))

    @sreset.command(pass_context=True)
    async def allowmembers(self, ctx, *, role: discord.Role):
        """
        Allow mods to edit the members of a role
        """
        self.add_op(role, MEMBERS)
        await self.bot.say("Members of role {0.name} changeable.".format(role))

    @sreset.command(pass_context=True)
    async def allowmention(self, ctx, *, role: discord.Role):
        """
        Allow mods to edit the mention settings of a role
        """
        self.add_op(role, MENTION)
        await self.bot.say("Mention setting of role {0.name} now changeable.".format(role))

    @sreset.command(pass_context=True)
    async def denymention(self, ctx, *, role: discord.Role):
        """
        Allow mods to edit the mention settings of a role
        """
        self.rem_op(role, MENTION)
        await self.bot.say("Mention setting of role {0.name} not changeable.".format(role))

    @sreset.command(pass_context=True)
    async def denycolor(self, ctx, *, role: discord.Role):
        """
        Blocks editing the color of a role
        """
        self.rem_op(role, COLOR)
        await self.bot.say("Color of role {0.name} not changeable.".format(role))

    @sreset.command(pass_context=True)
    async def denyname(self, ctx, *, role: discord.Role):
        """
        Blocks editing the name of a role
        """
        self.rem_op(role, NAME)
        await self.bot.say("Name of role {0.name} not changeable.".format(role))

    @sreset.command(pass_context=True)
    async def denymembers(self, ctx, *, role: discord.Role):
        """
        Blocks editing the members of a role
        """
        self.rem_op(role, MEMBERS)
        await self.bot.say("Members of role {0.name} not changeable.".format(role))

    @sreset.command(pass_context=True)
    async def logchannel(self, ctx, *, channel: discord.Channel):
        """
        Sets the channel to send verify/auth logs to.
        """
        if channel is None:
            self.log_settings[ctx.message.server.id] = None
            await self.bot.say("Log channel disabled.")
        elif channel.type is not discord.ChannelType.text:
            await self.bot.say("Must be a text channel.")
        else:
            self.log_settings[ctx.message.server.id] = channel.id
            self.save_log_settings()
            await self.bot.say("Log channel set.")

    @commands.check(has_set_role)
    @commands.command(pass_context=True, no_pm=True)
    async def auth(self, ctx, user: discord.Member, *, dob_str: str = None):
        """
        Adds `authenticated` removes `locked`
        """
        server = ctx.message.channel.server
        auth = discord.utils.find(lambda r: r.name.lower() == 'authenticated', server.roles)
        locked = discord.utils.find(lambda r: r.name.lower() == 'locked', server.roles)
        muted = discord.utils.find(lambda r: r.name.lower() == 'muted', server.roles)
        roles = set(user.roles)
        roles.discard(locked)
        roles.discard(muted)
        roles.add(auth)

        if roles != set(user.roles):
            await self.bot.replace_roles(user, *roles)
            await self.bot.say("{} authenticated.".format(user.name))
        else:
            await self.bot.say("Already authenticated.")

        dob = self._parse_dob(dob_str)

        if dob:
            await self.log_event(ctx, user, "Member authenticated", dob)
        elif dob_str:
            await self.bot.say("Invalid DoB format.")

    @commands.check(has_set_role)
    @commands.command(pass_context=True, no_pm=True)
    async def vf21(self, ctx, user: discord.Member, *, dob_str: str = None):
        """
        Adds `21+` and `verified` removes `locked`
        """
        server = ctx.message.channel.server
        auth = discord.utils.find(lambda r: r.name.lower() == 'verified', server.roles)
        twentyone = discord.utils.find(lambda r: r.name.lower() == '21+', server.roles)
        ping = discord.utils.find(lambda r: r.name.lower() == 'no ping', server.roles)
        elevator = discord.utils.find(lambda r: r.name.lower() == 'elevator', server.roles)
        locked = discord.utils.find(lambda r: r.name.lower() == 'locked', server.roles)
        muted = discord.utils.find(lambda r: r.name.lower() == 'muted', server.roles)
        roles = set(user.roles)
        roles.discard(locked)
        roles.discard(muted)
        roles.add(auth)
        roles.add(twentyone)
        roles.add(ping)
        roles.add(elevator)

        if roles != set(user.roles):
            await self.bot.replace_roles(user, *roles)
            await self.bot.say("{} verified.".format(user.name))
        else:
            await self.bot.say("Already verified.")

        dob = self._parse_dob(dob_str)

        if dob:
            await self.log_event(ctx, user, "Age verified", dob)
        elif dob_str:
            await self.bot.say("Invalid DoB format.")

    @commands.check(has_set_role)
    @commands.command(pass_context=True, no_pm=True)
    async def vm21(self, ctx, user: discord.Member, *, dob_str: str = None):
        """
        Adds `21+` and `verified` removes `locked`
        """
        server = ctx.message.channel.server
        auth = discord.utils.find(lambda r: r.name.lower() == 'verified', server.roles)
        twentyone = discord.utils.find(lambda r: r.name.lower() == '21+', server.roles)
        locked = discord.utils.find(lambda r: r.name.lower() == 'locked', server.roles)
        muted = discord.utils.find(lambda r: r.name.lower() == 'muted', server.roles)
        roles = set(user.roles)
        roles.discard(locked)
        roles.discard(muted)
        roles.add(auth)
        roles.add(twentyone)

        if roles != set(user.roles):
            await self.bot.replace_roles(user, *roles)
            await self.bot.say("{} verified.".format(user.name))
        else:
            await self.bot.say("Already verified.")

        dob = self._parse_dob(dob_str)

        if dob:
            await self.log_event(ctx, user, "Age verified", dob)
        elif dob_str:
            await self.bot.say("Invalid DoB format.")

    @commands.check(has_set_role)
    @commands.command(pass_context=True, no_pm=True)
    async def vm(self, ctx, user: discord.Member, *, dob_str: str = None):
        """
        Adds `verified` removes `locked`
        """
        server = ctx.message.channel.server
        auth = discord.utils.find(lambda r: r.name.lower() == 'verified', server.roles)
        locked = discord.utils.find(lambda r: r.name.lower() == 'locked', server.roles)
        muted = discord.utils.find(lambda r: r.name.lower() == 'muted', server.roles)
        roles = set(user.roles)
        roles.discard(locked)
        roles.discard(muted)
        roles.add(auth)

        if roles != set(user.roles):
            await self.bot.replace_roles(user, *roles)
            await self.bot.say("{} verified.".format(user.name))
        else:
            await self.bot.say("Already verified.")

        dob = self._parse_dob(dob_str)

        if dob:
            await self.log_event(ctx, user, "Age verified", dob)
        elif dob_str:
            await self.bot.say("Invalid DoB format.")

    @commands.check(has_set_role)
    @commands.command(pass_context=True, no_pm=True)
    async def vf(self, ctx, user: discord.Member, *, dob_str: str = None):
        """
        Adds `verified` and `elevator` removes `locked`
        """
        server = ctx.message.channel.server
        auth = discord.utils.find(lambda r: r.name.lower() == 'verified', server.roles)
        elevator = discord.utils.find(lambda r: r.name.lower() == 'elevator', server.roles)
        ping = discord.utils.find(lambda r: r.name.lower() == 'no ping', server.roles)
        lobby = discord.utils.find(lambda r: r.name.lower() == 'lobby', server.roles)
        locked = discord.utils.find(lambda r: r.name.lower() == 'locked', server.roles)
        muted = discord.utils.find(lambda r: r.name.lower() == 'muted', server.roles)
        roles = set(user.roles)
        roles.discard(locked)
        roles.discard(muted)
        roles.discard(lobby)
        roles.add(auth)
        roles.add(ping)
        roles.add(elevator)

        if roles != set(user.roles):
            await self.bot.replace_roles(user, *roles)
            await self.bot.say("{} verified.".format(user.name))
        else:
            await self.bot.say("Already verified.")

        dob = self._parse_dob(dob_str)

        if dob:
            await self.log_event(ctx, user, "Age verified", dob)
        elif dob_str:
            await self.bot.say("Invalid DoB format.")

    @commands.check(has_set_role)
    @commands.group(pass_context=True, no_pm=True)
    async def srerole(self, ctx):
        """
        Commands for roles
        """
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @srerole.command(pass_context=True)
    async def give(self, ctx, member: discord.Member, *, role: discord.Role):
        """
        Gives a role to a member.

        Multi word names need quotes.
        """
        me = ctx.message.channel.server.me
        if role >= me.top_role or not me.server_permissions.manage_roles:
            return await self.bot.say("I can't do that.")

        if role >= ctx.message.author.top_role or not self.op_valid_on_role(role, MEMBERS):
            return await self.bot.say("You can't do that.")

        if role in member.roles:
            return await self.bot.say("They already have that role.")

        try:
            await self.bot.add_roles(member, role)
        except discord.DiscordException:
            return await self.bot.say("Something went wrong.")
        else:
            message = MASS_MENTION_RE.sub(
                "@\u200b",
                "Role {role.name} added to {user.name}".format(role=role, user=member)
            )
            await self.bot.say(message)

    @srerole.command(pass_context=True)
    async def remove(self, ctx, member: discord.Member, *, role: discord.Role):
        """
        Removes a role from a member.

        Multi word names need quotes.
        """
        me = ctx.message.channel.server.me
        if role >= me.top_role or not me.server_permissions.manage_roles:
            return await self.bot.say("I can't do that.")

        if role >= ctx.message.author.top_role or not self.op_valid_on_role(role, MEMBERS):
            return await self.bot.say("You can't do that.")

        if role not in member.roles:
            return await self.bot.say("They aren't in that role.")

        try:
            await self.bot.remove_roles(member, role)
        except discord.DiscordException:
            return await self.bot.say("Something went wrong.")
        else:
            message = MASS_MENTION_RE.sub(
                "@\u200b",
                "Role {role.name} removed from {user.name}".format(role=role, user=member)
            )
            await self.bot.say(message)

    @srerole.command(pass_context=True)
    async def recolor(self, ctx, color: discord.Color, *, role: discord.Role):
        """
        Recolors a role.

        Color is expected to be in the form #F35692
        """
        server = ctx.message.channel.server
        me = server.me
        if role >= me.top_role or not me.server_permissions.manage_roles:
            return await self.bot.say("I can't do that.")

        if role >= ctx.message.author.top_role or not self.op_valid_on_role(role, COLOR):
            return await self.bot.say("You can't do that.")

        try:
            await self.bot.edit_role(server, role, color=color)
        except discord.DiscordException:
            return await self.bot.say("Something went wrong.")
        else:
            await self.bot.say("Role {0.name} recolored.".format(role))

    @srerole.command(pass_context=True)
    async def rename(self, ctx, role: discord.Role, *, name: str):
        """
        Renames a role.

        Multi word roles need quotes.
        """
        server = ctx.message.channel.server
        me = server.me
        if role >= me.top_role or not me.server_permissions.manage_roles:
            return await self.bot.say("I can't do that.")

        if role >= ctx.message.author.top_role or not self.op_valid_on_role(role, NAME):
            return await self.bot.say("You can't do that.")

        try:
            prior = role.name
            await self.bot.edit_role(server, role, name=name)
        except discord.DiscordException:
            return await self.bot.say("Something went wrong.")
        else:
            await self.bot.say("Role renamed from {prior} to {new}".format(prior=prior, new=name))

    @srerole.command(pass_context=True)
    async def togglemention(self, ctx, *, role: discord.Role):
        """
        Toggles if a role can be mentioned
        """
        server = ctx.message.channel.server
        me = server.me
        if role >= me.top_role or not me.server_permissions.manage_roles:
            return await self.bot.say("I can't do that.")

        if role >= ctx.message.author.top_role or not self.op_valid_on_role(role, MENTION):
            return await self.bot.say("You can't do that.")

        try:
            new_setting = not role.mentionable
            await self.bot.edit_role(server, role, mentionable=new_setting)
        except discord.DiscordException:
            return await self.bot.say("Something went wrong.")
        else:
            verb = "is now" if new_setting else "is no longer"
            await self.bot.say(
                "{role.name} {verb} mentionable.".format(role=role, verb=verb)
            )


def setup(bot):
    pathlib.Path(PATH).mkdir(parents=True, exist_ok=True)
    n = SelectiveRoleEdit(bot)
    bot.add_cog(n)
