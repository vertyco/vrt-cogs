import asyncio
import logging
import typing as t
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from inspect import iscoroutinefunction
from time import perf_counter

import discord
import openai
import orjson
from redbot.core import modlog

from ..abc import MixinMeta
from ..views import ModActionView
from .constants import (
    ARK_BAN_ACTION,
    ARK_TEMPBAN_ACTION,
    BUILTIN_MOD_ACTIONS,
    NO_ACTION_NEEDED,
    NOTE_ACTION,
    PROPOSE_MOD_ACTION,
    ModAction,
)
from .models import Conversation, GuildSettings


@dataclass
class ModActionRequest:
    """Everything an action handler needs to carry out a confirmed moderation action."""

    guild: discord.Guild
    flagged_message: discord.Message
    target: t.Union[discord.Member, discord.User]  # the offender
    reason: str
    actor: t.Union[discord.Member, discord.ClientUser]  # staff who clicked (or the bot for auto-action)
    duration_minutes: int = 0
    delete_message: bool = False


log = logging.getLogger("red.vrt.assistant.smartmod")

MODERATION_MODEL = "omni-moderation-latest"
# Categories absent from a guild's thresholds use this sentinel (never flags).
NEVER_FLAG = 1.1
# Discard repeat reviews for the same user within this many seconds.
REVIEW_COOLDOWN = 30.0
# Hard cap on review tool-loop turns.
MAX_REVIEW_ITERS = 10
EXEMPT_PERMS = ("ban_members", "kick_members", "manage_messages")


def smartmod_target_ids(message: discord.Message) -> set[int]:
    """All IDs a black/whitelist could match against for this message."""
    ids: set[int] = {message.author.id, message.channel.id}
    for attr in ("category_id", "parent_id"):
        value = getattr(message.channel, attr, None)
        if value:
            ids.add(value)
    ids.update(role.id for role in getattr(message.author, "roles", []))
    return ids


def smartmod_image_urls(message: discord.Message) -> list[str]:
    """Public URLs of image attachments on the message (for the omni-moderation image scan)."""
    urls = []
    for att in message.attachments:
        content_type = att.content_type or ""
        if content_type.startswith("image/"):
            urls.append(att.url)
    return urls


