# Age of War Changelog

## 0.2.1

- Opening the game shows the original's black loading screen, with its bar filling as the art downloads, instead of a half-built setup screen with a broken logo. The setup screen fades in once everything is ready.

## 0.2.0

Changes to make the game feel like the original Flash game:

- Movement is smooth now. Before, the field jumped back a little whenever an update from the bot came in late, then sped up to catch up, dozens of times a minute. Now it plays at a steady speed and never goes back.
- Each unit's animation now matches the bot's frame for frame. That includes which of its two swings a swordsman uses, which used to snap halfway through a swing about half the time.
- Sounds play at the volumes the original gave them. Most effects are quieter, explosions are a quarter of their old volume, and the music is as loud next to them as it was in the original.
- Buying a unit, building or selling a turret, adding a spot, evolving and using the special show right away, instead of waiting for the bot to answer.
- During a battle the pointer is the original's own arrow, with its dollar sign while selling.
- On wide windows the menu is drawn at the same size as the field, so it covers the top of the view like the original's. The round buttons move just under it, and the bases' health bars sit just under it as in the original.
- Special attacks shake the field up and down too, not just sideways.
- Moving the mouse off the side of the game keeps the field scrolling, like the original did.

## 0.1.2

- Fixed turrets not going onto the base when placed with a mouse. The see-through turret that follows the pointer was catching the click meant for the spot.
- Shots, smoke and other effects drawn over a turret spot no longer catch its clicks either.
- Dragging the field no longer presses the turret spot button the drag started on, so a drag can't build or sell a turret by accident.
- The see-through turret stays under the pointer while the field scrolls.
- When the computer plays the base of a player who is away, it no longer takes away the turret spots they bought.
- If a match breaks, every page goes back to the setup screen instead of staying on a frozen battle.
- The battle menu works during a pause: you can buy units, build and sell turrets, add a spot, evolve and use the special while the battle stands still.

## 0.1.1

- Fixed the battle menu's main buttons (units, turrets, sell, add a spot, evolve) not reacting to clicks.
- The field now scrolls like the original on wide windows too: the view is about the original's 650 wide, and moving the mouse to an edge below the menu scrolls it.
- Training goes on through a pause, as it did in the original. Units trained during a pause wait at the base.

## 0.1.0

- First release: Age of War for ActivityHub, ported from Louissi's Flash game with its original art, sounds and music. All 16 units, 15 turrets, five ages and five specials, the original's computer on Normal, Harder or Impossible, two-player games with others watching, pausing against the computer, and a global leaderboard of each player's fastest win on each difficulty.
