import asyncio
import contextlib
import logging
import traceback
from datetime import datetime
from typing import Optional, Union

import discord
from discord import ButtonStyle, Interaction, TextStyle
from discord.ui import Button, Modal, TextInput, View
from redbot.core import Config, commands
from redbot.core.i18n import Translator

_ = Translator("SupportViews", __file__)
log = logging.getLogger("red.vrt.supportview")


async def wait_reply(
    ctx: commands.Context, timeout: Optional[int] = 60, delete: Optional[bool] = True
) -> Optional[str]:
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        if delete:
            with contextlib.suppress(
                discord.HTTPException, discord.NotFound, discord.Forbidden
            ):
                await reply.delete(delay=10)
        if res.lower().strip() == _("cancel"):
            return None
        return res.strip()
    except asyncio.TimeoutError:
        return None


def get_color(color: str) -> ButtonStyle:
    if color == "red":
        style = ButtonStyle.red
    elif color == "blue":
        style = ButtonStyle.blurple
    elif color == "green":
        style = ButtonStyle.green
    else:
        style = ButtonStyle.grey
    return style


def get_modal_style(style: str) -> TextStyle:
    if style == "short":
        style = TextStyle.short
    elif style == "long":
        style = TextStyle.long
    else:
        style = TextStyle.paragraph
    return style


class Confirm(View):
    def __init__(self, ctx):
        self.ctx = ctx
        self.value = None
        super().__init__(timeout=60)

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                content=_("You are not allowed to interact with this button."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Yes", style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: Button):
        if not await self.interaction_check(interaction):
            return
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: Button):
        if not await self.interaction_check(interaction):
            return
        self.value = False
        await interaction.response.defer()
        self.stop()


async def confirm(ctx, msg: discord.Message):
    try:
        view = Confirm(ctx)
        await msg.edit(view=view)
        await view.wait()
        if view.value is None:
            await msg.delete()
        else:
            await msg.edit(view=None)
        return view.value
    except Exception as e:
        log.warning(f"Confirm Error: {e}")
        return None


class TestButton(View):
    def __init__(
        self,
        style: str = "grey",
        label: str = "Button Test",
        emoji: Union[discord.Emoji, discord.PartialEmoji, str] = None,
    ):
        super().__init__()
        style = get_color(style)
        butt = discord.ui.Button(label=label, style=style, emoji=emoji)
        self.add_item(butt)


class TicketModal(Modal):
    def __init__(self, title: str, fields: dict):
        self.fields = fields
        super().__init__(title=_("{} Panel").format(title.upper()))
        for info in fields.values():
            field = TextInput(
                label=info["label"],
                style=get_modal_style(info["style"]),
                placeholder=info["placeholder"],
                default=info["default"],
                required=info["required"],
                min_length=info["min_length"],
                max_length=info["max_length"],
            )
            self.add_item(field)
            info["field"] = field

    async def on_submit(self, interaction: discord.Interaction):
        for v in self.fields.values():
            v["answer"] = v["field"].value
        await interaction.response.defer()


