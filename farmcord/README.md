# FarmCord

A small FarmVille-style farming game for [ActivityHub](../activityhub/README.md), drawn with Zynga's original FarmVille art. Each player has one farm that follows them to every server and DM. They walk their farmer between the farmhouse, the Yard, the Pond, the Market and seven plots, grow crops through the seasons, raise animals and build the farm up over weeks of play.

- **Crops through the seasons.** Till, plant, water and harvest 16 crops. Each season lasts one real week, a crop grows at half speed out of its seasons, and rainy days water every crop. A ripe crop left too long dries, withers and then rots.
- **Animals.** Chickens, geese, pigs, goats, cows and horses. Each one is fed and watered on its own, babies grow into adults worth more with good care, and adults can be bred or sold.
- **Building up.** Levels 1 to 100 unlock new crops, animals, plots, bigger watering cans, better hoes, more storage and two extra farmhouse rooms. Fifteen achievements each give a badge.
- **Looks.** Decorations for the Yard and the extra rooms, and hats, tops and bottoms for the farmer.
- **Global leaderboard.** The top farms by level across every server on the bot, on the farmhouse board.
- **Desktop and phones.** Works in a desktop window and on a phone held upright or sideways, with the sound and music switches always on screen.

FarmCord is single player. Players see each other only on the leaderboard and in ActivityHub's "who's here" list.

## Setup

FarmCord needs ActivityHub, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs farmcord
[p]load farmcord
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it. Farms are kept in a SQLite database in the cog's data folder.

## Using it

`[p]farmcord` posts a Play button, and `/farmcord` opens the game directly. `[p]farmcord` works in DMs too, since a farm follows its player everywhere. `[p]farmcord version` shows the version and the credit.

There are no admin commands. Besides ActivityHub's own switches for turning the game off, the payout settings below are the only setting.

## Payouts

