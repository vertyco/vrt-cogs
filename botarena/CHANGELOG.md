# Changelog

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
