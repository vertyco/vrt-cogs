import inspect
import json
import logging
from abc import ABC
from datetime import datetime, timedelta, timezone

import discord
from redbot.core import modlog

from .abc import MixinMeta

log = logging.getLogger("red.vrt.vrtutils.rpc")

# Discord's hard ceiling on a single timeout.
MAX_TIMEOUT_SECONDS = 28 * 24 * 60 * 60


class RPCMethods(MixinMeta, ABC):
    """Localhost JSON-RPC surface for ops automation.

    Red only serves these when started with --rpc, and the socket is bound to
    localhost, which is the access control: reaching it at all means shell on the
    box. Nothing here is exposed to guild users.

    The moderation methods deliberately reimplement what the stock Warnings/Mod
    command callbacks do rather than invoking the commands. Those callbacks need a
    discord Context built from a real Message, which an RPC caller does not have.
    The underlying work (config write, modlog case, DM) needs no ctx, so calling it
    directly is the honest path; the resulting cases are indistinguishable from
    ones a human moderator made and `[p]unwarn` / `[p]listcases` operate on them
    normally.

    Every mutating method takes an explicit `moderator_id`. Cases attribute to
    whoever the caller names, so the caller is responsible for naming itself and
    not borrowing a human's identity.
    """

    @property
    def _rpc_handlers(self) -> tuple:
        # Single source of truth so cog_load registers and cog_unload unregisters
        # the same set. register_rpc_handler raises on a duplicate name, so without
        # the matching unregister a reload (the old instance never cleans up) aborts
        # and the handler keeps serving stale code until a full restart. Unregister-
        # first on load lets a plain reload swap the handlers live, no reboot.
        return (
            self.rpc_quickpull,
            self.rpc_master,
            self.rpc_warn,
            self.rpc_unwarn,
            self.rpc_get_warnings,
            self.rpc_get_cases,
            self.rpc_timeout,
            self.rpc_untimeout,
            self.rpc_modnote,
        )

    # ------------------------------------------------------------------ helpers

    def _resolve(self, guild_id: int, user_id: int) -> tuple:
        """-> (guild, member, error_dict). Exactly one of member/error is None."""
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return None, None, {"ok": False, "error": f"guild not found: {guild_id}"}
        member = guild.get_member(int(user_id))
        if member is None:
            return guild, None, {"ok": False, "error": f"member not in guild: {user_id}"}
        return guild, member, None

    def _guard(self, guild: discord.Guild, member: discord.Member) -> dict:
        """Shared refusals. Mirrors the stock command checks minus the ctx ones."""
        if member.bot:
            return {"ok": False, "error": "target is a bot"}
        if member == guild.owner:
            return {"ok": False, "error": "target is the guild owner"}
        return None

    @staticmethod
    def _case_out(case) -> dict:
        return {
            "case_number": getattr(case, "case_number", None),
            "action_type": getattr(case, "action_type", None),
            "reason": getattr(case, "reason", None),
            "user_id": getattr(getattr(case, "user", None), "id", None),
            "moderator_id": getattr(getattr(case, "moderator", None), "id", None),
            "created_at": getattr(case, "created_at", None),
            "until": getattr(case, "until", None),
        }

    async def _mod_object(self, moderator_id: int):
        """A user object for the moderator, or a bare Object if we can't see them."""
        if moderator_id is None:
            return None
        moderator_id = int(moderator_id)
        return self.bot.get_user(moderator_id) or discord.Object(id=moderator_id)

    # -------------------------------------------------------------- moderation

    async def rpc_warn(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        reason: str,
        points: int = 1,
    ) -> dict:
        """Warn a member. RPC equivalent of [p]warn, same records, no ctx.

        Writes the Warnings member config entry, DMs the member if the guild has
        DMs enabled, posts to the warn channel if that is enabled, and files a
        `warning` modlog case. The config key is a generated snowflake so that
        `[p]unwarn <user> <key>` works exactly as it does for a real warning.

        Registered guild reasons win over the free-text reason when the string
        matches one (same precedence as the command). Automated warn actions are
        NOT executed - those are command macros needing a ctx to invoke - but if
        the new point total crosses a configured threshold it is reported back in
        `action_pending` so the caller can run it by hand.
        """
        warnings_cog = self.bot.get_cog("Warnings")
        if warnings_cog is None:
            return {"ok": False, "error": "Warnings cog not loaded"}
        guild, member, err = self._resolve(guild_id, user_id)
        if err:
            return err
        if err := self._guard(guild, member):
            return err
        if int(moderator_id) == member.id:
            return {"ok": False, "error": "moderator and target are the same user"}
        points = int(points)

        config = warnings_cog.config
        guild_settings = await config.guild(guild).all()
        async with config.guild(guild).reasons() as registered:
            reason_type = registered.get(str(reason).lower())
        if reason_type is None:
            if not guild_settings["allow_custom_reasons"]:
                return {
                    "ok": False,
                    "error": "custom reasons are disabled and this is not a registered reason",
                    "registered": sorted(registered),
                }
            if points < 0:
                return {"ok": False, "error": "cannot apply negative points"}
            reason_type = {"description": str(reason), "points": points}

        now = datetime.now(timezone.utc)
        # Stock warn keys off ctx.message.id; a time-based snowflake keeps the key
        # shape (and therefore unwarn) identical without a message to key off.
        warn_key = str(discord.utils.time_snowflake(now))
        moderator = await self._mod_object(moderator_id)

        dm_failed = False
        if guild_settings["toggle_dm"]:
            title = "Warning"
            if guild_settings["show_mod"]:
                title = f"Warning from {moderator}"
            em = discord.Embed(
                title=title,
                description=reason_type["description"],
                color=await self.bot.get_embed_color(member),
            )
            em.add_field(name="Points", value=str(reason_type["points"]))
            try:
                await member.send(f"You have received a warning in {guild.name}.", embed=em)
            except discord.HTTPException:
                dm_failed = True

        member_settings = config.member(member)
        async with member_settings.warnings() as user_warnings:
            user_warnings[warn_key] = {
                "points": reason_type["points"],
                "description": reason_type["description"],
                "mod": int(moderator_id),
            }
        total = await member_settings.total_points() + reason_type["points"]
        await member_settings.total_points.set(total)

        # Actions are command macros (they need a ctx to invoke); surface instead.
        action_pending = None
        for action in guild_settings["actions"]:
            if total >= action["points"]:
                action_pending = action
                break

        if guild_settings["toggle_channel"]:
            channel = self.bot.get_channel(guild_settings["warn_channel"])
            if channel and channel.permissions_for(guild.me).send_messages:
                em = discord.Embed(
                    title="Warning from {}".format(moderator) if guild_settings["show_mod"] else "Warning",
                    description=reason_type["description"],
                    color=await self.bot.get_embed_color(channel),
                )
                em.add_field(name="Points", value=str(reason_type["points"]))
                try:
                    await channel.send(f"{member.mention} has been warned.", embed=em)
                except discord.HTTPException:
                    pass

        reason_msg = (
            f"{reason_type['description']}\nPoints: {reason_type['points']}"
            f"\n\nUse `[p]unwarn {member.id} {warn_key}` to remove this warning."
        )
        case = await modlog.create_case(
            self.bot,
            guild,
            now,
            "warning",
            member,
            moderator,
            reason_msg,
            until=None,
            channel=None,
        )
        return {
            "ok": True,
            "warning_id": warn_key,
            "user_id": member.id,
            "points": reason_type["points"],
            "total_points": total,
            "dm_sent": guild_settings["toggle_dm"] and not dm_failed,
            "dm_failed": dm_failed,
            "action_pending": action_pending,
            "case": self._case_out(case) if case else None,
        }

    async def rpc_unwarn(
        self,
        guild_id: int,
        user_id: int,
        warning_id: str,
        moderator_id: int,
        reason: str = None,
    ) -> dict:
        """Remove a warning by its id. RPC equivalent of [p]unwarn."""
        warnings_cog = self.bot.get_cog("Warnings")
        if warnings_cog is None:
            return {"ok": False, "error": "Warnings cog not loaded"}
        guild, member, err = self._resolve(guild_id, user_id)
        if err:
            return err
        config = warnings_cog.config
        member_settings = config.member(member)
        async with member_settings.warnings() as user_warnings:
            if str(warning_id) not in user_warnings:
                return {
                    "ok": False,
                    "error": f"no warning {warning_id} for this member",
                    "warning_ids": sorted(user_warnings),
                }
            removed = user_warnings.pop(str(warning_id))
        total = max(0, await member_settings.total_points() - removed["points"])
        await member_settings.total_points.set(total)
        case = await modlog.create_case(
            self.bot,
            guild,
            datetime.now(timezone.utc),
            "unwarned",
            member,
            await self._mod_object(moderator_id),
            reason or f"Warning {warning_id} removed",
            until=None,
            channel=None,
        )
        return {
            "ok": True,
            "removed": removed,
            "total_points": total,
            "case": self._case_out(case) if case else None,
        }

    async def rpc_get_warnings(self, guild_id: int, user_id: int) -> dict:
        """List a member's active warnings and point total. [p]warnings, as data."""
        warnings_cog = self.bot.get_cog("Warnings")
        if warnings_cog is None:
            return {"ok": False, "error": "Warnings cog not loaded"}
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return {"ok": False, "error": f"guild not found: {guild_id}"}
        # Works for members who have left: config.member_from_ids needs no member object.
        member_settings = warnings_cog.config.member_from_ids(int(guild_id), int(user_id))
        user_warnings = await member_settings.warnings()
        return {
            "ok": True,
            "user_id": int(user_id),
            "total_points": await member_settings.total_points(),
            "warnings": [
                {
                    "id": key,
                    "points": data.get("points"),
                    "description": data.get("description"),
                    "moderator_id": data.get("mod"),
                }
                for key, data in user_warnings.items()
            ],
        }

    async def rpc_get_cases(self, guild_id: int, user_id: int, limit: int = 0) -> dict:
        """Every modlog case filed against a member, oldest first. [p]listcases, as data.

        Reads through Red's own modlog API rather than the JSON store on disk, so
        it stays correct if the backend ever changes and never sees a half-written
        file.
        """
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return {"ok": False, "error": f"guild not found: {guild_id}"}
        try:
            cases = await modlog.get_cases_for_member(guild=guild, bot=self.bot, member_id=int(user_id))
        except discord.HTTPException as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out = [self._case_out(c) for c in cases]
        out.sort(key=lambda c: c["case_number"] or 0)
        if limit:
            out = out[-int(limit) :]
        return {"ok": True, "user_id": int(user_id), "count": len(out), "cases": out}

    async def rpc_timeout(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        duration_seconds: int,
        reason: str = None,
    ) -> dict:
        """Apply a native Discord timeout and file a modlog case.

        Discord caps a timeout at 28 days; anything longer is refused rather than
        silently clamped. Files a `timeout` case (registered by this cog on load).
        """
        guild, member, err = self._resolve(guild_id, user_id)
        if err:
            return err
        if err := self._guard(guild, member):
            return err
        duration_seconds = int(duration_seconds)
        if duration_seconds <= 0:
            return {"ok": False, "error": "duration must be positive"}
        if duration_seconds > MAX_TIMEOUT_SECONDS:
            return {
                "ok": False,
                "error": f"duration exceeds Discord's 28 day ceiling ({MAX_TIMEOUT_SECONDS}s)",
            }
        if not guild.me.guild_permissions.moderate_members:
            return {"ok": False, "error": "bot lacks moderate_members"}
        if member.top_role >= guild.me.top_role:
            return {"ok": False, "error": "target is equal or above the bot in the role hierarchy"}

        now = datetime.now(timezone.utc)
        until = now + timedelta(seconds=duration_seconds)
        try:
            await member.timeout(until, reason=reason)
        except discord.HTTPException as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        case = await modlog.create_case(
            self.bot,
            guild,
            now,
            "timeout",
            member,
            await self._mod_object(moderator_id),
            reason,
            until=until,
            channel=None,
        )
        return {
            "ok": True,
            "user_id": member.id,
            "until": until.isoformat(),
            "duration_seconds": duration_seconds,
            "case": self._case_out(case) if case else None,
        }

    async def rpc_untimeout(self, guild_id: int, user_id: int, moderator_id: int, reason: str = None) -> dict:
        """Lift a timeout early and file the matching case."""
        guild, member, err = self._resolve(guild_id, user_id)
        if err:
            return err
        if member.timed_out_until is None:
            return {"ok": False, "error": "member is not timed out"}
        try:
            await member.timeout(None, reason=reason)
        except discord.HTTPException as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        case = await modlog.create_case(
            self.bot,
            guild,
            datetime.now(timezone.utc),
            "untimeout",
            member,
            await self._mod_object(moderator_id),
            reason,
            until=None,
            channel=None,
        )
        return {"ok": True, "user_id": member.id, "case": self._case_out(case) if case else None}

    async def rpc_modnote(self, guild_id: int, user_id: int, moderator_id: int, note: str) -> dict:
        """File a `Mod Note` case against a user. No DM, no punishment, just the record."""
        guild = self.bot.get_guild(int(guild_id))
        if guild is None:
            return {"ok": False, "error": f"guild not found: {guild_id}"}
        target = guild.get_member(int(user_id)) or self.bot.get_user(int(user_id)) or discord.Object(id=int(user_id))
        case = await modlog.create_case(
            self.bot,
            guild,
            datetime.now(timezone.utc),
            "Mod Note",
            target,
            await self._mod_object(moderator_id),
            str(note),
            until=None,
            channel=None,
        )
        return {"ok": True, "user_id": int(user_id), "case": self._case_out(case) if case else None}

    # -------------------------------------------------------------- bot control

    async def rpc_master(self, cog: str, method: str, args: list = None, kwargs: dict = None) -> dict:
        """Generic bot-control bridge: read or call any attribute on a loaded cog (or the bot).

        One RPC endpoint instead of one handler per feature. Pass cog="bot" to
        target the Red bot object; the cog name match is case-insensitive. `method`
        may be a dotted path to walk nested attributes (e.g. "db.get_conf"); the
        leaf is called with args/kwargs when callable, otherwise its value is
        returned (so the bridge reads attributes, not just calls methods). On a miss
        it reports the loaded cogs / available members. Args/kwargs must be JSON
        values; the result comes back as-is when JSON-serializable, else as repr().
        Localhost binding is the access control, same as quickpull. Ops automation
        only, nothing here is reachable by guild users.
        """
        args = args or []
        kwargs = kwargs or {}
        # Resolve the target cog (case-insensitive) or the bot object.
        if cog.lower() == "bot":
            target = self.bot
        else:
            target = self.bot.get_cog(cog)
            if target is None:
                match = next((c for c in self.bot.cogs if c.lower() == cog.lower()), None)
                target = self.bot.get_cog(match) if match else None
        if target is None:
            return {"ok": False, "error": f"cog not loaded: {cog}", "loaded_cogs": sorted(self.bot.cogs)}
        # Walk a (possibly dotted) attribute path; the leaf is read or called.
        obj = target
        path = method.split(".")
        for i, seg in enumerate(path):
            if not hasattr(obj, seg):
                where = ".".join([cog, *path[:i]])
                members = sorted(m for m in dir(obj) if not m.startswith("_"))
                return {"ok": False, "error": f"no attribute '{seg}' on {where}", "available": members}
            obj = getattr(obj, seg)
        # Leaf: call if callable, else return the value as-is.
        try:
            if callable(obj):
                result = obj(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
            else:
                result = obj
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            json.dumps(result)
            return {"ok": True, "result": result}
        except (TypeError, ValueError):
            return {"ok": True, "result": repr(result)}

    async def rpc_quickpull(self, cogs: list, repo_name: str = "vrt-cogs") -> dict:
        """Update a downloader repo and reinstall + reload the given cogs.

        RPC equivalent of [p]quickpull (no dependency installs). Localhost
        binding is the access control. If 'vrtutils' itself is in the list,
        reload it via a separate call last; reloading the cog that owns this
        handler may drop the response.
        """
        downloader = self.bot.get_cog("Downloader")
        if downloader is None:
            return {"ok": False, "stage": "downloader", "output": "Downloader cog not loaded"}
        core = self.bot.get_cog("Core")
        if core is None:
            return {"ok": False, "stage": "reload", "output": "Core cog not loaded"}

        repo, (old_commit, new_commit) = await downloader._repo_manager.update_repo(repo_name)
        wanted = {str(c) for c in cogs}
        available = {cog.name: cog for cog in repo.available_cogs}
        missing = sorted(wanted - set(available))
        if missing:
            return {"ok": False, "stage": "lookup", "output": f"not in repo '{repo_name}': {missing}"}

        targets = [available[name] for name in sorted(wanted)]
        installed, failed = await downloader._install_cogs(targets)
        if installed:
            await downloader._save_to_installed(installed)
        reload_results = await core._reload([m.name for m in installed])
        return {
            "ok": not failed,
            "repo": repo_name,
            "old_commit": old_commit,
            "new_commit": new_commit,
            "installed": [m.name for m in installed],
            "failed": [c.name for c in failed],
            "reload": reload_results,
        }
