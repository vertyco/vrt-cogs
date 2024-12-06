import typing as t

import discord
import orjson
from piccolo.columns import (
    JSON,
    Array,
    BigInt,
    Boolean,
    ForeignKey,
    Integer,
    Serial,
    Text,
    Timestamptz,
)
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.table import Table, sort_table_classes
from redbot.core.bot import Red


class AppealGuild(Table):
    id = BigInt(primary_key=True, index=True)  # Guild ID
    created_at = Timestamptz()
    # Settings
    target_guild_id = BigInt()  # Target guild to be unbanned from
    appeal_channel = BigInt()  # Channel where the appeal message is located
    appeal_message = BigInt()  # Message ID of the appeal message with appeal button
    pending_channel = BigInt()  # Channel where pending appeals are stored
    approved_channel = BigInt()  # Channel where approved appeals are stored
    denied_channel = BigInt()  # Channel where denied appeals are stored
    alert_roles = Array(BigInt())  # Roles to alert when a new appeal is submitted
    alert_channel = BigInt()  # Channel to alert when a new appeal is submitted
    # Appeal button
    button_style = Text(default="primary")  # can be `primary`, `secondary`, `success`, `danger`
    button_label = Text(default="Submit Appeal")
    button_emoji = Text(default=None, null=True)  # int or string

    def get_emoji(self, bot: Red) -> str | discord.Emoji | discord.PartialEmoji | None:
        if not self.button_emoji:
            return None
        if self.button_emoji.isdigit():
            return bot.get_emoji(int(self.button_emoji))
        return self.button_emoji


class AppealQuestion(Table):
    id: Serial
    created_at = Timestamptz()
    updated_on = Timestamptz(auto_update=TimestamptzNow().python)
    guild = ForeignKey(references=AppealGuild, required=True)
    question = Text(required=True)  # Up to 256 characters
    # menu based setup only
    sort_order = Integer(default=0)
    # Modal specific (menu based setup only)
    required = Boolean(default=True)
    default = Text(default=None, null=True)
    placeholder = Text(default=None, null=True)
    max_length = BigInt(default=None, null=True)
    min_length = BigInt(default=None, null=True)  # Up to 1024 characters
    style = Text(default="long")  # can be `short` or `long`
    # Button specific (button based setup only)
    button_style = Text(default="primary")  # can be `primary`, `secondary`, `success`, `danger`

    def embed(self, color: discord.Color = None) -> discord.Embed:
        style_emojis = {
            "danger": "🔴",
            "success": "🟢",
            "primary": "🔵",
            "secondary": "⚫",
        }
        embed = discord.Embed(title=f"Question ID: {self.id}", description=self.question, color=color)
        embed.add_field(name="Sort Order", value=self.sort_order)
        embed.add_field(name="Required", value="Yes" if self.required else "No")
        embed.add_field(name="Modal Style", value=self.style)
        embed.add_field(name="Button Style", value=self.button_style + style_emojis[self.button_style])
        embed.add_field(name="Placeholder", value=self.placeholder or "Not set")
        embed.add_field(name="Default Answer", value=self.default or "Not set")
        embed.add_field(name="Max Length", value=self.max_length or "Not set")
        embed.add_field(name="Min Length", value=self.min_length or "Not set")
        return embed

    def created(self, type: t.Literal["t", "T", "d", "D", "f", "F", "R"]) -> str:
        return f"<t:{int(self.created_at.timestamp())}:{type}>"

    def modified(self, type: t.Literal["t", "T", "d", "D", "f", "F", "R"]) -> str:
        return f"<t:{int(self.updated_on.timestamp())}:{type}>"


class AppealSubmission(Table):
    id: Serial
    created_at = Timestamptz()
    guild = ForeignKey(references=AppealGuild)
    user_id = BigInt()  # Person who submitted the appeal
    answers = JSON()  # {question: answer}
    status = Text(default="pending")  # can be `pending`, `approved`, `denied`
    message_id = BigInt()  # Message ID of the submission message

    def created(self, type: t.Literal["t", "T", "d", "D", "f", "F", "R"]) -> str:
        return f"<t:{int(self.created_at.timestamp())}:{type}>"

    def embed(self, user: discord.Member | discord.User = None) -> discord.Embed:
        colors = {
            "pending": discord.Color.blurple(),
            "approved": discord.Color.green(),
            "denied": discord.Color.red(),
        }
        embed = discord.Embed(
            description=f"Submitted by <@{self.user_id}> ({self.user_id})",
            color=colors[self.status],
            timestamp=self.created_at,
        )
        embed.set_author(
            name=f"{self.status.capitalize()} Submission",
            icon_url=user.display_avatar if user else None,
        )
        embed.set_footer(text=f"Submission ID: {self.id}")
        answers = orjson.loads(self.answers) if isinstance(self.answers, str) else self.answers
        for question, answer in answers.items():
            embed.add_field(name=question, value=answer, inline=False)
        return embed


TABLES: list[Table] = sort_table_classes([AppealGuild, AppealQuestion, AppealSubmission])
