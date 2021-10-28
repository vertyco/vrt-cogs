import math
import random
import discord


TIPS = [
    "Tip: The shopstats command shows how many items have been purchased!",
    "Tip: The shoplb command shows the shop leaderboard for the server!",
    "Tip: The rshoplist command shows an overview of all RCON shop categories and items!",
    "Tip: The dshoplist command shows an overview of all DATA shop categories and items!",
    "Tip: The playershopstats command shows shop stats for a particular member, or yourself!",
    "Tip: You can use the playerstats command to view playtime stats for a specific player, or yourself!",
    "Tip: You can use the clusterstats command to view the top player on each cluster!",
    "Tip: You can use the arklb command to view a global playtime leaderboard for all maps!",
    "Tip: You can use the servergraph command to view player count over time!",
]


async def shop_stats(logs: dict):
    shop_logs = {}
    for item in logs["items"]:
        count = logs["items"][item]["count"]
        shop_logs[item] = count
    sorted_items = sorted(shop_logs.items(), key=lambda x: x[1], reverse=True)
    pages = math.ceil(len(sorted_items) / 10)
    embeds = []
    start = 0
    stop = 10
    for page in range(int(pages)):
        if stop > len(sorted_items):
            stop = len(sorted_items)
        items = ""
        for i in range(start, stop, 1):
            name = sorted_items[i][0]
            purchases = sorted_items[i][1]
            items += f"**{name}**: `{purchases} purchased`\n"
        embed = discord.Embed(
            title="Item Purchases",
            description=items
        )
        embed.set_footer(text=f"Pages: {page + 1}/{pages + 1}\n{random.choice(TIPS)}")
        embeds.append(embed)
        start += 10
        stop += 10
    return embeds

