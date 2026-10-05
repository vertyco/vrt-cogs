# Miner Changelog

## 1.4.0

- **New**: Pick which rock types ping you. `[p]miner notify` now opens a dropdown of rock types, and you only get pinged for the ones you tick. Clear every tick to turn pings off.
- **Change**: You can only get pings for rock types you have mined. Mine a rock type once to unlock its ping. If you already had pings on, you keep them for every type you have mined since 1.2.0.
- **Change**: `[p]miner notify` no longer takes `true` or `false`.

## 1.3.1

- **Fix**: The leaderboard's page arrows now show whenever there is more than one page. Before, a fresh leaderboard never had arrows, and leaderboards with fewer than 10 pages could never get past page 1.
- **Fix**: Two leaderboards open at once no longer swap dropdown choices. Picking Iron on one leaderboard could make another person's leaderboard show Iron selected while it still listed Stone.

## 1.3.0

- **Change**: The rock message has a new look. The rock picture stays big, the **Mine** button sits next to the HP bar below the recent swings (so it stays put while they update), and the **Inspect** button sits next to the rock's modifiers. Both buttons now have labels.
- **Change**: Rock results show one row per miner with their profile picture: damage, hits, score, loot and pickaxe durability. Up to 8 full rows; anyone past that is listed in a short "Also mined" block. Everyone is still paid.
- **Change**: When a rock ends, its buttons are removed instead of greyed out.
- **Change**: A rock that collapses before anyone hits it shrinks to a single small line.
- **Change**: The spawn ping is now part of the rock message instead of a separate message.
- **Change**: Clicking Mine costs one call to Discord instead of two, so busy rocks are much less likely to run into Discord's rate limits.
- **Fix**: The rock message always shows the final HP after a fast burst of clicks.
- **Fix**: Clicking Mine while a rock is paying out now gets a reply instead of "This interaction failed".
- **Fix**: `/rock` used as a slash command no longer shows "The application did not respond".
