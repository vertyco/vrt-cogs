# Block Blaster

Clear pixel pictures with a belt of hungry shooting cats, for [ActivityHub](../activityhub/README.md). A remake of Loom Games' phone puzzle "Pixel Flow!", with its sounds and pictures and all-new cats.

- **How it plays.** Columns of colored cats wait under a pixel picture. Tap the front cat of a column and it rides a belt once around the picture, shooting every cube of its own color that it can see. A cat with shots left waits in one of five slots for later. Run out of slots and the level is lost; clear every cube to win.
- **The original's levels.** All 2,600 levels from the phone game, with its level twists (locks and keys, ice, snakes, rockets and more) and its boosters.
- **Still being built.** Levels 1 to 599 have every twist they use. Later levels bring twists that are not in yet.
- **Progress that follows you.** The bot keeps each player's level, coins and boosters, the same on every server and device.
- **Watch a friend.** Friends in the game show as faces under the top bar. Tap one, or Join them from the hub, to watch their level live.
- **Coins and credits.** Wins pay in-game coins, which buy boosters and revives. Server admins can also sell boosters for Red currency from the game's settings dialog (off until a price is set). Those credits go to no one, so the shop takes money out of the economy and never pays any out.
- **Desktop and phones.** Live 3D, held upright on phones.

## Setup

Block Blaster needs ActivityHub 0.8.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs blockblaster
[p]load blockblaster
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Fair play

The bot runs its own copy of every level from the taps a player sends. Wins, the coins they pay and every booster used come from the bot's copy, not from the page.

## Credits

Block Blaster is a remake of Pixel Flow! by Loom Games and uses its levels, sound effects and non-character pictures and models. The cats, the music, the icon and some feature pictures are new. Drawing uses three.js (MIT License).
