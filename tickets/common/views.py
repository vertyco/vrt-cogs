import asyncio
import contextlib
import logging
import typing as t
from datetime import datetime

import discord
import numpy as np
from discord import ButtonStyle, Interaction, TextStyle
from discord.ui import Button, Modal, TextInput, View
from discord.ui.item import Item
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_list, pagify

from ..abc import MixinMeta
from .analytics import record_ticket_claimed, record_ticket_opened
from .models import GuildSettings, ModalField, OpenedTicket, Panel
from .utils import (
    can_close,
    close_ticket,
    format_response_time,
    format_working_hours_embed,
    get_average_response_time,
    is_within_working_hours,
    update_active_overview,
)

_ = Translator("SupportViews", __file__)
log = logging.getLogger("red.vrt.supportview")


async def wait_reply(
    ctx: commands.Context,
    timeout: int | None = 60,
    delete: bool | None = True,
) -> str | None:
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


def get_modal_style(styletype: str) -> TextStyle:
    if styletype == "short":
        style = TextStyle.short
    elif styletype == "long":
        style = TextStyle.long
    else:
        style = TextStyle.paragraph
    return style


class Confirm(View):
    def __init__(self, ctx: commands.Context):
        self.ctx: commands.Context = ctx
        self.value: bool | None = None
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
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: Button):
        if not await self.interaction_check(interaction):
            return
        self.value = False
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()


async def confirm(ctx: commands.Context, message: str | discord.Message) -> bool | None:
    """Show a confirmation dialog with Yes/No buttons.

    Args:
        ctx: The command context
        message: Either a string to send as a new message, or an existing Message to edit

    Returns:
        True if confirmed, False if denied, None if timed out
    """
    try:
        view: Confirm = Confirm(ctx)

        # Handle both string messages and existing Message objects
        if isinstance(message, str):
            msg = await ctx.send(message, view=view)
        else:
            msg = message
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
        emoji: discord.Emoji | discord.PartialEmoji | str | None = None,
    ):
        super().__init__()
        style = get_color(style)
        butt = discord.ui.Button(label=label, style=style, emoji=emoji)
        self.add_item(butt)


class CloseReasonModal(Modal):
    def __init__(self):
        self.reason: str | None = None
        super().__init__(title=_("Closing your ticket"), timeout=120)
        self.field: TextInput = TextInput(
            label=_("Reason for closing"),
            style=TextStyle.short,
            required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: Interaction):
        self.reason = self.field.value
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()


