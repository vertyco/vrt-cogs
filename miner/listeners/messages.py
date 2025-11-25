import logging
import random
from time import perf_counter

import discord
from piccolo.query import OrderByRaw
from redbot.core import commands

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import ActiveChannel, GuildSettings
from ..views.mining_view import RockView

log = logging.getLogger("red.vrt.miner.listeners.messages")


class MessageListener(MixinMeta):
    def __init__(self):
        super().__init__()
        self.last_user_message: dict[int, int] = {}
        # key (guild or channel) -> last rumble timestamp
        self.last_rumble: dict[int, float] = {}

    async def maybe_rumble(self, message: discord.Message, key: int, spawn_prob: float) -> None:
        """Occasionally send a flavor message when spawn probability is high.

        This is purely cosmetic feedback to make the game feel more alive and
        does not affect actual spawn mechanics.
        """

        # Don't rumble if there is already an active rock cap reached.
        if self.active_guild_rocks.get(message.guild.id, 0) >= constants.PER_GUILD_ROCK_CAP:
            return

        now = perf_counter()
        last = self.last_rumble.get(key, 0.0)
        # Minimum time between rumbles for a given key (seconds).
        if now - last < constants.RUMBLE_MIN_INTERVAL_SECONDS:
            return

        # Only consider feedback when chances are at least "medium".
        if spawn_prob < constants.RUMBLE_MEDIUM_THRESHOLD:
            return

        # Scale rumble likelihood based on probability bucket.
        if spawn_prob >= constants.RUMBLE_HIGH_THRESHOLD:
            chance = constants.RUMBLE_CHANCE_HIGH  # High spawn chance -> more likely to rumble.
        elif spawn_prob >= constants.RUMBLE_MEDIUM_THRESHOLD:
            chance = constants.RUMBLE_CHANCE_MEDIUM
        else:
            chance = 0.0

        if not chance or random.random() >= chance:
            return

        # Choose a short flavor message.
        rumble_lines = [
            "The ground rumbles softly beneath your feet...",
            "You hear distant rockfalls echoing through the mineshaft...",
            "Loose stones clatter around you as the earth shifts...",
        ]
        text = random.choice(rumble_lines)

        # In per-guild mode we might be spawning in a different channel; however
        # for feedback purposes we use the current channel where activity occurs.
        try:
            await message.channel.send(text)
        except discord.HTTPException:
            return

        self.last_rumble[key] = now

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if isinstance(message.channel, (discord.DMChannel, discord.ForumChannel, discord.CategoryChannel)):
            return
        if message.content and "reload" in message.content:
            return
        if self.active_guild_rocks[message.guild.id] >= constants.PER_GUILD_ROCK_CAP:
            return
        if not self.db_active():
            return

        settings: GuildSettings = await self.db_utils.get_cached_guild_settings(message.guild.id)
        key = message.channel.id if settings.per_channel_activity_trigger else message.guild.id
        self.activity.update(key)

        if message.guild.id not in self.last_user_message:
            self.last_user_message[message.guild.id] = message.author.id
        elif (
            self.last_user_message[message.guild.id] == message.author.id
            and (perf_counter() - self.activity.last_spawns.get(key, 0)) < constants.ABSOLUTE_MAX_TIME_BETWEEN_SPAWNS
        ):
            # Same user cannot spam messages to increase activity
            return
        else:
            self.last_user_message[message.guild.id] = message.author.id

        # Fetch global spawn timing.
        min_interval, max_interval = await self.db_utils.get_spawn_timing()

        # Spawn feedback: occasionally send a "rumble" message when spawn chance is high.
        spawn_prob = self.activity.get_spawn_probability(key, min_interval, max_interval)

        await self.maybe_rumble(message, key, spawn_prob)

        # Determine if a rock should spawn.
        rock_type: constants.RockTierName | None = self.activity.maybe_get_rock(
            key,
            min_interval=min_interval,
            max_interval=max_interval,
        )
        if not rock_type:
            return

        if settings.per_channel_activity_trigger:
            channel: discord.TextChannel | discord.Thread = message.channel
            if not await ActiveChannel.exists().where(ActiveChannel.id == channel.id):
                return
        else:
            query = ActiveChannel.select(ActiveChannel.id).where(ActiveChannel.guild == message.guild.id)
            if self.active_channel_rocks:
                query = query.where(ActiveChannel.id.not_in(list(self.active_channel_rocks)))
            query = query.order_by(OrderByRaw("RANDOM()")).first()
            active_channel = await query
            if not active_channel:
                return
            channel: discord.TextChannel | discord.Thread = message.guild.get_channel_or_thread(active_channel["id"])
            if not channel:
                # Delete stale active channel entry
                await ActiveChannel.delete().where(ActiveChannel.id == active_channel["id"])
                log.warning(f"Deleted stale active channel {active_channel['id']}")
                return

        if channel.id in self.active_channel_rocks:
            return

        self.active_guild_rocks[message.guild.id] += 1
        self.active_channel_rocks.add(channel.id)
        try:
            if settings.notify_players:
                valid_users = [i for i in settings.notify_players if message.guild.get_member(i)]
                invalid_users = [i for i in settings.notify_players if i not in valid_users]
                if invalid_users:
                    settings.notify_players = valid_users
                    await settings.save([GuildSettings.notify_players])
                    await self.db_utils.get_cached_guild_settings.cache.delete(
                        f"miner_guild_settings:{message.guild.id}"
                    )  # type: ignore
                if valid_users:
                    mention_str = " ".join(f"<@{i}>" for i in valid_users)
                    await channel.send(f"{mention_str}")
            rock: constants.RockType = constants.ROCK_TYPES[rock_type]
            view = RockView(self, rock)
            await view.start(channel)
            await view.wait()
        except Exception as e:
            log.error(f"Error spawning rock in {channel.id}: {e}")
        finally:
            self.active_guild_rocks[message.guild.id] = max(0, self.active_guild_rocks[message.guild.id] - 1)
            self.active_channel_rocks.discard(channel.id)
