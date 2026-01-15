import logging
import random
import re
import unicodedata
from time import perf_counter

import discord
from rapidfuzz import fuzz
from redbot.core import commands

from ..abc import MixinMeta
from ..common import const

log = logging.getLogger("red.vrt.levelup.listeners.messages")

# Patterns for message normalization
WHITESPACE_PATTERN = re.compile(r"\s+")
REPEATED_CHARS_PATTERN = re.compile(r"(.)\1{2,}")  # 3+ repeated chars
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
MENTION_PATTERN = re.compile(r"<[@#!&]?\d+>")


def normalize_message(content: str) -> str:
    """
    Normalize a message for comparison by:
    - Lowercasing
    - Removing URLs, mentions, emojis
    - Collapsing repeated characters
    - Stripping extra whitespace
    - Normalizing unicode
    """
    text = content.lower()
    # Remove URLs
    text = URL_PATTERN.sub("", text)
    # Remove mentions
    text = MENTION_PATTERN.sub("", text)
    # Remove custom Discord emojis
    text = const.EMOJI_PATTERN.sub("", text)
    # Normalize unicode (é -> e, etc.)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Collapse repeated characters (hellooooo -> helo)
    text = REPEATED_CHARS_PATTERN.sub(r"\1", text)
    # Collapse whitespace
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text


def get_unique_word_ratio(text: str) -> float:
    """Calculate the ratio of unique words to total words"""
    words = text.split()
    if not words:
        return 0.0
    unique = set(words)
    return len(unique) / len(words)


def is_spam_message(
    normalized: str,
    history: list[str],
    similarity_threshold: int,
    min_unique_ratio: float,
) -> bool:
    """
    Check if a message is spam based on:
    1. Similarity to recent messages (using rapidfuzz)
    2. Unique word ratio (low ratio = repetitive content)

    Returns True if the message is considered spam.
    """
    # Check unique word ratio first (catches self-contained spam like repeated phrases)
    if normalized and get_unique_word_ratio(normalized) < min_unique_ratio:
        log.debug(f"Message failed unique word ratio check: {normalized[:50]}")
        return True

    # Check similarity against recent messages
    for past_msg in history:
        # Use token_set_ratio for better handling of word order variations
        similarity = fuzz.token_set_ratio(normalized, past_msg)
        if similarity >= similarity_threshold:
            log.debug(f"Message too similar ({similarity}%) to recent message")
            return True

    return False


