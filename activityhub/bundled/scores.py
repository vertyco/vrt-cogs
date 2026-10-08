import asyncio
import secrets
import time
import typing as t
from dataclasses import dataclass

import discord

from ..common.sessions import SESSION_TTL, ActivityContext

BOARD_SIZE = 10
# A round left open longer than this is dropped, so a closed tab doesn't keep one forever. It matches the login,
# since a round paused for hours (the game pauses itself when the player clicks away) is still a real round
RUN_TTL = SESSION_TTL


@dataclass
class Run:
    user_id: int
    guild_id: int
    key: str
    seed: int
    started: float


class ScoreBoard:
    """Rounds being played right now, and each server's best scores for the bundled games"""

    def __init__(self, config: t.Any, clock: t.Callable[[], float] = time.monotonic):
        self.config = config
        self.clock = clock
        self.runs: dict[str, Run] = {}
        self.lock = asyncio.Lock()

    def open_run(self, ctx: ActivityContext, key: str, seed: int) -> str:
        """Start a round on the bot's clock. Starting again drops the player's unfinished round of that game"""
        now = self.clock()
        self.runs = {
            run_id: run
            for run_id, run in self.runs.items()
            if now - run.started < RUN_TTL and not (run.user_id == ctx.author.id and run.key == key)
        }
        run_id = secrets.token_urlsafe(16)
        self.runs[run_id] = Run(ctx.author.id, ctx.guild_id, key, seed, now)
        return run_id

    def close_run(self, ctx: ActivityContext, key: str, run_id: t.Any) -> tuple[Run, float] | None:
        """The player's open round with this id and how long it ran, or None when there is no such round"""
        run = self.runs.get(run_id) if isinstance(run_id, str) else None
        if run is None or run.user_id != ctx.author.id or run.key != key or run.guild_id != ctx.guild_id:
            return None
        del self.runs[run_id]
        return run, self.clock() - run.started

    async def save(self, member: discord.Member, key: str, score: int) -> tuple[int, bool]:
        """Keep the score if it beats the member's best here. Returns their best and whether this was it"""
        async with self.lock:
            group = self.config.member(member)
            best = await group.best()
            old = best.get(key)
            if score <= 0 or (old is not None and old["score"] >= score):
                return (old["score"] if old else 0), False
            # The time breaks ties: whoever got there first ranks higher
            best[key] = {"score": score, "at": time.time()}
            await group.best.set(best)
        return score, True

    async def board(self, guild: discord.Guild, member: discord.Member, key: str) -> dict:
        """The server's top scores for a game, plus the member's own row (None before their first score)"""
        entries = []
        for user_id, data in (await self.config.all_members(guild)).items():
            entry = data.get("best", {}).get(key)
            person = guild.get_member(user_id)
            # People who left the server drop off its board
            if entry and person is not None:
                entries.append((person, entry))
        entries.sort(key=lambda item: (-item[1]["score"], item[1]["at"]))
        top = [board_row(rank, person, entry, member) for rank, (person, entry) in enumerate(entries[:BOARD_SIZE], 1)]
        rank = next((rank for rank, (person, _) in enumerate(entries, 1) if person.id == member.id), None)
        you = board_row(rank, entries[rank - 1][0], entries[rank - 1][1], member) if rank else None
        return {"server": guild.name, "top": top, "you": you}


def board_row(rank: int, person: discord.Member, entry: dict, member: discord.Member) -> dict:
    return {
        "rank": rank,
        "name": person.display_name,
        "avatar": person.display_avatar.url,
        "score": entry["score"],
        "you": person.id == member.id,
    }
