import json
import math
import typing as t
from datetime import datetime

import discord
from redbot.core import bank
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from . import Base

_ = Translator("ExtendedEconomy", __file__)


class PaydayClaimInformation(t.NamedTuple):
    member: discord.Member
    channel: t.Union[discord.TextChannel, discord.Thread, discord.ForumChannel]
    message: discord.Message
    amount: int
    old_balance: int
    new_balance: int

    def to_dict(self) -> dict:
        return {
            "member": self.member.id,
            "channel": self.channel.id,
            "message": self.message.id,
            "amount": self.amount,
            "old_balance": self.old_balance,
            "new_balance": self.new_balance,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class CommandCost(Base):
    """
    - cost: the base cost of the command
    - duration: the time period in seconds in which the command usage is tracked and used to calculate the cost
    - level: the minimum permission level of the command in which the cost is applied
        - admin: admins and above can use the command for free
        - mod: mods and above can use the command for free
        - all: everyone must pay the cost to use the command
        - user: all users must pay the cost to use the command unless they are mod or admin
        - global: the cost is applied to all users globally
    - prompt: how will the user be prompted to confirm the cost (Slash commands will always use silent mode)
        - text: the bot will send a text message asking the user to confirm the cost with yes or no
        - reaction: the bot will send a message with emoji reactions to confirm the cost
        - button: the bot will send a message with buttons to confirm the cost
        - silent: the bot will not prompt the user to confirm the cost
        - notify: the bot will simply notify the user of the cost without asking for confirmation
    - modifier: the type of cost modifier
        - static: the cost is a fixed amount
        - percent: the cost is a percentage of the user's balance on top of the base cost
        - exponential: the cost increases exponentially based on how frequenty the command is used
            - Ex: cost gets doubled every time the command is used within a set time period
        - linear: the cost increases linearly based on how frequently the command is used
            - Ex: cost gets increased by a fixed amount every time the command is used within a set time period
    - value: the value of the cost modifier depends on the modifier type
        - static: this will be 0 and does nothing
        - percent: value will be the percentage of the user's balance to add to the base cost
        - exponential: value will be the base cost multiplier
        - linear: value will multiplied by the number of uses in the last hour to get the cost increase
    - uses: a list of lists containing the user ID and the timestamp of the command usage
    """

    cost: int
    duration: int
    level: t.Literal["admin", "mod", "all", "user", "global"]
    prompt: t.Literal["text", "reaction", "button", "silent", "notify"]
    modifier: t.Literal["static", "percent", "exponential", "linear"]
    value: float
    uses: t.List[t.List[t.Union[int, float]]] = []

    async def get_cost(self, bot: Red, user: t.Union[discord.Member, discord.User]) -> int:
        if self.level == "global" and user.id in bot.owner_ids:
            return 0
        elif self.level != "global":
            free = [
                await bot.is_admin(user) and self.level in ["admin", "mod"],
                await bot.is_mod(user) and self.level == "mod",
            ]
            if any(free):
                return 0
        if self.modifier == "static":
            return self.cost
        if self.modifier == "percent":
            bal = await bank.get_balance(user)
            return math.ceil(self.cost + (bal * self.value))
        min_time = datetime.now().timestamp() - self.duration
        uses_in_duration = len([u for u in self.uses if u[0] == user.id and u[1] > min_time])
        if self.modifier == "exponential":
            return math.ceil(self.cost + self.value * (2**uses_in_duration))
        if self.modifier == "linear":
            return math.ceil(self.cost + (self.value * uses_in_duration))
        raise ValueError(f"Invalid cost modifier: {self.modifier}")

    def update_usage(self, user_id: int):
        self.uses.append([user_id, datetime.now().timestamp()])
        self.uses = [u for u in self.uses if u[1] > datetime.now().timestamp() - self.duration]


class LogChannels(Base):
    default_log_channel: int = 0
    # Event log channel overrides
    set_balance: int = 0
    transfer_credits: int = 0
    bank_wipe: int = 0
    prune: int = 0
    set_global: int = 0
    payday_claim: int = 0

    auto_claim: int = 0


class GuildSettings(Base):
    logs: LogChannels = LogChannels()
    command_costs: t.Dict[str, CommandCost] = {}
    transfer_tax: float = 0.0
    transfer_tax_whitelist: t.List[int] = []  # Role IDs that are exempt from transfer tax

    # Unique to GuildSettings (local bank only)
    stack_paydays: bool = False
    auto_claim_roles: t.List[int] = []  # Role IDs that auto claim paydays
    role_bonuses: t.Dict[int, float] = {}  # Role ID: bonus multiplier


class DB(Base):
    configs: t.Dict[int, GuildSettings] = {}
    delete_after: t.Union[int, None] = None

    logs: LogChannels = LogChannels()
    command_costs: t.Dict[str, CommandCost] = {}
    transfer_tax: float = 0.0

    auto_payday_claim: bool = False  # If True, guilds that set auto_claim_roles will auto claim paydays

    # Allow prices per guild when global bank is enabled
    # per_guild_override: bool = False

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
