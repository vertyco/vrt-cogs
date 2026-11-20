# Penguin Wars

A penguin knockout game for [ActivityHub](../activityhub/README.md). Up to six penguins belly-slide into each other on an ice floe that sinks from the edges in. Knock everyone else into the sea, and the last penguin on the ice wins.

- **Play alone or with friends.** CPU penguins fill empty seats. Everyone in the same window shares one floe.
- **Rounds start when you're ready.** Alone, Play starts a round at once, and the end card stays until you tap Play again. With two or more people seated, a 10-second countdown starts each round. A friend who taps Play during the 3-2-1 still gets in, taking over a CPU's penguin.
- **Four moves.** Drag back anywhere and let go to slide. Tap to brace, so anyone who slides into you bounces off. Grab a fish for one extra-heavy slide. Knocked in? You come back as a seal and can splash penguins off the edge.
- **Room for big groups.** With more than six people, watchers tap to join a line. After each round, the people in the line take the spots of whoever went out first, and the people swapped out go to the back of the line by themselves. The winner keeps their spot.
- **Dropped connections.** While someone else is still on the ice, a player who drops has 20 seconds to come back to their seat before a CPU takes over their penguin. Someone waiting in the line keeps their place for 20 seconds too. When the last person on the ice leaves or drops, the round stops at once and nothing is saved.
- **A new map every round.** Six ice shapes, and most rounds add wind, a walrus or thin ice.
- **Crates, party rounds and snowballs.** Players pay to drop a crate of power-ups on the ice, or to make the next round a fish frenzy for everyone. Watchers pay to throw snowballs. They cost currency every time.
- **73 looks to collect.** Skins, hats, glasses, scarves, capes, slide trails, a winner's cheer, a knockout splash, titles and name styles. Half are bought with the bot's currency and half are earned by playing. Nothing worn changes how a penguin plays.
- **Call-outs, a nemesis and profile cards.** Every knockout is called out, the last one plays in slow motion, and each player's card shows their counts and who knocks them out the most.
- **A leaderboard for each server.** Wins, then knockouts, for rounds played with at least two people.
- **Desktop and phones.** One finger on a phone held upright or sideways, or the mouse on desktop.

## Setup

Penguin Wars needs ActivityHub 0.8.0 or later, loaded and set up (see its README). Then:

```
[p]cog install vrt-cogs penguinwars
[p]load penguinwars
```

It appears in the hub's menu by itself. `[p]activityhub games` lists it.

## Looks

A penguin wears one thing of each kind: a skin, a hat, something on its face, something round its neck, something on its back, a slide trail, a cheer for when it wins, a splash that plays where a penguin it knocked in goes under, a title and a name style. Everyone on the ice sees them. Nothing worn changes how a penguin plays.

Players open the wardrobe with the Looks button on the title card, the end card, or beside the "Watching" note while they watch a round. They turn the penguin with a finger, tap anything to try it on, then buy it or put it on. Opening the wardrobe gives up the player's seat and place in the line, so the others carry on without them. What a player has stays theirs in every server. Buying only works in a server, while wearing works anywhere.

Every penguin starts in a free scarf, which its player can swap or take off. A faint ring on the ice under each penguin shows that player's color, the same as their dot in the top bar.

36 of the 73 looks are bought with the bot's currency. Penguin Wars never pays currency out, so everything spent here leaves your economy. They start on sale at these prices:

| Kind | 1,000 | 2,500 | 5,000 |
| --- | --- | --- | --- |
| Skins | | Emperor, Snowy | Bubblegum |
| Hats | Beanie, Party hat | Top hat, Flower, Cowboy hat | Crown, Ice block |
| Face | Shades, Round glasses | | |
| Neck | Bow tie, Bandana | Necktie | Pearl necklace |
| Back | Backpack | Cape | Jetpack |
| Trails | | Sparkle, Hearts, Bubbles | Flames |
| Cheers | Twirl | Backflip | |
| Splashes | Heart splash, Bubble bath | | |

Another 36 can't be bought. Each is earned by playing, and the wardrobe shows what it takes and how far along the player is. Every round played to its end counts, alone against CPUs too, and the counts are the same in every server.

| Earned by | Looks |
| --- | --- |
| Playing 5, 25, 50 and 100 rounds | Propeller cap, Moustache, Striped scarf, Steel skin |
| Winning 1, 3, 5, 15, 25 and 40 rounds | Monocle, Medal, Midnight skin, Wizard hat, Fireworks cheer, Golden skin |
| Knocking out 10, 25, 50, 150 and 300 penguins | Eye patch, Snowflake trail, Viking helmet, Ember skin, Star burst splash |
| Eating 10, 15 and 40 fish | Chef hat, Bell collar, Leaf trail |
| Splashing 5 and 25 penguins in as a seal | Snorkel, Shark fin |
| Bouncing 5 and 20 penguins into the sea with a brace | Halo, Sizzle splash |
| Winning 3 and 5 rounds in a row | Wings, Belly spin cheer |
| Knocking out 3 penguins in one round | Gem trail |
| Winning 1 and 5 rounds that 3 or more people played | Balloon, Flower lei |

Titles and name styles are the two kinds that are words, not things to wear. A title is a short line under the player's name. A name style colors the name or makes it glow.

| | 1,000 | 2,500 | 5,000 | Earned |
| --- | --- | --- | --- | --- |
| Titles | Chill Penguin, Pro Waddler | Ice Breaker, Big Fish | Ice Royalty | Ice Regular (10 rounds), Fish Fanatic (25 fish), The Bouncer (10 brace bounces), Seal Slayer (10 seal splashes), Champion (10 wins) |
| Name styles | Rose, Ice blue | Sunset | Neon glow | Mint (5 fish), Aurora (3 wins with 3 or more people), Lava (100 knockouts), Gold shine (20 wins) |

