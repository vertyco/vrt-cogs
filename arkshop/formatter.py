import math


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
        embeds.append(embed)
        start += 10
        stop += 10
    return embeds