Players can turn FarmCoins (the game's own money) into your bot's currency at the Market's bank counter, the way Neopets pays for its games. Each FarmCoin pays a set rate, up to a most-per-cash-in, and each player gets a few cash-ins a day. A cash-in only takes the FarmCoins that the most-per-cash-in pays for, so the rest stay on the farm. Credits never turn back into FarmCoins.

Server admins (the server owner, anyone with Manage Server, or Red's admin role) and the bot owner see a gear button on the bank counter's panel. It turns payouts on and sets the credits per FarmCoin (1 by default), the most per cash-in (1,000) and the cash-ins a day (3). So at the defaults, one player can earn at most 3,000 credits a day. Payouts start off. Cash-ins come back at midnight UTC.

With a global bank every server shares one balance, so only the bot owner sees the gear button, the settings apply in every server, and the daily cash-ins count across servers. In a DM the bank counter says cash-ins only work in a server.

FarmCord only pays credits out: it never takes any in. Inside the game, FarmCoins are spent on seeds, feed, animals, tools, plots, storage, rooms and looks.

## Fair play

The bot keeps the clock and rolls every random result. The page only sends what the player wants to do, like "water spot 4 of Plot 2". The bot checks the tool, the items, the level, the FarmCoins and the time before doing it, and it decides every harvest size, free seed, exceptional crop or animal and breeding try. Crops grow and animals get hungry while players are away: the bot works it out from its own clock when the farm is next opened, so nothing runs in the background, and changing a device's clock changes nothing.

Two limits remain:

- Someone with several Discord accounts gets a farm, and daily cash-ins, on each one.
- A script could click for a player, but every crop and animal runs on the bot's clock, so it can't make anything grow faster.

Neither one gets past the payout limits. Each Discord account can still only cash in a few times a day, and each cash-in pays at most the most per cash-in.

## Credits

Game design by [Vainne](https://github.com/Atuelliss).

The art is from Zynga's FarmVille (2009 to 2020). FarmVille and its art are Zynga's, and FarmCord is not made or endorsed by Zynga. Most pictures are FarmVille's own, used as they were: the crops and soil, the crop icons, the coin and XP icons, the starter watering can and hoe, the decorations and scenery, the animals, the farmer and most of his clothes, the summer and winter grass, the path, and the summer, autumn and winter skies. Some are FarmVille pictures edited for this game: the dried crops, the gold-rimmed exceptional crop icons, the feed sacks (FarmVille's chicken feed sack relabeled for each animal), the achievement badges (FarmVille's ribbons with the logo painted over), the cap without its logo, the red overalls, the farmer's plain shirt and trousers, the spring and autumn grass, the spring sky and the autumn pond. A few pieces FarmVille didn't have were made with OpenAI's Codex image generation, matched to FarmVille's art: the seed packet (each crop's packet shows FarmVille's icon for that crop), the big watering can, the sprinkler can, the wide hoe, the plow, the inside of the farmhouse and the feed trough.

The background music, "Sunny Meadow", was made with Google's Lyria 3. The font is Fredoka (SIL Open Font License). Drawing uses PixiJS (MIT License).

Every sound effect is CC0 (a [public domain dedication](https://creativecommons.org/publicdomain/zero/1.0/)). They come from Kenney's packs (Kenney Vleugels, [kenney.nl](https://kenney.nl)) and from clips on Freesound, cut and mixed for this game:

| Sound | Source | License |
|---|---|---|
| Footstep | Kenney, [Impact Sounds](https://kenney.nl/assets/impact-sounds) | CC0 |
| Hoe | dr19, ["Shovel_dirt.wav"](https://freesound.org/people/dr19/sounds/353907/) on Freesound | CC0 |
| Planting | thatonecode, ["seeds"](https://freesound.org/people/thatonecode/sounds/755503/) on Freesound, with Kenney, [Impact Sounds](https://kenney.nl/assets/impact-sounds) | CC0 |
| Watering | FOSSarts, ["pouring water on grass - 1"](https://freesound.org/people/FOSSarts/sounds/763461/) on Freesound | CC0 |
| Refilling the can | XiiiSamples, ["Filling bucket with water"](https://freesound.org/people/XiiiSamples/sounds/384181/) on Freesound | CC0 |
| Harvest | Kenney, [Interface Sounds](https://kenney.nl/assets/interface-sounds) | CC0 |
| Exceptional harvest | Kenney, [Interface Sounds](https://kenney.nl/assets/interface-sounds) | CC0 |
| Clearing a spot | Kenney, [Impact Sounds](https://kenney.nl/assets/impact-sounds) | CC0 |
| Feeding | Wastefield, ["Cereals are poure in a large jar - individual grains at the end"](https://freesound.org/people/Wastefield/sounds/692102/) on Freesound | CC0 |
| Chicken | chanyatenn, ["chicken sound - clucking.wav"](https://freesound.org/people/chanyatenn/sounds/424076/) on Freesound | CC0 |
| Goose | wjoojoo, ["cibolo_geese09.wav"](https://freesound.org/people/wjoojoo/sounds/204337/) on Freesound | CC0 |
| Pig | qubodup, ["Pig Oink"](https://freesound.org/people/qubodup/sounds/442906/) on Freesound | CC0 |
| Goat | Kinoton, ["Single Goat Bleating 2x"](https://freesound.org/people/Kinoton/sounds/581240/) on Freesound | CC0 |
| Cow | invertedturtle, ["Cow Moo 2"](https://freesound.org/people/invertedturtle/sounds/546479/) on Freesound | CC0 |
| Horse | shadoWisp, ["horse neigh shortened.wav"](https://freesound.org/people/shadoWisp/sounds/269571/) on Freesound | CC0 |
| Babies born | Kenney, [Music Jingles](https://kenney.nl/assets/music-jingles) | CC0 |
| Buying | Kenney, [RPG Audio](https://kenney.nl/assets/rpg-audio) and [Interface Sounds](https://kenney.nl/assets/interface-sounds) | CC0 |
| Selling | Kenney, [RPG Audio](https://kenney.nl/assets/rpg-audio) and [Interface Sounds](https://kenney.nl/assets/interface-sounds) | CC0 |
| Level up | Kenney, [Music Jingles](https://kenney.nl/assets/music-jingles) | CC0 |
| Achievement | Kenney, [Music Jingles](https://kenney.nl/assets/music-jingles) | CC0 |
| Refused | Kenney, [Interface Sounds](https://kenney.nl/assets/interface-sounds) | CC0 |
| Tap | Kenney, [Interface Sounds](https://kenney.nl/assets/interface-sounds) | CC0 |
| Door | Kenney, [RPG Audio](https://kenney.nl/assets/rpg-audio) | CC0 |
| Rain | samesamesame, ["Rain from Indoors - Perfect loop"](https://freesound.org/people/samesamesame/sounds/242889/) on Freesound | CC0 |
