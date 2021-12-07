# vrt-cogs
Various utility/random cogs for Red V3.

<p align="center">
  <a href="https://github.com/Cog-Creators/Red-DiscordBot/tree/V3/develop">
    <img src="https://img.shields.io/badge/Red%20DiscordBot-V3-red.svg">
    </a>
  <a href="https://github.com/Rapptz/discord.py">
    <img src="https://img.shields.io/badge/Discord-py-blue.svg">
    </a>
<p>

I enjoy working with API's and making cogs for game servers or other helpful use cases. Check out some of my projects below

| Cog | Status | Description |
|---|:---:|---|
| ArkSave | ✓ | <details><summary>Plugin for the ArkTools/ArkShop cog adding a (Very Specific) feature, see extended summary for example.</summary> This cog adds just 1 feature to ArkTools/ArkShop, the ability for users to pay credits to append their XUID to a .txt file in the data packs folder. This can be used for hosts that wipe occasionally and want to "sell" data saves so that on wipe day they have the XUID's of everyone that wants their data saved. (Requires BOTH ArkTools and ArkShop cogs)</details> |
| ArkShop | ✓ | <details><summary>Plugin for the ArkTools cog adding extensive automated shop features.</summary> This cog requires the ArkTools cog to function, it adds two types of shops: RCON and DATA shops. The rcon shop uses item blueprint strings to send items directly to the players inventory, while the data shop uses actual file transfer to move and rename pre-made data packs into the server's cluster folder. ArkShop has many other features to help making data packs easier and also includes shop leaderboards and player shop stat commands.</details> |
| ArkTools | ✓ | <details><summary>Remotely manage/monitor your Crossplay or Steam Ark servers via RCON protocol and chat seamlessly between in-game and discord.</summary> This cog comes packed with utility features for overseeing your Ark: Survival Evolved server; Including a status channel, join/leave logs, auto-renaming blacklisted player names, admin command logging with tribe logs, player stat tracking with leaderboards, and a sizeable collection of API tools for crossplay servers hosted from a Gamertag. (This cog is for self-hosted Xbox/PC crossplay or steam servers only, will not work with Nitrado)</details> |
| ATLA | ❌ | <details><summary>(IN CONCEPT) Explore the world from Avatar: The Last Airbender and find/raise your own animals from the ATLA universe!</summary> This cog is still in the concept stage and is NOT intended to be downloaded yet.</details> |
| DayZTools | beta | <details><summary>Remotely manage/monitor your Nitrado Day-Z server from Discord.</summary> Various logging/management features for Day Z: Player join/leave log, server reboots, Killfeed and server status channel with server info.</details> |
| Fluent | ✓ | <details><summary>Set any channel as a two-way translator for fluent conversation.</summary> Set a channel and both languages, if a message is in language 1 it gets converted to language 2 and vice versa using googles free api.</details> |
| Inspire | ✓ | <details><summary>Get inspirational messages.</summary> Super simple cog that replies to certain sad words with positive encouragements, and responds to the [p]inspire command with an inspirational quote using zenquotes.io API. Note: this cog was my very first project just to get the feel for Red so it's not very big and there aren't any plans of expanding it at the moment.</details>|
| MCTools | ✓ | <details><summary>Super simple status cog for Minecraft Bedrock servers.</summary> Displays a status embed showing server version and player count. Only for **Bedrock** dedicated servers since there is already one that supports Java.</details> |
| Meow | ✓ | <details><summary>Meow</summary> Replaces the word "now" with "meow" in someone's latest message, if word doesnt exist in the most recent 2 messages, it sends a random cat unicode emoji. Yall have a good day meow.</details> |
| NoBot | ✓ | <details><summary>Filter certain messages from other bots.</summary> (ONLY checks messages from other bots), Add a bot to be filtered and a key phrase to check for. When that bot sends a message containing that phrase the message will be auto-deleted.</details> |
| SCTools | Beta | <details><summary>View detailed Star Citizen ship info.</summary> Right now there is only one command (scships) that displays detailed info for ships in SC, you can use "[p]scships shipname" to search for a specific ship.</details> |
| XTools | ✓ | <details><summary>View your Xbox profile, friends, screenshots and game clips using simple commands and interactive menus.</summary> Various tools for Xbox using Microsoft's XSAPI. (You will need to register a Microsoft Azure application to use this cog. Type "[p]apiset help" after install for more info)</details> |

# Installation
Run the following commands with your Red instance, replacing `[p]` with your prefix:

If you havent loaded the Downloader cog already, go ahead and do that first with: `[p]load downloader`. Then, 
```ini
[p]repo add vrt-cogs https://github.com/vertyco/vrt-cogs
[p]cog install vrt-cogs <list of cogs>
[p]load <list of cogs>
```

# Credits
- Obi-Wan3 for holding my hand through a lot of my issues and questions i've had while learning python, and providing me with the insight to find things by myself.
- The Red community as a whole for having dope cogs that I can creep on and see how they make stuff work.
- The Red discord coding channel for having lots of helpful cog creators!

# Contact
For support with my cogs, feel free to hit me up in #support_othercogs in the [Red Cog Support](https://discord.gg/GET4DVk) server.

# Contributing
If you have any suggestions, or found any bugs, please ping me in Discord (Vertyco#0117) or [open an issue](https://github.com/vertyco/vrt-cogs/issues) on my repo!

If you would like to contribute, please talk to me on Discord first about your ideas before opening a PR.

# Feature Requests
I am open to ideas or suggestions for new cogs and features!
