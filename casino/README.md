# Casino

Redjumpman's Casino rebuilt as a Discord Activity for [ActivityHub](../activityhub/README.md). Nine games on a walk-in Classic Vegas floor, with everyone in the Activity window sharing the tables. Every game also plays alone.

- **Nine games.** All In, Blackjack, Coin, Craps, Cups, Dice, Hi-Lo, War and Double or Nothing. All In is solo only; the rest are shared tables.
- **Red's bank credits.** Bets come out of the bank and winnings go back in.
- **The original's settings.** Per-game minimum and maximum bets, multipliers, cooldowns, access levels, the payout limit and memberships. Admins edit all of it in the Activity's settings, and the original's `[p]casino` and `[p]casinoset` commands still work.
- **Phones and desktop.** Works on a desktop window and on a phone, upright or sideways.

## Setup

Casino needs ActivityHub 0.1.13 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs casino
[p]load casino
```

Unload Redjumpman's Casino first, since both use the `casino` command. Data starts fresh: an old Casino's settings are not imported. It appears in the hub's menu by itself. `[p]activityhub games` lists it.

Global mode needs Red's bank to be global, and only the bot owner can switch it. Both modes' data is kept, so switching back loses nothing.

## Using it

`[p]casino` posts a Play button, and `/casino` opens the casino directly. Players walk the floor and sit at a table. Admins change game settings and membership tiers in the Activity's settings, or with `[p]casinoset`. `[p]casino version` shows the version and the credit.

## Fair play

The bot decides every card, roll and flip with a secure random source, and checks and pays every bet. The page only animates what the bot decided, so a changed page can't change an outcome or a payout.

## What changed from the original

- **War.** Surrender now returns half the bet, where it used to return nothing. Going to war now takes the second bet it promised, and a win pays the stake with the multiplier plus the war bet back.
- **Craps.** The help text now matches what the code does: a come-out 7 pays stake x 3 x the multiplier, and the shooter gets exactly one more roll.
- **Payout limit.** The limit now compares the real total, with the multiplier and bonus, instead of the smaller number. A held win pays what was actually won, and several held wins add up instead of replacing each other.
- **Cooldowns.** The time left shown to a member with a cooldown reduction now has the reduction taken off, not added.
- **Memberships.** The 5 minute loop no longer crashes on a days requirement. Memberships given by hand stay put. Role requirements are kept by role id, so renaming a role breaks nothing, and renaming a membership keeps its players. In global mode all the admin commands are owner-only.
- **Other.** Each table has its own deck. All In refuses a balance of 0. Switching modes no longer wipes data.

## Credits

Casino is a rebuild of Redjumpman's Casino from [Jumper-Plugins](https://github.com/Redjumpman/Jumper-Plugins), the original this cog is based on. The background music, "High Roller Lounge", was made with Google's Lyria 3. The table sounds are from Kenney's Casino Audio (CC0). The font is Playfair Display (SIL Open Font License). The art was made with Codex image generation. Drawing uses PixiJS (MIT License).
