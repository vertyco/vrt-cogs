import asyncio
import json
import logging
import random
import textwrap
import typing as t
from io import BytesIO
from time import perf_counter

import discord
from piccolo.engine.postgres import PostgresEngine
from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common import achievements, constants, tracker
from .db.tables import (
    TABLES,
    GuildSettings,
    Player,
    PlayerAchievement,
    PlayerAchievementStats,
)
from .db.utils import DBUtils
from .engine import engine
from .listeners import Listeners
from .tasks import TaskLoops

log = logging.getLogger("red.vrt.miner")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class Miner(Commands, Listeners, TaskLoops, commands.Cog, metaclass=CompositeMetaClass):
    """Pickaxe in hand, fortune awaits"""

    __author__ = "Vertyco"
    __version__ = "1.2.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.db: PostgresEngine | None = None
        self.db_utils = DBUtils()

        self.chat_cache = tracker.ChannelChatCache()
        self.guild_spawn_cooldowns: dict[int, float] = {}  # {guild_id: last_spawn_timestamp}
        self.guild_spawn_locks: dict[int, asyncio.Lock] = {}
        self._durability_warning_state: dict[int, float] = {}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_get_data_for_user(self, *, user_id: int) -> t.MutableMapping[str, BytesIO]:
        player_rows = await Player.select(Player.all_columns()).where(Player.id == user_id)
        achievement_rows = await PlayerAchievement.select(PlayerAchievement.all_columns()).where(
            PlayerAchievement.player == user_id
        )
        achievement_stats_rows = await PlayerAchievementStats.select(PlayerAchievementStats.all_columns()).where(
            PlayerAchievementStats.player == user_id
        )
        payload = {
            "player": player_rows,
            "achievements": achievement_rows,
            "achievement_stats": achievement_stats_rows,
        }
        return {"data.json": BytesIO(json.dumps(payload, default=str).encode())}

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        if not self.db:
            return "Data not deleted, database connection is not active"
        await Player.delete().where(Player.id == user_id)
        return f"Data for user ID {user_id} has been deleted"

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        if self.db:
            self.db.pool.terminate()
            log.info("Database connection terminated")

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        config = await self.bot.get_shared_api_tokens("postgres")
        if not config:
            log.warning("Postgres credentials not set!")
            return
        if self.db_active():
            log.info("Closing existing database connection")
            await self.db.close_connection_pool()
        log.info("Registering database connection")
        try:
            self.db = await engine.register_cog(self, TABLES, config, trace=True)
            # If anyone's tool is at 0 dura for some reason (and not wood), update it to the tool's max durability
            sql = f"""
                UPDATE player SET durability = CASE tool
                WHEN 'stone' THEN {constants.TOOLS["stone"].max_durability}
                WHEN 'iron' THEN {constants.TOOLS["iron"].max_durability}
                WHEN 'steel' THEN {constants.TOOLS["steel"].max_durability}
                WHEN 'carbide' THEN {constants.TOOLS["carbide"].max_durability}
                WHEN 'diamond' THEN {constants.TOOLS["diamond"].max_durability}
                ELSE durability
                END
                WHERE durability = 0
            """
            await Player.raw(textwrap.dedent(sql))
        except Exception as e:
            log.error("Failed to connect to database", exc_info=e)
            self.db = None
            return
        log.info("Cog initialized")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: dict):
        if service_name != "postgres":
            return
        await self.initialize()

    # ---------------------------- GLOBAL METHODS ----------------------------
    def db_active(self) -> bool:
        if not self.db:
            return False
        if hasattr(self.db.pool, "is_closing"):
            return not self.db.pool.is_closing()  # 1.27.1
        if self.db.pool._closed:
            return False
        return self.db is not None

    # ---------------------------- DURABILITY UTILITIES ----------------------------
    def reset_durability_warnings(self, player_id: int) -> None:
        """Clear tracked durability warnings for a player (e.g., after repair or tool reset)."""

        self._durability_warning_state.pop(player_id, None)

    def register_durability_ratio(self, player_id: int, ratio: float | None) -> float | None:
        """Record the player's current durability ratio and return the threshold crossed, if any."""

        if ratio is None:
            return None
        thresholds = getattr(constants, "DURABILITY_WARNING_THRESHOLDS", ())
        if not thresholds:
            return None
        last_threshold = self._durability_warning_state.get(player_id, 1.0)
        for threshold in sorted(thresholds, reverse=True):
            if ratio <= threshold < last_threshold:
                self._durability_warning_state[player_id] = threshold
                return threshold
        return None

    # ---------------------------- ROCK SPAWN UTILITIES ----------------------------
    def get_spawn_activity_metrics(self, channel_id: int) -> tuple[float, int, float]:
        """Return normalized average tool tier, player count, and combined quality multiplier."""

        avg_tool_tier = self.chat_cache.get_average_tool_tier(channel_id)
        player_count = self.chat_cache.get_recent_player_count(channel_id)
        player_count_ratio = min(player_count / constants.EXPECTED_ACTIVE_PLAYERS, 1.0)
        combined_multiplier = (avg_tool_tier * constants.TOOL_TIER_WEIGHT) + (
            player_count_ratio * constants.PLAYER_COUNT_WEIGHT
        )
        return avg_tool_tier, player_count, combined_multiplier

    def get_guild_spawn_cooldown_remaining(self, guild_id: int, cooldown_seconds: int) -> float:
        """Return remaining guild cooldown in seconds (0 if ready)."""

        now = perf_counter()
        last_spawn = self.guild_spawn_cooldowns.get(guild_id, 0.0)
        return max(0.0, cooldown_seconds - (now - last_spawn))

    def get_guild_spawn_lock(self, guild_id: int) -> asyncio.Lock:
        """Return the guild-scoped lock used to serialize manual spawn attempts."""

        lock = self.guild_spawn_locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self.guild_spawn_locks[guild_id] = lock
        return lock

    def choose_rock_type(self, channel_id: int) -> constants.RockTierName:
        """Choose rock type with randomness, biased by recent tool tiers and active player count."""

        _, _, combined_multiplier = self.get_spawn_activity_metrics(channel_id)
        # High multiplier flattens rarity curve slightly so rarer rocks become more likely, not guaranteed.
        rarity_exponent = 1.5 - combined_multiplier

        rock_types = list(constants.ROCK_TYPES.keys())
        weights: list[float] = []
        for rock_type in rock_types:
            rarity = max(1, constants.ROCK_TYPES[rock_type].rarity)
            weight = 1.0 / (rarity**rarity_exponent)
            weights.append(weight)

        if not any(weights):
            return "small"
        return t.cast(constants.RockTierName, random.choices(rock_types, weights=weights, k=1)[0])

    def choose_modifiers(self, rock_type: constants.RockTierName) -> list[constants.Modifier]:
        """Choose 0-2 random modifiers for a rock based on rock rarity.

        Higher rarity rocks are more likely to have modifiers.
        Modifiers are weighted by their own rarity value (higher rarity = rarer modifiers).
        """
        rock = constants.ROCK_TYPES[rock_type]
        # Base chance: 20% + 5% per rock rarity tier
        modifier_chance = 0.20 + (rock.rarity * 0.05)
        modifier_chance = min(0.95, modifier_chance)  # Cap at 95%

        if random.random() > modifier_chance:
            return []

        # Decide how many modifiers (1 or 2, weighted towards 1)
        num_modifiers = 1 if random.random() < 0.7 else 2

        # Select modifiers weighted by their rarity (higher rarity = less common)
        all_modifiers = list(constants.MODIFIERS.values())
        mod_weights = [1.0 / modifier.rarity for modifier in all_modifiers]

        # Choose without replacement
        selected = []
        available_mods = list(zip(all_modifiers, mod_weights))
        for _ in range(num_modifiers):
            if not available_mods:
                break
            mods, weights = zip(*available_mods)
            chosen = random.choices(mods, weights=weights, k=1)[0]
            selected.append(chosen)
            # Remove from available to avoid duplicates
            available_mods = [(m, w) for m, w in available_mods if m.key != chosen.key]

        return selected

    async def notify_spawn_subscribers(
        self,
        guild: discord.Guild,
        settings: GuildSettings,
        destination: t.Callable[[str], t.Awaitable[discord.Message]],
    ) -> None:
        """Notify opted-in players about a new spawn and clean stale IDs."""

        if not settings.notify_players:
            return

        valid_users = [uid for uid in settings.notify_players if guild.get_member(uid)]
        invalid_users = [uid for uid in settings.notify_players if uid not in valid_users]
        if invalid_users:
            settings.notify_players = valid_users
            await settings.save([GuildSettings.notify_players])
            await self.db_utils.get_cached_guild_settings.cache.delete(f"miner_guild_settings:{guild.id}")  # type: ignore

        if not valid_users:
            return

        mention_str = " ".join(f"<@{uid}>" for uid in valid_users)
        await destination(mention_str)

    async def get_player_achievements(self, user: discord.User | discord.Member | int) -> list[PlayerAchievement]:
        return await self.db_utils.get_player_achievements(user)

    async def get_player_achievement_stats(self, user: discord.User | discord.Member | int) -> PlayerAchievementStats:
        return await self.db_utils.get_create_player_achievement_stats(user)

    async def unlock_player_achievements(
        self,
        user: discord.User | discord.Member | int,
        keys: list[str],
        destination: discord.abc.Messageable | None = None,
        notify: bool = False,
    ) -> list[achievements.AchievementDef]:
        new_rows = await self.db_utils.ensure_player_achievements(user, keys)
        unlocked = [
            achievements.ACHIEVEMENTS_BY_KEY[row.key] for row in new_rows if row.key in achievements.ACHIEVEMENTS_BY_KEY
        ]
        if notify and destination and unlocked:
            await self.announce_achievement_unlocks(destination, user, unlocked)
        return unlocked

    async def sync_player_achievements(
        self,
        user: discord.User | discord.Member | int,
        destination: discord.abc.Messageable | None = None,
        notify: bool = False,
    ) -> list[achievements.AchievementDef]:
        player = await self.db_utils.get_create_player(user)
        await self.db_utils.get_create_player_achievement_stats(player.id)
        resource_lower_bounds = await self.db_utils.get_player_resource_lower_bounds(player.id)
        exact_unlock_keys = achievements.get_exact_retroactive_unlock_keys(player.tool, resource_lower_bounds)
        return await self.unlock_player_achievements(
            player.id, exact_unlock_keys, destination=destination, notify=notify
        )

    async def announce_achievement_unlocks(
        self,
        destination: discord.abc.Messageable,
        user: discord.User | discord.Member | int,
        unlocked: list[achievements.AchievementDef],
    ) -> None:
        unlocked = achievements.dedupe_achievement_defs(unlocked)
        if not unlocked:
            return
        if isinstance(user, int):
            mention = f"<@{user}>"
        else:
            mention = user.mention

        title = "Achievement Unlocked!" if len(unlocked) == 1 else "Achievements Unlocked!"
        lines = [f"{mention} unlocked `{len(unlocked)}` new Miner achievement(s).", ""]
        for achievement in unlocked[:6]:
            lines.append(f"**{achievement.name}**")
            lines.append(achievement.condition)
            lines.append("")
        if len(unlocked) > 6:
            lines.append(f"...and `{len(unlocked) - 6}` more.")

        embed = discord.Embed(
            title=title,
            description="\n".join(lines).strip(),
            color=discord.Color.gold(),
        )
        await destination.send(embed=embed)
