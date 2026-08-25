from datetime import datetime, timezone

import discord


class AskCustomModal(discord.ui.Modal):
    """Free-text answer for the 'Other...' button on an operator question."""

    def __init__(self, view: "AskOperatorView"):
        super().__init__(title="Your answer")
        self.view = view
        self.answer = discord.ui.TextInput(
            label="Your answer",
            style=discord.TextStyle.paragraph,
            required=True,
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        await self.view.record_answer(interaction, self.answer.value, custom=True)


class AskOperatorView(discord.ui.View):
    """One button per offered option plus a grey 'Other...' free-text button.

    Writes the result straight into the cog's pending_asks record so the RPC
    poller (rpc_get_ask_answer) can read it without holding the view.
    """

    def __init__(
        self,
        pending_asks: dict,
        ask_id: str,
        options: list,
        target_user_id: int = None,
        timeout_seconds: int = 3600,
    ):
        super().__init__(timeout=timeout_seconds)
        self.pending_asks = pending_asks
        self.ask_id = ask_id
        self.target_user_id = int(target_user_id) if target_user_id else None
        self.message: discord.Message = None
        for idx, option in enumerate(options, start=1):
            button = discord.ui.Button(label=str(idx), style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(str(option))
            self.add_item(button)
        other = discord.ui.Button(label="Other...", style=discord.ButtonStyle.grey)
        other.callback = self._other_callback
        self.add_item(other)

    def _make_callback(self, option: str):
        async def callback(interaction: discord.Interaction):
            if not self._allowed(interaction):
                return await interaction.response.send_message("This question is not for you.", ephemeral=True)
            await self.record_answer(interaction, option, custom=False)

        return callback

    async def _other_callback(self, interaction: discord.Interaction):
        if not self._allowed(interaction):
            return await interaction.response.send_message("This question is not for you.", ephemeral=True)
        await interaction.response.send_modal(AskCustomModal(self))

    def _allowed(self, interaction: discord.Interaction) -> bool:
        return self.target_user_id is None or interaction.user.id == self.target_user_id

    async def record_answer(self, interaction: discord.Interaction, answer: str, custom: bool):
        record = self.pending_asks.get(self.ask_id)
        if record is not None:
            record.update(
                answered=True,
                answer=answer,
                custom=custom,
                by_user_id=interaction.user.id,
                ts=datetime.now(timezone.utc).isoformat(),
            )
        for item in self.children:
            item.disabled = True
        embed = None
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            embed.add_field(name="Answer", value=f"{answer}\n- {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def on_timeout(self) -> None:
        record = self.pending_asks.get(self.ask_id)
        if record is not None and not record.get("answered"):
            record["timed_out"] = True
        for item in self.children:
            item.disabled = True
        if self.message:
            embed = self.message.embeds[0] if self.message.embeds else None
            if embed:
                embed.add_field(name="Answer", value="Timed out, no answer given.", inline=False)
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass
