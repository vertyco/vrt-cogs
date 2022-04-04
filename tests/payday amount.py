@commands.command(name="ptest")
async def get_payday(self, ctx):
    b = self.bot.get_cog("Economy")
    if not b:
        return
    await ctx.send(str(await bank.is_global()))
    if await bank.is_global():
        conf = b.config
    else:
        conf = b.config.guild(ctx.guild)
    pdamount = await conf.PAYDAY_CREDITS()
    await ctx.send(pdamount)