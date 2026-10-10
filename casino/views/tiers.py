"""Memberships in chat: a menu to read one (everyone), and the designer that makes and changes them (admins)"""

import logging

import discord
from redbot.core.i18n import Translator

from ..commands.embeds import tier_embed
from ..common.info import tiers
from ..common.memberships import clean_membership, has_requirements, open_tier_warning
from .choose import Choose

log = logging.getLogger("red.vrt.casino")
_ = Translator("Casino", __file__)

TIMEOUT = 180


def tier_options(shown) -> list[discord.SelectOption]:
    # A select menu holds 25 options at most
    return [discord.SelectOption(label=tier["name"], value=str(tier["id"])) for tier in list(shown)[:25]]


class OwnedView(discord.ui.View):
    """Only the person who ran the command can use it"""

    def __init__(self, author_id: int):
        super().__init__(timeout=TIMEOUT)
        self.author_id = author_id
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        # Buttons that no longer answer would only look broken
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.debug("Could not disable a timed out menu", exc_info=e)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(_("This isn't your menu."), ephemeral=True)
            return False
        return True


class TierReader(OwnedView):
    """[p]casino memberships: pick a tier to see its perks, requirements and games"""

    def __init__(self, author_id: int, shown: list[dict]):
        super().__init__(author_id)
        self.shown = {str(tier["id"]): tier for tier in shown}
        picker = discord.ui.Select(placeholder=_("Pick a membership"), options=tier_options(shown))
        picker.callback = self.pick
        self.picker = picker
        self.add_item(picker)

    async def pick(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=tier_embed(self.shown[self.picker.values[0]]))


def open_warning(tier: dict, scope: int) -> str | None:
    """The editor's warning for a tier with no requirements: every player gets it (scope 0 is global mode)"""
    return None if has_requirements(tier, scope == 0) else open_tier_warning()


def tier_fields(tier: dict | None) -> dict:
    """A shown tier's saved fields, as clean_membership takes them"""
    if tier is None:
        return {}
    keys = ("name", "color", "access", "reduction", "bonus", "req_credits", "req_role_id", "req_days")
    return {key: tier[key] for key in keys}


class Designer(OwnedView):
    """[p]casino memdesigner: make a new tier, or pick one to change or delete"""

    def __init__(self, cog, author_id: int, scope: int, guild, shown: list[dict]):
        super().__init__(author_id)
        self.cog, self.scope, self.guild = cog, scope, guild
        self.shown = {str(tier["id"]): tier for tier in shown}
        self.picker: discord.ui.Select | None = None
        create = discord.ui.Button(label=_("New membership"), style=discord.ButtonStyle.success)
        create.callback = self.create
        self.add_item(create)
        self.fit_picker()

    def fit_picker(self) -> None:
        """The select lists the tiers as they are now; with none left it goes away"""
        if self.is_finished():
            return
        if self.picker is not None:
            self.remove_item(self.picker)
            self.picker = None
        if self.shown:
            picker = discord.ui.Select(placeholder=_("Change a membership"), options=tier_options(self.shown.values()))
            picker.callback = self.pick
            self.picker = picker
            self.add_item(picker)

    async def show_again(self) -> None:
        # A timed out designer stays as it was left: disabled
        if self.message is not None and not self.is_finished():
            try:
                await self.message.edit(view=self)
            except discord.HTTPException as e:
                log.debug("Could not update the membership designer", exc_info=e)

    async def create(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PerksForm(self, None))

    async def pick(self, interaction: discord.Interaction):
        tier = self.shown[self.picker.values[0]]
        editor = TierEditor(self, tier)
        await interaction.response.send_message(open_warning(tier, self.scope), embed=tier_embed(tier), view=editor)
        editor.message = await interaction.original_response()

    async def save(self, interaction: discord.Interaction, tier: dict | None, data: dict) -> None:
        """Checks and saves a tier, then shows it with its editor"""
        tier_id = tier["id"] if tier else None
        store = self.cog.store
        row = None
        # The name check and the save happen under one lock, so two saves can't both take the same name
        async with store.lock:
            taken = [each.name for each in await store.memberships(self.scope) if each.id != tier_id]
            fields, problem = clean_membership({**tier_fields(tier), **data}, taken)
            if not problem and tier_id is not None and await store.membership(self.scope, tier_id) is None:
                problem = _("That membership is gone.")
            if not problem:
                row = await store.write_membership(self.scope, fields, tier_id)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        # Answer first: the refresh below can take longer than Discord waits
        await interaction.response.defer()
        try:
            await self.cog.refresh(self.scope)
            shown = await tiers(store, self.scope, self.guild)
            self.shown = {str(each["id"]): each for each in shown}
            self.fit_picker()
            await self.show_again()
            saved = self.shown[str(row.id)]
            editor = TierEditor(self, saved)
            editor.message = await interaction.followup.send(
                open_warning(saved, self.scope), embed=tier_embed(saved), view=editor, wait=True
            )
        except Exception as e:
            log.exception("Could not show a saved membership", exc_info=e)
            await interaction.followup.send(
                _("The membership was saved, but showing it failed. Run the command again.")
            )

    async def drop(self, tier_id: int) -> None:
        self.shown.pop(str(tier_id), None)
        self.fit_picker()
        await self.show_again()


