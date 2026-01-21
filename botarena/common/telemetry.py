"""
Bot Arena - Battle Telemetry System

Logs campaign battle outcomes for balance analysis.
Data is stored in a JSONL (JSON Lines) file for easy filtering and analysis.
"""

import logging
import typing as t
from datetime import datetime, timezone
from pathlib import Path

import orjson

log = logging.getLogger("red.vrt.botarena.telemetry")


class BattleTelemetry:
    """
    Manages battle telemetry logging and analysis.

    Data is stored in JSONL format (one JSON object per line) for:
    - Easy appending without loading entire file
    - Simple filtering by reading line-by-line
    - Efficient pruning by rewriting without old entries
    """

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.telemetry_file = data_path / "telemetry.jsonl"

    def log_campaign_battle(
        self,
        mission_id: str,
        mission_name: str,
        chapter_id: int,
        player_id: int,
        result: str,  # "win", "loss", "stalemate"
        duration: float,
        player_bots_count: int,
        player_bots_survived: int,
        player_total_hp_remaining: int,
        player_max_hp: int,
        enemy_bots_count: int,
        enemy_bots_survived: int,
        total_damage_dealt: float,
        total_damage_taken: float,
        attempt_number: int,
        is_first_win: bool,
    ) -> None:
        """
        Log a campaign battle outcome.

        Args:
            mission_id: Mission identifier (e.g., "1-1", "3-2")
            mission_name: Human-readable mission name
            chapter_id: Chapter number (1-5)
            player_id: Discord user ID (for tracking per-player patterns)
            result: "win", "loss", or "stalemate"
            duration: Battle duration in seconds
            player_bots_count: Number of bots the player brought
            player_bots_survived: Number of player bots that survived
            player_total_hp_remaining: Sum of surviving bot HP
            player_max_hp: Sum of all player bot max HP (for percentage calc)
            enemy_bots_count: Number of enemy bots in the mission
            enemy_bots_survived: Number of enemy bots that survived
            total_damage_dealt: Total damage dealt by player
            total_damage_taken: Total damage taken by player
            attempt_number: Which attempt this is for this player on this mission
            is_first_win: True if this is the player's first time beating this mission
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mission_id": mission_id,
            "mission_name": mission_name,
            "chapter_id": chapter_id,
            "player_id": player_id,
            "result": result,
            "duration": round(duration, 2),
            "player_bots_count": player_bots_count,
            "player_bots_survived": player_bots_survived,
            "player_hp_remaining": player_total_hp_remaining,
            "player_max_hp": player_max_hp,
            "enemy_bots_count": enemy_bots_count,
            "enemy_bots_survived": enemy_bots_survived,
            "damage_dealt": round(total_damage_dealt, 1),
            "damage_taken": round(total_damage_taken, 1),
            "attempt_number": attempt_number,
            "is_first_win": is_first_win,
        }

        # Append to file (create if doesn't exist)
        with open(self.telemetry_file, "ab") as f:
            f.write(orjson.dumps(entry) + b"\n")

        log.debug(f"Logged telemetry: {mission_id} - {result} by player {player_id}")

    def get_entries(
        self,
        since: t.Optional[datetime] = None,
        mission_id: t.Optional[str] = None,
    ) -> list[dict]:
        """
        Read telemetry entries with optional filtering.

        Args:
            since: Only return entries after this datetime (UTC)
            mission_id: Only return entries for this mission

        Returns:
            List of telemetry entry dicts
        """
        if not self.telemetry_file.exists():
            return []

        entries = []
        with open(self.telemetry_file, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = orjson.loads(line)

                # Filter by time
                if since:
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    if entry_time < since:
                        continue

                # Filter by mission
                if mission_id and entry.get("mission_id") != mission_id:
                    continue

                entries.append(entry)

        return entries

    def get_mission_stats(
        self,
        since: t.Optional[datetime] = None,
    ) -> dict[str, dict]:
        """
        Aggregate statistics per mission.

        Returns dict like:
        {
            "1-1": {
                "name": "Roxtan Park Arena",
                "chapter": 1,
                "attempts": 150,
                "wins": 120,
                "losses": 25,
                "stalemates": 5,
                "win_rate": 0.80,
                "first_try_wins": 95,
                "first_try_rate": 0.79,
                "avg_attempts_to_win": 1.3,
                "avg_win_duration": 45.2,
                "avg_loss_duration": 38.1,
                "avg_hp_remaining_pct": 0.65,
                "avg_bots_used": 2.1,
            },
            ...
        }
        """
        entries = self.get_entries(since=since)

        # Group by mission
        missions: dict[str, list[dict]] = {}
        for entry in entries:
            mid = entry["mission_id"]
            if mid not in missions:
                missions[mid] = []
            missions[mid].append(entry)

        # Calculate stats per mission
        stats = {}
        for mission_id, mission_entries in missions.items():
            wins = [e for e in mission_entries if e["result"] == "win"]
            losses = [e for e in mission_entries if e["result"] == "loss"]
            stalemates = [e for e in mission_entries if e["result"] == "stalemate"]
            first_try_wins = [e for e in wins if e["attempt_number"] == 1]

            total = len(mission_entries)
            win_count = len(wins)

            # Calculate average attempts to first win per player
            # (sum of attempt_number for first wins / number of players who won)
            first_win_entries = [e for e in wins if e.get("is_first_win", False)]
            avg_attempts = (
                sum(e["attempt_number"] for e in first_win_entries) / len(first_win_entries) if first_win_entries else 0
            )

            # Average HP remaining on wins (as percentage)
            avg_hp_pct = 0.0
            if wins:
                hp_pcts = []
                for e in wins:
                    if e["player_max_hp"] > 0:
                        hp_pcts.append(e["player_hp_remaining"] / e["player_max_hp"])
                if hp_pcts:
                    avg_hp_pct = sum(hp_pcts) / len(hp_pcts)

            stats[mission_id] = {
                "name": mission_entries[0].get("mission_name", mission_id),
                "chapter": mission_entries[0].get("chapter_id", 0),
                "attempts": total,
                "wins": win_count,
                "losses": len(losses),
                "stalemates": len(stalemates),
                "win_rate": win_count / total if total > 0 else 0,
                "first_try_wins": len(first_try_wins),
                "first_try_rate": len(first_try_wins) / total if total > 0 else 0,
                "avg_attempts_to_win": round(avg_attempts, 1),
                "avg_win_duration": round(sum(e["duration"] for e in wins) / len(wins), 1) if wins else 0,
                "avg_loss_duration": round(sum(e["duration"] for e in losses) / len(losses), 1) if losses else 0,
                "avg_hp_remaining_pct": round(avg_hp_pct, 2),
                "avg_bots_used": round(sum(e["player_bots_count"] for e in mission_entries) / total, 1)
                if total > 0
                else 0,
            }

        return stats

    def prune(self, before: datetime) -> int:
        """
        Remove entries older than the given datetime.

        Args:
            before: Remove entries with timestamp before this (UTC)

        Returns:
            Number of entries removed
        """
        if not self.telemetry_file.exists():
            return 0

        # Read all entries
        entries = []
        removed = 0
        with open(self.telemetry_file, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = orjson.loads(line)
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if entry_time >= before:
                    entries.append(entry)
                else:
                    removed += 1

        # Rewrite file with remaining entries
        with open(self.telemetry_file, "wb") as f:
            for entry in entries:
                f.write(orjson.dumps(entry) + b"\n")

        log.info(f"Pruned {removed} telemetry entries older than {before.isoformat()}")
        return removed

    def wipe(self) -> int:
        """
        Delete all telemetry data.

        Returns:
            Number of entries deleted
        """
        if not self.telemetry_file.exists():
            return 0

        # Count entries first
        count = 0
        with open(self.telemetry_file, "rb") as f:
            for line in f:
                if line.strip():
                    count += 1

        # Delete file
        self.telemetry_file.unlink()
        log.info(f"Wiped {count} telemetry entries")
        return count

    def get_entry_count(self) -> int:
        """Get total number of telemetry entries."""
        if not self.telemetry_file.exists():
            return 0

        count = 0
        with open(self.telemetry_file, "rb") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
