import math
import random

import discord
from redbot.core.utils.chat_formatting import pagify

TIPS = [
    "Tip: The {p}shopstats command shows how many items have been purchased!",
    "Tip: The {p}shoplb command shows the shop leaderboard for the server!",
    "Tip: The {p}rshoplist command shows an overview of all RCON shop categories and items!",
    "Tip: The {p}dshoplist command shows an overview of all DATA shop categories and items!",
    "Tip: The {p}playershopstats command shows shop stats for a particular member, or yourself!",
    "Tip: You can use the {p}playerstats command to view playtime stats for a specific player, or yourself!",
    "Tip: You can use the {p}clusterstats command to view the top player on each cluster!",
    "Tip: You can use the {p}arklb command to view a global playtime leaderboard for all maps!",
    "Tip: You can use the {p}servergraph command to view player count over time!",
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
    sorted_shops = sorted(shops, key=lambda x: x.lower())
    for category in sorted_shops:
        sorted_items = sorted(shops[category], key=lambda x: x.lower())
        category_items = ""
        for item in sorted_items:
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
        if len(category_items) <= 4096:
            embed = discord.Embed(
                title=f"🔰 {category}",
                description=f"{category_items}"
            )
            embeds.append(embed)
        else:
            for p in pagify(category_items):
                embed = discord.Embed(
                    title=f"🔰 {category}",
                    description=f"{p}"
                )
                embeds.append(embed)
    return embeds


async def rlist(shops: dict):
    embeds = []
    sorted_shops = sorted(shops, key=lambda x: x.lower())
    for category in sorted_shops:
        sorted_items = sorted(shops[category], key=lambda x: x.lower())
        category_items = ""
        for item in sorted_items:
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
        if len(category_items) <= 4096:
            embed = discord.Embed(
                title=f"🔰 {category}",
                description=f"{category_items}"
            )
            embeds.append(embed)
        else:
            for p in pagify(category_items):
                embed = discord.Embed(
                    title=f"🔰 {category}",
                    description=f"{p}"
                )
                embeds.append(embed)
    return embeds
