# Sandfall Changelog

## 0.3.1

Music and sound effects get their own volume, plus fixes for the phone layouts.

- Settings has a Music switch and a Sound effects switch, each with its own volume slider under it, in place of the one Volume slider that turned both down together. Both start at 70.
- With Colored sand picked, its color slider takes the place of the tool's name, so the brush size slider keeps its full width (it used to shrink to a sliver, or vanish on a sideways phone). The color slider only shows while a tool paints Colored sand.
- Picking an element only closes the element panel on a sideways phone, where it covers the world, not on tablets and touch laptops.
- Turning an upright phone sideways keeps the part of the world you were looking at, instead of jumping back to the middle.
- The world no longer drifts on its own when the tool rows change size, and it follows your finger while you drag the sheet's handle.
- Pressing and holding Hide tools to read what it does no longer also hides the tools, and the button shows one hint instead of two.
- The world fits itself again when a sideways phone is turned end over end and the notch moves to the other side.
- With the tools hidden, the F key brings them up with the search box, which used to open out of sight. Opening a menu or the gallery puts peeked tools away again.
- An upright window shorter than a phone keeps its top bar as a row when the tools are hidden.
- For players who turned motion down, the sheet shrinks to its top row cleanly, and the world never jerks backward as it starts to glide.
- The page does less work while the sheet's handle is dragged.

## 0.3.0

Phones get much more room to draw, upright and sideways.

- Hide tools: a new button tucks the toolbars away so the world fills the screen. Upright, the tools shrink to one row at the bottom and the world zooms in to fill the height. Sideways, the bar turns into a slim column on the right with the people button, Show tools, pause, undo and the element in hand. The same button brings everything back.
- While the tools are hidden, tap the element in hand to bring them up for a quick change. Picking an element or starting to paint tucks them away again.
- Upright, the bar fits on one row, and the tools sheet shows as many whole rows of elements as fit under the world (up to five), so a row is never cut in half. Drag its handle down to hide the tools or up to bring them back; a tap on it shows or hides the extra tools.
- On phones, rarely used buttons (music, sound, settings, help, and upright also save and gallery) wait in the bar's More menu, which now shows each button's name.
- Sideways, the recent colors row no longer runs off narrow screens, and an open element list sits above it instead of under it.
- Moving the brush size slider shows the brush's size as a ring in the middle of the world for a moment.
- The world glides to its new place when the tools come or go (no motion for players who turned motion down). Buttons light up while pressed on touch screens, hover highlights no longer stick after a tap, and taps no longer wait for a possible double-tap on iPhones.
- The world makes room for Discord's notch and home bar areas even when Discord sends them after the game has opened.

## 0.2.1

Needs ActivityHub 0.8.0 or later.

- Works with ActivityHub 0.8.0, which changed how games get raw requests and check for server admins. An older ActivityHub refuses Sandfall with a message saying to update it.

## 0.2.0

- Reset to start: a button in the world menu, beside Clear, puts back the scene every new world starts with (the dunes, the pond and waterfall, the tree, the candle and the slug), with its settings. In a shared world only the owner can use it. In a private world Undo brings back what was there.

## 0.1.0

Needs ActivityHub 0.5.0 or later.

First release. Sandfall is a falling-sand sandbox: paint a material into the world and watch it fall, flow, burn and blow up.

- Fifty-odd elements in tabs: powders, liquids, gases, solids, fire and explosives, plants, machines and creatures.
- Heat: fire, lava and ice change what they touch, so wax melts, water boils and plants burn.
- Electricity: wires, batteries and sparks carry power to whatever is wired up.
- Explosions that throw material around.
- Trees that grow from seeds, a slug that rolls through the world, and zombies.
- A private world for each player that saves itself.
- Shared worlds: friends in the same Activity window paint together and see each other's brushes.
- A gallery for each server: publish a world with a name and a preview, browse, like, and load a copy.
- Glow and backdrop options.
- On an upright phone the tools start in a small sheet that leaves the world more room, with zoom buttons for painting up close.
- Music (four songs) and sound effects, each with its own volume.
- The menu and the people panel show what you are doing, like "Painting" or "In a shared world".
