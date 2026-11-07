# Vegas

Redjumpman's Casino rebuilt as a Discord Activity for [ActivityHub](../activityhub/README.md). Eleven games on a menu of game cards in a Classic Vegas casino, with everyone in the Activity window sharing the tables. Every game also plays alone.

- **Eleven games.** Texas Hold'em, Slots, All In, Blackjack, Coin, Craps, Cups, Dice, Hi-Lo, War and Double or Nothing. Each has its own painted card on the menu, with the faces of who's playing there. Slots and All In are solo only, each player at their own machine or wheel; the rest are shared tables.
- **Texas Hold'em.** A 6-seat no-limit poker table where players bet against each other, not the casino. Someone alone at the table practices free against 3 CPUs with play chips; once a second person buys in, hands are played for real credits. Players buy in between the game's Min and Max, and the blinds come from the Max. The casino keeps a cut of each pot that reaches the flop (5% by default, at most 3 big blinds), and nobody receives it, so real hands slowly drain currency out of the economy.
- **Slots.** Three reels and a fixed pay table, spun by pulling the machine's lever down. 2% of every bet grows a progressive jackpot that 7-7-7 wins: a max bet wins the whole pot, a smaller bet its share, and the pot never drops below 60 times the max bet. The house keeps about 5 of every 100 credits bet, so Slots slowly takes currency out of the economy.
- **All In.** Bets the player's whole balance on a lit prize wheel. Its gold slice is the true chance of winning, 1 in (multiplier + 2), so it thins as the multiplier grows.
- **Red's bank credits.** Bets come out of the bank and winnings go back in.
- **The original's settings.** Per-game minimum and maximum bets, multipliers, cooldowns, access levels, the payout limit and memberships. Admins edit all of it in the Activity's settings, and the original's `[p]casino` and `[p]casinoset` commands are here as `[p]vegas` and `[p]vegasset`.
- **Phones and desktop.** Works on a desktop window and on a phone, upright or sideways.

## Setup

Vegas needs ActivityHub 0.13.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs vegas
[p]load vegas
```

It can stay loaded next to Redjumpman's Casino, since the names don't clash. Data starts fresh: Redjumpman's Casino's settings are not imported. It appears in the hub's menu by itself. `[p]activityhub games` lists it.

Global mode needs Red's bank to be global, and only the bot owner can switch it. Both modes' data is kept, so switching back loses nothing.

## Using it

`[p]vegas` posts a Play button, and `/vegas` opens the casino directly. Players pick a game card to sit at its table. Admins change game settings and membership tiers in the Activity's settings, or with `[p]vegasset`. `[p]vegas version` shows the version and the credit.

## Fair play

The bot decides every card, roll, flip and wheel spin with a secure random source, and checks and pays every bet. At Slots it draws every reel's stop, and the lever's pull only changes how the reels spin, never where they stop. The page only animates what the bot decided, so a changed page can't change an outcome or a payout. At the Hold'em table each player's cards are sent only to them until the showdown, so no page, a watcher's included, ever holds another player's secret cards.

## What changed from the original

- **War.** Surrender now returns half the bet, where it used to return nothing. Going to war now takes the second bet it promised, and a win pays the stake with the multiplier plus the war bet back.
- **Craps.** The help text now matches what the code does: a come-out 7 pays stake x 3 x the multiplier, and the shooter gets exactly one more roll.
- **Payout limit.** The limit now compares the real total, with the multiplier and bonus, instead of the smaller number. A held win pays what was actually won, and several held wins add up instead of replacing each other.
- **Cooldowns.** The time left shown to a member with a cooldown reduction now has the reduction taken off, not added.
- **Memberships.** The 5 minute loop no longer crashes on a days requirement. Memberships given by hand stay put. Role requirements are kept by role id, so renaming a role breaks nothing, and renaming a membership keeps its players. A membership can also raise its players' max bets with a max bet multiplier. In global mode all the admin commands are owner-only.
- **Other.** Each table has its own deck. All In refuses a balance of 0. Switching modes no longer wipes data.

## Credits

Vegas is a rebuild of Redjumpman's Casino from [Jumper-Plugins](https://github.com/Redjumpman/Jumper-Plugins), the original this cog is based on. The background music, "High Roller Lounge", was made with Google's Lyria 3. The table sounds are from Kenney's Casino Audio (CC0). The font is Playfair Display (SIL Open Font License). The art was made with Codex image generation. Drawing uses PixiJS (MIT License).
