import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Union

import discord
import numpy as np
from discord import ButtonStyle, Interaction, TextStyle
from discord.ui import Button, Modal, TextInput, View
from discord.ui.item import Item
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, pagify

from .utils import can_close, close_ticket, update_active_overview

_ = Translator("SupportViews", __file__)
log = logging.getLogger("red.vrt.supportview")


async def wait_reply(
    ctx: commands.Context,
    timeout: Optional[int] = 60,
    delete: Optional[bool] = True,
) -> Optional[str]:
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        if delete:
            with contextlib.suppress(discord.HTTPException, discord.NotFound, discord.Forbidden):
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


class CloseReasonModal(Modal):
    def __init__(self):
        self.reason = None
        super().__init__(title=_("Closing your ticket"), timeout=120)
        self.field = TextInput(
            label=_("Reason for closing"),
            style=TextStyle.short,
            required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: Interaction):
        self.reason = self.field.value
        await interaction.response.defer()
        self.stop()


class CloseView(View):
    def __init__(
        self,
        bot: Red,
        config: Config,
        owner_id: int,
        channel: Union[discord.TextChannel, discord.Thread],
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = config
        self.owner_id = owner_id
        self.channel = channel

        self.closeticket.custom_id = str(channel.id)

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[Any]):
        log.warning(
            f"View failed for user ticket {self.owner_id} in channel {self.channel.name} in {self.channel.guild.name}",
            exc_info=error,
        )
        return await super().on_error(interaction, error, item)

    @discord.ui.button(label="Close", style=ButtonStyle.danger)
    async def closeticket(self, interaction: Interaction, button: Button):
        conf = await self.config.guild(interaction.guild).all()
        if not await can_close(self.bot, interaction.guild, interaction.channel, interaction.user, self.owner_id, conf):
            return await interaction.response.send_message(
                _("You do not have permissions to close this ticket"), ephemeral=True
            )
        panel_name = conf["opened"][str(self.owner_id)][str(self.channel.id)]["panel"]
        requires_reason = conf["panels"][panel_name].get("close_reason", True)
        reason = None
        if requires_reason:
            modal = CloseReasonModal()
            await interaction.response.send_modal(modal)
            await modal.wait()
            if modal.reason is None:
                return
            reason = modal.reason
            await interaction.followup.send(_("Closing..."), ephemeral=True)
        else:
            await interaction.response.send_message(_("Closing..."), ephemeral=True)
        owner = self.channel.guild.get_member(int(self.owner_id))
        if not owner:
            owner = await self.bot.fetch_user(int(self.owner_id))
        await close_ticket(
            bot=self.bot,
            member=owner,
            guild=self.channel.guild,
            channel=self.channel,
            conf=conf,
            reason=reason,
            closedby=interaction.user.display_name,
            config=self.config,
        )


class TicketModal(Modal):
    def __init__(self, title: str, data: dict):
        super().__init__(title=title, timeout=300)
        self.fields = {}
        self.inputs: Dict[str, TextInput] = {}
        for key, info in data.items():
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
            self.inputs[key] = field

    async def on_submit(self, interaction: discord.Interaction):
        for k, v in self.inputs.items():
            self.fields[k] = {"question": v.label, "answer": v.value}
        await interaction.response.defer()
        self.stop()


