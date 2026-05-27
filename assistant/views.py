import asyncio
import inspect
import json
import logging
import re
from contextlib import suppress
from typing import Awaitable, Callable, Dict, List, Optional, Set, Tuple

import discord
import json5
from rapidfuzz import fuzz
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, pagify, text_to_file

from .common.constants import ModAction
from .common.models import (
    DB,
    CustomFunction,
    EndpointProfile,
    GuildSettings,
    get_category_state,
    normalize_tool_category,
    render_tool_category,
)
from .common.utils import (
    DYNAMIC_VARIABLE_GROUP_LABELS,
    DYNAMIC_VARIABLE_GROUPS,
    DYNAMIC_VARIABLE_NAMES,
    STABLE_VARIABLE_GROUP_LABELS,
    STABLE_VARIABLE_GROUPS,
    VARIABLE_NARRATIVES,
    code_string_valid,
    extract_code_blocks,
    get_attachments,
    json_schema_invalid,
    wait_message,
)

log = logging.getLogger("red.vrt.assistant.views")
_ = Translator("Assistant", __file__)
ON_EMOJI = "🟢"
OFF_EMOJI = "🔴"
MIXED_EMOJI = "🟡"
STATE_EMOJIS = {
    "on": ON_EMOJI,
    "off": OFF_EMOJI,
    "mixed": MIXED_EMOJI,
}
MAX_SELECT_OPTION_DESCRIPTION = 100


def format_tool_option_description(entry: dict) -> str:
    source = entry["source"] if entry["source"] != "Custom" else _("Custom")
    description = entry.get("schema", {}).get("description", "")
    cleaned = re.sub(r"\s+", " ", description).strip()
    combined = f"{source} - {cleaned}" if cleaned else source
    if len(combined) <= MAX_SELECT_OPTION_DESCRIPTION:
        return combined
    return combined[: MAX_SELECT_OPTION_DESCRIPTION - 3].rstrip() + "..."


