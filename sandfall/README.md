# Sandfall

A falling-sand sandbox for [ActivityHub](../activityhub/README.md). Pick a material, paint it into a small world and watch it fall, flow, burn, melt, conduct and blow up. Sand piles up, water finds its level, fire eats plants and wax, lightning runs along metal, and trees grow from seeds.

Sandfall is a reimagining of the falling-sand games, not a port of any one of them. The simulation, the art, the sound and the music are new.

- **Fifty-odd materials in tabs.** Powders, liquids, gases, solids, fire and explosives, plants, machines and creatures, all picked from a toolbar.
- **Heat and electricity.** Fire, lava and ice change what they touch, and wires, batteries and sparks carry power.
- **Explosions.** Gunpowder, nitro and friends blow up with a blast that throws material around.
- **Trees, a slug and zombies.** Seeds grow into trees, a slug rolls through the world, and zombies shamble after what they find.
- **Private and shared worlds.** Every player has a private world that saves itself. Friends in the same Activity window can paint in one shared world together and see each other's brushes.
- **A gallery for each server.** Players publish worlds with a name and a preview picture, browse them, like them and load a copy to play with.
- **Glow, backdrops, music and sound.** Hot things can glow, the world can sit on a backdrop, and four songs and the sound effects can be turned down or off.
- **Desktop and phones.** Works with mouse, touch and keys, on desktop or a phone held either way.

## Setup

Sandfall needs ActivityHub 0.8.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs sandfall
[p]load sandfall
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it. Sandfall has no commands, no settings and no payouts.

## Data

Sandfall keeps each player's private world, and the worlds players publish to a server's gallery with their maker, name and likes. Deleting a player's data (Red's data deletion request) removes their private world, every gallery world they made on any server, and their likes on other worlds.

## Credits

Sandfall borrows ideas from the falling-sand games that came before it, but none of their code:

- The 2005 Japanese Java applet known as the Falling Sand Game and Hell of Sand, first seen on the Dofi Blog. Its author is not named.
- The fan versions on fallingsandgame.com, X Falling Sand 2 and Pyro Sand 2 by Xavier Case.
- "Project Sand" by Josh Don, hosted by BoredHumans.

The music is four tracks made for Sandfall with Google's Lyria. The font is Nunito (SIL Open Font License, license file in `web/fonts/`).