class SupportButton(Button):
    def __init__(self, panel: dict):
        super().__init__(
            style=get_color(panel["button_color"]),
            label=panel["button_text"],
            custom_id=panel["name"],
            emoji=panel["button_emoji"],
            row=panel.get("row"),
            disabled=panel.get("disabled", False),
        )
        self.panel_name = panel["name"]

    async def callback(self, interaction: Interaction):
        try:
            await self.create_ticket(interaction)
        except Exception as e:
            guild = interaction.guild.name
            user = interaction.user.name
            log.exception(f"Failed to create ticket in {guild} for {user}", exc_info=e)

    async def create_ticket(self, interaction: Interaction):
        guild = interaction.guild
        user = interaction.user
        channel = interaction.channel
        roles = [r.id for r in user.roles]
        conf = await self.view.config.guild(guild).all()

        for rid_uid in conf["blacklist"]:
            if rid_uid == user.id:
                em = discord.Embed(
                    description=_("You been blacklisted from creating tickets!"),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)
            elif rid_uid in roles:
                em = discord.Embed(
                    description=_("You have a role that has been blacklisted from creating tickets!"),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)

        panel = conf["panels"][self.panel_name]
        if required_roles := panel.get("required_roles", []):
            if not any(r.id in required_roles for r in user.roles):
                roles = [guild.get_role(i).mention for i in required_roles if guild.get_role(i)]
                em = discord.Embed(
                    description=_("You must have one of the following roles to open this ticket: ")
                    + humanize_list(roles),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)

        max_tickets = conf["max_tickets"]
        opened = conf["opened"]
        uid = str(user.id)
        if uid in opened and max_tickets <= len(opened[uid]):
            channels = "\n".join([f"<#{i}>" for i in opened[uid]])
            em = discord.Embed(
                description=_("You have the maximum amount of tickets opened already!{}").format(f"\n{channels}"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        category = guild.get_channel(panel["category_id"]) if panel["category_id"] else None
        if not category:
            em = discord.Embed(
                description=_("The category for this support panel cannot be found!\n" "please contact an admin!"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        user_can_close = conf["user_can_close"]
        logchannel = guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None

        # Throw modal before creating ticket if the panel has one
        form_embed = discord.Embed()
        modal = panel.get("modal")
        panel_title = panel.get("modal_title", "{} Ticket".format(self.panel_name))
        answers = {}
        has_response = False
        if modal:
            title = _("Submission Info")
            form_embed = discord.Embed(color=user.color)
            if user.avatar:
                form_embed.set_author(name=title, icon_url=user.display_avatar.url)
            else:
                form_embed.set_author(name=title)

            m = TicketModal(panel_title, modal)
            await interaction.response.send_modal(m)
            await m.wait()

            if not m.fields:
                return

            for submission_info in m.fields.values():
                question = submission_info["question"]
                answer = submission_info["answer"]
                if not answer:
                    answer = _("Unanswered")
                else:
                    has_response = True

                if "DISCOVERABLE" in guild.features and "discord" in answer.lower():
                    txt = _("Your response cannot contain the word 'Discord' in discoverable servers.")
                    return await interaction.followup.send(txt, ephemeral=True)

                answers[question] = answer

                if len(answer) <= 1024:
                    form_embed.add_field(name=question, value=answer, inline=False)
                    continue

                chunks = [ans for ans in pagify(answer, page_length=1024)]
                for index, chunk in enumerate(chunks):
                    form_embed.add_field(
                        name=f"{question} ({index + 1})",
                        value=chunk,
                        inline=False,
                    )

        open_txt = _("Your ticket is being created, one moment...")
        if modal:
            existing_msg = await interaction.followup.send(open_txt, ephemeral=True)
        else:
            await interaction.response.send_message(open_txt, ephemeral=True)
            existing_msg = await interaction.original_response()

        can_read_send = discord.PermissionOverwrite(
            read_messages=True,
            read_message_history=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            use_application_commands=True,
        )
        read_and_manage = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            manage_channels=True,
            manage_messages=True,
        )

        support_roles = []
        support_mentions = []
        panel_roles = []
        panel_mentions = []
        for role_id, mention_toggle in conf["support_roles"]:
            role = guild.get_role(role_id)
            if not role:
                continue
            support_roles.append(role)
            if mention_toggle:
                support_mentions.append(role.mention)
        for role_id, mention_toggle in panel.get("roles", []):
            role = guild.get_role(role_id)
            if not role:
                continue
            panel_roles.append(role)
            if mention_toggle:
                panel_mentions.append(role.mention)

        support_roles.extend(panel_roles)
        support_mentions.extend(panel_mentions)

        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read_send,
        }
        for role in support_roles:
            overwrite[role] = can_read_send

        num = panel["ticket_num"]
        now = datetime.now().astimezone()
        name_fmt = panel["ticket_name"]
        params = {
            "num": str(num),
            "user": user.name,
            "displayname": user.display_name,
            "id": str(user.id),
            "shortdate": now.strftime("%m-%d"),
            "longdate": now.strftime("%m-%d-%Y"),
            "time": now.strftime("%I-%M-%p"),
        }
        channel_name = name_fmt.format(**params) if name_fmt else user.name
        try:
            if panel.get("threads"):
                if alt_cid := panel.get("alt_channel"):
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.TextChannel):
                        channel = alt_channel
                archive = round(conf["inactive"] * 60)
                arr = np.asarray([60, 1440, 4320, 10080])
                index = (np.abs(arr - archive)).argmin()
                auto_archive_duration = int(arr[index])

                reason = _("{} ticket for {}").format(self.panel_name, str(interaction.user))
                channel_or_thread: discord.Thread = await channel.create_thread(
                    name=channel_name,
                    auto_archive_duration=auto_archive_duration,
                    reason=reason,
                    invitable=conf["user_can_manage"],
                )
                asyncio.create_task(channel_or_thread.add_user(interaction.user))
                if conf["auto_add"] and not support_mentions:
                    for role in support_roles:
                        for member in role.members:
                            asyncio.create_task(channel_or_thread.add_user(member))
            else:
                if alt_cid := panel.get("alt_channel"):
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.CategoryChannel):
                        category = alt_channel
                    elif alt_channel and isinstance(alt_channel, discord.TextChannel):
                        if alt_channel.category:
                            category = alt_channel.category
                channel_or_thread: discord.TextChannel = await category.create_text_channel(
                    channel_name, overwrites=overwrite
                )
        except discord.Forbidden:
            txt = _(
                "I am missing the required permissions to create a ticket for you. "
                "Please contact an admin so they may fix my permissions."
            )
            em = discord.Embed(description=txt, color=discord.Color.red())
            return await interaction.followup.send(embed=em, ephemeral=True)

        except Exception as e:
            em = discord.Embed(
                description=_("There was an error while preparing your ticket, please contact an admin!\n{}").format(
                    box(str(e), "py")
                ),
                color=discord.Color.red(),
            )
            log.info(f"Failed to create ticket for {user.display_name} in {guild.name}", exc_info=e)
            return await interaction.followup.send(embed=em, ephemeral=True)

        prefix = (await self.view.bot.get_valid_prefixes(self.view.guild))[0]
        default_message = _("Welcome to your ticket channel ") + f"{user.display_name}!"
        if user_can_close:
            default_message += _("\nYou or an admin can close this with the `{}close` command").format(prefix)

        messages = panel["ticket_messages"]
        params = {
            "username": user.name,
            "displayname": user.display_name,
            "mention": user.mention,
            "id": str(user.id),
            "server": guild.name,
            "guild": guild.name,
            "members": int(guild.member_count or len(guild.members)),
            "toprole": user.top_role.name,
        }

        def fmt_params(text: str) -> str:
            for k, v in params.items():
                text = text.replace("{" + str(k) + "}", str(v))
            return text

        content = "" if panel.get("threads") else user.mention
        if support_mentions:
            if not panel.get("threads"):
                support_mentions.append(user.mention)
            content = " ".join(support_mentions)

        allowed_mentions = discord.AllowedMentions(roles=True)
        close_view = CloseView(
            self.view.bot,
            self.view.config,
            user.id,
            channel_or_thread,
        )
        if messages:
            embeds = []
            for index, einfo in enumerate(messages):
                em = discord.Embed(
                    title=fmt_params(einfo["title"]) if einfo["title"] else None,
                    description=fmt_params(einfo["desc"]),
                    color=user.color,
                )
                if index == 0:
                    em.set_thumbnail(url=user.display_avatar.url)
                if einfo["footer"]:
                    em.set_footer(text=fmt_params(einfo["footer"]))
                embeds.append(em)

            msg = await channel_or_thread.send(
                content=content, embeds=embeds, allowed_mentions=allowed_mentions, view=close_view
            )
        else:
            # Default message
            em = discord.Embed(description=default_message, color=user.color)
            em.set_thumbnail(url=user.display_avatar.url)
            msg = await channel_or_thread.send(
                content=content, embed=em, allowed_mentions=allowed_mentions, view=close_view
            )

        if len(form_embed.fields) > 0:
            form_msg = await channel_or_thread.send(embed=form_embed)
            try:
                asyncio.create_task(form_msg.pin(reason=_("Ticket form questions")))
            except discord.Forbidden:
                txt = _("I tried to pin the response message but don't have the manage messages permissions!")
                asyncio.create_task(channel_or_thread.send(txt))

        desc = _("Your ticket has been created! {}").format(channel_or_thread.mention)
        em = discord.Embed(description=desc, color=user.color)
        with contextlib.suppress(discord.HTTPException):
            if existing_msg:
                asyncio.create_task(existing_msg.edit(content=None, embed=em))
            else:
                asyncio.create_task(interaction.followup.send(embed=em, ephemeral=True))

        if logchannel:
            ts = int(now.timestamp())
            kwargs = {
                "user": str(user),
                "userid": user.id,
                "timestamp": f"<t:{ts}:R>",
                "channelname": channel_name,
                "panelname": self.panel_name,
                "jumpurl": msg.jump_url,
            }
            desc = _(
                "`Created By: `{user}\n"
                "`User ID:    `{userid}\n"
                "`Opened:     `{timestamp}\n"
                "`Ticket:     `{channelname}\n"
                "`Panel Name: `{panelname}\n"
                "**[Click to Jump!]({jumpurl})**"
            ).format(**kwargs)
            em = discord.Embed(
                title=_("Ticket Opened"),
                description=desc,
                color=discord.Color.red(),
            )
            if user.avatar:
                em.set_thumbnail(url=user.display_avatar.url)

            for question, answer in answers.items():
                em.add_field(name=f"__{question}__", value=answer, inline=False)

            view = LogView(guild, channel_or_thread, panel.get("max_claims", 0))
            log_message = await logchannel.send(embed=em, view=view)
        else:
            log_message = None

        async with self.view.config.guild(guild).all() as data:
            data["panels"][self.panel_name]["ticket_num"] += 1
            if uid not in data["opened"]:
                data["opened"][uid] = {}
            data["opened"][uid][str(channel_or_thread.id)] = {
                "panel": self.panel_name,
                "opened": now.isoformat(),
                "pfp": str(user.display_avatar.url) if user.avatar else None,
                "logmsg": log_message.id if log_message else None,
                "answers": answers,
                "has_response": has_response,
                "message_id": msg.id,
                "max_claims": data["panels"][self.panel_name].get("max_claims", 0),
            }

            new_id = await update_active_overview(guild, data)
            if new_id:
                data["overview_msg"] = new_id


