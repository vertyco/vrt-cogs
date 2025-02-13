import typing as t

import discord
from redbot.core.bot import Red

# from ..abc import MixinMeta
from ..db.tables import AppealGuild, AppealQuestion, AppealSubmission


class AnswerModal(discord.ui.Modal):
    def __init__(self, question: AppealQuestion, question_number: int, answers: dict[str, str]) -> None:
        super().__init__(timeout=None, title=f"Question {question_number}")
        self.question = question
        self.question_number = question_number
        self.answers = answers
        self.input = discord.ui.TextInput(
            label=(question.question if len(question.question) <= 45 else f"{question.question[:42]}..."),
            required=question.required,
            default=question.default or answers.get(question.question),
            placeholder=question.placeholder,
            min_length=question.min_length,
            max_length=question.max_length,
            style=discord.TextStyle.paragraph if question.style == "long" else discord.TextStyle.short,
        )
        self.add_item(self.input)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        return await super().on_error(interaction, error)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.input.value:
            self.answers[self.question.question] = self.input.value
        else:
            self.answers.pop(self.question.question, None)
        self.stop()


class MenuButton(discord.ui.Button):
    def __init__(
        self,
        question: AppealQuestion,
        question_number: int,
        answers: dict[str, str],
        response_func: t.Callable,
        emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
        label: str | None = None,
        disabled: bool = False,
        row: int | None = None,
    ):
        super().__init__(style=style, label=label, disabled=disabled, emoji=emoji, row=row)
        self.question = question
        self.question_number = question_number
        self.answers = answers
        self.func = response_func

    async def callback(self, interaction: discord.Interaction):
        modal = AnswerModal(self.question, self.question_number, self.answers)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.input.value:
            self.style = discord.ButtonStyle.secondary
        else:
            self.style = getattr(discord.ButtonStyle, self.question.button_style)
        await self.func(interaction, self)


class SubmissionView(discord.ui.View):
    def __init__(self, questions: list[AppealQuestion]) -> None:
        super().__init__(timeout=None)
        self.questions = questions
        self.answers: dict[str, str] = {}  # {question: answer}
        self.buttons: dict[str, MenuButton] = {}

        for i, question in enumerate(questions):
            button = MenuButton(
                question=question,
                question_number=i + 1,
                answers=self.answers,
                response_func=self.response,
                label=f"Question {i + 1}",
                style=getattr(discord.ButtonStyle, question.button_style),
            )
            self.add_item(button)
            self.buttons[question.question] = button

    async def on_timeout(self) -> None:
        await super().on_timeout()

    async def on_error(self, error: Exception, item: discord.ui.Item, interaction: discord.Interaction) -> None:
        await super().on_error(error, item, interaction)

    async def response(self, interaction: discord.Interaction, button: MenuButton):
        # Intearaction has already been responded to
        # bot: Red = interaction.client
        # cog: MixinMeta = bot.get_cog("Appeals")
        embed = await self.make_embed()
        self.toggle_submit_button()
        await interaction.edit_original_response(embed=embed, view=self)

    async def make_embed(self):
        color = discord.Color.green() if len(self.answers) == len(self.questions) else discord.Color.blue()
        embed = discord.Embed(title="Appeal Submission", color=color)
        if self.can_submit():
            embed.set_footer(text="Required questions have been answered. You may submit when ready.")
        else:
            embed.set_footer(text="Click the buttons that correspond to the questions to answer them.")
        for i, question in enumerate(self.questions):
            name = f"{i + 1}. {question.question}"
            value = self.answers.get(question.question)
            if not value:
                value = "Required" if question.required else "Optional"
            embed.add_field(name=name, value=value, inline=False)
        return embed

    def can_submit(self) -> bool:
        required_questions = [q.question for q in self.questions if q.required]
        required_answers = [q for q in self.answers if q in required_questions]
        return len(required_questions) == len(required_answers)

    def toggle_submit_button(self):
        self.submit_appeal.disabled = not self.can_submit()

    async def send(
        self,
        interaction: discord.Interaction,
        content: str = None,
        embed: discord.Embed = None,
        ephemeral: bool = False,
    ):
        try:
            await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
        except discord.HTTPException:
            await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.success, disabled=True, row=4)
    async def submit_appeal(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot: Red = interaction.client
        # cog: MixinMeta = bot.get_cog("Appeals")
        if not self.can_submit():
            # This shouldn't happen since the button will be disabled until all required questions are answered
            return await self.send(
                interaction,
                "You must answer all required questions before submitting.",
                ephemeral=True,
            )

        appealguild: AppealGuild = (
            await AppealGuild.select(
                AppealGuild.pending_channel,
                AppealGuild.alert_roles,
                AppealGuild.alert_channel,
            )
            .where(AppealGuild.id == interaction.guild.id)
            .first()
        )
        if not appealguild:
            return await self.send(interaction, "Appeal system is no longer setup for this server.")

        pending_channel = interaction.guild.get_channel(appealguild["pending_channel"])
        if not pending_channel:
            return await self.send(
                interaction,
                "Appeal system is no longer setup for this server as the pending channel is missing.",
            )

        perms = [
            pending_channel.permissions_for(interaction.guild.me).view_channel,
            pending_channel.permissions_for(interaction.guild.me).send_messages,
            pending_channel.permissions_for(interaction.guild.me).embed_links,
        ]
        if not all(perms):
            return await self.send(
                interaction,
                "I don't have the required permissions to send messages in the pending channel.",
            )

        try:
            await interaction.response.edit_message(content="Submission complete!", embed=None, view=None)
        except discord.HTTPException:
            await interaction.edit_original_response(content="Submission complete!", embed=None, view=None)

        final_answers = {}
        for question in self.questions:
            answer = self.answers.get(question.question, "*Not answered*")
            final_answers[question.question] = answer
        submission = AppealSubmission(
            guild=interaction.guild.id,
            user_id=interaction.user.id,
            answers=final_answers,
        )
        await submission.save()

        embed = submission.embed(interaction.user)

        allowed_mentions = discord.AllowedMentions(users=True, roles=True)
        mentions = None
        if alert_roles := appealguild["alert_roles"]:
            mentions = ", ".join([f"<@&{r}>" for r in alert_roles])

        message = await pending_channel.send(content=mentions, embed=embed, allowed_mentions=allowed_mentions)

        # If alert channel exists and bot has permissions to send messages in it, ping there instead
        # otherwise ping the pending channel
        alert_channel = bot.get_channel(appealguild["alert_channel"])
        if alert_channel:
            perms = [
                alert_channel.permissions_for(alert_channel.guild.me).view_channel,
                alert_channel.permissions_for(alert_channel.guild.me).send_messages,
                alert_channel.permissions_for(alert_channel.guild.me).embed_links,
            ]
            if all(perms):
                desc = f"New appeal submission from **{interaction.user.name}** (`{interaction.user.id}`)"
                desc += f"\n[View Appeal]({message.jump_url})"
                embed = discord.Embed(description=desc, color=discord.Color.yellow())
                embed.set_thumbnail(url=interaction.user.display_avatar)
                await alert_channel.send(embed=embed, allowed_mentions=allowed_mentions)

        await AppealSubmission.update({AppealSubmission.message_id: message.id}).where(
            AppealSubmission.id == submission.id
        )