Server admins (the server owner, Manage Server, or Red's admin role) see a gear button in the game's top bar. It sets a price for each look that is sold. Leave a box empty to stop selling that one, and people who already bought it keep it. **Reset to defaults** fills in the prices above, ready to save. The same dialog shows what was spent today and by how many players, starting over at midnight UTC. With a global bank every server shares one balance, so only the bot owner sees the button, and the prices apply in every server.

While anything is on sale, the game's card in the ActivityHub menu says so, like "Penguin looks for credits".

## Crates, party rounds and snowballs

Three things cost currency every time they are used, so they keep taking currency out of your economy after a player owns every look. None of them sells a win.

**Crate drop (100).** During a round, anyone in the window can press the crate button under the top bar, players and watchers alike. The first press asks, the second pays. A crate falls onto a random spot on the ice, with the buyer's name over it, and the first penguin to reach it gets one of three things by chance:

- **Shield:** a bubble that takes the next hit or seal splash, then bursts. It lasts 8 seconds.
- **Frost:** every other penguin is frozen for 1.5 seconds and can't slide or brace.
- **Fish feast:** the next 3 slides are extra-heavy, like after a fish.

One crate is out at a time. The buyer can't place it, and CPUs go for it too.

**Party round (250).** The party button on the title card and the end card makes the next round different for everyone. The buyer picks one, and the 3-2-1 says what it is and who paid:

- **Fish frenzy:** a new fish every couple of seconds.
- **Slippery ice:** everyone slides much further.
- **Turbo:** half the wait between slides.
- **Fast melt:** the ice breaks up twice as fast.

**Snowball (2).** While a round is on, anyone without a seat sees a snowball button under the top bar. One press arms it, and each tap on the ice after that throws a snowball at that spot and pays for it. It lands a moment later and nudges the penguins near it. A braced penguin is not moved, and a shield bubble pops instead. One throw a second per person. A penguin a snowball knocks in is nobody's knockout.

One party round can be waiting at a time. Rounds with a crate or a party round count for the leaderboard and for earning looks like any other round. All three prices are in the same gear dialog as the looks, and an empty box turns one off.

## Maps and hazards

Every round is played on a new map, picked by chance. The 3-2-1 shows its name.

| Shape | What it is |
| --- | --- |
| Classic | The whole floe |
| Donut | A big hole in the middle |
| Twin Islands | Two islands joined by a bridge |
| Crescent | A bite is missing from one side |
| Hourglass | Wide ends and a narrow middle |
| Swiss Cheese | A few holes in random spots |

Each shape is turned at random, and the ice still sinks from its edges in. About 6 rounds in 10 also get one hazard:

- **Windy:** every 7 to 11 seconds an arrow warns of a gust, then it pushes every penguin across the ice for 2 seconds. A brace holds on.
- **Walrus:** a walrus sits near the middle. Penguins bounce off it. Every few seconds it rears up, then slams and shoves away any penguin close by. It dives off when its tile cracks.
- **Thin ice:** some tiles are bare blue ice. They crack as soon as a penguin touches them.

A penguin that wind, the walrus or thin ice puts in the sea is nobody's knockout, unless a player pushed it in the 3 seconds before.

## Knockouts, nemesis and profile cards

Each knockout shows as a line to everyone, like "Ann knocked out Bob", and the player who fell sees who did it in big letters. The last knockout of a round plays in slow motion before the end card.

The person who has knocked a player out the most, 3 times or more, is their nemesis. Only that player sees the mark on their nemesis's name. The counts are the same in every server, and only knockouts between two real people who played the round to its end count.

Tapping a player's name on the title card or end card, a leaderboard row or a watcher's face opens their profile card: their penguin in its looks, their play counts, their rank on this server, the looks they have earned and the ones they are closest to, and their nemesis. The person button on the title card opens your own.

## Leaderboard

Each server has its own top 10, opened with the trophy button on the title card. Players rank by wins, with knockouts breaking ties. A knockout counts for whoever hit, bounced or splashed a penguin that falls in within 3 seconds. A round only counts if at least two people played it, so beating CPUs alone earns nothing. Someone whose seat went to a CPU gets nothing for that round, and rounds played outside a server aren't saved. There is nothing to set up.

## Tuning

The bot owner sees a sliders button in the game's top bar. It opens a sheet beside the ice, so you can change the numbers while you play. Changes apply at once, even mid-round, and cover every server on the bot. **Reset** puts the starting numbers back.

| Slider | Start | Range |
| --- | --- | --- |
| Slide speed | 11 | 6 to 16 |
| Friction (share of speed) | 1.7 | 0.8 to 3 |
| Friction (fixed) | 1.4 | 0.4 to 3 |
| Seconds between slides | 0.9 | 0.3 to 2 |
| Brace length | 0.5 | 0.2 to 1 |
| Seconds between braces | 1.2 | 0.5 to 3 |
| Fish power boost | 1.12 | 1 to 1.5 |
| Seal reach | 1.7 | 1 to 3 |
| Seconds between seals | 2.2 | 1 to 5 |
| Ice pace (only the gap between cracks) | 1 | 0.4 to 1.5 |
| Wind push (how far a gust moves a penguin) | 1.5 | 0.5 to 3 |
| Walrus slam strength | 4.5 | 2 to 9 |
| Snowball nudge strength | 2.6 | 1 to 5 |

## Credits

The penguins, seals, the walrus, looks and sound effects are all made in code. The fonts are Lilita One and Nunito (SIL Open Font License). Drawing uses PlayCanvas (MIT License).
