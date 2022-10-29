import asyncio
import logging
import traceback
from datetime import datetime
from typing import Union

import discord
from redbot.core import commands, Config
from redbot.core.i18n import Translator

_ = Translator("SupportViews", __file__)
log = logging.getLogger("red.vrt.supportview")


async def wait_reply(ctx: commands.Context, timeout: int = 60):
    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        reply = await ctx.bot.wait_for("message", timeout=timeout, check=check)
        res = reply.content
        try:
            await reply.delete()
        except (discord.Forbidden, discord.NotFound, discord.DiscordServerError):
            pass
        return res
    except asyncio.TimeoutError:
        return None


def get_color(color: str):
    if color == "red":
        style = discord.ButtonStyle.red
    elif color == "blue":
        style = discord.ButtonStyle.blurple
    elif color == "green":
        style = discord.ButtonStyle.green
    else:
        style = discord.ButtonStyle.grey
    return style


async def interaction_check(ctx, interaction):
    if interaction.user.id != ctx.author.id:
        await interaction.response.send_message(
            content=_("You are not allowed to interact with this button."),
            ephemeral=True
        )
        return False
    return True


class Confirm(discord.ui.View):
    def __init__(self, ctx):
        self.ctx = ctx
        self.value = None
        super().__init__(timeout=60)

    @discord.ui.button(label='Yes', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await interaction_check(self.ctx, interaction):
            return
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label='No', style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await interaction_check(self.ctx, interaction):
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


class TestButton(discord.ui.View):
    def __init__(
            self,
            style: str = "grey",
            label: str = "Button Test",
            emoji: Union[discord.Emoji, discord.PartialEmoji, str] = None
    ):
        super().__init__()
        style = get_color(style)
        butt = discord.ui.Button(
            label=label,
            style=style,
            emoji=emoji
        )
        self.add_item(butt)


class SupportButton(discord.ui.Button):
    def __init__(
            self,
            panel_name: str,
            panel: dict
    ):
        super().__init__(
            style=get_color(panel["button_color"]),
            label=panel["button_text"],
            custom_id=panel_name,
            emoji=panel["button_emoji"]
        )
        self.panel_name = panel_name

    async def callback(self, interaction: discord.Interaction):
        try:
            await self.create_ticket(interaction)
        except Exception as e:
            log.error(f"Failed to create ticket in {interaction.guild.name}: {e}\n"
                      f"TRACEBACK\n"
                      f"{traceback.format_exc()}")

    async def create_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        user = interaction.user
        conf = await self.view.config.guild(guild).all()
        panel = conf["panels"][self.panel_name]
        max_tickets = conf["max_tickets"]
        opened = conf["opened"]
        user_can_close = conf["user_can_close"]
        logchannel = guild.get_channel(panel["log_channel"]) if panel["log_channel"] else None
        uid = str(user.id)
        if uid in opened and max_tickets <= len(opened[uid]):
            em = discord.Embed(description=_("You have the maximum amount of tickets opened already!"),
                               color=user.color)
            return await interaction.response.send_message(embed=em, ephemeral=True)
        category = guild.get_channel(panel["category_id"]) if panel["category_id"] else None
        if not category:
            em = discord.Embed(description=_("The category for this support panel cannot be found!\n"
                                             "please contact an admin!"), color=discord.Color.red())
            return await interaction.response.send_message(embed=em, ephemeral=True)
        can_read_send = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
        read_and_manage = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        support = [
            guild.get_role(role_id) for role_id in conf["support_roles"] if guild.get_role(role_id)
        ]
        overwrite = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: read_and_manage,
            user: can_read_send
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
            "time": now.strftime("%I-%M-%p")
        }
        channel_name = name_fmt.format(**params) if name_fmt else user.name
        channel = await category.create_text_channel(channel_name, overwrites=overwrite)

        default_message = _("Welcome to your ticket channel ") + f"{user.display_name}!"
        if user_can_close:
            default_message += _("\nYou or an admin can close this with the `close` command")

        messages = conf["panels"][self.panel_name]["ticket_messages"]
        params = {
            "username": user.name,
            "displayname": user.display_name,
            "mention": user.mention,
            "id": str(user.id)
        }
        if messages:
            embeds = []
            for einfo in messages:
                em = discord.Embed(
                    title=einfo["title"].format(**params) if einfo["title"] else None,
                    description=einfo["desc"].format(**params),
                    color=user.color
                )
                if einfo["footer"]:
                    em.set_footer(text=einfo["footer"].format(**params))
                embeds.append(em)
            msg = await channel.send(user.mention, embeds=embeds)
        else:
            em = discord.Embed(
                description=default_message,
                color=user.color
            )
            if user.avatar:
                em.set_thumbnail(url=user.avatar.url)
            msg = await channel.send(user.mention, embed=em)

        desc = _("Your ticket channel has been created, **[CLICK HERE]") + f"({msg.jump_url})**"
        em = discord.Embed(description=desc,
                           color=user.color)
        await interaction.response.send_message(embed=em, ephemeral=True)

        if logchannel:
            ts = int(now.timestamp())
            desc = _("Ticket created by ") + f"**{user.name}-{user.id}**" + _(" was opened ") + f"<t:{ts}:R>\n"
            desc += _("To view this ticket, **[Click Here]") + f"({msg.jump_url})**"
            em = discord.Embed(
                title=_("Ticket opened"),
                description=desc,
                color=discord.Color.red()
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
                "logmsg": log_message.id if log_message else None
            }


class SupportView(discord.ui.View):
    def __init__(
            self,
            guild: discord.Guild,
            config: Config,
            panel_name: str,
            panel: dict,
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.config = config
        self.panel_name = panel_name
        self.panel = panel
        self.add_item(SupportButton(panel_name, panel))
        self.channel = panel["channel_id"]
        self.message = panel["message_id"]

    async def start(self):
        chan = self.guild.get_channel(self.channel)
        message = await chan.fetch_message(self.message)
        await message.edit(view=self)


async def start_button(
        guild: discord.Guild,
        config: Config,
        panel_name: str,
        panel: dict,
):
    b = SupportView(guild, config, panel_name, panel)
    await b.start()