class PanelView(View):
    def __init__(
        self,
        bot: Red,
        guild: discord.Guild,
        config: Config,
        panels: list,  # List of support panels that have the same message/channel ID
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.config = config
        self.panels = panels
        for panel in self.panels:
            self.add_item(SupportButton(panel))

    async def start(self):
        chan = self.guild.get_channel(self.panels[0]["channel_id"])
        message = await chan.fetch_message(self.panels[0]["message_id"])
        await message.edit(view=self)


class LogView(View):
    def __init__(
        self,
        guild: discord.Guild,
        channel: Union[discord.TextChannel, discord.Thread],
        max_claims: int,
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.channel = channel
        self.max_claims = max_claims

        self.added = set()
        self.join_ticket.custom_id = str(channel.id)

    @discord.ui.button(label="Join Ticket", style=ButtonStyle.green)
    async def join_ticket(self, interaction: Interaction, button: Button):
        user = interaction.user
        if user.id in self.added:
            return await interaction.response.send_message(
                _("You have already been added to the ticket **{}**!").format(self.channel.name),
                ephemeral=True,
                delete_after=60,
            )
        if self.max_claims and len(self.added) >= self.max_claims:
            return await interaction.response.send_message(
                _("The maximum amount of staff have claimed this ticket!"),
                ephemeral=True,
                delete_after=60,
            )
        perms = [
            self.channel.permissions_for(user).view_channel,
            self.channel.permissions_for(user).send_messages,
        ]
        if isinstance(self.channel, discord.TextChannel):
            if all(perms):
                return await interaction.response.send_message(
                    _("You already have access to the ticket **{}**!").format(self.channel.name),
                    ephemeral=True,
                    delete_after=60,
                )
            await self.channel.set_permissions(user, read_messages=True, send_messages=True)
            await self.channel.send(_("{} was added to the ticket").format(str(user)))
        else:
            await self.channel.add_user(user)
        self.added.add(user.id)
        await interaction.response.send_message(
            _("You have been added to the ticket **{}**").format(self.channel.name),
            ephemeral=True,
            delete_after=60,
        )