class MessageListener(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # If message object is None for some reason
        if not message:
            return
        # If message wasn't sent in a guild
        if not message.guild:
            return
        # If message was from a bot
        if message.author.bot and self.db.ignore_bots:
            return
        # Check if guild is in the master ignore list
        if str(message.guild.id) in self.db.ignored_guilds:
            return
        # Ignore webhooks
        if not isinstance(message.author, discord.Member):
            return
        # Check if cog is disabled
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        try:
            roles = list(message.author.roles)
            role_ids = [role.id for role in roles]
        except AttributeError:
            # User sent messange and left immediately?
            return
        conf = self.db.get_conf(message.guild)
        if not conf.enabled:
            return

        user_id = message.author.id
        if user_id in conf.ignoredusers:
            # If we're specifically ignoring a user we don't want to see them anywhere
            return

        profile = conf.get_profile(user_id).add_message()
        weekly = None
        if conf.weeklysettings.on:
            weekly = conf.get_weekly_profile(message.author).add_message()

        if perf_counter() - self.last_save > 300:
            # Save at least every 5 minutes
            self.save()

        prefixes = await self.bot.get_valid_prefixes(guild=message.guild)
        if not conf.command_xp and message.content.startswith(tuple(prefixes)):
            # Don't give XP for commands
            return

        if conf.allowedchannels:
            # Make sure the channel is allowed
            if message.channel.id not in conf.allowedchannels:
                # See if its category or parent channel is allowed then
                if isinstance(message.channel, (discord.Thread, discord.ForumChannel)):
                    channel_id = message.channel.parent_id
                    if channel_id not in conf.allowedchannels:
                        # Mabe the parent channel's category is allowed?
                        category_id = message.channel.parent.category_id
                        if category_id not in conf.allowedchannels:
                            # Nope, not allowed
                            return
                else:
                    channel_id = message.channel.category_id
                    if channel_id and channel_id not in conf.allowedchannels:
                        return

        if message.channel.id in conf.ignoredchannels:
            return
        if (
            isinstance(
                message.channel,
                (
                    discord.Thread,
                    discord.ForumChannel,
                ),
            )
            and message.channel.parent_id in conf.ignoredchannels
        ):
            return
        elif message.channel.category_id and message.channel.category_id in conf.ignoredchannels:
            return

        if conf.allowedroles:
            # Make sure the user has at least one allowed role
            if not any(role in conf.allowedroles for role in role_ids):
                return

        if any(role in conf.ignoredroles for role in role_ids):
            return
        now = perf_counter()
        last_messages = self.lastmsg.setdefault(message.guild.id, {})
        addxp = False

        length_check_content = const.EMOJI_PATTERN.sub("", message.content)
        if len(length_check_content) > conf.min_length:
            if user_id not in last_messages:
                addxp = True
            elif now - last_messages[user_id] > conf.cooldown:
                addxp = True

        if not addxp:
            return

        # Anti-spam checks
        if conf.antispam.enabled:
            normalized = normalize_message(message.content)
            # Get or create the message cache for this guild/user
            guild_cache = self.msg_cache.setdefault(message.guild.id, {})
            user_history = guild_cache.setdefault(user_id, [])

            # Check if message is spam
            if is_spam_message(
                normalized=normalized,
                history=user_history,
                similarity_threshold=conf.antispam.similarity_threshold,
                min_unique_ratio=conf.antispam.min_unique_ratio,
            ):
                log.debug(f"Anti-spam: Blocked XP for {message.author.name} in {message.guild.name}")
                return

            # Add to history (maintain max size)
            if normalized:  # Only add non-empty normalized messages
                user_history.append(normalized)
                # Trim history to configured size
                while len(user_history) > conf.antispam.history_size:
                    user_history.pop(0)

        self.lastmsg[message.guild.id][user_id] = now

        xp_to_add = random.randint(conf.xp[0], conf.xp[1])
        # Add channel bonus if it exists
        channel_bonuses = conf.channelbonus.msg
        category = None
        if isinstance(message.channel, discord.Thread):
            parent = message.channel.parent
            if parent:
                category = parent.category
        else:
            category = message.channel.category
        cat_id = category.id if category else 0

        if message.channel.id in channel_bonuses:
            xp_to_add += random.randint(*channel_bonuses[message.channel.id])
        elif cat_id in channel_bonuses:
            xp_to_add += random.randint(*channel_bonuses[cat_id])
        # Stack all role bonuses
        for role_id, (bonus_min, bonus_max) in conf.rolebonus.msg.items():
            if role_id in role_ids:
                xp_to_add += random.randint(bonus_min, bonus_max)

        # Add presence bonus if applicable
        presence_status = str(message.author.status).lower()  # 'online', 'idle', 'dnd', 'offline'
        if presence_status in conf.presencebonus.msg:
            bonus_min, bonus_max = conf.presencebonus.msg[presence_status]
            xp_to_add += random.randint(bonus_min, bonus_max)
            log.debug(f"Adding {presence_status} presence bonus to {message.author.name} in {message.guild.name}")

        # Add application bonus if the user is using a specific application
        if hasattr(message.author, "activity") and message.author.activity:
            activity_name = getattr(message.author.activity, "name", "").upper()
            if activity_name and activity_name in conf.appbonus.msg:
                app_bonus_min, app_bonus_max = conf.appbonus.msg[activity_name]
                app_bonus = random.randint(app_bonus_min, app_bonus_max)
                xp_to_add += app_bonus
                log.debug(f"Adding {app_bonus} application bonus XP to {message.author.name} for using {activity_name}")

        # Add the xp to the role groups
        for role_id in role_ids:
            if role_id in conf.role_groups:
                conf.role_groups[role_id] += xp_to_add
        # Add the xp to the user's profile
        log.debug(f"Adding {xp_to_add} xp to {message.author.name} in {message.guild.name}")
        profile.xp += xp_to_add
        if weekly:
            weekly.xp += xp_to_add
        # Check for levelups
        await self.check_levelups(
            guild=message.guild,
            member=message.author,
            profile=profile,
            conf=conf,
            message=message,
            channel=message.channel,
        )
