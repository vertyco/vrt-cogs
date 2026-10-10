"""What the page and the commands show: the casino's settings, a player's stats, the membership list"""

from .catalog import GAME_NAMES, GAMES
from .memberships import perks_for
from .money import Money
from .store import Store


async def casino_info(store: Store, scope: int) -> dict:
    """The original's [p]casino info: the casino and every game's settings"""
    casino = await store.casino(scope)
    games = await store.games(scope)
    return {
        "name": casino.name,
        "open": casino.is_open,
        "global": await store.global_mode(),
        "limit_on": casino.limit_on,
        "limit_amount": casino.limit_amount,
        "games": {
            key: {
                "name": GAME_NAMES[key],
                "open": row.is_open,
                "access": row.access,
                "cooldown": row.cooldown,
                "min": row.min_bet,
                "max": row.max_bet,
                "multiplier": row.multiplier,
            }
            for key, row in games.items()
        },
    }


async def player_stats(store: Store, money: Money, scope: int, who) -> dict:
    """The original's [p]casino stats: membership, perks, and per game played, won and time until ready"""
    perks = await perks_for(store, scope, who.id)
    rows = await store.player_games(scope, who.id)
    player = await store.player(scope, who.id)
    return {
        "id": str(who.id),
        "name": who.display_name,
        "avatar": who.display_avatar.url,
        "membership": {"name": perks.name, "color": perks.color},
        "access": perks.access,
        "reduction": perks.reduction,
        "bonus": perks.bonus,
        "pending": player.pending,
        "by_hand": player.by_hand,
        "membership_id": player.membership,
        "games": [
            {
                "key": key,
                "name": GAME_NAMES[key],
                "played": rows[key].played,
                "won": rows[key].won,
                "ready_in": await money.ready_in(scope, who.id, key),
            }
            for key in GAMES
        ],
    }


async def me(store: Store, money: Money, scope: int, who) -> dict:
    """The top bar's facts about the player, and how long until each game is ready for them"""
    perks = await perks_for(store, scope, who.id)
    player = await store.player(scope, who.id)
    return {
        "t": "me",
        "id": str(who.id),
        "name": who.display_name,
        "balance": await money.bank.balance(who),
        "membership": {"name": perks.name, "color": perks.color},
        "access": perks.access,
        "pending": player.pending,
        "ready": {key: await money.ready_in(scope, who.id, key) for key in GAMES},
    }


async def tiers(store: Store, scope: int, guild) -> list[dict]:
    """The original's [p]casino memberships: each tier's perks, requirements and the games it unlocks"""
    games = await store.games(scope)
    shown = []
    for tier in await store.memberships(scope):
        role = guild.get_role(tier.req_role_id) if guild is not None and tier.req_role_id else None
        shown.append(
            {
                "id": tier.id,
                "name": tier.name,
                "color": tier.color,
                "access": tier.access,
                "reduction": tier.reduction,
                "bonus": tier.bonus,
                "req_credits": tier.req_credits,
                "req_role_id": str(tier.req_role_id) if tier.req_role_id else None,
                "req_role": role.name if role else None,
                "req_days": tier.req_days,
                "games": [GAME_NAMES[key] for key, row in games.items() if row.access <= tier.access],
            }
        )
    return shown
