# Changelog

## 1.4.1

- Replaying a campaign mission you already beat now pays the full credit reward, the same as the first win. Replays used to pay only 25%. The replay entry fee stays at 25%.

## 1.4.0

- The battle AI was rewritten so tactics and chassis intelligence matter. Before, shots almost never missed, dodges barely moved a bot, and a Defensive squad won most fights whatever the matchup.
- **Aggressive** bots charge in and hold their ground, and slip inside the minimum range of long guns like the Devenge, where those can't shoot back.
- **Defensive** bots stay just out of the enemy's reach and stop to shoot accurately. When chased, they turn and run with the turret firing over their back, and circle the arena instead of backing into a corner.
- **Tactical** bots circle side-on at mid range, attack from a different side than their teammates, change direction when shot at, and roll out of the way of slow cannon shells and missiles. The trade-off: shooting while moving sideways is less accurate.
- **Closest** targeting goes for whoever the bot can shoot soonest and fights back against whoever is attacking it. **Weakest** goes for whoever the bot's weapon can finish off soonest, instead of the lowest health anywhere on the map. **Focus Fire** bots now agree on one target, the enemy they can kill fastest together.
- New **Support First** targeting hunts enemy healers first, then the hardest-hitting enemy.
- Bots stick with their target instead of switching every few seconds, and shoot any enemy in reach while closing on the one they picked instead of holding fire.
- Bots lead moving targets and only fire once their turret is on target. Intelligence now decides how well a bot aims, how quickly it reacts and how well it picks its spot. It no longer just rolls dice.
- Bots can drive in reverse (slower than forward), so they can back off while keeping their nose to the enemy.
- Cannon shells and missiles fly slower, so a side-on bot can dodge them at long range. Lasers and bullets are unchanged.
- Healers pick who to heal and where to stand in one decision, stay within reach of their patient with the turret ready, and shadow the front line before anyone is hurt instead of wandering into the middle. Badly hurt bots fall back to a friendly healer and return once patched up.
- Bots move to get a clear shot when a teammate is in the way, instead of just holding fire.
- Challenges were retuned for the new AI. Challenge 7, Strategy, now teaches Focus Fire. Challenge 2, Evasion, faces three slower brawlers. Some loaned bots and enemies have different armor. Each challenge's intended orders win far more often than wrong ones.
- Campaign enemies use the new AI too, so some missions play differently. The hints after a loss now point to the tactic that works, such as Support First against healers.

## 1.3.0

- Battle videos got a visual overhaul: muzzle flashes, glowing tracers and laser bolts, missile smoke trails, sparks where shots land, fireballs when missiles hit and bots blow up, and burning wrecks that smoke for the rest of the fight. Destroyed bots leave scorch marks on the arena floor.
- Bots now cast a shadow, sit on a ring in their team's color, and flash white when hit. Health bars show the damage just taken draining away.
- A scoreboard along the top shows the clock, how many bots each side has left and each team's total health, with recent kills listed under it. The video ends on a banner naming the winner. All text is outlined so it reads on every arena.
- When both teams would get the same color (a red player against the red default enemy, or two PvP players with the same color), the enemy team now gets a different one.
- Bots now speed up and brake smoothly, slide around each other and along walls instead of freezing on contact, and stand a little further apart when they touch.
- Shots now leave from the tip of the drawn barrel, and are checked along their whole flight path so fast shots can't skip through a hull between frames.
- Fixed bot bodies being drawn off-center and drifting as the turret turned. The drawn hull now matches where shots actually hit.
- Hit detection no longer depends on numpy being installed. Without it, bots used to get a smaller round hitbox instead of their plating's real shape.

## 1.2.1

- Battle videos render about 5x faster. Part images, their turned angles and text labels are now made once per battle and reused for every frame, instead of being re-read and redrawn each frame. Videos look the same.

## 1.2.0

- Added Challenges: seven puzzle battles opened from the new 🧩 Challenges button on the hub. You get a loaned squad and only pick each bot's stance and target. Two challenges are open from the start and the rest unlock as you beat campaign missions. Each pays credits on its first clear only, and challenge battles never count toward wins, losses, damage totals or leaderboards. The profile shows how many you've cleared.
- Added two prize-only parts, won from the last two challenges: Prize Overwatch R760 plating and the Prize Darsik R200-Z machine gun. They are never sold in the shop and can't be sold back.
- Weapons now have accuracy. Each shot can stray by up to the weapon's spread, so low-accuracy guns miss more at long range. Accuracy is shown as Pinpoint, High, Medium, Low or Very low in the shop, when equipping a weapon, and when a part unlocks.
- The Circes and Scream Shard missiles now explode on impact, hurting other enemies near the target for half damage. The shop shows their blast radius.
- The results screen now hands out awards: MVP (most damage), Toughest (most damage taken), Last stand (every survivor under 10% health) and Top healer.
- Healing no longer counts as damage dealt. Healers' damage totals, the damage leaderboard and PvP damage totals now count real damage only. Past totals are left as they were.
- Fixed the point-blank shockwave only showing for a single frame, and the empty hit and heal events it created.
- Fixed a loading tip that promised missiles track targets.
