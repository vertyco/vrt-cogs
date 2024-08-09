import logging
from contextlib import suppress

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.bot import Red

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.vrtutils")

checks = ["✅", "\N{WHITE HEAVY CHECK MARK}"]
cross = ["❌", "\N{CROSS MARK}"]


class EditModal(discord.ui.Modal):
    included_embed_fields = [
        "title",
        "description",
        "author name",
        "author icon url",
        "footer text",
        "footer icon url",
        "thumbnail",
        "image",
    ]

    def __init__(self, message: discord.Message):
        super().__init__(title="Edit Message", timeout=900)
        self.message = message

        self.changed = False
        self.timed_out = False

        self.content: str | None = message.content.strip() if message.content else None
        self.content_field = discord.ui.TextInput(
            label="Message Content",
            style=discord.TextStyle.paragraph,
            placeholder="Enter the new message content here.",
            default=self.content,
            required=False,
        )
        if self.content:
            log.info(f"Creating field for message content: {self.content}")
            self.add_item(self.content_field)

        # For other parts of the message
        self.inputs: dict[str, str] | None = None
        self.content_fields: dict[str, discord.ui.TextInput] = {}
        self.extras = 0
        if self.content:
            self.extras += 1
        if len(message.embeds) == 1:
            embed = message.embeds[0]
            for val in self.included_embed_fields:
                match val:
                    case "title":
                        current = embed.title
                        max_length = 256
                        style = discord.TextStyle.short
                    case "description":
                        current = embed.description
                        max_length = None
                        style = discord.TextStyle.paragraph
                        if current and len(current) > 4000:
                            # We can't edit embed descriptions over 4000 characters
                            continue
                    case "author name":
                        current = embed.author.name
                        max_length = 256
                        style = discord.TextStyle.short
                    case "author icon url":
                        current = embed.author.icon_url
                        max_length = None
                        style = discord.TextStyle.paragraph
                    case "footer text":
                        current = embed.footer.text
                        max_length = 2048
                        style = discord.TextStyle.paragraph
                    case "footer icon url":
                        current = embed.footer.icon_url
                        max_length = None
                        style = discord.TextStyle.paragraph
                    case "thumbnail":
                        current = embed.thumbnail.url
                        max_length = None
                        style = discord.TextStyle.paragraph
                    case "image":
                        current = embed.image.url
                        max_length = None
                        style = discord.TextStyle.paragraph
                    case _:
                        raise ValueError(f"Invalid embed field: {val}")

                current = current.strip() if current else None
                if not current:
                    continue
                field = discord.ui.TextInput(
                    label=val,
                    style=style,
                    placeholder=f"Enter the new {val} here.",
                    default=str(current) if current else None,
                    required=False,
                    max_length=max_length,
                )
                if self.extras < 5:
                    log.info(f"Creating field for {val}: {current}")
                    self.add_item(field)
                    self.content_fields[val] = field
                    self.extras += 1

    def embeds(self) -> list[discord.Embed]:
        if len(self.message.embeds) == 1:
            embed = self.message.embeds[0]
            for attr in self.included_embed_fields:
                if attr not in self.content_fields:
                    continue
                new_value = self.content_fields[attr].value
                if attr in self.content_fields:
                    if attr == "title" and new_value != embed.title:
                        embed.title = new_value
                        self.changed = True
                    elif attr == "description" and new_value != embed.description:
                        embed.description = new_value
                        self.changed = True
                    elif attr == "author icon url" and new_value != embed.author.icon_url:
                        embed.set_author(name=embed.author.name, icon_url=new_value)
                        self.changed = True
                    elif attr == "author name" and new_value != embed.author.name:
                        embed.set_author(name=new_value, icon_url=embed.author.icon_url)
                        self.changed = True
                    elif attr == "footer text" and new_value != embed.footer.text:
                        embed.set_footer(text=new_value, icon_url=embed.footer.icon_url)
                        self.changed = True
                    elif attr == "footer icon url" and new_value != embed.footer.icon_url:
                        embed.set_footer(text=embed.footer.text, icon_url=new_value)
                        self.changed = True
                    elif attr == "thumbnail" and new_value != embed.thumbnail.url:
                        embed.set_thumbnail(url=new_value)
                        self.changed = True
                    elif attr == "image" and new_value != embed.image.url:
                        embed.set_image(url=new_value)
                        self.changed = True
            return [embed]
        return self.message.embeds

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.content_field.value != self.content:
            self.content = self.content_field.value
            self.changed = True
        self.stop()

    async def on_timeout(self) -> None:
        self.timed_out = True
        self.stop()
        return await super().on_timeout()