class SupportButton(Button):
    def __init__(self, panel: dict):
        super().__init__(
            style=get_color(panel["button_color"]),
            label=panel["button_text"],
            custom_id=panel["name"],
            emoji=panel["button_emoji"],
        )
        self.panel_name = panel["name"]

    async def callback(self, interaction: Interaction):
        try:
            await self.create_ticket(interaction)
        except Exception as e:
            log.error(
                f"Failed to create ticket in {interaction.guild.name}: {e}\n"
                f"TRACEBACK\n"
                f"{traceback.format_exc()}"
            )

    async def create_ticket(self, interaction: Interaction):
        guild = interaction.guild
        user = interaction.user
        roles = [r.id for r in user.roles]
        conf = await self.view.config.guild(guild).all()
        blacklist = conf["blacklist"]
        for rid_uid in blacklist:
            if rid_uid == user.id:
                em = discord.Embed(
                    description=_("You been blacklisted from creating tickets!"),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)
            elif rid_uid in roles:
                em = discord.Embed(
                    description=_(
                        "You have a role that has been blacklisted from creating tickets!"
                    ),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)

        panel = conf["panels"][self.panel_name]
        max_tickets = conf["max_tickets"]
        opened = conf["opened"]
        user_can_close = conf["user_can_close"]
        logchannel = (
            guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None
        )
        uid = str(user.id)
        if uid in opened and max_tickets <= len(opened[uid]):
            em = discord.Embed(
                description=_("You have the maximum amount of tickets opened already!"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)
        category = (
            guild.get_channel(panel["category_id"]) if panel["category_id"] else None
        )
        if not category:
            em = discord.Embed(
                description=_(
                    "The category for this support panel cannot be found!\n"
                    "please contact an admin!"
                ),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        # Throw modal before creating ticket if the panel has one
        form_embed = discord.Embed()
        modal = panel.get("modal")
        answers = {}
        has_response = False
        if modal:
            title = _("Submission Info")
            form_embed = discord.Embed(color=user.color)
            if user.avatar:
                form_embed.set_author(name=title, icon_url=user.avatar.url)
            else:
                form_embed.set_author(name=title)
            m = TicketModal(self.panel_name, modal)
            await interaction.response.send_modal(m)
            await m.wait()
            for v in m.fields.values():
                q = v["label"]
                a = v["answer"]
                if not a:
                    a = _("Unanswered")
                else:
                    has_response = True
                answers[q] = a
                form_embed.add_field(name=q, value=a, inline=False)

        can_read_send = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, attach_files=True
        )
        read_and_manage = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, manage_channels=True
        )
        support = [
            guild.get_role(role_id)
            for role_id in conf["support_roles"]
            if guild.get_role(role_id)
        ]
        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read_send,
        }
        for role in support:
            overwrite[role] = can_read_send
        num = conf["panels"][self.panel_name]["ticket_num"]
        now = datetime.now()
        name_fmt = conf["panels"][self.panel_name]["ticket_name"]
        params = {
            "num": str(num),
            "user": user.name,
            "id": str(user.id),
            "shortdate": now.strftime("%m-%d"),
            "longdate": now.strftime("%m-%d-%Y"),
            "time": now.strftime("%I-%M-%p"),
        }
        channel_name = name_fmt.format(**params) if name_fmt else user.name
        try:
            channel = await category.create_text_channel(
                channel_name, overwrites=overwrite
            )
        except discord.Forbidden:
            em = discord.Embed(
                description=_(
                    "I do not have permission to create new channels, please contact an admin!"
                ),
                color=discord.Color.red(),
            )
            if modal:
                return await interaction.followup.send(embed=em, ephemeral=True)
            else:
                return await interaction.response.send_message(embed=em, ephemeral=True)

        default_message = _("Welcome to your ticket channel ") + f"{user.display_name}!"
        if user_can_close:
            default_message += _(
                "\nYou or an admin can close this with the `close` command"
            )

        messages = conf["panels"][self.panel_name]["ticket_messages"]
        params = {
            "username": user.name,
            "displayname": user.display_name,
            "mention": user.mention,
            "id": str(user.id),
        }
        if messages:
            embeds = []
            for einfo in messages:
                em = discord.Embed(
                    title=einfo["title"].format(**params) if einfo["title"] else None,
                    description=einfo["desc"].format(**params),
                    color=user.color,
                )
                if einfo["footer"]:
                    em.set_footer(text=einfo["footer"].format(**params))
                embeds.append(em)
            msg = await channel.send(user.mention, embeds=embeds)
        else:
            em = discord.Embed(description=default_message, color=user.color)
            if user.avatar:
                em.set_thumbnail(url=user.avatar.url)
            msg = await channel.send(user.mention, embed=em)

        if len(form_embed.fields) > 0:
            await channel.send(embed=form_embed)

        desc = _("Your ticket channel has been created, **[CLICK HERE]({})**").format(
            msg.jump_url
        )
        em = discord.Embed(description=desc, color=user.color)
        if modal:
            await interaction.followup.send(embed=em, ephemeral=True)
        else:
            await interaction.response.send_message(embed=em, ephemeral=True)

        if logchannel:
            ts = int(now.timestamp())
            desc = (
                _("Ticket created by ")
                + f"**{user.name}-{user.id}**"
                + _(" was opened ")
                + f"<t:{ts}:R>\n"
            )
            desc += _("To view this ticket, **[Click Here]({})**").format(msg.jump_url)
            em = discord.Embed(
                title=_("Ticket opened"), description=desc, color=discord.Color.red()
            )
            if user.avatar:
                em.set_thumbnail(url=user.avatar.url)
            log_message = await logchannel.send(embed=em)
        else:
            log_message = None

        async with self.view.config.guild(guild).all() as conf:
            conf["panels"][self.panel_name]["ticket_num"] += 1
            opened = conf["opened"]
            if uid not in opened:
                opened[uid] = {}
            opened[uid][str(channel.id)] = {
                "panel": self.panel_name,
                "opened": now.isoformat(),
                "pfp": str(user.avatar.url) if user.avatar else None,
                "logmsg": log_message.id if log_message else None,
                "answers": answers,
                "has_response": has_response,
            }


class PanelView(View):
    def __init__(
        self,
        guild: discord.Guild,
        config: Config,
        panels: list,  # List of support panels that have the same message/channel ID
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.config = config
        self.panels = panels

    async def start(self):
        for panel in self.panels:
            self.add_item(SupportButton(panel))
        chan = self.guild.get_channel(self.panels[0]["channel_id"])
        message = await chan.fetch_message(self.panels[0]["message_id"])
        await message.edit(view=self)
