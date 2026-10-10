from piccolo.columns import BigInt, Boolean, ForeignKey, Integer, Real, Serial, Varchar
from piccolo.columns.base import OnDelete
from piccolo.table import Table, sort_table_classes

# "scope" is whose data a row belongs to: a server's id in server mode, 0 in global mode


class BotState(Table):
    id = Integer(primary_key=True, help_text="Always 1: there is one row")
    global_mode = Boolean(default=False)


class CasinoSettings(Table):
    id = BigInt(primary_key=True, help_text="Scope")
    # Empty default: an apostrophe in a column default breaks Piccolo's table SQL, and every new row gets CASINO_DEFAULTS
    name = Varchar(length=30, default="")
    is_open = Boolean(default=True)
    limit_on = Boolean(default=False)
    limit_amount = BigInt(default=10000)


class GameSettings(Table):
    id: Serial
    scope = BigInt(index=True)
    game = Varchar(length=16)
    is_open = Boolean(default=True)
    access = Integer(default=0)
    cooldown = Integer(default=5, help_text="Seconds")
    min_bet = BigInt(null=True, default=None)
    max_bet = BigInt(null=True, default=None)
    multiplier = Real(null=True, default=None)


class Membership(Table):
    id: Serial
    scope = BigInt(index=True)
    name = Varchar(length=32)
    color = Varchar(length=16, default="blue")
    access = Integer(default=0)
    reduction = Integer(default=0, help_text="Cooldown reduction in seconds")
    bonus = Real(default=1.0)
    req_credits = BigInt(null=True, default=None)
    req_role_id = BigInt(null=True, default=None)
    req_days = Integer(null=True, default=None)


class Player(Table):
    id: Serial
    scope = BigInt(index=True)
    user_id = BigInt(index=True)
    membership = ForeignKey(references=Membership, null=True, on_delete=OnDelete.set_null)
    by_hand = Boolean(default=False, help_text="The membership was given by an admin, so the updater skips them")
    pending = BigInt(default=0, help_text="Winnings held by the payout limit")


class PlayerGame(Table):
    id: Serial
    scope = BigInt(index=True)
    user_id = BigInt(index=True)
    game = Varchar(length=16)
    played = Integer(default=0)
    won = Integer(default=0)
    ready_at = Real(default=0.0, help_text="Unix time the cooldown ends, before any membership reduction")


TABLES: list[type[Table]] = sort_table_classes([BotState, CasinoSettings, GameSettings, Membership, Player, PlayerGame])
