@commands.command(name="plot", hidden=True)
async def plotly_graph(self, ctx: commands.Context):
    settings = await self.config.guild(ctx.guild).all()
    x = []
    y = []
    times = settings["serverstats"]["dates"]
    counts = settings["serverstats"]["counts"]
    for i in range(len(times) - 1):
        timestamp = datetime.datetime.fromisoformat(times[i])
        x.append(timestamp)
        y.append(counts[i])
    x.reverse()
    y.reverse()
    df = pd.DataFrame(
        {
            "time": x,
            "players": y
        }
    )
    fig = px.line(df, x='time', y='players')
    fig.write_image("plot.png")
    with open("plot.png", "rb") as file:
        file = discord.File(file, "plot.png")
        await ctx.send(file=file)