class SmartMod(MixinMeta):
    """AI moderation: free OpenAI moderation pre-filter -> LLM review -> staff action panel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # (guild_id, user_id) -> monotonic timestamp of last review start
        self.smartmod_cooldowns: dict[tuple[int, int], float] = {}
        # Strong refs to in-flight review tasks so the event loop can't GC them mid-run.
        self.smartmod_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Filtering / key resolution
    # ------------------------------------------------------------------
    def resolve_smartmod_key(self, conf: GuildSettings) -> t.Optional[str]:
        """OpenAI key for the moderation endpoint (OpenAI-only, no base_url).

        Uses the explicit smartmod override, else the guild's key when the chat
        endpoint is OpenAI itself. Returns None when no usable OpenAI key exists.
        """
        sm = conf.smartmod
        if sm.openai_key:
            return sm.openai_key
        if self.get_guild_endpoint_url(conf) is not None:
            # Chat endpoint is custom/non-OpenAI: its key won't work on OpenAI.
            return None
        key = self.get_api_key(conf)
        return key if key and key != "not-needed" else None

    def smartmod_passes_filters(self, message: discord.Message, conf: GuildSettings) -> bool:
        sm = conf.smartmod
        if not sm.enabled:
            return False
        if message.author.bot:
            return False
        has_text = bool(message.content and message.content.strip())
        if not has_text and not smartmod_image_urls(message):
            return False
        if self.resolve_smartmod_key(conf) is None:
            return False

        target_ids = smartmod_target_ids(message)
        if sm.blacklist:
            if target_ids & set(sm.blacklist):
                return False
        elif sm.whitelist and not (target_ids & set(sm.whitelist)):
            return False

        if sm.exempt_staff and isinstance(message.author, discord.Member):
            perms = message.author.guild_permissions
            if any(getattr(perms, flag, False) for flag in EXEMPT_PERMS):
                return False

        key = (message.guild.id, message.author.id)
        last = self.smartmod_cooldowns.get(key, 0.0)
        if perf_counter() - last < REVIEW_COOLDOWN:
            return False
        return True

    # ------------------------------------------------------------------
    # Stage 1: moderation scan
    # ------------------------------------------------------------------
    async def smartmod_score(
        self, content: str, conf: GuildSettings, image_urls: t.Optional[list[str]] = None
    ) -> t.Optional[dict[str, float]]:
        """Raw moderation scan of text (and optional images): max category score across all inputs.

        Returns ALL category scores (API names), or None on failure. Independent of the message
        filters/thresholds so it can also power the `[p]assistant smartmod test` command. Hits
        OpenAI directly (no base_url).
        """
        key = self.resolve_smartmod_key(conf)
        image_urls = image_urls or []
        if not key or (not content.strip() and not image_urls):
            return None
        try:
            client = openai.AsyncOpenAI(api_key=key)
            resp = await client.moderations.create(
                model=MODERATION_MODEL, input=self.build_moderation_input(content, image_urls)
            )
        except openai.AuthenticationError:
            log.warning("smartmod: OpenAI moderation key rejected; set a valid key with `smartmod key`")
            return None
        except Exception as e:
            log.warning("smartmod: moderation scan failed", exc_info=e)
            return None
        # A list input (text + each image) yields one result per item; the message as a whole is
        # flagged if ANY part trips, so take the max score per category. by_alias=True gives the
        # API category names ("harassment/threatening", "self-harm", ...).
        merged: dict[str, float] = {}
        for result in resp.results:
            for cat, score in result.category_scores.model_dump(by_alias=True).items():
                if score is not None and score > merged.get(cat, -1.0):
                    merged[cat] = score
        return merged or None

    def build_moderation_input(self, content: str, image_urls: list[str]) -> t.Union[str, list[dict]]:
        """Plain string for text-only; a multimodal list (text + image_url blocks) when images present."""
        if not image_urls:
            return content[:40000]
        items: list[dict] = []
        if content.strip():
            items.append({"type": "text", "text": content[:40000]})
        for url in image_urls[:10]:
            items.append({"type": "image_url", "image_url": {"url": url}})
        return items

    async def smartmod_scan(self, message: discord.Message, conf: GuildSettings) -> dict[str, float]:
        """Categories from the flagged message (text + image attachments) that meet/exceed their threshold."""
        scores = await self.smartmod_score(message.content, conf, smartmod_image_urls(message))
        if not scores:
            return {}
        thresholds = conf.smartmod.effective_thresholds()
        return {
            cat: score
            for cat, score in scores.items()
            if score is not None and score >= thresholds.get(cat, NEVER_FLAG)
        }

    async def run_smartmod(self, message: discord.Message, conf: GuildSettings) -> None:
        """Entry point scheduled by the listener: scan, then review on a hit."""
        tripped = await self.smartmod_scan(message, conf)
        if not tripped:
            return
        # Stamp the per-user review cooldown only AFTER a real trip, so a benign message
        # can't consume the window and let a later violation slip through unscanned.
        now = perf_counter()
        if len(self.smartmod_cooldowns) > 5000:
            cutoff = now - REVIEW_COOLDOWN
            self.smartmod_cooldowns = {k: v for k, v in self.smartmod_cooldowns.items() if v > cutoff}
        self.smartmod_cooldowns[(message.guild.id, message.author.id)] = now
        log.debug("smartmod flagged %s in %s: %s", message.author, message.guild, tripped)
        outcome = "error"
        try:
            outcome, _ = await self.smartmod_review(message, conf, tripped)
        except Exception as e:
            log.error("smartmod review failed for %s", message.author, exc_info=e)
        # Never silently drop a flagged message: if the model couldn't decide (loop exhausted,
        # endpoint without tool support, etc.) or errored, post a manual-review notice for staff.
        if outcome in ("no_decision", "error"):
            await self.notify_review_incomplete(message, conf, tripped)

    async def notify_review_incomplete(
        self, message: discord.Message, conf: GuildSettings, tripped: dict[str, float]
    ) -> None:
        """Fallback notice when the review model couldn't reach a decision, so staff still see the flag."""
        sm = conf.smartmod
        target = message.guild.get_channel(sm.report_channel) if sm.report_channel else None
        me = message.guild.me
        if not isinstance(target, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return
        if me is None or not target.permissions_for(me).send_messages:
            return
        cats = ", ".join(sorted(tripped))
        content = ""
        allowed = discord.AllowedMentions.none()
        if sm.staff_ping_roles:
            content = " ".join(f"<@&{rid}>" for rid in sm.staff_ping_roles)
            allowed = discord.AllowedMentions(roles=[discord.Object(id=rid) for rid in sm.staff_ping_roles])
        embed = discord.Embed(
            title="⚠️ Smartmod: manual review needed",
            description=(
                f"A message by {message.author.mention} tripped the filter ({cats}) but the review "
                f"model couldn't reach a decision.\n[Jump to message]({message.jump_url})"
            ),
            color=discord.Color.orange(),
        )
        try:
            await target.send(content=content or None, embed=embed, allowed_mentions=allowed)
        except discord.HTTPException as e:
            log.error("smartmod: failed to post manual-review notice", exc_info=e)

    # ------------------------------------------------------------------
    # Stage 2: LLM review
    # ------------------------------------------------------------------
    async def smartmod_review(
        self,
        message: discord.Message,
        conf: GuildSettings,
        tripped: dict[str, float],
        *,
        content: t.Optional[str] = None,
        dry_run: bool = False,
        output_channel: t.Optional[discord.abc.Messageable] = None,
    ) -> tuple[str, str]:
        """Run the review tool-loop. Returns ``(outcome, detail)`` where outcome is one of
        ``"proposed"`` | ``"no_action"`` | ``"no_decision"``.

        ``output_channel`` overrides where the panel is posted (None -> configured report
        channel); ``dry_run`` makes the resulting panel's buttons no-ops. Both are used by
        the admin simulation command.
        """
        flagged_content = content if content is not None else message.content
        if not flagged_content.strip() and smartmod_image_urls(message):
            flagged_content = "[image attachment]"
        flagged_cats = ", ".join(f"{c} ({tripped[c]:.2f})" for c in sorted(tripped))
        context_text = await self.build_smartmod_context(message, conf, flagged_content=flagged_content)
        messages = await self.build_review_messages(message, conf, flagged_cats, context_text, flagged_content)

        # Actions actually available here (built-ins + Ark/Notes when those cogs are loaded);
        # constrain the model's propose_mod_action enum to exactly these.
        available = await self.available_mod_actions(message.guild, message.author)
        propose_schema = deepcopy(PROPOSE_MOD_ACTION)
        propose_schema["parameters"]["properties"]["action"]["enum"] = [a.name for a in available]

        # Scope the reviewer's tools to what the BOT itself may use: the bot is never an
        # owner, so owner-only tools are excluded, without over-restricting to user-level.
        function_calls, function_map = await self.db.prep_functions(
            bot=self.bot, conf=conf, registry=self.registry, member=message.guild.me, showall=False
        )
        function_calls = [*function_calls, propose_schema, NO_ACTION_NEEDED]

        base_url = self.get_guild_endpoint_url(conf)
        supports_forced = base_url is None or "openrouter.ai" in base_url.lower()
        review_model = conf.smartmod.review_model or None

        seen_calls: dict[str, int] = {}
        for _ in range(MAX_REVIEW_ITERS):
            response = await self.request_response(
                messages=messages,
                conf=conf,
                functions=function_calls,
                member=None,
                model_override=review_model,
                temperature_override=0.0,
                tool_choice="required" if supports_forced else None,
                guild_id=message.guild.id,
            )
            tool_calls = response.tool_calls or ([response.function_call] if response.function_call else [])
            if not tool_calls:
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append(
                    {"role": "user", "content": "You must call either no_action_needed or propose_mod_action now."}
                )
                continue

            messages.append(self.dump_assistant_message(response))
            for call in tool_calls:
                name, args_str, tool_id = parse_tool_call(call)
                args = safe_json(args_str)
                if name == "no_action_needed":
                    reason = args.get("reason", "")
                    log.info("smartmod: no action for %s in %s: %s", message.author, message.guild, reason)
                    return "no_action", reason
                if name == "propose_mod_action":
                    await self.send_mod_panel(
                        message,
                        conf,
                        args,
                        tripped,
                        context_text,
                        available,
                        dry_run=dry_run,
                        channel=output_channel,
                    )
                    return "proposed", str(args.get("action", ""))
                key = f"{name}:{args_str}"
                seen_calls[key] = seen_calls.get(key, 0) + 1
                if seen_calls[key] > 2:
                    # Break a stuck loop: drop the repeated tool and push toward a terminal decision.
                    function_calls = [f for f in function_calls if f.get("name") != name]
                    function_map.pop(name, None)
                    loop_msg = {"role": "tool", "name": name, "content": f"Stop calling {name}; decide now."}
                    if tool_id:
                        loop_msg["tool_call_id"] = tool_id
                    messages.append(loop_msg)
                    continue
                result = await self.exec_review_tool(name, function_map.get(name), args, message, conf, messages)
                tool_msg = {"role": "tool", "name": name, "content": str(result)[:4000]}
                if tool_id:
                    tool_msg["tool_call_id"] = tool_id
                messages.append(tool_msg)

        log.info(
            "smartmod: review hit max iterations for %s in %s; defaulting to no action",
            message.author,
            message.guild,
        )
        return "no_decision", ""

    async def simulate_smartmod(
        self,
        message: discord.Message,
        conf: GuildSettings,
        tripped: dict[str, float],
        content: str,
        output_channel: discord.abc.Messageable,
    ) -> tuple[str, str]:
        """Dry-run the full review pipeline for an admin test.

        The model runs for real, but the resulting panel's buttons take no real action and
        any panel/output is posted to ``output_channel`` instead of the report channel.
        """
        return await self.smartmod_review(
            message, conf, tripped, content=content, dry_run=True, output_channel=output_channel
        )

    async def build_review_messages(
        self,
        message: discord.Message,
        conf: GuildSettings,
        flagged_cats: str,
        context_text: str,
        flagged_content: str,
    ) -> list[dict]:
        base_prompt = self.db.get_effective_system_prompt(conf)
        mod_prompt = conf.smartmod.mod_prompt.replace("{flagged_categories}", flagged_cats)
        messages: list[dict] = [{"role": "system", "content": f"{base_prompt}\n\n{mod_prompt}"}]

        rag_block = await self.build_review_rag(message, conf, flagged_content)
        if rag_block:
            messages.append({"role": "system", "content": f"Relevant server knowledge / rules:\n{rag_block}"})

        messages.append(
            {
                "role": "user",
                "content": (
                    f"FLAGGED MESSAGE\n"
                    f"Author: {message.author} (ID: {message.author.id})\n"
                    f"Channel: #{getattr(message.channel, 'name', message.channel.id)}\n"
                    f"Jump URL: {message.jump_url}\n"
                    f"Tripped categories: {flagged_cats}\n\n"
                    f"CONVERSATION CONTEXT (chronological; the flagged message is marked with >>>):\n{context_text}"
                ),
            }
        )
        return messages

    async def build_review_rag(self, message: discord.Message, conf: GuildSettings, query: str) -> str:
        if not conf.top_n or not query.strip():
            return ""
        try:
            if not await self.embedding_store.has_embeddings(message.guild.id):
                return ""
            embedding = await self.request_embedding(query, conf)
            related = await self.embedding_store.get_related(
                guild_id=message.guild.id,
                query_embedding=embedding,
                top_n=conf.top_n,
                min_relatedness=conf.min_relatedness,
            )
        except Exception as e:
            log.warning("smartmod: RAG lookup failed", exc_info=e)
            return ""
        return "\n\n".join(f"{name}:\n{text}" for name, text, *_ in related)

    async def build_smartmod_context(
        self, message: discord.Message, conf: GuildSettings, flagged_content: t.Optional[str] = None
    ) -> str:
        sm = conf.smartmod
        before = max(0, min(sm.context_before, 50))
        after = max(0, min(sm.context_after, 25))
        collected: list[discord.Message] = []
        try:
            older = [m async for m in message.channel.history(limit=before, before=message)]
            older.reverse()
            collected.extend(older)
            collected.append(message)
            if after:
                collected.extend([m async for m in message.channel.history(limit=after, after=message)])
        except discord.HTTPException as e:
            log.warning("smartmod: context fetch failed", exc_info=e)
            collected = [message]

        lines = []
        for msg in collected:
            is_flagged = msg.id == message.id
            marker = ">>> " if is_flagged else ""
            # For simulations the flagged "message" is the admin's command; show the test text instead.
            text = flagged_content if (is_flagged and flagged_content is not None) else (msg.content or "[no text]")
            lines.append(f"{marker}[{msg.author}]: {text}")
        return "\n".join(lines)

    async def exec_review_tool(
        self,
        name: str,
        func: t.Optional[t.Callable],
        args: dict,
        message: discord.Message,
        conf: GuildSettings,
        messages: list[dict],
    ) -> str:
        """Run an intermediate tool during review WITHOUT posting anything to the channel."""
        if func is None:
            return f"{name} is not an available tool."
        data = {
            # Tools run AS the bot during an autonomous review, not as the flagged offender.
            "user": message.guild.me or message.author,
            "channel": message.channel,
            "guild": message.guild,
            "bot": self.bot,
            "conf": conf,
            "messages": messages,
            "conversation": Conversation(),
            "message_obj": message,
        }
        try:
            if iscoroutinefunction(func):
                result = await func(**args, **data)
            else:
                result = await asyncio.to_thread(lambda: func(**args, **data))
        except Exception as e:
            log.warning("smartmod: tool %s failed during review", name, exc_info=e)
            return f"Tool {name} error: {e}"

        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return result.get("result_text") or result.get("content") or "[tool returned data]"
        if isinstance(result, bytes):
            return result.decode(errors="replace")
        if isinstance(result, (discord.Embed, discord.File)):
            return "[tool produced a file/embed; omitted during silent review]"
        return str(result)

    def dump_assistant_message(self, response) -> dict:
        # Strip null/empty SDK fields (refusal, annotations, audio, reasoning_content, empty
        # function_call/tool_calls, null content) so strict non-OpenAI endpoints don't reject
        # the assistant message when it's re-sent on the next review turn.
        dump = response.model_dump()
        dump.pop("reasoning_content", None)
        cleaned = {}
        for key, value in dump.items():
            if value is None:
                continue
            if key in ("function_call", "tool_calls") and not value:
                continue
            cleaned[key] = value
        return cleaned

    # ------------------------------------------------------------------
    # Action panel
    # ------------------------------------------------------------------
    async def send_mod_panel(
        self,
        message: discord.Message,
        conf: GuildSettings,
        proposal: dict,
        tripped: dict[str, float],
        context_text: str,
        available_actions: list[ModAction],
        *,
        dry_run: bool = False,
        channel: t.Optional[discord.abc.Messageable] = None,
    ) -> None:
        sm = conf.smartmod
        target = channel or (message.guild.get_channel(sm.report_channel) if sm.report_channel else None)
        me = message.guild.me
        if not isinstance(target, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            log.warning("smartmod: no usable report channel in %s; cannot post proposal", message.guild)
            return
        if me is None or not target.permissions_for(me).send_messages:
            log.warning("smartmod: missing send permission in report channel for %s", message.guild)
            return

        # Don't ping staff for a dry-run simulation.
        ping_roles = [] if dry_run else list(sm.staff_ping_roles)
        view = ModActionView(
            cog=self,
            flagged_message=message,
            proposal=proposal,
            tripped=tripped,
            context_text=context_text,
            available_actions=available_actions,
            staff_ping_roles=ping_roles,
            timeout=float(sm.action_timeout),
            auto_action_on_timeout=sm.auto_action_on_timeout,
            dry_run=dry_run,
        )
        view.build_layout()
        allowed = discord.AllowedMentions.none()
        if ping_roles:
            allowed = discord.AllowedMentions(roles=[discord.Object(id=rid) for rid in ping_roles])
        try:
            view.message = await target.send(view=view, allowed_mentions=allowed)
        except discord.HTTPException as e:
            log.error("smartmod: failed to send mod panel", exc_info=e)

    # ------------------------------------------------------------------
    # Action catalog + execution
    # ------------------------------------------------------------------
    async def available_mod_actions(
        self, guild: discord.Guild, target: t.Union[discord.Member, discord.User]
    ) -> list[ModAction]:
        """Actions offered for this target here: built-ins, plus Ark/Notes when those cogs are loaded."""
        actions = list(BUILTIN_MOD_ACTIONS)
        arktools = self.bot.get_cog("ArkTools")
        if arktools is not None and isinstance(target, discord.Member):
            try:
                players = await arktools.db_utils.search_players(guild, target)
            except Exception as e:
                log.debug("smartmod: ArkTools player lookup failed", exc_info=e)
                players = []
            if players:
                actions += [ARK_BAN_ACTION, ARK_TEMPBAN_ACTION]
        if self.bot.get_cog("ModNotes") is not None:
            actions.append(NOTE_ACTION)
        return actions

    async def execute_mod_action(
        self,
        action: str,
        *,
        guild: discord.Guild,
        flagged_message: discord.Message,
        target: t.Union[discord.Member, discord.User],
        reason: str,
        actor: t.Union[discord.Member, discord.ClientUser],
        duration_minutes: int = 0,
        delete_message: bool = False,
    ) -> tuple[str, bool]:
        """Carry out a staff-confirmed action. Returns (outcome_text, success). Never raises."""
        req = ModActionRequest(
            guild=guild,
            flagged_message=flagged_message,
            target=target,
            reason=reason or "No reason provided.",
            actor=actor,
            duration_minutes=duration_minutes,
            delete_message=delete_message,
        )
        handlers = {
            "warn": self.action_warn,
            "timeout": self.action_timeout,
            "kick": self.action_kick,
            "tempban": self.action_tempban,
            "ban": self.action_ban,
            "delete": self.action_delete,
            "ark_ban": self.action_ark_ban,
            "ark_tempban": self.action_ark_tempban,
            "note": self.action_note,
        }
        handler = handlers.get(action)
        if handler is None:
            return f"Unknown action: {action}", False
        try:
            text, ok = await handler(req)
        except discord.Forbidden:
            return f"❌ Missing permission or role hierarchy for {action}.", False
        except discord.HTTPException as e:
            return f"❌ {action} failed: {e}", False
        except Exception as e:
            log.error("smartmod: action %s failed unexpectedly", action, exc_info=e)
            return f"❌ {action} failed unexpectedly: {e}", False
        # Discord (temp)bans already purge messages via delete_message_seconds; for the rest,
        # honor delete_message by removing the flagged message after a successful action.
        if ok and delete_message and action not in ("delete", "ban", "tempban"):
            with suppress(discord.HTTPException):
                await flagged_message.delete()
        return text, ok

    def resolve_duration(self, req: "ModActionRequest", default_minutes: int) -> int:
        try:
            minutes = int(req.duration_minutes) if req.duration_minutes else default_minutes
        except (ValueError, TypeError):
            minutes = default_minutes
        return max(1, minutes)

    async def action_delete(self, req: "ModActionRequest") -> tuple[str, bool]:
        await req.flagged_message.delete()
        return "🗑️ Message deleted.", True

    async def action_timeout(self, req: "ModActionRequest") -> tuple[str, bool]:
        member = req.guild.get_member(req.target.id)
        if member is None:
            return "⚠️ That user is no longer in the server.", False
        minutes = min(self.resolve_duration(req, 10), 40320)  # Discord cap: 28 days
        await member.timeout(timedelta(minutes=minutes), reason=req.reason)
        return f"⏳ {member} timed out for {minutes} min.\n-# {req.reason}", True

    async def action_kick(self, req: "ModActionRequest") -> tuple[str, bool]:
        member = req.guild.get_member(req.target.id)
        if member is None:
            return "⚠️ That user is no longer in the server.", False
        await member.kick(reason=req.reason)
        return f"👢 {member} was kicked.\n-# {req.reason}", True

    async def action_ban(self, req: "ModActionRequest") -> tuple[str, bool]:
        seconds = 86400 if req.delete_message else 0
        await req.guild.ban(req.target, reason=req.reason, delete_message_seconds=seconds)
        return f"🔨 {req.target} was banned.\n-# {req.reason}", True

    async def action_tempban(self, req: "ModActionRequest") -> tuple[str, bool]:
        minutes = self.resolve_duration(req, 1440)
        seconds = 86400 if req.delete_message else 0
        await req.guild.ban(req.target, reason=req.reason, delete_message_seconds=seconds)
        unban_at = datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
        self.scheduler.add_job(
            self.smartmod_unban,
            "date",
            run_date=unban_at,
            args=[req.guild.id, req.target.id, req.reason],
            id=f"smartmod_unban_{req.guild.id}_{req.target.id}",
            replace_existing=True,
        )
        return f"⏲️ {req.target} temp-banned for {minutes} min (auto-unban scheduled).\n-# {req.reason}", True

    async def smartmod_unban(self, guild_id: int, user_id: int, reason: str) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        with suppress(discord.HTTPException):
            await guild.unban(discord.Object(id=user_id), reason=f"Smartmod temp-ban expired: {reason}"[:500])

    async def action_warn(self, req: "ModActionRequest") -> tuple[str, bool]:
        member = req.guild.get_member(req.target.id)
        warnings_cog = self.bot.get_cog("Warnings")
        if warnings_cog is not None and member is not None:
            try:
                member_conf = warnings_cog.config.member(member)
                async with member_conf.warnings() as warns:
                    warns[str(req.flagged_message.id)] = {
                        "points": 1,
                        "description": req.reason,
                        "mod": getattr(req.actor, "id", 0),
                    }
                await member_conf.total_points.set(await member_conf.total_points() + 1)
                await modlog.create_case(
                    self.bot,
                    req.guild,
                    datetime.now(tz=timezone.utc),
                    "warning",
                    member,
                    req.actor,
                    req.reason,
                    until=None,
                    channel=None,
                )
                return f"📣 Warned {member} (1 pt via Red Warnings).\n-# {req.reason}", True
            except Exception as e:
                log.warning("smartmod: Red Warnings warn failed, falling back to DM", exc_info=e)
        if member is not None:
            try:
                await member.send(f"⚠️ Warning from {req.guild.name}: {req.reason}")
                return f"📣 Warned {member} via DM.\n-# {req.reason}", True
            except discord.HTTPException:
                return "⚠️ Warning recorded but the user's DMs are closed.", True
        return "⚠️ Couldn't warn: the Warnings cog isn't loaded and the user isn't in the server.", False

    async def action_note(self, req: "ModActionRequest") -> tuple[str, bool]:
        modnotes = self.bot.get_cog("ModNotes")
        if modnotes is None or not hasattr(modnotes, "api"):
            return "⚠️ ModNotes cog not available.", False
        await modnotes.api.create_note(req.guild, req.target, req.actor, req.reason)
        return f"📝 Note added for {req.target}.\n-# {req.reason}", True

    async def action_ark_ban(self, req: "ModActionRequest") -> tuple[str, bool]:
        return await self.do_ark_ban(req, temp=False)

    async def action_ark_tempban(self, req: "ModActionRequest") -> tuple[str, bool]:
        return await self.do_ark_ban(req, temp=True)

    async def do_ark_ban(self, req: "ModActionRequest", temp: bool) -> tuple[str, bool]:
        arktools = self.bot.get_cog("ArkTools")
        if arktools is None:
            return "⚠️ ArkTools cog not loaded.", False
        member = req.guild.get_member(req.target.id) or req.target
        players = await arktools.db_utils.search_players(req.guild, member)
        if not players:
            return f"⚠️ No linked ARK player found for {req.target}.", False
        banned_until = None
        if temp:
            banned_until = datetime.now(tz=timezone.utc) + timedelta(minutes=self.resolve_duration(req, 1440))
        ok_any = False
        for player in players:
            result = await arktools.ban_unban_player(
                guild=req.guild,
                gameid=player.gameid,
                ban=True,
                reason=req.reason,
                ctx=None,
                banned_until=banned_until,
            )
            if result:
                ok_any = True
                if temp:
                    arktools.delay_unban_player(
                        guild_id=req.guild.id,
                        gameid=player.gameid,
                        banned_until=banned_until,
                        original_reason=req.reason,
                    )
        if not ok_any:
            return "❌ ArkTools ban failed (check the bot logs).", False
        ids = ", ".join(p.gameid for p in players)
        verb = "temp-banned" if temp else "banned"
        return f"🦖 ARK {verb} {req.target} ({ids}).\n-# {req.reason}", True


def parse_tool_call(call) -> tuple[str, str, t.Optional[str]]:
    """Normalize FunctionCall / ChatCompletionMessageToolCall into (name, arguments, tool_id)."""
    if hasattr(call, "function") and hasattr(call, "id"):
        return call.function.name, call.function.arguments, call.id
    return call.name, call.arguments, None


def safe_json(raw: t.Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        parsed = orjson.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except orjson.JSONDecodeError:
        return {}
