# The Last Stand: Union City

A zombie survival RPG for [ActivityHub](../activityhub/README.md), ported from Con Artist Games' Flash game "The Last Stand: Union City" (2010, published by Armor Games). You make a survivor, wake up after a car crash on the edge of Union City, and fight, search and trade your way across the city to find your partner and escape by boat.

- **The whole original game.** 11 areas and 285 rooms, 33 quests, 54 achievements, every weapon, item and character, and the ending, with the original's art and sounds. The original's bugs are fixed, and the numbers are the ones it played with.
- **Your own survivor.** Pick a name, look and occupation, or set your own attributes and skills. Run & Gun or Survivor mode (eating and sleeping), with Hardcore and Headshots options.
- **Three save slots per Discord user.** The bot keeps them, so a story follows the player to every server and device and survives a cleared browser cache.
- **Single player, side by side.** Each person plays their own story. The hub's people button shows who is here, and friends' faces appear next to their area on the city map.
- **Desktop and phones.** Mouse and keyboard on a computer. On a phone held sideways: a move stick, an aim stick (push to the edge to fire) and buttons for the rest. An upright phone shows a card asking to turn the phone.
- **No currency.** The game pays no server currency and has no leaderboard.

## Setup

Union City needs ActivityHub 0.8.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs laststand
[p]load laststand
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Saves

Saves live as compressed files in the cog's data folder, one per user and slot (about 30 to 150 KB each). The page runs the game and sends the bot the save; the bot checks its size and shape before keeping it. Each slot carries a revision number, so an older copy from another device or a late request can never overwrite newer progress. Nothing is at stake in a save (no currency, no ranking), so a player who edits their own save only changes their own story. A user's saves are removed when they ask Red to delete their data.

## Credits

The Last Stand: Union City is a game by Con Artist Games. This is a port of the Flash version published on Armor Games (https://armorgames.com/play/12009/the-last-stand-union-city), and uses its art and sounds. Drawing uses PixiJS (MIT License).

## For developers

Union City shows the page-runs-everything pattern: the page plays the whole game and the bot only stores saves, through the actions in `activityhub_game()`. See "Bigger examples" in ActivityHub's [DEVELOPERS.md](../activityhub/DEVELOPERS.md#16-bigger-examples-the-included-games).
