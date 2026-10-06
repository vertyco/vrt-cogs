# Miner Changelog

## 1.11.1

- **Fix**: The large rock's mined out picture no longer shows a polished diamond in the middle of the rubble.

## 1.11.0

- **New**: A rock's modifiers now show on its picture. Electrified rocks crackle with lightning, Crystalline rocks sparkle, Volatile rocks burn, Enchanted rocks swirl with magic, Fortified rocks sit under a shield dome, and Blessed rocks glow in golden light. A rock with two modifiers shows both. The results picture after the rock ends is unchanged.

## 1.10.0

- **New**: Every rock type now has its own "mined out" picture on the results when players break it in time: small, medium and large rocks leave rubble that matches their size, the meteor leaves a smoking crater with glassy shards, and the Volatile Geode bursts into glowing purple crystals. A rock that runs out of time still shows the collapsed mineshaft.

## 1.9.0

- **New**: Small, medium and large rocks now come with several pictures each (three small, three medium, two large), and each rock that spawns shows one at random. A rock keeps the same picture until it is mined out or collapses.
- **Change**: The small rock no longer glows, so it stops looking like a rare rock, and the large rock is now a rough boulder instead of a polished gem.
- **Change**: The Volatile Geode has a new, brighter picture that is easy to see and no longer looks like the meteor.

## 1.8.2

- **Fix**: Rocks from 1.8.1 stopped updating after they spawned: HP stayed at 100% and clicks failed until the rock collapsed. Rock updates now keep the uploaded picture correctly.

## 1.8.1

- **Fix**: A finished rock could flip back to the live rock a moment after its results showed, with HP still left and buttons that no longer worked. The rock's picture is now uploaded with the rock message instead of linked, so Discord no longer reloads it after every update and can't put an older version of the message back on top of the results.

- **Change**: All rock pictures (the five rocks, the depleted rock and the collapsed mineshaft) now ship with the cog and are uploaded by the bot, so rocks no longer depend on imgur.

## 1.8.0

- **New**: Weak spots and gem veins. Bigger rocks now and then show an extra button for 5 seconds. The first miner to click a weak spot deals 15% of the rock's HP in one hit; the first to click a gem vein gets bonus gems. You have to have hit the rock to claim one, and clicking it never counts toward swinging too fast.

## 1.7.0

- **New**: Pickaxe perks. Spend stone, iron and gems on permanent perks with `[p]miner perks`: Forceful, Lucky, Steady, Closer, Sturdy and Prospector. Iron and Steel pickaxes hold one perk, Carbide two, Diamond three. Perks stay through upgrades and repairs, but a pickaxe that shatters or wears out takes its perks with it.

## 1.6.1

- **Fix**: A pickaxe that wears out at the end of a rock now stops hitting at its old tier right away. Before, the next few minutes of swings could still use the broken pickaxe's power and crit chance.

## 1.6.0

- **New**: Every achievement category has its own picture.
- **Change**: `[p]miner achievements` has a new look. The first screen lists your categories with their pictures and progress bars, six to a page, plus your overall progress and recent unlocks.
- **Change**: Pick a category from the dropdown to open it. The arrows flip between categories, and **All categories** takes you back to the list.

## 1.5.0

- **New**: 38 new achievements, 92 in total. Faster solo clears, modifier combos, crew and role milestones, clutch plays, and a few hidden ones to discover.
- **New**: Seven new achievement categories so the list is easier to browse: Elite Speed Clears, Modifier Combos, Crew Milestones, Role Mastery, Clutch Plays, Mishaps and Mastery.
- **New**: Mastery achievements for collecting other achievements, including Completionist for unlocking every achievement that is not hidden.
- **Change**: Achievements your saved stats already prove now unlock automatically, including older ones like clean streaks, solo speed clears, party roles and rock counts. They show up after your next rock, or when you open `[p]miner achievements`.
- **Change**: Hidden achievements show as ??? until you unlock them.

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
