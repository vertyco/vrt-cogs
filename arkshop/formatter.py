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
SHOP_ICON = "https://i.imgur.com/iYpszMO.jpg"
SELECTORS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
REACTIONS = ["↩️", "◀️", "❌", "▶️", "1️⃣", "2️⃣", "3️⃣", "4️⃣"]


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
        embed.set_footer(text=f"Pages: {page + 1}/{pages}\n{random.choice(TIPS)}")
        embeds.append(embed)
        start += 10
        stop += 10
    return embeds


async def dlist(shops: dict):
    embeds = []
    for category in shops:
        category_items = ""
        for item in shops[category]:
            if shops[category][item]["options"] == {}:
                price = shops[category][item]["price"]
                category_items += f"🔸 {item}: `{price}`\n"
            else:
                category_items += f"🔸 {item}\n```py\n"
                for k, v in shops[category][item]["options"].items():
                    price = v
                    option = k
                    category_items += f"• {option}: {price}\n"
                category_items += "```"
        embed = discord.Embed(
            title=f"🔰 {category}",
            description=f"{category_items}"
        )
        embeds.append(embed)
    return embeds


async def rlist(shops):
    embeds = []
    for category in shops:
        category_items = ""
        for item in shops[category]:
            if "options" in shops[category][item]:
                if shops[category][item]["options"] == {}:
                    price = shops[category][item]["price"]
                    category_items += f"🔸 {item}: `{price}`\n"
                else:
                    category_items += f"🔸 {item}\n```py\n"
                    for k, v in shops[category][item]["options"].items():
                        price = v["price"]
                        option = k
                        category_items += f"• {option}: {price}\n"
                    category_items += "```"
        embed = discord.Embed(
            title=f"🔰 {category}",
            description=f"{category_items}"
        )
        embeds.append(embed)
    return embeds