class CloseView(View):
    def __init__(
        self,
        bot: Red,
        cog: "MixinMeta",
        owner_id: int,
        channel: discord.TextChannel | discord.Thread,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.cog = cog
        self.owner_id = owner_id
        self.channel = channel

        self.closeticket.custom_id = str(channel.id)

    async def on_error(self, interaction: Interaction, error: Exception, item: Item[t.Any]):
        log.warning(
            f"View failed for user ticket {self.owner_id} in channel {self.channel.name} in {self.channel.guild.name}",
            exc_info=error,
        )
        return await super().on_error(interaction, error, item)

    @discord.ui.button(label="Close", style=ButtonStyle.danger)
    async def closeticket(self, interaction: Interaction, button: Button):
        if not interaction.guild or not interaction.channel:
            return
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return

        conf = self.cog.db.get_conf(interaction.guild)
        txt = _("This ticket has already been closed! Please delete it manually.")
        if self.owner_id not in conf.opened:
            return await interaction.response.send_message(txt, ephemeral=True)
        if self.channel.id not in conf.opened[self.owner_id]:
            return await interaction.response.send_message(txt, ephemeral=True)

        allowed = await can_close(
            bot=self.bot,
            guild=interaction.guild,
            channel=interaction.channel,
            author=user,
            owner_id=self.owner_id,
            conf=conf,
        )
        if not allowed:
            return await interaction.response.send_message(
                _("You do not have permissions to close this ticket"),
                ephemeral=True,
            )
        panel_name = conf.opened[self.owner_id][self.channel.id].panel
        requires_reason = conf.panels[panel_name].close_reason
        reason = None
        if requires_reason:
            modal = CloseReasonModal()
            try:
                await interaction.response.send_modal(modal)
            except discord.NotFound as e:
                log.warning(f"Failed to send ticket modal for panel {panel_name}", exc_info=e)
                txt = _("Something went wrong, please try again.")
                try:
                    await interaction.followup.send(txt, ephemeral=True)
                except discord.NotFound:
                    channel = interaction.channel
                    if channel and isinstance(channel, discord.abc.Messageable):
                        await channel.send(txt, delete_after=10)
                return

            await modal.wait()
            if modal.reason is None:
                return
            reason = modal.reason
            await interaction.followup.send(_("Closing..."), ephemeral=True)
        else:
            await interaction.response.send_message(_("Closing..."), ephemeral=True)
        owner = self.channel.guild.get_member(self.owner_id)
        if not owner:
            owner = await self.bot.fetch_user(self.owner_id)
        await close_ticket(
            bot=self.bot,
            member=owner,
            guild=self.channel.guild,
            channel=self.channel,
            conf=conf,
            reason=reason,
            closedby=interaction.user.id,
            cog=self.cog,
        )


class TicketModal(Modal):
    def __init__(self, title: str, data: dict[str, ModalField]):
        super().__init__(title=title, timeout=300)
        self.fields: dict[str, dict[str, str]] = {}
        self.inputs: dict[str, TextInput] = {}
        self.labels: dict[str, str] = {}  # Store labels separately to avoid deprecation warning
        for key, info in data.items():
            field: TextInput = TextInput(
                label=info.label,
                style=get_modal_style(info.style),
                placeholder=info.placeholder,
                default=info.default,
                required=info.required,
                min_length=info.min_length,
                max_length=info.max_length,
            )
            self.add_item(field)
            self.inputs[key] = field
            self.labels[key] = info.label

    async def on_submit(self, interaction: discord.Interaction):
        for k, v in self.inputs.items():
            self.fields[k] = {"question": self.labels[k], "answer": v.value}
        with contextlib.suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()


class SupportButton(Button):
    def __init__(self, panel_name: str, panel: Panel, mock_user: discord.Member | None = None):
        """Create a support button.

        Args:
            panel_name: Name of the panel
            panel: Panel model
            mock_user: Optional user to create ticket for (for testing)
        """
        super().__init__(
            style=get_color(panel.button_color),
            label=panel.button_text,
            custom_id=panel_name,
            emoji=panel.button_emoji,
            row=panel.row,
            disabled=panel.disabled,
        )
        self.panel_name: str = panel_name
        self.mock_user: discord.Member | None = mock_user

    async def callback(self, interaction: Interaction):
        try:
            await self.create_ticket(interaction)
        except Exception as e:
            guild = interaction.guild.name
            user = self.mock_user.name if self.mock_user else interaction.user.name
            log.exception(f"Failed to create ticket in {guild} for {user}", exc_info=e)

    async def create_ticket(self, interaction: Interaction):
        guild: discord.Guild | None = interaction.guild
        user: discord.Member | None = self.mock_user or guild.get_member(interaction.user.id) if guild else None
        if not isinstance(interaction.channel, discord.TextChannel) or not guild:
            return

        roles = [r.id for r in user.roles]
        conf: GuildSettings = self.view.cog.db.get_conf(guild)
        if conf.suspended_msg:
            em = discord.Embed(
                title=_("Ticket System Suspended"),
                description=conf.suspended_msg,
                color=discord.Color.yellow(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        for rid_uid in conf.blacklist:
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

        panel: Panel = conf.panels[self.panel_name]
        if required_roles := panel.required_roles:
            if not any(r.id in required_roles for r in user.roles):
                roles_list = [guild.get_role(i).mention for i in required_roles if guild.get_role(i)]
                em = discord.Embed(
                    description=_("You must have one of the following roles to open this ticket: ")
                    + humanize_list(roles_list),
                    color=discord.Color.red(),
                )
                return await interaction.response.send_message(embed=em, ephemeral=True)

        # Check working hours
        within_hours, start_time, end_time = is_within_working_hours(panel)
        if not within_hours and panel.block_outside_hours:
            em = discord.Embed(
                title=_("Outside Working Hours"),
                description=_("Tickets cannot be opened outside of working hours. Please try again later."),
                color=discord.Color.red(),
            )
            if start_time and end_time:
                em.add_field(
                    name=_("Working Hours"),
                    value=f"<t:{start_time}:t> - <t:{end_time}:t>",
                    inline=False,
                )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        channel: discord.TextChannel = guild.get_channel(panel.channel_id or 0)
        if not channel:
            channel = interaction.channel

        max_tickets = conf.max_tickets
        opened = conf.opened
        uid = user.id
        if uid in opened and max_tickets <= len(opened[uid]):
            channels = "\n".join([f"<#{i}>" for i in opened[uid]])
            em = discord.Embed(
                description=_("You have the maximum amount of tickets opened already!{}").format(f"\n{channels}"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        category = guild.get_channel(panel.category_id) if panel.category_id else None
        if not category:
            em = discord.Embed(
                description=_("The category for this support panel cannot be found!\nplease contact an admin!"),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)
        if not isinstance(category, discord.CategoryChannel):
            em = discord.Embed(
                description=_(
                    "The category for this support panel is not a category channel!\nplease contact an admin!"
                ),
                color=discord.Color.red(),
            )
            return await interaction.response.send_message(embed=em, ephemeral=True)

        user_can_close = conf.user_can_close
        logchannel = guild.get_channel(panel.log_channel) if panel.log_channel else None

        # Throw modal before creating ticket if the panel has one
        form_embed = discord.Embed()
        modal = panel.modal
        panel_title = panel.modal_title or "{} Ticket".format(self.panel_name)
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
            try:
                await interaction.response.send_modal(m)
            except discord.NotFound:
                return
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
        for role_id, mention_toggle in conf.support_roles:
            role = guild.get_role(role_id)
            if not role:
                continue
            support_roles.append(role)
            if mention_toggle:
                support_mentions.append(role.mention)
        for role_id, mention_toggle in panel.roles:
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

        num = panel.ticket_num
        now = datetime.now().astimezone()
        name_fmt = panel.ticket_name
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
        default_channel_name = f"{self.panel_name}-{num}"
        try:
            if panel.threads:
                if alt_cid := panel.alt_channel:
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.TextChannel):
                        channel = alt_channel

                if not channel.permissions_for(guild.me).manage_threads:
                    return await interaction.followup.send(
                        "I don't have permissions to create threads!", ephemeral=True
                    )

                archive = round(conf.inactive * 60)
                arr = np.asarray([60, 1440, 4320, 10080])
                index = (np.abs(arr - archive)).argmin()
                auto_archive_duration = int(arr[index])

                reason = _("{} ticket for {}").format(self.panel_name, str(interaction.user))
                try:
                    channel_or_thread = await channel.create_thread(
                        name=channel_name,
                        auto_archive_duration=auto_archive_duration,  # type: ignore
                        reason=reason,
                        invitable=conf.user_can_manage,
                    )
                except discord.Forbidden:
                    return await interaction.followup.send(
                        _("I don't have permissions to create threads!"), ephemeral=True
                    )
                except Exception as e:
                    if "Contains words not allowed" in str(e):
                        channel_or_thread = await channel.create_thread(
                            name=default_channel_name,
                            auto_archive_duration=auto_archive_duration,
                            reason=reason,
                            invitable=conf.user_can_manage,
                        )
                        await channel_or_thread.send(
                            _(
                                "I was not able to name the ticket properly due to Discord's filter!\nIntended name: {}"
                            ).format(channel_name)
                        )
                    else:
                        raise e
                asyncio.create_task(channel_or_thread.add_user(interaction.user))
                if self.mock_user:
                    asyncio.create_task(channel_or_thread.add_user(self.mock_user))
                if conf.auto_add and not support_mentions:
                    for role in support_roles:
                        for member in role.members:
                            asyncio.create_task(channel_or_thread.add_user(member))
            else:
                if alt_cid := panel.alt_channel:
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.CategoryChannel):
                        category = alt_channel
                    elif alt_channel and isinstance(alt_channel, discord.TextChannel):
                        if alt_channel.category:
                            category = alt_channel.category
                if not category.permissions_for(guild.me).manage_channels:
                    return await interaction.followup.send(
                        _("I don't have permissions to create channels!"),
                        ephemeral=True,
                    )
                try:
                    channel_or_thread = await category.create_text_channel(channel_name, overwrites=overwrite)
                except discord.Forbidden:
                    return await interaction.followup.send(
                        _("I don't have permissions to create channels under this category!"),
                        ephemeral=True,
                    )
                except Exception as e:
                    if "Contains words not allowed" in str(e):
                        channel_or_thread = await category.create_text_channel(
                            default_channel_name, overwrites=overwrite
                        )
                        await channel_or_thread.send(
                            _(
                                "I was not able to name the ticket properly due to Discord's filter!\nIntended name: {}"
                            ).format(channel_name)
                        )
                    else:
                        raise e
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
            log.info(
                f"Failed to create ticket for {user.name} in {guild.name}",
                exc_info=e,
            )
            return await interaction.followup.send(embed=em, ephemeral=True)

        prefix = (await self.view.bot.get_valid_prefixes(self.view.guild))[0]
        default_message = _("Welcome to your ticket channel ") + f"{user.display_name}!"
        if user_can_close:
            default_message += _("\nYou or an admin can close this with the `{}close` command").format(prefix)

        messages = panel.ticket_messages
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

        content = "" if panel.threads else user.mention
        if support_mentions:
            if not panel.threads:
                support_mentions.append(user.mention)
            content = " ".join(support_mentions)

        allowed_mentions = discord.AllowedMentions(roles=True)
        close_view = CloseView(
            self.view.bot,
            self.view.cog,
            user.id,
            channel_or_thread,
        )
        if messages:
            embeds: list[discord.Embed] = []
            for index, einfo in enumerate(messages):
                # Use custom color if set and valid, otherwise default to user's color
                color_val = einfo.color
                embed_color = (
                    discord.Color(color_val) if color_val is not None and isinstance(color_val, int) else user.color
                )
                em = discord.Embed(
                    title=fmt_params(einfo.title) if einfo.title else None,
                    description=fmt_params(einfo.desc),
                    color=embed_color,
                )
                if index == 0:
                    em.set_thumbnail(url=user.display_avatar.url)
                if einfo.footer:
                    em.set_footer(text=fmt_params(einfo.footer))
                # Set image if configured
                if einfo.image:
                    em.set_image(url=einfo.image)
                embeds.append(em)

            msg = await channel_or_thread.send(
                content=content,
                embeds=embeds,
                allowed_mentions=allowed_mentions,
                view=close_view,
            )
        else:
            # Default message
            em = discord.Embed(description=default_message, color=user.color)
            em.set_thumbnail(url=user.display_avatar.url)
            msg = await channel_or_thread.send(
                content=content,
                embed=em,
                allowed_mentions=allowed_mentions,
                view=close_view,
            )

        if len(form_embed.fields) > 0:
            form_msg = await channel_or_thread.send(embed=form_embed)
            try:
                asyncio.create_task(form_msg.pin(reason=_("Ticket form questions")))
            except discord.Forbidden:
                txt = _("I tried to pin the response message but don't have the manage messages permissions!")
                asyncio.create_task(channel_or_thread.send(txt))

        # Send outside working hours notice if applicable
        if not within_hours and panel.working_hours:
            hours_embed = format_working_hours_embed(panel, user)
            if hours_embed:
                await channel_or_thread.send(embed=hours_embed)

        # Send average response time notice if we have data and it's enabled
        if conf.show_response_time:
            response_times = conf.response_times
            avg_response = get_average_response_time(response_times)
            if avg_response is not None:
                formatted_time = format_response_time(avg_response)
                response_embed = discord.Embed(
                    description=_("⏱️ Our average staff response time is **{}**.").format(formatted_time),
                    color=discord.Color.blue(),
                )
                await channel_or_thread.send(embed=response_embed)

        async def delete_delay():
            desc = _("Your ticket has been created! {}").format(channel_or_thread.mention)
            em = discord.Embed(description=desc, color=user.color)
            with contextlib.suppress(discord.HTTPException):
                if existing_msg:
                    await existing_msg.edit(content=None, embed=em)
                    await existing_msg.delete(delay=30)
                else:
                    msg = await interaction.followup.send(embed=em, ephemeral=True)
                    if msg:
                        await msg.delete(delay=30)

        asyncio.create_task(delete_delay())

        if (
            logchannel
            and isinstance(logchannel, discord.TextChannel)
            and logchannel.permissions_for(guild.me).send_messages
        ):
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

            view = LogView(guild, channel_or_thread, panel.max_claims, cog=self.view.cog)
            log_message = await logchannel.send(embed=em, view=view)
        else:
            log_message = None

        # Update the config and save - if this fails, clean up the ticket channel
        try:
            panel.ticket_num += 1
            cid = channel_or_thread.id
            if uid not in conf.opened:
                conf.opened[uid] = {}
            conf.opened[uid][cid] = OpenedTicket(
                panel=self.panel_name,
                opened=now,
                pfp=str(user.display_avatar.url) if user.avatar else None,
                logmsg=log_message.id if log_message else None,
                answers=answers,
                has_response=has_response,
                message_id=msg.id,
                max_claims=panel.max_claims,
                first_response=None,
            )

            # Record analytics for ticket opened
            record_ticket_opened(conf, uid, self.panel_name, cid)

            new_id = await update_active_overview(guild, conf)
            if new_id:
                conf.overview_msg = new_id

            await self.view.cog.save()
        except Exception as e:
            log.error(f"Failed to save ticket config for {user.name}, cleaning up channel", exc_info=e)
            # Clean up the Discord resources since we failed to save
            with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                if isinstance(channel_or_thread, discord.Thread):
                    await channel_or_thread.delete()
                else:
                    await channel_or_thread.delete(reason="Failed to save ticket configuration")
            # Clean up log message if it exists
            if log_message:
                with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                    await log_message.delete()
            # Notify user
            error_msg = _("There was an error saving your ticket. The channel has been cleaned up. Please try again.")
            with contextlib.suppress(discord.HTTPException):
                await interaction.followup.send(error_msg, ephemeral=True)
            return


class PanelView(View):
    def __init__(
        self,
        bot: Red,
        guild: discord.Guild,
        cog: "MixinMeta",
        panels: list[tuple[str, Panel]],
        mock_user: discord.Member | None = None,
        timeout: int | None = None,
    ):
        super().__init__(timeout=timeout)
        self.bot: Red = bot
        self.guild: discord.Guild = guild
        self.cog: "MixinMeta" = cog
        self.panels: list[tuple[str, Panel]] = panels
        for panel_name, panel in self.panels:
            self.add_item(SupportButton(panel_name, panel, mock_user=mock_user))

    async def start(self):
        chan = self.guild.get_channel(self.panels[0][1].channel_id)
        if not isinstance(chan, discord.TextChannel):
            return
        message = await chan.fetch_message(self.panels[0][1].message_id)
        await message.edit(view=self)


class LogView(View):
    def __init__(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel | discord.Thread,
        max_claims: int,
        cog: "MixinMeta",
    ):
        super().__init__(timeout=None)
        self.guild: discord.Guild = guild
        self.channel: discord.TextChannel | discord.Thread = channel
        self.max_claims: int = max_claims
        self.cog: "MixinMeta" = cog

        self.added: set[int] = set()
        self.join_ticket.custom_id = str(channel.id)

    @discord.ui.button(label="Join Ticket", style=ButtonStyle.green)
    async def join_ticket(self, interaction: Interaction, button: Button):
        user = interaction.guild.get_member(interaction.user.id)
        if not user:
            return
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
            if not all(perms):
                await self.channel.set_permissions(user, read_messages=True, send_messages=True)
            await self.channel.send(_("{} was added to the ticket").format(str(user)))
        else:
            await self.channel.add_user(user)
        self.added.add(user.id)

        # Track claim analytics
        conf = self.cog.db.get_conf(self.guild)
        panel_name = ""
        for _uid, tickets in conf.opened.items():
            if self.channel.id in tickets:
                panel_name = tickets[self.channel.id].panel
                break
        record_ticket_claimed(conf, user.id, self.channel.id, panel_name)
        await self.cog.save()

        await interaction.response.send_message(
            _("You have been added to the ticket **{}**").format(self.channel.name),
            ephemeral=True,
            delete_after=60,
        )
