# Starhold Changelog

## 0.1.0

Needs ActivityHub 0.8.0 or later.

- First release: a solo sci-fi tower defense for ActivityHub. Build and upgrade four towers (Blaster, Missile pod, Tesla coil, and a Drone bay whose drones wall off the road until a crowd breaks through), each with two final forms, fire Orbital strikes and Stasis fields, and survive endless waves of scrap mechs with a Scrap Colossus every tenth wave.
- The map's road has a long straight in, a tight hairpin, a loop round a crater and a last run to the core, with 12 build spots at its bends, most reaching two stretches of road and the one inside the loop three. Each tower kind reaches its own distance, and every upgrade reaches further.
- A tower card says what each tower does, with its numbers. Point at a tower in the build ring with the mouse, or tap it once on a phone (a second tap builds it). Upgrades show the numbers before and after, and tapping a built tower shows what it is.
- The map fills the screen. One thin bar floats over its top (lives, money, wave, score, the people button and Pause), and Strike and Stasis are round buttons in its bottom corners. While one recharges it shows the seconds left inside a ring that fills up; once ready it glows, with a pop the moment it comes back. On desktop and phones held sideways the map turns on its side, so it fills a wide screen too.
- Between waves, a robot-head button where the road comes in counts down to the next wave. The mouse over it, or a first tap on a phone, shows the robots the wave brings; a click or a second tap calls it early for the bonus.
- Tap a robot to see what it is, its health and what stops it. The first time each robot type comes in during a run, a note says what it does.
- Each server keeps a high score table. Server admins can turn on Neopets-style cash-ins from the game's own settings dialog; the bot checks every paid or ranked score by replaying the run's moves in a short-lived side program. If the bot can't check at all (mini-racer isn't installed), it says so in its log when the cog loads, and a finished run is checked again once it can, instead of staying failed.
- Friends in the same Activity window see each other's wave and score live. If Starhold closes mid-run, the run is kept for 30 minutes after it closes, and opening Starhold again in that time picks it up where it left off.
- Sound: 46 sound effects (our own mixes, layered from recordings in the Sonniss GDC Game Audio Bundle; its license text and the credits are in `web/sounds/`) and two music loops made with Google's Lyria 3, "Reactor Watch" for the menus and "Scrapfall" for battle.