@app_commands.context_menu(name="Edit Message")
async def mock_edit_message(interaction: discord.Interaction, message: discord.Message):
    member = message.guild.get_member(interaction.user.id)
    if not member:
        return await interaction.response.send_message("You must be in the server to use this command.", ephemeral=True)
    bot: Red = interaction.client
    bots_own_message = message.author.id == bot.user.id
    if not bots_own_message and not message.webhook_id:
        # User is human, we'll need to check permissions
        if not message.channel.permissions_for(message.guild.me).manage_messages:
            return await interaction.response.send_message(
                "I require manage messages permission to 'edit' messages of other users.", ephemeral=True
            )
        if not message.channel.permissions_for(member).manage_messages:
            return await interaction.response.send_message(
                "You require the manage messages permission to use this command.", ephemeral=True
            )
        if not message.channel.permissions_for(message.guild.me).manage_webhooks:
            return await interaction.response.send_message(
                "I require manage webhooks permission to edit messages.", ephemeral=True
            )
        # If user is trying to edit the message of a user who outranks them, deny
        if (
            member.top_role <= message.author.top_role
            and not message.channel.permissions_for(interaction.guild.me).administrator
        ):
            return await interaction.response.send_message(
                "You cannot edit the messages of users with equal or higher roles than you.", ephemeral=True
            )
    else:
        if not await bot.is_admin(member) and interaction.user.id not in bot.owner_ids:
            return await interaction.response.send_message("You must be an admin to edit my messages!", ephemeral=True)

    # Throw a modal to edit the message
    modal = EditModal(message=message)
    try:
        await interaction.response.send_modal(modal)
    except discord.NotFound:
        return
    except discord.HTTPException as e:
        txt = ""
        for k, v in modal.content_fields.items():
            txt += f"{k}: {v.default}\n"
        log.error(f"Failed to send modal for message {message.id}\n{txt}", exc_info=e)
        with suppress(discord.HTTPException):
            await interaction.response.send_message("Failed to send modal.", ephemeral=True)
        return

    await modal.wait()
    embeds = modal.embeds()

    if modal.timed_out:
        return

    if not modal.changed:
        return await interaction.followup.send("No changes detected.", ephemeral=True)

    if bots_own_message:
        await message.edit(content=modal.content, embeds=embeds)
    elif message.webhook_id:
        webhook = await bot.fetch_webhook(message.webhook_id)
        await webhook.edit_message(message.id, content=modal.content, embeds=embeds)
    else:
        # User is human or another bot, we'll need to mock with a webhook
        if not modal.content and not message.author.bot:
            return await interaction.followup.send("User messages must have content.", ephemeral=True)
        webhooks = await message.channel.webhooks()
        if not webhooks:
            webhook = await message.channel.create_webhook(name="Edit Message", reason="VrtUtils Edit Message")
        else:
            webhook = webhooks[0]

        await webhook.send(
            content=modal.content,
            embeds=embeds,
            username=message.author.display_name,
            avatar_url=message.author.display_avatar.url,
            files=[await a.to_file() for a in message.attachments],
        )
        await message.delete(delay=1)

    with suppress(discord.HTTPException):
        await interaction.followup.send("Message edited.", ephemeral=True)
    log.info(f"{interaction.user} edited message {message.id} in {message.guild}.")


class ToDo(MixinMeta):
    @commands.command(aliases=["refreshtodo"])
    @commands.mod_or_permissions(manage_messages=True)
    async def todorefresh(self, ctx: commands.Context, confirm: bool):
        """
        Refresh a todo list channel.

        Bring all messages without a ✅ or ❌ to the front of the channel.

        **WARNING**: DO NOT USE THIS COMMAND IN A BUSY CHANNEL.
        """
        if not confirm:
            return await ctx.send("Not refreshing.")
        if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
            return await ctx.send("I require manage messages permission to refresh the todo list.")
        if not ctx.channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send("I require read message history permission to refresh the todo list.")
        if not ctx.channel.permissions_for(ctx.guild.me).add_reactions:
            return await ctx.send("I require add reactions permission to refresh the todo list.")
        if not ctx.channel.permissions_for(ctx.guild.me).attach_files:
            return await ctx.send("I require attach files permission to refresh the todo list.")
        if not ctx.channel.permissions_for(ctx.guild.me).manage_webhooks:
            return await ctx.send("I require manage webhooks permission to refresh the todo list.")

        # Get a webhook to use for moving messages
        webhooks = await ctx.channel.webhooks()
        if not webhooks:
            webhook = await ctx.channel.create_webhook(name="ToDo Refresh", reason="VrtUtils ToDo Refresh")
        else:
            webhook = webhooks[0]

        def _has_reaction(message: discord.Message):
            return any(
                [
                    any([str(r.emoji) in checks for r in message.reactions]),
                    any([str(r.emoji) in cross for r in message.reactions]),
                ]
            )

        # We want to bring old incomplete tasks to the front of the channel
        # Skip the first 5 messages since they can likely already be seen
        async with ctx.typing():
            skipped = 0
            first_checked = False
            async for message in ctx.channel.history(limit=None, oldest_first=False):
                if skipped < 5:
                    skipped += 1
                    continue
                if message.author.bot:
                    # Only continue if it is NOT a webhook message
                    if not message.webhook_id:
                        print(f"Bot message: {message.content}")
                        continue
                # We only want to move incomplete tasks
                if _has_reaction(message):
                    first_checked = True
                    continue
                if not first_checked:
                    continue
                # We want to move this message to the front
                await webhook.send(
                    content=message.content,
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    files=[await a.to_file() for a in message.attachments],
                )
                # Now we can delete the original message
                await message.delete(delay=10)

        with suppress(discord.HTTPException):
            await ctx.send("ToDo list refreshed.", delete_after=10)
            await ctx.message.delete()
