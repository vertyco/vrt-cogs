import asyncio
import contextlib
import logging
from datetime import datetime
from io import StringIO

import discord
import numpy as np
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.utils import (
    format_response_time,
    format_working_hours_embed,
    get_average_response_time,
    is_within_working_hours,
    update_active_overview,
)
from ..common.views import CloseView, LogView
from .analytics import record_ticket_opened
from .models import OpenedTicket

_ = Translator("SupportViews", __file__)
log = logging.getLogger("red.vrt.tickets.functions")


class Functions(MixinMeta):
    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema = {
            "name": "get_ticket_types",
            "description": (
                "Fetch support ticket types available for the user to open (Use this before opening a ticket). "
                "The user MUST answer the questions in detail before the ticket can be opened!"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        }
        await cog.register_function("Tickets", schema)

        schema = {
            "name": "create_ticket_for_user",
            "description": (
                "Create a support ticket for the user you are speaking with if you are unable to help sufficiently. "
                "Use `get_ticket_types` function before this one to get the panel names and response section requirements. "
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "panel_name": {
                        "type": "string",
                        "description": "The name of the panel to use for opening a ticket.",
                    },
                    "answer1": {
                        "type": "string",
                        "description": "The answer to the first question if one exists.",
                    },
                    "answer2": {
                        "type": "string",
                        "description": "The answer to the second question if one exists.",
                    },
                    "answer3": {
                        "type": "string",
                        "description": "The answer to the third question if one exists.",
                    },
                    "answer4": {
                        "type": "string",
                        "description": "The answer to the fourth question if one exists.",
                    },
                    "answer5": {
                        "type": "string",
                        "description": "The answer to the fifth question if one exists.",
                    },
                },
                "required": ["panel_name"],
            },
        }
        await cog.register_function("Tickets", schema)

    async def get_ticket_types(self, user: discord.Member, *args, **kwargs) -> str:
        """Fetch available ticket types that the user can open.
        Returns the available tickets as well as their section requriements and panel names.

        Args:
            user (discord.Member): User that the ticket would be for.
        """
        guild = user.guild
        conf = self.db.get_conf(guild)
        if conf.suspended_msg:
            return f"Tickets are suspended: {conf.suspended_msg}"
        if user.id in conf.blacklist:
            return "This user has been blacklisted from opening tickets!"
        if any(r.id in conf.blacklist for r in user.roles):
            return "This user has a role that is blacklisted from opening tickets!"

        opened = conf.opened
        uid = user.id
        if uid in opened and conf.max_tickets <= len(opened[uid]):
            channels = "\n".join([f"<#{i}>" for i in opened[uid]])
            txt = f"This user has the maximum amount of tickets opened already!\nTickets: {channels}"
            return txt

        panels = conf.panels
        if not panels:
            return "There are no support ticket panels available!"

        buffer = StringIO()
        q = "Pre-ticket questions (USER MUST ANSWER THESE IN DETAIL BEFORE TICKET CAN BE OPENED!)\n"
        for panel_name, panel in panels.items():
            # Check if the panel is disabled
            if panel.disabled:
                continue

            # Check if the channel exists
            channel = guild.get_channel(panel.channel_id)
            if channel is None:
                continue

            # Check if the member has the required roles to open a ticket from this panel
            if panel.required_roles and not any(role.id in panel.required_roles for role in user.roles):
                continue

            buffer.write(f"# Support ticket panel name: {panel_name}\n")
            if btext := panel.button_text:
                buffer.write(f"- Tag: {btext}\n")

            if panel.modal:
                if questions := list(panel.modal.values()):
                    buffer.write(q)
                    for idx, field in enumerate(questions):
                        required = "(Required)" if field.required else "(Optional)"
                        buffer.write(f"- Question {idx + 1} {required}: {field.label}\n")
                        if placeholder := field.placeholder:
                            buffer.write(f" - Example: {placeholder}\n")

            buffer.write("\n")

        final = buffer.getvalue()
        if not final:
            return "There are no tickets available to be opened by this user!"

        return final

    async def create_ticket_for_user(
        self,
        user: discord.Member,
        panel_name: str,
        answer1: str = None,
        answer2: str = None,
        answer3: str = None,
        answer4: str = None,
        answer5: str = None,
        *args,
        **kwargs,
    ) -> str:
        """Create a ticket for the given member.

        Args:
            user (discord.Member): User to open a ticket for.
            panel_name (str): Name of the panel to create a ticket for.
            answer1 (str, optional): The answer to the first ticket question. Defaults to None.
            answer2 (str, optional): The answer to the second ticket question. Defaults to None.
            answer3 (str, optional): The answer to the third ticket question. Defaults to None.
            answer4 (str, optional): The answer to the fourth ticket question. Defaults to None.
            answer5 (str, optional): The answer to the fifth ticket question. Defaults to None.
        """

        guild = user.guild
        conf = self.db.get_conf(guild)
        if conf.suspended_msg:
            return f"Tickets are suspended: {conf.suspended_msg}"

        panels = conf.panels

        # Validate the panel_name
        if panel_name not in panels or panels[panel_name].disabled:
            panel_names = ", ".join(list(panels.keys()))
            txt = "The specified ticket panel does not exist!\n"
            txt += "Use the `get_ticket_types` function to get ticket panel details!\n"
            txt += f"Available ticket panel names are {panel_names}"
            return txt

        if panels[panel_name].disabled:
            return "That ticket panel is disabled!"

        panel = panels[panel_name]

        # Check working hours
        within_hours, start_time, end_time = is_within_working_hours(panel)
        if not within_hours and panel.block_outside_hours:
            msg = "Tickets cannot be opened outside of working hours."
            if start_time and end_time:
                msg += f" Working hours today are <t:{start_time}:t> to <t:{end_time}:t>."
            return msg

        logchannel = guild.get_channel(panel.log_channel)
        category = guild.get_channel(panel.category_id)
        channel = guild.get_channel(panel.channel_id)
        if alt_cid := panel.alt_channel:
            alt_channel = guild.get_channel(alt_cid)
            if isinstance(alt_channel, discord.TextChannel):
                channel = alt_channel.category

        if not panel.threads and not category:
            return "The category for this panel is missing!"
        if not channel:
            return "The channel required for this ticket panel is missing!"

        # Check if the member has already reached the maximum number of open tickets allowed
        max_tickets = conf.max_tickets
        opened = conf.opened
        uid = user.id
        if uid in opened and max_tickets <= len(opened[uid]):
            return "This user has reached the maximum number of open tickets allowed!"

        # Verify that the member has the required roles to open a ticket from the specified panel
        if panel.required_roles and not any(role.id in panel.required_roles for role in user.roles):
            return "This user does not have the required roles to open this ticket."

        # Prepare the modal responses
        responses = [
            answer1,
            answer2,
            answer3,
            answer4,
            answer5,
        ]
        answers = {}
        if panel.modal:
            for idx, field in enumerate(list(panel.modal.values())):
                if field.required and not responses[idx]:
                    return f"THE FOLLOWING TICKET QUESTION WAS NOT ANSWERED!\n{field.label}"
                response = str(responses[idx])
                if "DISCOVERABLE" in guild.features:
                    response = response.replace("Discord", "").replace("discord", "")

                answers[field.label] = response

        form_embed = discord.Embed()
        if answers:
            title = "Submission Info"
            form_embed = discord.Embed(color=user.color)
            if user.avatar:
                form_embed.set_author(name=title, icon_url=user.display_avatar.url)
            else:
                form_embed.set_author(name=title)

            for question, answer in answers.items():
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
        default_channel_name = f"{panel_name}-{num}"
        try:
            if panel.threads:
                if alt_cid := panel.alt_channel:
                    alt_channel = guild.get_channel(alt_cid)
                    if alt_channel and isinstance(alt_channel, discord.TextChannel):
                        channel = alt_channel
                archive = round(conf.inactive * 60)
                arr = np.asarray([60, 1440, 4320, 10080])
                index = (np.abs(arr - archive)).argmin()
                auto_archive_duration = int(arr[index])

                reason = _("{} ticket for {}").format(panel_name, str(user))
                try:
                    channel_or_thread: discord.Thread = await channel.create_thread(
                        name=channel_name,
                        auto_archive_duration=auto_archive_duration,
                        reason=reason,
                        invitable=conf.user_can_manage,
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
                asyncio.create_task(channel_or_thread.add_user(user))
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
                try:
                    channel_or_thread: discord.TextChannel = await category.create_text_channel(
                        channel_name, overwrites=overwrite
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
            return "Missing requried permissions to create the ticket!"

        except Exception as e:
            log.error("Error creating ticket channel", exc_info=e)
            return f"ERROR: {e}"

        prefix = (await self.bot.get_valid_prefixes(guild))[0]
        default_message = _("Welcome to your ticket channel ") + f"{user.display_name}!"
        user_can_close = conf.user_can_close
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
            self.bot,
            self,
            user.id,
            channel_or_thread,
        )
        if messages:
            embeds = []
            for index, msg in enumerate(messages):
                # Use custom color if set and valid, otherwise default to user's color
                embed_color = discord.Color(msg.color) if msg.color is not None else user.color
                em = discord.Embed(
                    title=fmt_params(msg.title) if msg.title else None,
                    description=fmt_params(msg.desc),
                    color=embed_color,
                )
                if index == 0:
                    em.set_thumbnail(url=user.display_avatar.url)
                if msg.footer:
                    em.set_footer(text=fmt_params(msg.footer))
                # Set image if configured
                if msg.image:
                    em.set_image(url=msg.image)
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

        # Send outside working hours notice if applicable
        if not within_hours and panel.working_hours:
            hours_embed = format_working_hours_embed(panel, user)
            if hours_embed:
                await channel_or_thread.send(embed=hours_embed)

        # Send average response time notice if we have data and it's enabled
        if conf.show_response_time:
            avg_response = get_average_response_time(conf.response_times)
            if avg_response is not None:
                formatted_time = format_response_time(avg_response)
                response_embed = discord.Embed(
                    description=_("⏱️ Our average staff response time is **{}**.").format(formatted_time),
                    color=discord.Color.blue(),
                )
                await channel_or_thread.send(embed=response_embed)

        if logchannel:
            ts = int(now.timestamp())
            kwargs = {
                "user": str(user),
                "userid": user.id,
                "timestamp": f"<t:{ts}:R>",
                "channelname": channel_name,
                "panelname": panel_name,
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

            view = LogView(guild, channel_or_thread, panel.max_claims, cog=self)
            log_message = await logchannel.send(embed=em, view=view)
        else:
            log_message = None

        # Update the config and save - if this fails, clean up the ticket channel
        try:
            panel.ticket_num += 1
            uid = user.id
            cid = channel_or_thread.id
            if uid not in conf.opened:
                conf.opened[uid] = {}
            conf.opened[uid][cid] = OpenedTicket(
                panel=panel_name,
                opened=now,
                pfp=str(user.display_avatar.url) if user.avatar else None,
                logmsg=log_message.id if log_message else None,
                answers=answers,
                has_response=True if answers else False,
                message_id=msg.id,
                max_claims=panel.max_claims,
                first_response=None,
            )

            # Record analytics for ticket opened
            record_ticket_opened(conf, uid, panel_name, cid)

            new_id = await update_active_overview(guild, conf)
            if new_id:
                conf.overview_msg = new_id

            await self.save()
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
            # Return error message
            return _("There was an error saving your ticket. The channel has been cleaned up. Please try again.")

        txt = f"Ticket has been created!\nChannel mention: {channel_or_thread.mention}"

        return txt