class APIModal(discord.ui.Modal):
    def __init__(self, key: str = None):
        self.key = key
        super().__init__(title=_("Set API Key"), timeout=120)
        self.field = discord.ui.TextInput(
            label=_("Enter your API Key below"),
            style=discord.TextStyle.short,
            default=self.key,
            required=False,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.key = self.field.value
        await interaction.response.defer()
        self.stop()


class SetAPI(discord.ui.View):
    def __init__(self, author: discord.Member, key: str = None):
        self.author = author
        self.key = key
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Set API Key", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        modal = APIModal(key=self.key)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.key = modal.key
        if modal.key:
            self.stop()


class AdminToolApprovalView(discord.ui.View):
    def __init__(self, author_id: int, timeout: float = 120):
        self.author_id = author_id
        self.decision: str = "timeout"
        self.message: Optional[discord.Message] = None
        super().__init__(timeout=timeout)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(_("This approval prompt isn't for you!"), ephemeral=True)
            return False
        return True

    def disable_all(self) -> None:
        for item in self.children:
            item.disabled = True

    async def on_timeout(self):
        self.disable_all()
        with suppress(discord.HTTPException):
            if self.message is not None:
                await self.message.edit(view=self)
        return await super().on_timeout()

    async def finish(self, interaction: discord.Interaction, decision: str):
        self.decision = decision
        self.disable_all()
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Approve Once", style=discord.ButtonStyle.primary)
    async def approve_once(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.finish(interaction, "once")

    @discord.ui.button(label="Allow This Session", style=discord.ButtonStyle.success)
    async def allow_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.finish(interaction, "session")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.finish(interaction, "skip")


# ---------------------------------------------------------------------------
# Smartmod (AI moderation) action panel
# ---------------------------------------------------------------------------
# Actions rendered with a red (destructive) accent.
HEAVY_MOD_ACTIONS = {"ban", "tempban", "ark_ban", "ark_tempban"}


class ModReasonModal(discord.ui.Modal):
    def __init__(self, view: "ModActionView", action: str, default_reason: str):
        super().__init__(title=_("Confirm: {}").format(action.title())[:45], timeout=300)
        self.view_ref = view
        self.action = action
        self.field = discord.ui.TextInput(
            label=_("Reason (blank = use AI's reason)"),
            style=discord.TextStyle.paragraph,
            default=default_reason[:512],
            required=False,
            max_length=512,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        reason = self.field.value.strip() or self.view_ref.proposal_reason
        await self.view_ref.execute_and_finalize(interaction, self.action, reason, via_modal=True)


class ModActionButton(discord.ui.Button):
    def __init__(self, action: str, label: str, style: discord.ButtonStyle, emoji: Optional[str] = None):
        super().__init__(label=label[:80], style=style, emoji=emoji)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_action(interaction, self.action)


class ModActionSelect(discord.ui.Select):
    """Dropdown of every action available on this server (built-ins + Ark/Notes)."""

    def __init__(self, actions: List[ModAction]):
        options = [discord.SelectOption(label=a.label[:100], value=a.name, emoji=a.emoji or None) for a in actions[:25]]
        super().__init__(placeholder=_("Choose a different action…"), min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_action(interaction, self.values[0])


class ModActionView(discord.ui.LayoutView):
    """Interactive staff panel proposing a moderation action suggested by the LLM."""

    def __init__(
        self,
        cog,
        flagged_message: discord.Message,
        proposal: dict,
        tripped: Dict[str, float],
        context_text: str = "",
        available_actions: Optional[List[ModAction]] = None,
        staff_ping_roles: Optional[List[int]] = None,
        timeout: float = 3600,
        auto_action_on_timeout: bool = False,
        dry_run: bool = False,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.flagged_message = flagged_message
        self.proposal = proposal
        self.tripped = tripped
        self.context_text = context_text
        self.available_actions = available_actions or []
        self.actions_by_name: Dict[str, ModAction] = {a.name: a for a in self.available_actions}
        self.staff_ping_roles = staff_ping_roles or []
        self.auto_action_on_timeout = auto_action_on_timeout
        self.dry_run = dry_run
        proposed = proposal.get("action", "")
        if proposed not in self.actions_by_name:
            proposed = self.available_actions[0].name if self.available_actions else proposed
        self.proposed_action = proposed
        self.proposal_reason = proposal.get("reason", "") or _("No reason provided.")
        self.message: Optional[discord.Message] = None
        self.resolved = False
        self.outcome_text = ""

    # ---------------- layout ----------------
    def build_layout(self) -> None:
        self.clear_items()
        action = self.proposed_action
        severity = str(self.proposal.get("severity", "?")).title()
        cats = ", ".join(f"{c} ({self.tripped[c]:.2f})" for c in sorted(self.tripped))
        author = self.flagged_message.author
        spec = self.actions_by_name.get(action)
        emoji = spec.emoji if spec else "⚠️"
        action_label = spec.label if spec else action.title()

        accent = (
            discord.Color.purple()
            if self.dry_run
            else (discord.Color.red() if action in HEAVY_MOD_ACTIONS else discord.Color.orange())
        )
        container = discord.ui.Container(accent_colour=accent)
        if self.dry_run:
            container.add_item(discord.ui.TextDisplay(_("# 🧪 SIMULATION — dry run")))
            container.add_item(discord.ui.TextDisplay(_("-# Buttons take no real action; this is a test.")))
        if self.staff_ping_roles and not self.resolved:
            container.add_item(discord.ui.TextDisplay(" ".join(f"<@&{rid}>" for rid in self.staff_ping_roles)))
        container.add_item(discord.ui.TextDisplay(_("# ⚠️ Proposed Moderation Action")))
        container.add_item(
            discord.ui.TextDisplay(
                _("**Suggested:** {emoji} {action} • **Severity:** {sev}").format(
                    emoji=emoji, action=action_label, sev=severity
                )
            )
        )
        container.add_item(
            discord.ui.TextDisplay(
                _("**User:** {mention} `{uid}`\n**Message:** [jump to message]({url})\n**Channel:** {channel}").format(
                    mention=author.mention,
                    uid=author.id,
                    url=self.flagged_message.jump_url,
                    channel=getattr(self.flagged_message.channel, "mention", "#?"),
                )
            )
        )
        container.add_item(discord.ui.TextDisplay(_("-# Flagged for: {}").format(cats)))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(discord.ui.TextDisplay(_("**Reason**\n{}").format(self.proposal_reason[:1024])))
        excerpt = self.context_excerpt()
        if excerpt:
            container.add_item(discord.ui.TextDisplay(excerpt))
        if self.resolved:
            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            container.add_item(discord.ui.TextDisplay(self.outcome_text))
        else:
            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            for row in self.build_action_components():
                container.add_item(row)
        self.add_item(container)

    def context_excerpt(self) -> str:
        if not self.context_text:
            return ""
        tail = self.context_text[-1000:]
        rendered = "\n".join(f"-# {line[:160]}" for line in tail.splitlines() if line.strip())
        # Keep the whole panel's text well under the components-v2 ~4000-char aggregate budget.
        return _("**Context**\n{}").format(rendered[:1200]) if rendered else ""

    def build_action_components(self) -> List[discord.ui.ActionRow]:
        # Row 1: the suggested action (highlighted) + No action. Row 2: a dropdown of every
        # available action (a select must occupy its own ActionRow).
        rows: List[discord.ui.ActionRow] = []
        buttons: List[discord.ui.Button] = []
        primary = self.actions_by_name.get(self.proposed_action)
        if primary is not None:
            buttons.append(
                ModActionButton(
                    primary.name,
                    _("{} (suggested)").format(primary.label),
                    discord.ButtonStyle.primary,
                    primary.emoji,
                )
            )
        buttons.append(ModActionButton("none", _("No action"), discord.ButtonStyle.success, "✅"))
        rows.append(discord.ui.ActionRow(*buttons))
        if self.available_actions:
            rows.append(discord.ui.ActionRow(ModActionSelect(self.available_actions)))
        return rows

    # ---------------- interaction ----------------
    def disable_all(self) -> None:
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True

    def user_authorized(self, user: discord.Member, action: str) -> bool:
        if user.id in self.cog.bot.owner_ids:
            return True
        if any(role.id in self.staff_ping_roles for role in getattr(user, "roles", [])):
            return True
        perms = user.guild_permissions
        if perms.administrator:
            return True
        spec = self.actions_by_name.get(action)
        required = spec.perm if spec else "manage_messages"
        return getattr(perms, required or "manage_messages", False)

    async def handle_action(self, interaction: discord.Interaction, action: str) -> None:
        if self.resolved:
            await interaction.response.send_message(_("This panel was already resolved."), ephemeral=True)
            return
        if not self.user_authorized(interaction.user, action):
            await interaction.response.send_message(
                _("You don't have permission to perform that action."), ephemeral=True
            )
            return
        if action == "none":
            await self.finalize(
                interaction,
                _("✅ Dismissed — no action taken.\n-# By {}").format(interaction.user.mention),
                edit_via_response=True,
            )
            return
        if action == "delete":
            await self.execute_and_finalize(interaction, "delete", self.proposal_reason, via_modal=False)
            return
        await interaction.response.send_modal(ModReasonModal(self, action, self.proposal_reason))

    async def execute_and_finalize(
        self, interaction: discord.Interaction, action: str, reason: str, via_modal: bool
    ) -> None:
        if self.resolved:
            with suppress(discord.HTTPException):
                await interaction.response.send_message(_("This panel was already resolved."), ephemeral=True)
            return
        # Claim the panel before the awaited action so a concurrent click can't double-act.
        self.resolved = True
        outcome = (await self.run_action(action, reason, interaction.user))[0]
        outcome = _("{outcome}\n-# Action by {user}").format(outcome=outcome, user=interaction.user.mention)
        await self.finalize(interaction, outcome, edit_via_response=not via_modal)

    async def run_action(self, action: str, reason: str, actor) -> Tuple[str, bool]:
        target = self.flagged_message.author
        if self.dry_run:
            return _("🧪 (dry-run) Would **{action}** {target}.\n-# {reason}").format(
                action=action, target=getattr(target, "mention", target), reason=reason
            ), True
        # All real execution (incl. Ark / ModNotes / Warnings integrations) lives on the cog.
        return await self.cog.execute_mod_action(
            action,
            guild=self.flagged_message.guild,
            flagged_message=self.flagged_message,
            target=target,
            reason=reason,
            actor=actor,
            duration_minutes=self.duration_minutes(),
            delete_message=bool(self.proposal.get("delete_message")),
        )

    def duration_minutes(self) -> int:
        raw = self.proposal.get("duration_minutes")
        try:
            return int(raw) if raw else 0
        except (ValueError, TypeError):
            return 0

    async def finalize(self, interaction: discord.Interaction, outcome_text: str, edit_via_response: bool) -> None:
        self.resolved = True
        self.outcome_text = outcome_text
        self.build_layout()
        self.stop()
        if edit_via_response and not interaction.response.is_done():
            with suppress(discord.HTTPException):
                await interaction.response.edit_message(view=self)
            return
        if not interaction.response.is_done():
            with suppress(discord.HTTPException):
                await interaction.response.defer()
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)

    async def on_timeout(self) -> None:
        if self.resolved:
            return
        if self.auto_action_on_timeout and not self.dry_run:
            actor = self.flagged_message.guild.me
            outcome = (await self.run_action(self.proposed_action, self.proposal_reason, actor))[0]
            self.resolved = True
            self.outcome_text = _("⏱️ Auto-action on timeout: {}").format(outcome)
            self.build_layout()
        else:
            self.disable_all()
        with suppress(discord.HTTPException):
            if self.message:
                await self.message.edit(view=self)


class EmbeddingModal(discord.ui.Modal):
    def __init__(self, title: str, name: str = None, text: str = None):
        super().__init__(title=title, timeout=None)
        self.name = ""
        self.text = ""

        self.name_field = discord.ui.TextInput(
            label=_("Entry name"),
            style=discord.TextStyle.short,
            default=name,
            required=True,
            max_length=250,
        )
        self.add_item(self.name_field)
        self.text_field = discord.ui.TextInput(
            label=_("Training context"),
            style=discord.TextStyle.paragraph,
            default=text,
            required=True,
        )
        self.add_item(self.text_field)

    async def on_submit(self, interaction: discord.Interaction):
        self.name = self.name_field.value
        self.text = self.text_field.value
        await interaction.response.defer()
        self.stop()


class SearchModal(discord.ui.Modal):
    def __init__(self, title: str, current: str = None):
        self.query = None
        super().__init__(title=title, timeout=120)
        self.field = discord.ui.TextInput(
            label=_("Search Query"),
            style=discord.TextStyle.short,
            required=True,
            default=current,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.query = self.field.value
        await interaction.response.defer()
        self.stop()


class EmbeddingMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        conf: GuildSettings,
        save_func: Callable,
        fetch_pages: Callable,
        embed_method: Callable,
        embedding_store,
        guild_id: int,
    ):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.conf = conf
        self.save = save_func
        self.fetch_pages = fetch_pages
        self.embed_method = embed_method
        self.embedding_store = embedding_store
        self.guild_id = guild_id

        self.has_skip = True
        self.place = 0
        self.page = 0
        self.pages: List[discord.Embed] = []
        self.message: discord.Message = None
        self.tasks: List[asyncio.Task] = []

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        with suppress(discord.HTTPException):
            await self.message.edit(view=None)
        for task in self.tasks:
            await task
        return await super().on_timeout()

    async def get_pages(self) -> None:
        self.pages = await self.fetch_pages(self.guild_id, self.conf, self.place)
        if len(self.pages) > 30 and not self.has_skip:
            self.add_item(self.left10)
            self.add_item(self.right10)
            self.has_skip = True
        elif len(self.pages) <= 30 and self.has_skip:
            self.remove_item(self.left10)
            self.remove_item(self.right10)
            self.has_skip = False

    def change_place(self, inc: int):
        current = self.pages[self.page]
        if not current.fields:
            return
        old_place = self.place
        self.place += inc
        self.place %= len(current.fields)
        for embed in self.pages:
            # Cleanup old place
            if len(embed.fields) > old_place:
                embed.set_field_at(
                    old_place,
                    name=embed.fields[old_place].name.replace("➣ ", "", 1),
                    value=embed.fields[old_place].value,
                    inline=False,
                )
            # Add new place
            if len(embed.fields) > self.place:
                embed.set_field_at(
                    self.place,
                    name="➣ " + embed.fields[self.place].name.replace("➣ ", "", 1),
                    value=embed.fields[self.place].value,
                    inline=False,
                )

    async def add_embedding(self, name: str, text: str):
        embedding, observed_model = await self.embed_method(text, self.conf)
        if not embedding:
            return await self.ctx.send(_("Failed to process embedding `{}`\nContent: ```\n{}\n```").format(name, text))
        if await self.embedding_store.exists(self.guild_id, name):
            return await self.ctx.send(_("An embedding with the name `{}` already exists!").format(name))
        await self.embedding_store.add(self.guild_id, name, text, embedding, observed_model)
        await self.get_pages()
        with suppress(discord.NotFound):
            self.message = await self.message.edit(embed=self.pages[self.page], view=self)
        await self.ctx.send(_("Your embedding labeled `{}` has been processed!").format(name))

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.primary,
        emoji="\N{PRINTER}\N{VARIATION SELECTOR-16}",
    )
    async def view(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No embeddings to inspect!"), ephemeral=True)
        await interaction.response.defer()
        name = self.pages[self.page].fields[self.place].name.replace("➣ ", "", 1)
        meta = await self.embedding_store.get(self.guild_id, name)
        if not meta:
            return await interaction.followup.send(_("Embedding not found!"), ephemeral=True)
        for p in pagify(meta.get("text", ""), page_length=4000):
            embed = discord.Embed(description=p)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{UPWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.pages[self.page].fields:
            self.change_place(-1)
            self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{MEMO}")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No embeddings to edit!"), ephemeral=True)
        name = self.pages[self.page].fields[self.place].name.replace("➣ ", "", 1)
        meta = await self.embedding_store.get(self.guild_id, name)
        existing_text = meta.get("text", "") if meta else ""
        modal = EmbeddingModal(title="Edit embedding", name=name, text=existing_text[:4000])
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.name or not modal.text:
            return
        embedding, observed_model = await self.embed_method(modal.text, self.conf)
        if not embedding:
            return await interaction.followup.send(
                _("Failed to edit that embedding, please try again later"), ephemeral=True
            )
        if modal.name != name:
            await self.embedding_store.delete(self.guild_id, name)
        await self.embedding_store.update(self.guild_id, modal.name, modal.text, embedding, observed_model)
        await self.get_pages()
        await self.message.edit(embed=self.pages[self.page], view=self)
        await interaction.followup.send(_("Your embedding has been modified!"), ephemeral=True)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        row=1,
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.page %= len(self.pages)
        new_place = min(self.place, len(self.pages[self.page].fields) - 1)
        if place_change := self.place - new_place:
            self.change_place(-place_change)
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{CROSS MARK}", row=1)
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.message.delete()
        for task in self.tasks:
            await task
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        row=1,
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.page %= len(self.pages)
        new_place = min(self.place, len(self.pages[self.page].fields) - 1)
        if place_change := self.place - new_place:
            self.change_place(-place_change)
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{SQUARED NEW}", row=2)
    async def new_embedding(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EmbeddingModal(title=_("Add an embedding"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.name or not modal.text:
            return
        self.tasks.append(asyncio.create_task(self.add_embedding(modal.name, modal.text)))
        await interaction.followup.send(_("Your embedding is processing and will appear when ready!"), ephemeral=True)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{DOWNWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        row=2,
    )
    async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.pages[self.page].fields:
            self.change_place(1)
            self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No embeddings to delete!"), ephemeral=True)
        name = self.pages[self.page].fields[self.place].name.replace("➣ ", "", 1)
        await interaction.response.send_message(_("Deleted `{}` embedding.").format(name), ephemeral=True)
        await self.embedding_store.delete(self.guild_id, name)
        await self.get_pages()
        self.page %= len(self.pages)
        self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}",
        row=3,
    )
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 10
        self.page %= len(self.pages)
        self.place = min(self.place, len(self.pages[self.page].fields) - 1)
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{LEFT-POINTING MAGNIFYING GLASS}",
        row=3,
    )
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        all_meta = await self.embedding_store.get_all_metadata(self.guild_id)
        if not all_meta:
            return await interaction.response.send_message(_("No embeddings to search!"), ephemeral=True)
        modal = SearchModal(_("Search for an embedding"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return
        query = modal.query.lower()
        matches: List[Tuple[str, int]] = []
        for name, meta in all_meta.items():
            text = meta.get("text", "")
            if query == name.lower():
                matches.append((name, 100))
                break
            if query in text.lower():
                matches.append((name, 98))
                continue
            matches.append((name, fuzz.ratio(query, name.lower())))
            matches.append((name, fuzz.ratio(query, text.lower())))
        if len(matches) > 1:
            matches.sort(key=lambda x: x[1], reverse=True)

        sorted_embeddings = matches
        embedding_name = sorted_embeddings[0][0]
        await interaction.followup.send(_("Search result: **{}**").format(embedding_name), ephemeral=True)
        for page_index, embed in enumerate(self.pages):
            found = False
            for place_index, field in enumerate(embed.fields):
                name = field.name.replace("➣ ", "", 1)
                if name == embedding_name:
                    self.page = page_index
                    self.place = place_index
                    found = True
                    break
            if found:
                break
        await self.get_pages()
        self.message = await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}",
        row=3,
    )
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 10
        self.page %= len(self.pages)
        self.place = min(self.place, len(self.pages[self.page].fields) - 1)
        await self.message.edit(embed=self.pages[self.page], view=self)


class CodeModal(discord.ui.Modal):
    def __init__(
        self,
        schema: str,
        code: str,
        permission_level: str = None,
        required_permissions: str = None,
        category: str = None,
    ):
        super().__init__(title=_("Function Edit"), timeout=None)

        self.schema = ""
        self.code = ""
        self.permission_level = ""
        self.required_permissions: list[str] = []
        self.category = normalize_tool_category(category)

        self.schema_field = discord.ui.TextInput(
            label=_("JSON Schema"),
            style=discord.TextStyle.paragraph,
            default=schema,
        )
        self.add_item(self.schema_field)
        self.code_field = discord.ui.TextInput(
            label=_("Code"),
            style=discord.TextStyle.paragraph,
            default=code,
        )
        self.add_item(self.code_field)
        self.perm_field = discord.ui.TextInput(
            label=_("Permission Level"),
            placeholder=_("User, Mod, Admin, or Owner"),
            style=discord.TextStyle.short,
            default=permission_level,
        )
        self.add_item(self.perm_field)
        self.perms_field = discord.ui.TextInput(
            label=_("Required Discord Permissions"),
            placeholder=_("e.g. manage_messages, kick_members (comma-separated, or leave blank)"),
            style=discord.TextStyle.short,
            required=False,
            default=required_permissions or "",
        )
        self.add_item(self.perms_field)
        self.category_field = discord.ui.TextInput(
            label=_("Category"),
            placeholder=_("memory, web, utility"),
            style=discord.TextStyle.short,
            required=False,
            default=self.category,
        )
        self.add_item(self.category_field)

    async def on_submit(self, interaction: discord.Interaction):
        self.schema = self.schema_field.value
        self.code = self.code_field.value
        if self.perm_field.value.lower() not in ("user", "mod", "admin", "owner"):
            return await interaction.response.send_message(
                _("Invalid permission level, must be one of `User`, `Mod`, `Admin`, or `Owner`"),
                ephemeral=True,
            )
        self.permission_level = self.perm_field.value.lower()

        # Parse required_permissions
        raw_perms = self.perms_field.value.strip()
        if raw_perms:
            perms = [p.strip().lower() for p in raw_perms.split(",") if p.strip()]
            valid_flags = set(discord.Permissions.VALID_FLAGS)
            invalid = [p for p in perms if p not in valid_flags]
            if invalid:
                return await interaction.response.send_message(
                    _("Invalid Discord permission names: {}").format(", ".join(f"`{p}`" for p in invalid)),
                    ephemeral=True,
                )
            self.required_permissions = perms
        else:
            self.required_permissions = []

        self.category = normalize_tool_category(self.category_field.value)

        await interaction.response.defer()
        self.stop()


class AIToolsCategoryToggleButton(discord.ui.Button["AIToolsView"]):
    def __init__(self, category: str, state: str):
        self.category = category
        super().__init__(label=_("Toggle"), style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await self.view.toggle_category(interaction, self.category)


class AIToolsCategorySelect(discord.ui.Select["AIToolsView"]):
    def __init__(
        self,
        category: str,
        entries: list[dict],
        conf: GuildSettings,
        chunk_index: int = 0,
        chunk_total: int = 1,
    ):
        self.category = category
        self.function_names = [entry["name"] for entry in entries]

        options = []
        for entry in entries:
            options.append(
                discord.SelectOption(
                    label=entry["name"][:100],
                    value=entry["name"],
                    description=format_tool_option_description(entry),
                    default=conf.function_statuses.get(entry["name"], False),
                )
            )

        if chunk_total > 1:
            placeholder = _("Choose tools for {} ({}/{})...").format(
                render_tool_category(category),
                chunk_index + 1,
                chunk_total,
            )
        else:
            placeholder = _("Choose tools for {}...").format(render_tool_category(category))
        super().__init__(
            placeholder=placeholder[:150],
            min_values=0 if options else 1,
            max_values=len(options) if options else 1,
            options=options or [discord.SelectOption(label=_("No tools available"), value="none")],
            disabled=not options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_names = set(self.values)
        await self.view.apply_category_selection(interaction, self.category, selected_names, set(self.function_names))


class AIToolsNavigationRow(discord.ui.ActionRow["AIToolsView"]):
    def __init__(self, page: int, total_pages: int):
        super().__init__()
        previous_button = discord.ui.Button(
            label=_("Prev"),
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=total_pages <= 1,
        )
        previous_button.callback = self.previous_page
        self.add_item(previous_button)

        next_button = discord.ui.Button(
            label=_("Next"),
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=total_pages <= 1,
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

        close_button = discord.ui.Button(label=_("Close"), emoji="✖️", style=discord.ButtonStyle.secondary)
        close_button.callback = self.close_view
        self.add_item(close_button)

    async def previous_page(self, interaction: discord.Interaction):
        await self.view.change_page(interaction, -1)

    async def next_page(self, interaction: discord.Interaction):
        await self.view.change_page(interaction, 1)

    async def close_view(self, interaction: discord.Interaction):
        self.view.stop()
        if not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        await self.view.delete_view_message(interaction)


class AIToolsView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        db: DB,
        registry: Dict[str, Dict[str, dict]],
        save_func: Callable,
        page_size: int = 4,
    ):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.db = db
        self.conf = db.get_conf(ctx.guild)
        self.registry = registry
        self.save = save_func
        self.page_size = page_size
        self.page = 0
        self.total_pages = 1
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True
        with suppress(discord.HTTPException):
            if self.message:
                await self.message.edit(view=self)

    def get_grouped_categories(self) -> dict[str, list[dict]]:
        grouped = self.db.get_functions_by_category(self.ctx.bot, self.registry)
        return {
            category: sorted(entries, key=lambda entry: entry["name"].lower())
            for category, entries in sorted(grouped.items(), key=lambda item: item[0])
        }

    def get_category_preview(self, entries: list[dict]) -> str:
        preview = ", ".join(entry["name"] for entry in entries[:4])
        remaining = len(entries) - 4
        if remaining > 0:
            preview += f", +{remaining}"
        return preview

    def chunk_category_entries(self, entries: list[dict], size: int = 25) -> list[list[dict]]:
        if not entries:
            return []
        return [entries[index : index + size] for index in range(0, len(entries), size)]

    def build_layout(self) -> None:
        self.clear_items()
        grouped = self.get_grouped_categories()
        catalog = [entry for entries in grouped.values() for entry in entries]
        container = discord.ui.Container(accent_colour=discord.Color.blue())

        if not catalog:
            container.add_item(discord.ui.TextDisplay("# 🤖 AI Tools"))
            container.add_item(discord.ui.TextDisplay("-# No registered tools found."))
            container.add_item(AIToolsNavigationRow(0, 1))
            self.add_item(container)
            return

        categories = list(grouped)
        self.total_pages = max(1, (len(categories) + self.page_size - 1) // self.page_size)
        self.page %= self.total_pages
        start = self.page * self.page_size
        stop = start + self.page_size
        page_categories = categories[start:stop]

        enabled_total = sum(self.conf.function_statuses.get(entry["name"], False) for entry in catalog)
        container.add_item(discord.ui.TextDisplay("# 🤖 AI Tools"))
        container.add_item(
            discord.ui.TextDisplay(
                _("{} {}/{} enabled • {} categories • Page {}/{}").format(
                    ON_EMOJI,
                    enabled_total,
                    len(catalog),
                    len(categories),
                    self.page + 1,
                    self.total_pages,
                )
            )
        )
        container.add_item(discord.ui.TextDisplay(f"{ON_EMOJI} On • {MIXED_EMOJI} Mixed • {OFF_EMOJI} Off"))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        for index, category in enumerate(page_categories):
            entries = grouped[category]
            function_names = [entry["name"] for entry in entries]
            state = get_category_state(function_names, self.conf.function_statuses)
            enabled_count = sum(self.conf.function_statuses.get(name, False) for name in function_names)
            preview = self.get_category_preview(entries)

            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"**{STATE_EMOJIS[state]} {render_tool_category(category)}**\n{enabled_count}/{len(entries)} enabled"
                    ),
                    discord.ui.TextDisplay(preview),
                    accessory=AIToolsCategoryToggleButton(category, state),
                )
            )
            entry_chunks = self.chunk_category_entries(entries)
            for chunk_index, entry_chunk in enumerate(entry_chunks):
                container.add_item(
                    discord.ui.ActionRow(
                        AIToolsCategorySelect(
                            category,
                            entry_chunk,
                            self.conf,
                            chunk_index=chunk_index,
                            chunk_total=len(entry_chunks),
                        )
                    )
                )
            if index != len(page_categories) - 1:
                container.add_item(discord.ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(AIToolsNavigationRow(self.page, self.total_pages))
        self.add_item(container)

    async def start(self):
        self.build_layout()
        self.message = await self.ctx.send(view=self)

    async def edit_view_message(
        self,
        view: Optional[discord.ui.View],
        interaction: Optional[discord.Interaction] = None,
    ) -> bool:
        candidate_messages: list[discord.Message] = []
        if self.message is not None:
            candidate_messages.append(self.message)
        if interaction is not None and interaction.message is not None:
            if not any(message.id == interaction.message.id for message in candidate_messages):
                candidate_messages.append(interaction.message)

        for candidate in candidate_messages:
            with suppress(discord.HTTPException):
                await candidate.edit(view=view)
                self.message = candidate
                return True

        if interaction is not None:
            with suppress(discord.HTTPException):
                await interaction.edit_original_response(view=view)
                return True

        return False

    async def delete_view_message(self, interaction: Optional[discord.Interaction] = None) -> bool:
        candidate_messages: list[discord.Message] = []
        if self.message is not None:
            candidate_messages.append(self.message)
        if interaction is not None and interaction.message is not None:
            if not any(message.id == interaction.message.id for message in candidate_messages):
                candidate_messages.append(interaction.message)

        for candidate in candidate_messages:
            with suppress(discord.HTTPException):
                await candidate.delete()
                self.message = None
                return True

        if interaction is not None:
            with suppress(discord.HTTPException):
                await interaction.delete_original_response()
                self.message = None
                return True

        return False

    async def refresh(self, interaction: Optional[discord.Interaction] = None):
        self.build_layout()
        if interaction is not None and not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        if interaction is None:
            await self.edit_view_message(self)
            return
        if self.message is None:
            self.message = interaction.message
        await self.edit_view_message(self, interaction)

    async def change_page(self, interaction: discord.Interaction, delta: int):
        self.page += delta
        self.page %= self.total_pages
        await self.refresh(interaction)

    async def toggle_category(self, interaction: discord.Interaction, category: str):
        grouped = self.get_grouped_categories()
        entries = grouped.get(category, [])
        if not entries:
            return await interaction.response.send_message(_("That category no longer exists."), ephemeral=True)

        function_names = [entry["name"] for entry in entries]
        state = get_category_state(function_names, self.conf.function_statuses)
        new_state = state != "on"
        for function_name in function_names:
            self.conf.function_statuses[function_name] = new_state
        await self.save()
        await self.refresh(interaction)

    async def apply_category_selection(
        self,
        interaction: discord.Interaction,
        category: str,
        selected_names: Set[str],
        available_names: Optional[Set[str]] = None,
    ):
        grouped = self.get_grouped_categories()
        entries = grouped.get(category, [])
        if not entries:
            return await interaction.response.send_message(_("That category no longer exists."), ephemeral=True)

        function_names = [entry["name"] for entry in entries]
        if available_names is not None:
            function_names = [name for name in function_names if name in available_names]
        for function_name in function_names:
            self.conf.function_statuses[function_name] = function_name in selected_names
        await self.save()
        await self.refresh(interaction)


# ---------------------------------------------------------------------------
# Endpoint model picker (`[p]assistant set model` / `embed model` with no args).
#
# Discovers models from the endpoint profile, groups them by provider prefix
# (e.g. ``openai/gpt-4`` → ``openai``), and renders a paginated LayoutView
# of provider dropdowns. Selecting a model from any dropdown immediately
# writes it to the appropriate ``conf.<field>`` and saves.
#
# A "Manual entry" button opens a modal so admins can type a model id that
# the probe missed (e.g. private routes, router-specific aliases like
# ``openrouter/auto`` or ``openrouter/free``).
# ---------------------------------------------------------------------------


ROUTER_MODEL_HINTS = [
    "openrouter/auto",
    "openrouter/free",
]
MODEL_PICKER_PAGE_SIZE = 4
MODEL_OPTION_LIMIT = 25  # Discord Select max
PROVIDER_OTHER = "other"


def split_model_provider(model_id: str) -> Tuple[str, str]:
    """Split a model id into (provider, short_name).

    For ids like ``openai/gpt-4-turbo`` returns ``("openai", "gpt-4-turbo")``.
    For ids with no slash returns ``(PROVIDER_OTHER, model_id)``.
    """
    if "/" in model_id:
        provider, _, short = model_id.partition("/")
        provider = provider.strip().lower()
        if not provider:
            return PROVIDER_OTHER, model_id
        return provider, short or model_id
    return PROVIDER_OTHER, model_id


def group_models_by_provider(model_ids: List[str]) -> Dict[str, List[str]]:
    """Group endpoint model ids by their provider prefix.

    Returns an ordered dict: providers sorted alphabetically (``other`` last),
    each value is the list of full model ids sorted by short name.
    """
    grouped: Dict[str, List[str]] = {}
    for model_id in model_ids:
        provider, _short = split_model_provider(model_id)
        grouped.setdefault(provider, []).append(model_id)

    ordered: Dict[str, List[str]] = {}
    sorted_providers = sorted(p for p in grouped if p != PROVIDER_OTHER)
    if PROVIDER_OTHER in grouped:
        sorted_providers.append(PROVIDER_OTHER)
    for provider in sorted_providers:
        ordered[provider] = sorted(grouped[provider], key=lambda mid: split_model_provider(mid)[1].lower())
    return ordered


def render_provider_label(provider: str) -> str:
    if provider == PROVIDER_OTHER:
        return _("Other")
    return provider


class ModelPickerSelect(discord.ui.Select["ModelPickerView"]):
    def __init__(
        self,
        provider: str,
        model_ids: List[str],
        current_model: str,
        chunk_index: int = 0,
        chunk_total: int = 1,
    ):
        self.provider = provider
        self.model_ids = model_ids

        options: List[discord.SelectOption] = []
        for model_id in model_ids[:MODEL_OPTION_LIMIT]:
            _provider, short_name = split_model_provider(model_id)
            label = short_name[:100] or model_id[:100]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=model_id[:100],
                    description=model_id[:MAX_SELECT_OPTION_DESCRIPTION],
                    default=(model_id == current_model),
                )
            )

        if chunk_total > 1:
            placeholder = _("Pick a model from {} ({}/{})...").format(
                render_provider_label(provider),
                chunk_index + 1,
                chunk_total,
            )
        else:
            placeholder = _("Pick a model from {}...").format(render_provider_label(provider))
        super().__init__(
            placeholder=placeholder[:150],
            min_values=0,
            max_values=1,
            options=options or [discord.SelectOption(label=_("No models"), value="none")],
            disabled=not options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            with suppress(discord.NotFound):
                await interaction.response.defer()
            return
        chosen = self.values[0]
        if chosen == "none":
            with suppress(discord.NotFound):
                await interaction.response.defer()
            return
        await self.view.apply_selection(interaction, chosen)


class ModelPickerManualEntryModal(discord.ui.Modal):
    def __init__(self, current_model: str):
        super().__init__(title=_("Enter Model ID"), timeout=120)
        self.value: Optional[str] = None
        self.field = discord.ui.TextInput(
            label=_("Model ID"),
            placeholder=_("e.g. openrouter/auto, openai/gpt-4o, anthropic/claude-3-opus"),
            style=discord.TextStyle.short,
            default=current_model or None,
            required=True,
            max_length=200,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        self.value = (self.field.value or "").strip()
        await interaction.response.defer()
        self.stop()


class ModelPickerNavigationRow(discord.ui.ActionRow["ModelPickerView"]):
    def __init__(self, total_pages: int, kind_label: str):
        super().__init__()
        prev_btn = discord.ui.Button(
            label=_("Prev"),
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=total_pages <= 1,
        )
        prev_btn.callback = self.previous_page
        self.add_item(prev_btn)

        next_btn = discord.ui.Button(
            label=_("Next"),
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=total_pages <= 1,
        )
        next_btn.callback = self.next_page
        self.add_item(next_btn)

        manual_btn = discord.ui.Button(
            label=_("Manual entry"),
            emoji="✏️",
            style=discord.ButtonStyle.primary,
        )
        manual_btn.callback = self.manual_entry
        self.add_item(manual_btn)

        refresh_btn = discord.ui.Button(
            label=_("Re-probe"),
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
        )
        refresh_btn.callback = self.reprobe
        self.add_item(refresh_btn)

        close_btn = discord.ui.Button(label=_("Close"), emoji="✖️", style=discord.ButtonStyle.secondary)
        close_btn.callback = self.close_view
        self.add_item(close_btn)

    async def previous_page(self, interaction: discord.Interaction):
        await self.view.change_page(interaction, -1)

    async def next_page(self, interaction: discord.Interaction):
        await self.view.change_page(interaction, 1)

    async def manual_entry(self, interaction: discord.Interaction):
        await self.view.open_manual_entry(interaction)

    async def reprobe(self, interaction: discord.Interaction):
        await self.view.reprobe(interaction)

    async def close_view(self, interaction: discord.Interaction):
        self.view.stop()
        if not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        await self.view.delete_view_message(interaction)


class ModelPickerView(discord.ui.LayoutView):
    """Endpoint model picker grouped by provider prefix."""

    def __init__(
        self,
        ctx: commands.Context,
        conf: GuildSettings,
        kind: str,  # "chat" or "embedding"
        save_func: Callable,
        reprobe_func: Callable,
        get_profile: Callable[[], Optional[EndpointProfile]],
        endpoint_url: str,
        post_select: Optional[Callable[[str], Awaitable[Optional[str]]]] = None,
        page_size: int = MODEL_PICKER_PAGE_SIZE,
    ):
        super().__init__(timeout=300)
        if kind not in ("chat", "embedding"):
            raise ValueError(f"Invalid model picker kind: {kind}")
        self.ctx = ctx
        self.conf = conf
        self.kind = kind
        self.save = save_func
        self.reprobe_func = reprobe_func
        self.get_profile = get_profile
        self.endpoint_url = endpoint_url
        self.post_select = post_select
        self.page_size = page_size
        self.page = 0
        self.total_pages = 1
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True
        with suppress(discord.HTTPException):
            if self.message:
                await self.message.edit(view=self)

    @property
    def current_model(self) -> str:
        if self.kind == "chat":
            return self.conf.model
        return self.conf.embed_model

    def set_current_model(self, model: str) -> None:
        if self.kind == "chat":
            self.conf.model = model
        else:
            self.conf.embed_model = model

    def get_models_for_kind(self) -> List[str]:
        profile = self.get_profile()
        if not profile:
            return []
        bucket = profile.chat_models if self.kind == "chat" else profile.embedding_models
        return list(bucket.keys())

    def get_grouped(self) -> Dict[str, List[str]]:
        return group_models_by_provider(self.get_models_for_kind())

    def chunk_models(self, model_ids: List[str]) -> List[List[str]]:
        if not model_ids:
            return []
        return [model_ids[i : i + MODEL_OPTION_LIMIT] for i in range(0, len(model_ids), MODEL_OPTION_LIMIT)]

    def kind_label(self) -> str:
        return _("Chat model") if self.kind == "chat" else _("Embedding model")

    def build_layout(self) -> None:
        self.clear_items()
        grouped = self.get_grouped()
        providers = list(grouped)
        container = discord.ui.Container(accent_colour=discord.Color.blue())

        header_lines = [_("# 🤖 {} picker").format(self.kind_label())]
        header_lines.append(_("-# Endpoint: `{}`").format(self.endpoint_url))
        header_lines.append(_("Current: **{}**").format(self.current_model or _("(none)")))
        if not providers:
            header_lines.append(
                _(
                    "No models were discovered from this endpoint. Try **Re-probe** or use **Manual entry** "
                    "to type a model id. Router endpoints like OpenRouter accept aliases such as `{}` or `{}`."
                ).format(*ROUTER_MODEL_HINTS[:2])
            )
            container.add_item(discord.ui.TextDisplay("\n".join(header_lines)))
            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            container.add_item(ModelPickerNavigationRow(1, self.kind_label()))
            self.add_item(container)
            return

        total_models = sum(len(ids) for ids in grouped.values())
        self.total_pages = max(1, (len(providers) + self.page_size - 1) // self.page_size)
        self.page %= self.total_pages
        start = self.page * self.page_size
        stop = start + self.page_size
        page_providers = providers[start:stop]

        header_lines.append(
            _("{} models across {} providers • Page {}/{}").format(
                total_models,
                len(providers),
                self.page + 1,
                self.total_pages,
            )
        )
        if self.kind == "chat":
            header_lines.append(
                _("-# Tip: router endpoints accept aliases like `{}` or `{}` via **Manual entry**.").format(
                    *ROUTER_MODEL_HINTS[:2]
                )
            )
        container.add_item(discord.ui.TextDisplay("\n".join(header_lines)))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        for index, provider in enumerate(page_providers):
            model_ids = grouped[provider]
            preview_short = ", ".join(split_model_provider(mid)[1] for mid in model_ids[:3])
            remaining = len(model_ids) - 3
            if remaining > 0:
                preview_short += f", +{remaining}"
            container.add_item(
                discord.ui.TextDisplay(
                    f"**{render_provider_label(provider)}** - {len(model_ids)} model(s)\n-# {preview_short}"
                )
            )
            chunks = self.chunk_models(model_ids)
            for chunk_index, chunk in enumerate(chunks):
                container.add_item(
                    discord.ui.ActionRow(
                        ModelPickerSelect(
                            provider,
                            chunk,
                            self.current_model,
                            chunk_index=chunk_index,
                            chunk_total=len(chunks),
                        )
                    )
                )
            if index != len(page_providers) - 1:
                container.add_item(discord.ui.Separator(visible=False, spacing=discord.SeparatorSpacing.small))

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(ModelPickerNavigationRow(self.total_pages, self.kind_label()))
        self.add_item(container)

    async def start(self):
        self.build_layout()
        self.message = await self.ctx.send(view=self)

    async def edit_view_message(
        self,
        view: Optional[discord.ui.View],
        interaction: Optional[discord.Interaction] = None,
    ) -> bool:
        candidates: List[discord.Message] = []
        if self.message is not None:
            candidates.append(self.message)
        if interaction is not None and interaction.message is not None:
            if not any(m.id == interaction.message.id for m in candidates):
                candidates.append(interaction.message)

        for candidate in candidates:
            with suppress(discord.HTTPException):
                await candidate.edit(view=view)
                self.message = candidate
                return True

        if interaction is not None:
            with suppress(discord.HTTPException):
                await interaction.edit_original_response(view=view)
                return True
        return False

    async def delete_view_message(self, interaction: Optional[discord.Interaction] = None) -> bool:
        candidates: List[discord.Message] = []
        if self.message is not None:
            candidates.append(self.message)
        if interaction is not None and interaction.message is not None:
            if not any(m.id == interaction.message.id for m in candidates):
                candidates.append(interaction.message)

        for candidate in candidates:
            with suppress(discord.HTTPException):
                await candidate.delete()
                self.message = None
                return True

        if interaction is not None:
            with suppress(discord.HTTPException):
                await interaction.delete_original_response()
                self.message = None
                return True
        return False

    async def refresh(self, interaction: Optional[discord.Interaction] = None):
        self.build_layout()
        if interaction is not None and not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        if interaction is None:
            await self.edit_view_message(self)
            return
        if self.message is None:
            self.message = interaction.message
        await self.edit_view_message(self, interaction)

    async def change_page(self, interaction: discord.Interaction, delta: int):
        self.page += delta
        self.page %= self.total_pages
        await self.refresh(interaction)

    async def apply_selection(self, interaction: discord.Interaction, model_id: str):
        self.set_current_model(model_id)
        await self.save()
        await self.refresh(interaction)
        extra_notice = await self.post_select(model_id) if self.post_select else None
        message = _("{} set to **{}**").format(self.kind_label(), model_id)
        if extra_notice:
            message = f"{message}\n{extra_notice}"
        with suppress(discord.HTTPException):
            await interaction.followup.send(message, ephemeral=True)

    async def open_manual_entry(self, interaction: discord.Interaction):
        modal = ModelPickerManualEntryModal(self.current_model)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.value:
            return
        self.set_current_model(modal.value)
        await self.save()
        await self.refresh(None)
        extra_notice = await self.post_select(modal.value) if self.post_select else None
        message = _("{} set to **{}**").format(self.kind_label(), modal.value)
        if extra_notice:
            message = f"{message}\n{extra_notice}"
        with suppress(discord.HTTPException):
            await self.ctx.send(message)

    async def reprobe(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        await self.reprobe_func()
        await self.refresh(interaction)


# ---------------------------------------------------------------------------
# Floating context block manager (`[p]floatingcontext`).
#
# Lets admins toggle which variables are appended to the trailing
# ``[Current Context]`` payload-only user message the bot sends after
# conversation history. Because this message rides after the cached prefix
# it can carry per-request values without invalidating provider prompt
# caches. Categories cover:
#   - Builtin **dynamic** vars - changing per-request, the prime candidates
#     for the floating block.
#   - Builtin **stable** vars - already substituted inline into prompts,
#     but admins may opt to also surface them here.
#   - Per-cog 3rd-party context variables, one category each.
# Everything defaults to OFF; admins opt variables in explicitly.
# ---------------------------------------------------------------------------


def context_block_category_state(var_names: List[str], statuses: Dict[str, bool]) -> str:
    """Return on/off/mixed for a trailing-block category.

    Inclusion defaults to **off** for every variable on a fresh install.
    """
    if not var_names:
        return "off"
    enabled = sum(statuses.get(f"var:{name}", False) for name in var_names)
    if enabled == 0:
        return "off"
    if enabled == len(var_names):
        return "on"
    return "mixed"


def get_context_block_categories(
    db: DB, conf: GuildSettings, bot, context_registry: Dict[str, Dict[str, dict]]
) -> Dict[str, Dict[str, object]]:
    """Return every category eligible for the trailing-context-block menu.

    Output: ``{category_key: {"label": str, "variables": [str, ...]}}``.

    Inclusion in the floating block is fully admin-controlled - there is
    no implicit default. On a fresh install everything is OFF (blank
    slate). Admins opt variables in one at a time via the floatingcontext
    menu.
    """
    categories: Dict[str, Dict[str, object]] = {}

    # Builtin dynamic groups - the prime candidates for the floating block
    # since they change per-request and would otherwise bust the prompt
    # cache if referenced inline in a system/initial prompt.
    for key, names in DYNAMIC_VARIABLE_GROUPS.items():
        categories[key] = {
            "label": DYNAMIC_VARIABLE_GROUP_LABELS.get(key, key.title()),
            "variables": list(names),
        }

    # Builtin stable groups.
    for key, names in STABLE_VARIABLE_GROUPS.items():
        categories[key] = {
            "label": STABLE_VARIABLE_GROUP_LABELS.get(key, key.title()),
            "variables": list(names),
        }

    # Per-cog custom context variables: one category per source cog. The
    # cog-declared ``cache_safe`` flag is informational only; it surfaces
    # in the variable's description so admins know which ones bust caching
    # when inlined into a prompt template.
    catalog = db.get_context_variable_catalog(bot, context_registry)
    grouped: Dict[str, List[dict]] = {}
    for entry in catalog:
        grouped.setdefault(entry["source"], []).append(entry)
    for source in sorted(grouped):
        key = f"custom:{source}"
        entries = sorted(grouped[source], key=lambda e: e["name"])
        categories[key] = {
            "label": f"Custom - {source}",
            "variables": [e["name"] for e in entries],
        }
    return categories


def describe_var(var_name: str, context_descriptions: Optional[Dict[str, str]] = None) -> str:
    """Return a short human-readable description for a context variable."""
    # Use narrative template summary if available
    narrative = VARIABLE_NARRATIVES.get(var_name)
    if narrative:
        # Strip the "{value}" placeholder and trailing period for brevity
        short = narrative.replace("{value}", "…").rstrip(".")
        return short
    # Fall back to 3rd-party registry description
    if context_descriptions:
        desc = context_descriptions.get(var_name, "").strip()
        if desc:
            return desc[:MAX_SELECT_OPTION_DESCRIPTION]
    return var_name


class FloatingContextToggleButton(discord.ui.Button["FloatingContextView"]):
    def __init__(self, category_key: str, state: str):
        self.category_key = category_key
        super().__init__(label=_("Toggle"), style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        await self.view.toggle_category(interaction, self.category_key)


class FloatingContextVarSelect(discord.ui.Select["FloatingContextView"]):
    def __init__(
        self,
        category_key: str,
        label: str,
        variables: List[str],
        conf: GuildSettings,
        context_descriptions: Optional[Dict[str, str]] = None,
    ):
        self.category_key = category_key
        self.variables = list(variables)
        context_descriptions = context_descriptions or {}

        options: List[discord.SelectOption] = []
        for var_name in self.variables:
            # Default OFF on a fresh install; per-var key overrides.
            current = conf.context_block_var_statuses.get(f"var:{var_name}", False)
            # Derive a short description from the narrative template or registry
            desc = describe_var(var_name, context_descriptions)
            options.append(
                discord.SelectOption(
                    label=var_name[:100],
                    value=var_name,
                    description=desc[:MAX_SELECT_OPTION_DESCRIPTION],
                    default=current,
                )
            )

        super().__init__(
            placeholder=_("Toggle individual vars in {}...").format(label)[:150],
            min_values=0,
            max_values=len(options) if options else 1,
            options=options or [discord.SelectOption(label=_("No variables"), value="none")],
            disabled=not options,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        await self.view.apply_variable_selection(interaction, self.category_key, self.variables, selected)


class FloatingContextNavigationRow(discord.ui.ActionRow["FloatingContextView"]):
    def __init__(self, page: int, total_pages: int):
        super().__init__()
        previous_button = discord.ui.Button(
            label=_("Prev"),
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=total_pages <= 1,
        )
        previous_button.callback = self.previous_page
        self.add_item(previous_button)

        next_button = discord.ui.Button(
            label=_("Next"),
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=total_pages <= 1,
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

        close_button = discord.ui.Button(label=_("Close"), emoji="✖️", style=discord.ButtonStyle.secondary)
        close_button.callback = self.close_view
        self.add_item(close_button)

    async def previous_page(self, interaction: discord.Interaction):
        await self.view.change_page(interaction, -1)

    async def next_page(self, interaction: discord.Interaction):
        await self.view.change_page(interaction, 1)

    async def close_view(self, interaction: discord.Interaction):
        self.view.stop()
        if not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        await self.view.delete_view_message(interaction)


class FloatingContextView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        db: DB,
        context_registry: Dict[str, Dict[str, dict]],
        save_func: Callable,
        page_size: int = 3,
    ):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot = ctx.bot
        self.db = db
        self.conf = db.get_conf(ctx.guild)
        self.context_registry = context_registry
        self.save = save_func
        self.page_size = page_size
        self.page = 0
        self.total_pages = 1
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if hasattr(item, "disabled"):
                item.disabled = True
        with suppress(discord.HTTPException):
            if self.message:
                await self.message.edit(view=self)

    def get_categories(self) -> Dict[str, Dict[str, object]]:
        return get_context_block_categories(self.db, self.conf, self.bot, self.context_registry)

    def category_state(self, var_names: List[str]) -> str:
        return context_block_category_state(var_names, self.conf.context_block_var_statuses)

    def scan_prompt_warnings(self) -> List[str]:
        """Return formatted warning lines for prompts containing dynamic vars."""
        warnings: List[str] = []

        def find_dyn_vars(text: str) -> List[str]:
            if not text:
                return []
            return sorted({name for name in DYNAMIC_VARIABLE_NAMES if "{" + name + "}" in text})

        sys_vars = find_dyn_vars(self.conf.system_prompt or "")
        if sys_vars:
            warnings.append(_("**System prompt** - `{}`").format(", ".join(sys_vars)))
        init_vars = find_dyn_vars(self.conf.prompt or "")
        if init_vars:
            warnings.append(_("**Initial prompt** - `{}`").format(", ".join(init_vars)))
        for channel_id, prompt in self.conf.channel_prompts.items():
            chan_vars = find_dyn_vars(prompt)
            if not chan_vars:
                continue
            warnings.append(_("<#{}> - `{}`").format(channel_id, ", ".join(chan_vars)))
        return warnings

    def get_context_descriptions(self) -> Dict[str, str]:
        """Build a mapping of variable name → description for 3rd-party vars."""
        context_descriptions: Dict[str, str] = {}
        catalog = self.db.get_context_variable_catalog(self.bot, self.context_registry)
        for entry in catalog:
            desc = entry.get("description", "").strip()
            if desc:
                context_descriptions[entry["name"]] = desc
        return context_descriptions

    def build_layout(self) -> None:
        self.clear_items()
        categories = self.get_categories()
        context_descriptions = self.get_context_descriptions()
        container = discord.ui.Container(accent_colour=discord.Color.teal())

        category_keys = list(categories)
        self.total_pages = max(1, (len(category_keys) + self.page_size - 1) // self.page_size)
        self.page %= self.total_pages
        start = self.page * self.page_size
        stop = start + self.page_size
        page_keys = category_keys[start:stop]

        # Summary
        enabled_total = 0
        var_total = 0
        for info in categories.values():
            for var_name in info["variables"]:
                var_total += 1
                if self.conf.context_block_var_statuses.get(f"var:{var_name}", False):
                    enabled_total += 1

        container.add_item(discord.ui.TextDisplay("# 🧊 Floating Context Block"))
        container.add_item(
            discord.ui.TextDisplay(
                _(
                    "Toggle which variables are included in the trailing `[Current Context]` system message that "
                    "the bot appends after conversation history. Everything is OFF by default - opt variables in "
                    "one at a time. Variables you toggle on are rendered as self-encapsulated sentences (e.g. "
                    '`"The current date is May 16, 2026."`), so you do not need to author a prompt that '
                    "references them."
                )
            )
        )
        container.add_item(
            discord.ui.TextDisplay(
                _("{} {}/{} variables in block • {} categories • Page {}/{}").format(
                    ON_EMOJI,
                    enabled_total,
                    var_total,
                    len(category_keys),
                    self.page + 1,
                    self.total_pages,
                )
            )
        )
        container.add_item(discord.ui.TextDisplay(f"{ON_EMOJI} On • {MIXED_EMOJI} Mixed • {OFF_EMOJI} Off"))
        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))

        for index, category_key in enumerate(page_keys):
            info = categories[category_key]
            var_names: List[str] = info["variables"]  # type: ignore[assignment]
            label: str = info["label"]  # type: ignore[assignment]
            state = self.category_state(var_names)
            enabled_count = sum(self.conf.context_block_var_statuses.get(f"var:{name}", False) for name in var_names)
            preview = ", ".join(var_names[:4])
            if len(var_names) > 4:
                preview += f", +{len(var_names) - 4}"

            container.add_item(
                discord.ui.Section(
                    discord.ui.TextDisplay(
                        f"**{STATE_EMOJIS[state]} {label}**\n"
                        f"{enabled_count}/{len(var_names)} included\n"
                        f"{preview or _('(no variables)')}"
                    ),
                    accessory=FloatingContextToggleButton(category_key, state),
                )
            )
            if var_names:
                container.add_item(
                    discord.ui.ActionRow(
                        FloatingContextVarSelect(category_key, label, var_names, self.conf, context_descriptions)
                    )
                )

        # Prompt warnings
        warnings = self.scan_prompt_warnings()
        if warnings:
            container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
            container.add_item(discord.ui.TextDisplay(_("## ⚠️ Cache Warning")))
            container.add_item(
                discord.ui.TextDisplay(
                    _(
                        "These prompts contain dynamic variable placeholders that are substituted inline, "
                        "which busts provider-side prompt-prefix caching on every request:"
                    )
                )
            )
            for line in warnings[:5]:
                container.add_item(discord.ui.TextDisplay(line))
            container.add_item(
                discord.ui.TextDisplay(
                    _(
                        "Tip: remove the placeholder from your prompt and toggle the variable on in the menu above "
                        "instead - the bot will append the value to the floating context block automatically."
                    )
                )
            )

        container.add_item(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(FloatingContextNavigationRow(self.page, self.total_pages))
        self.add_item(container)

    async def start(self):
        self.build_layout()
        self.message = await self.ctx.send(view=self)

    async def edit_view_message(
        self,
        view: Optional[discord.ui.View],
        interaction: Optional[discord.Interaction] = None,
    ) -> bool:
        candidate_messages: List[discord.Message] = []
        if self.message is not None:
            candidate_messages.append(self.message)
        if interaction is not None and interaction.message is not None:
            if not any(message.id == interaction.message.id for message in candidate_messages):
                candidate_messages.append(interaction.message)

        for candidate in candidate_messages:
            with suppress(discord.HTTPException):
                await candidate.edit(view=view)
                self.message = candidate
                return True

        if interaction is not None:
            with suppress(discord.HTTPException):
                await interaction.edit_original_response(view=view)
                return True

        return False

    async def delete_view_message(self, interaction: Optional[discord.Interaction] = None) -> bool:
        candidate_messages: List[discord.Message] = []
        if self.message is not None:
            candidate_messages.append(self.message)
        if interaction is not None and interaction.message is not None:
            if not any(message.id == interaction.message.id for message in candidate_messages):
                candidate_messages.append(interaction.message)

        for candidate in candidate_messages:
            with suppress(discord.HTTPException):
                await candidate.delete()
                self.message = None
                return True

        if interaction is not None:
            with suppress(discord.HTTPException):
                await interaction.delete_original_response()
                self.message = None
                return True

        return False

    async def refresh(self, interaction: Optional[discord.Interaction] = None):
        self.build_layout()
        if interaction is not None and not interaction.response.is_done():
            with suppress(discord.NotFound):
                await interaction.response.defer()
        if interaction is None:
            await self.edit_view_message(self)
            return
        if self.message is None:
            self.message = interaction.message
        await self.edit_view_message(self, interaction)

    async def change_page(self, interaction: discord.Interaction, delta: int):
        self.page += delta
        self.page %= self.total_pages
        await self.refresh(interaction)

    async def toggle_category(self, interaction: discord.Interaction, category_key: str):
        categories = self.get_categories()
        info = categories.get(category_key)
        if not info:
            return await interaction.response.send_message(_("That category no longer exists."), ephemeral=True)

        var_names: List[str] = info["variables"]  # type: ignore[assignment]
        state = self.category_state(var_names)
        new_state = state != "on"
        for var_name in var_names:
            self.conf.context_block_var_statuses[f"var:{var_name}"] = new_state
        # Also record the category-level state so admin commands / API
        # consumers can read it without re-aggregating.
        self.conf.context_block_var_statuses[category_key] = new_state
        await self.save()
        await self.refresh(interaction)

    async def apply_variable_selection(
        self,
        interaction: discord.Interaction,
        category_key: str,
        variables: List[str],
        selected: Set[str],
    ):
        for var_name in variables:
            self.conf.context_block_var_statuses[f"var:{var_name}"] = var_name in selected
        # Update aggregate category state (all per-var True → category True).
        all_on = all(self.conf.context_block_var_statuses.get(f"var:{name}", False) for name in variables)
        self.conf.context_block_var_statuses[category_key] = all_on
        await self.save()
        await self.refresh(interaction)


class CodeMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        db: DB,
        registry: Dict[str, Dict[str, dict]],
        save_func: Callable,
        fetch_pages: Callable,
    ):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.db = db
        self.conf = db.get_conf(ctx.guild)
        self.registry = registry
        self.save = save_func
        self.fetch_pages = fetch_pages

        self.has_skip = True

        self.page = 0
        self.pages: List[discord.Embed] = []
        self.message: discord.Message = None

        if ctx.author.id not in ctx.bot.owner_ids:
            self.remove_item(self.new_function)
            self.remove_item(self.delete)
            self.remove_item(self.edit)
            self.remove_item(self.view_function)

            # Let users see but not touch
            if not ctx.author.guild_permissions.manage_guild:
                self.remove_item(self.toggle)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        with suppress(discord.HTTPException):
            await self.message.edit(view=None)
        return await super().on_timeout()

    async def get_pages(self) -> None:
        self.pages = await self.fetch_pages(self.ctx.author)
        self.update_button()
        if len(self.pages) > 30 and not self.has_skip:
            self.add_item(self.left10)
            self.add_item(self.right10)
            self.close.row = 2
            self.has_skip = True
        elif len(self.pages) <= 30 and self.has_skip:
            self.remove_item(self.left10)
            self.remove_item(self.right10)
            self.close.row = 0
            self.has_skip = False

    async def start(self):
        self.message = await self.ctx.send(embed=self.pages[self.page], view=self)

    def test_func(self, function_string: str) -> bool:
        try:
            compile(function_string, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def schema_valid(self, schema: dict) -> str:
        missing = ""
        if "name" not in schema:
            missing += "- `name`\n"
        if "description" not in schema:
            missing += "- `description`\n"
        if "parameters" not in schema:
            missing += "- `parameters`\n"
        if "parameters" in schema:
            if "type" not in schema["parameters"]:
                missing += "- `type` in **parameters**\n"
            if "properties" not in schema["parameters"]:
                missing = "- `properties` in **parameters**\n"
        return missing

    def update_button(self):
        if not self.pages:
            return
        if not self.pages[self.page].fields:
            return
        function_name = self.pages[self.page].description
        enabled = self.conf.function_statuses.get(function_name, False)
        if enabled:
            self.toggle.emoji = ON_EMOJI
            self.toggle.style = discord.ButtonStyle.success
        else:
            self.toggle.emoji = OFF_EMOJI
            self.toggle.style = discord.ButtonStyle.secondary

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}")
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 10
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page -= 1
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{CROSS MARK}")
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        await interaction.response.defer()
        await self.message.delete()
        self.stop()

    @discord.ui.button(
        style=discord.ButtonStyle.secondary,
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 1
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}")
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.page += 10
        self.page %= len(self.pages)
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{PRINTER}\N{VARIATION SELECTOR-16}", row=1)
    async def view_function(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to inspect!"), ephemeral=True)
        function_name = self.pages[self.page].description
        if function_name in self.db.functions:
            function_schema = self.db.functions[function_name].jsonschema
            function_code = self.db.functions[function_name].code
        else:
            # Registered function
            for cog_name, functions in self.registry.items():
                cog = self.ctx.bot.get_cog(cog_name)
                if not cog:
                    continue
                if function_name in functions:
                    function_schema = functions[function_name]["schema"]
                    function_obj = getattr(cog, function_name, None)
                    if not function_obj:
                        continue
                    function_code = inspect.getsource(function_obj)
                    break
            else:
                return await interaction.response.send_message("Cannot find function!")
        files = [
            text_to_file(function_code, f"{function_name}.py"),
            text_to_file(json.dumps(function_schema, indent=2), f"{function_name}.json"),
        ]
        await interaction.response.send_message(_("Here are your custom functions"), files=files)

    @discord.ui.button(style=discord.ButtonStyle.success, emoji="\N{SQUARED NEW}", row=1)
    async def new_function(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            description=_(
                "Reply to this message with the json schema for your function\n"
                "- [Example Functions](https://github.com/vertyco/vrt-cogs/tree/main/assistant/example-funcs)"
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed)
        message = await wait_message(self.ctx)
        if not message:
            return
        attachments = get_attachments(message)
        try:
            if attachments:
                text = (await attachments[0].read()).decode()
            else:
                text = message.content
            if extracted := extract_code_blocks(text):
                schema: dict = json5.loads(extracted[0].strip())
            else:
                schema: dict = json5.loads(text.strip())
        except Exception as e:
            return await interaction.followup.send(_("SchemaError\n{}").format(box(str(e), "py")))
        if not schema:
            return await interaction.followup.send(_("Empty schema!"))

        if missing := json_schema_invalid(schema):
            return await interaction.followup.send(_("Invalid schema!\n**Missing**\n{}").format(missing))

        function_name = schema["name"]
        embed = discord.Embed(
            description=_("Reply to this message with the custom code"),
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=embed)
        message = await wait_message(self.ctx)
        if not message:
            return
        attachments = get_attachments(message)
        if attachments:
            code = (await attachments[0].read()).decode()
        else:
            code = message.content.strip()
        if extracted := extract_code_blocks(code):
            code = extracted[0]
        if not code_string_valid(code):
            return await interaction.followup.send(_("Invalid function"))

        entry = CustomFunction(code=code, jsonschema=schema)
        if function_name in self.db.functions:
            await interaction.followup.send(_("`{}` has been overwritten!").format(function_name))
        else:
            await interaction.followup.send(_("`{}` has been created!").format(function_name))
        self.db.functions[function_name] = entry
        await self.get_pages()
        self.page = len(self.pages) - 1
        self.update_button()
        await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="\N{MEMO}")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to edit!"), ephemeral=True)

        function_name = self.pages[self.page].description
        if function_name not in self.db.functions:
            for cog, functions in self.registry.items():
                if function_name in functions:
                    break
            else:
                return await interaction.response.send_message(_("Could not find function!"), ephemeral=True)
            return await interaction.response.send_message(
                _("This function is managed by the `{}` cog and cannot be edited").format(cog),
                ephemeral=True,
            )
        entry = self.db.functions[function_name]
        if len(json.dumps(entry.jsonschema, indent=2)) > 4000:
            return await interaction.response.send_message(
                _("The json schema for this function is too long, you'll need to re-upload it to modify"),
                ephemeral=True,
            )
        if len(entry.code) > 4000:
            return await interaction.response.send_message(
                _("The code for this function is too long, you'll need to re-upload it to modify"),
                ephemeral=True,
            )

        perms_str = ", ".join(entry.required_permissions) if entry.required_permissions else ""
        modal = CodeModal(
            json.dumps(entry.jsonschema, indent=2), entry.code, entry.permission_level, perms_str, entry.category
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.schema or not modal.code:
            return
        text = modal.schema
        try:
            schema: dict = json5.loads(text.strip())
        except Exception as e:
            return await interaction.followup.send(_("SchemaError\n{}").format(box(str(e), "py")), ephemeral=True)
        if not schema:
            return await interaction.followup.send(_("Empty schema!"))
        if missing := json_schema_invalid(schema):
            return await interaction.followup.send(
                _("Invalid schema!\n**Missing**\n{}").format(missing), ephemeral=True
            )
        new_name = schema["name"]

        code = modal.code
        if not code_string_valid(code):
            return await interaction.followup.send(_("Invalid function"), ephemeral=True)

        if function_name != new_name:
            self.db.functions[new_name] = CustomFunction(
                code=code,
                jsonschema=schema,
                permission_level=modal.permission_level,
                required_permissions=modal.required_permissions,
                category=modal.category,
            )
            del self.db.functions[function_name]
        else:
            self.db.functions[function_name].code = code
            self.db.functions[function_name].jsonschema = schema
            self.db.functions[function_name].permission_level = modal.permission_level
            self.db.functions[function_name].required_permissions = modal.required_permissions
            self.db.functions[function_name].category = modal.category
        await interaction.followup.send(_("`{}` function updated!").format(function_name), ephemeral=True)
        await self.get_pages()
        await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}", row=2)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to delete!"), ephemeral=True)
        function_name = self.pages[self.page].description
        if function_name not in self.db.functions:
            for cog, functions in self.registry.items():
                if function_name in functions:
                    break
            else:
                return await interaction.response.send_message(_("Could not find function!"), ephemeral=True)
            return await interaction.response.send_message(
                _("This function is managed by the `{}` cog and cannot be deleted").format(cog),
                ephemeral=True,
            )
        del self.db.functions[function_name]
        await self.get_pages()
        self.page %= len(self.pages)
        self.update_button()
        await interaction.response.send_message(_("`{}` has been deleted!").format(function_name), ephemeral=True)
        await self.message.edit(embed=self.pages[self.page], view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.success, emoji=ON_EMOJI, row=2)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.pages[self.page].fields:
            return await interaction.response.send_message(_("No code to toggle!"), ephemeral=True)
        await interaction.response.defer()
        function_name = self.pages[self.page].description
        enabled = self.conf.function_statuses.get(function_name, False)
        if enabled:
            self.conf.function_statuses[function_name] = False
        else:
            self.conf.function_statuses[function_name] = True
        self.update_button()
        await self.message.edit(view=self)
        await self.save()

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="\N{LEFT-POINTING MAGNIFYING GLASS}", row=2)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(_("Search for a function"))
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return
        if modal.query.isdigit():
            self.page = int(modal.query) - 1
            self.page %= len(self.pages)
            return await self.message.edit(embed=self.pages[self.page], view=self)

        query = modal.query.lower()
        # Search by
        # Description
        # Field 0 (json schema)
        # Field 1 (code)

        def _get_matches():
            matches: List[Tuple[int, int]] = []
            for i, embed in enumerate(self.pages):
                code_field = embed.fields[-1]
                schema_field = embed.fields[-2]

                if query == embed.description.lower():
                    matches.append((100, i))
                    break
                if query in code_field.value.lower():
                    matches.append((98, i))
                    continue
                if query in schema_field.value.lower():
                    matches.append((98, i))
                    continue

                matches.append((fuzz.ratio(query, embed.description.lower()), i))

            if len(matches) > 1:
                matches.sort(key=lambda x: x[0], reverse=True)

            return matches

        sorted_functions = await asyncio.to_thread(_get_matches)
        best = sorted_functions[0][1]

        self.page = best
        self.page %= len(self.pages)

        self.update_button()

        await self.message.edit(embed=self.pages[self.page], view=self)