class TierEditor(OwnedView):
    def __init__(self, designer: Designer, tier: dict):
        super().__init__(designer.author_id)
        self.designer = designer
        self.tier = tier

    @discord.ui.button(label=_("Perks"), style=discord.ButtonStyle.primary)
    async def perks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PerksForm(self.designer, self.tier))

    @discord.ui.button(label=_("Requirements"), style=discord.ButtonStyle.primary)
    async def requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RequirementsForm(self.designer, self.tier))

    @discord.ui.button(label=_("Delete"), style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = Choose(self.author_id, [("yes", _("Delete it")), ("no", _("Keep it"))], danger=("yes",))
        text = _("Delete {name}? Its players go back to Basic. This can't be undone.").format(name=self.tier["name"])
        await interaction.response.send_message(text, view=view)
        if await view.wait():
            await interaction.edit_original_response(
                content=text + "\n" + _("No answer, so nothing changed."), view=None
            )
            return
        if view.choice != "yes":
            return
        await self.designer.cog.store.delete_membership(self.designer.scope, self.tier["id"])
        await self.designer.cog.refresh(self.designer.scope)
        await self.designer.drop(self.tier["id"])
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException as e:
                log.debug("Could not close the tier editor", exc_info=e)
        await interaction.followup.send(_("{name} has been deleted.").format(name=self.tier["name"]))
        self.stop()


class PerksForm(discord.ui.Modal):
    def __init__(self, designer: Designer, tier: dict | None):
        super().__init__(title=_("Membership"), timeout=TIMEOUT)
        self.designer, self.tier = designer, tier
        fields = tier_fields(tier)
        self.name = discord.ui.TextInput(label=_("Name"), max_length=32, default=fields.get("name"))
        self.color = discord.ui.TextInput(
            label=_("Color"),
            placeholder=_("blue, red, green, orange, purple, yellow, ..."),
            default=fields.get("color", "blue"),
        )
        self.access = discord.ui.TextInput(label=_("Access level"), default=str(fields.get("access", 0)))
        self.reduction = discord.ui.TextInput(
            label=_("Cooldown reduction in seconds"), default=str(fields.get("reduction", 0))
        )
        self.bonus = discord.ui.TextInput(label=_("Bonus payout multiplier"), default=str(fields.get("bonus", 1.0)))
        for item in (self.name, self.color, self.access, self.reduction, self.bonus):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        data = {
            "name": self.name.value,
            "color": self.color.value.strip().lower(),
            "access": self.access.value,
            "reduction": self.reduction.value,
            "bonus": self.bonus.value,
        }
        await self.designer.save(interaction, self.tier, data)


class RequirementsForm(discord.ui.Modal):
    def __init__(self, designer: Designer, tier: dict):
        super().__init__(title=_("Requirements (blank means none)"), timeout=TIMEOUT)
        self.designer, self.tier = designer, tier
        self.credits = discord.ui.TextInput(label=_("Credits"), required=False, default=str(tier["req_credits"] or ""))
        self.days = discord.ui.TextInput(
            label=_("Days in the server (Discord in global mode)"),
            required=False,
            default=str(tier["req_days"] or ""),
        )
        self.role = discord.ui.TextInput(
            label=_("Role name or ID (ignored in global mode)"), required=False, default=tier["req_role"] or ""
        )
        for item in (self.credits, self.days, self.role):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        role_text = self.role.value.strip()
        role = None
        if role_text and interaction.guild is not None:
            role = discord.utils.get(interaction.guild.roles, name=role_text)
            if role is None and role_text.isdigit():
                role = interaction.guild.get_role(int(role_text))
            if role is None:
                await interaction.response.send_message(
                    _("There's no role called {role}.").format(role=role_text), ephemeral=True
                )
                return
        data = {
            "req_credits": self.credits.value.strip(),
            "req_days": self.days.value.strip(),
            "req_role_id": role.id if role else None,
        }
        await self.designer.save(interaction, self.tier, data)
