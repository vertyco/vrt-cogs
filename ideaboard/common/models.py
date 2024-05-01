from datetime import datetime

import discord
from redbot.core.bot import Red

from . import Base


class Suggestion(Base):
    id: str
    message_id: int
    author_id: int
    thread_id: int = 0

    # Upvotes/Downvotes are a list of user IDs
    upvotes: list[int] = []
    downvotes: list[int] = []


class Profile(Base):
    suggestions_made: int = 0
    suggestions_approved: int = 0
    suggestions_denied: int = 0

    # How many the user has voted on
    upvotes: int = 0
    downvotes: int = 0

    # How many the user has voted on that did/didn't go their way
    wins: int = 0
    losses: int = 0

    last_suggestion: datetime | None = None


class GuildSettings(Base):
    # Channels for approved, denied, and pending suggestions
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    # Whether suggestions are anonymous
    anonymous: bool = True
    # Whether to reveal the author of anonymous suggestion when approved
    reveal: bool = True
    # Whether to DM the author of a suggestion when approved/denied
    dm: bool = True
    # Upvote/downvote emojis
    upvote: str | int = "\N{THUMBS UP SIGN}"
    downvote: str | int = "\N{THUMBS DOWN SIGN}"
    show_vote_counts: bool = True
    # Whether to open a discussion thread for each suggestion
    discussion_threads: bool = False
    # Delete threads when suggestion is approved/denied
    delete_threads: bool = True

    # Roles required to make suggestions and vote
    vote_roles: list[int] = []
    suggest_roles: list[int] = []

    # Roles required to approve suggestions
    approvers: list[int] = []

    # Voting/Suggesting blacklists
    role_blacklist: list[int] = []
    user_blacklist: list[int] = []

    # Cooldowns (seconds)
    base_cooldown: int = 0
    role_cooldowns: dict[int, int] = {}

    # Active suggestions {suggestion_number: Suggestion}
    suggestions: dict[int, Suggestion] = {}
    counter: int = 0
    # User profiles {user_id: Profile}
    profiles: dict[int, Profile] = {}

    # Minimum age of account (hours)
    min_account_age_to_vote: int = 0
    min_account_age_to_suggest: int = 0

    # Minimum join time (hours)
    min_join_time_to_vote: int = 0
    min_join_time_to_suggest: int = 0

    # LevelUp integration
    min_level_to_vote: int = 0
    min_level_to_suggest: int = 0

    # ArkTools integration (private Cog)
    min_playtime_to_vote: int = 0
    min_playtime_to_suggest: int = 0

    def get_profile(self, user: discord.User | int) -> Profile:
        uid = user if isinstance(user, int) else user.id
        return self.profiles.setdefault(uid, Profile())

    def get_emojis(self, bot: Red):
        up = self.upvote
        if isinstance(up, int):
            up = bot.get_emoji(up)
        elif isinstance(up, str) and up.isdigit():
            up = bot.get_emoji(int(up))

        if not up:
            up = "\N{THUMBS UP SIGN}"

        down = self.downvote
        if isinstance(down, int):
            down = bot.get_emoji(down)
        elif isinstance(down, str) and down.isdigit():
            down = bot.get_emoji(int(down))

        if not down:
            down = "\N{THUMBS DOWN SIGN}"

        return up, down


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
