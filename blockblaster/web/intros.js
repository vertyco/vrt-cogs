// What the game tells a player the first time: the New Feature popup of each level feature, the popup that unlocks each
// booster, and the tutorial lines. Words are the original's strings (`Level Features String Table`, the booster string
// tables and `Tutorial String Table`), with every pig a cat ("piggy" is "kitty"). In a line, **double stars** mark the
// words the original colors blue.

// The first level of each feature, which is where its popup shows (feature number to level number)
export const FEATURE_FIRST = {
  1: 8,
  2: 14,
  3: 30,
  4: 40,
  5: 55,
  6: 70,
  7: 85,
  8: 100,
  9: 120,
  10: 140,
  11: 171,
  12: 200,
  13: 230,
  14: 290,
  15: 350,
  16: 400,
  17: 500,
  18: 600,
  19: 700,
  20: 801,
  21: 901,
  22: 1001,
  23: 1101,
  24: 1201,
  25: 1301,
  26: 1401,
  27: 1501,
  28: 1601,
  29: 1701,
  30: 1801,
  31: 1901,
  32: 2001,
  33: 2201,
  34: 2401,
};

const FEATURES = "art/features/FeatureImage_";

// Feature number to its popup: the picture, the name and the one line under it
export const INTROS = {
  1: { picture: `${FEATURES}SurpriseShooter.png`, name: "Surprise Cat", line: "Cat with hidden features!" },
  2: { picture: `${FEATURES}ConnectedShooter.png`, name: "Connected Cat", line: "They move together!" },
  3: { picture: `${FEATURES}HardPixel.png`, name: "Hard Pixels", line: "Takes more hits to destroy!" },
  4: { picture: `${FEATURES}LockandKey.png`, name: "Locks and Keys", line: "Release keys to open locks!" },
  5: { picture: `${FEATURES}Gate.png`, name: "Gate", line: "Shoot it to pull back the gate!" },
  6: {
    picture: `${FEATURES}PixelPipe.png`,
    name: "Pixel Pipe",
    line: "Replaces pixels when they are destroyed!",
  },
  7: {
    picture: `${FEATURES}SurprisePixel.png`,
    name: "Surprise Pixel",
    line: "Expose them to reveal its color!",
  },
  8: { picture: `${FEATURES}Snake.png`, name: "Snake", line: "Return the snake to its nest by shooting!" },
  9: { picture: `${FEATURES}Wall.png`, name: "Wall", line: "Blocks the cats sight." },
  10: { picture: `${FEATURES}EggBox.png`, name: "Egg Box", line: "Shoot the eggs to crack them all!" },
  11: { picture: `${FEATURES}ShooterPipe.png`, name: "Cat Pipe", line: "Rescue all the cats inside!" },
  12: {
    picture: `${FEATURES}IceBlock.png`,
    name: "Ice Blocks",
    line: "Shatter ice blocks by destroying pixels!",
  },
  13: {
    picture: `${FEATURES}WoodHammer.png`,
    name: "Woods and Hammers",
    line: "Push hammers to first place to break wood blocks!",
  },
  14: {
    picture: `${FEATURES}FrozenShooter.png`,
    name: "Frozen Cat",
    line: "Deplete other cats to shatter their ice!",
  },
  15: {
    picture: `${FEATURES}ColorDoor.png`,
    name: "Hungry Door",
    line: "Feed the door with the same color pixels!",
  },
  16: { picture: `${FEATURES}Biscuit.png`, name: "Biscuit", line: "Blow up fruits, melt creams, crack biscuits!" },
  17: {
    picture: `${FEATURES}Rocket.png`,
    name: "Rocket",
    line: "Shoot the rocket parts to fuse them! The light path blocks shooting.",
  },
  18: {
    picture: `${FEATURES}Ufo.png`,
    name: "U.F.O.",
    line: "Cats love to sit on their colored seats and fly away!",
  },
  19: {
    picture: `${FEATURES}Pumpkin.png`,
    name: "Pumpkin",
    line: "Plump, colorful pumpkins ready to be shot!",
  },
  20: {
    picture: `${FEATURES}Shackles.png`,
    name: "Shackles",
    line: "Set the cats free when they reach first in line!",
  },
  21: {
    picture: `${FEATURES}Curtain.png`,
    name: "Curtain",
    line: "Pull up the curtains to reveal what's underneath!",
  },
  22: { picture: `${FEATURES}PigCell.png`, name: "Cat Cell", line: "Rescue the cat from the cell!" },
  23: {
    picture: `${FEATURES}Dragon.png`,
    name: "Dragon",
    line: "Shoot the different colored scales to shrink the dragon!",
  },
  24: { picture: `${FEATURES}JellyBeans.png`, name: "Jelly Beans", line: "Pop the beans and clear the box!" },
  25: {
    picture: `${FEATURES}BullTotem.png`,
    name: "Bull Totem",
    line: "Move the totem to the front, then send kitties to chip away at it until it breaks!",
  },
  26: {
    picture: `${FEATURES}MusicToy.png`,
    name: "Music Toy",
    line: "Push mallets to first place to hit and break the music notes!",
  },
  27: {
    picture: `${FEATURES}Crossbow.png`,
    name: "Crossbow",
    line: "Shoot the crossbow to fire the arrow and clear the pixels in front!",
  },
  28: {
    picture: `${FEATURES}Accordion.png`,
    name: "Scissors Gate",
    line: "Collect pixels to rotate the gear and open the gate!",
  },
  29: {
    picture: `${FEATURES}ColoredShooterCage.png`,
    name: "Dungeon",
    line: "Blast the dungeon apart and rescue the cat trapped inside!",
  },
  30: {
    picture: `${FEATURES}SlotCage.png`,
    name: "Slot Cage",
    line: "Collect pixels to blast the door open and unlock the blocked slot!",
  },
  31: {
    picture: `${FEATURES}Matryoshka.png`,
    name: "Catroshka",
    line: "Shoot the cat dolls nested inside one another to open them!",
  },
  32: {
    picture: `${FEATURES}AstroPig.png`,
    name: "Astro Cat",
    line: "Shoot with the cat with astro suit and place it to the spaceship!",
  },
  33: {
    picture: `${FEATURES}ConveyorWall.png`,
    name: "Conveyor Wall",
    line: "Pass walls with same color cats to destroy the walls!",
  },
  34: {
    picture: `${FEATURES}PixelMixer.png`,
    name: "Pixel Mixer",
    line: "Collect matching pixels to drain the mixer and free the pixels under its hose!",
  },
};

const ICONS = "art/ui/IconPowerup_";

// Booster name (as in the bot's progress) to its unlock popup: the big picture, the name and the line
export const BOOSTER_INTROS = {
  tray: { icon: `${ICONS}ExtraSlot_Colored.png`, name: "Add Tray", line: "Add extra tray to conveyor!" },
  hand: { icon: `${ICONS}Hand_Colored.png`, name: "Hand", line: "Pick any cat or item in the queue." },
  shuffle: { icon: `${ICONS}Shuffle_Colored.png`, name: "Shuffle", line: "Shuffle the cats in queues!" },
  super: {
    icon: `${ICONS}SuperShooter_Colored.png`,
    name: "Super Cat",
    line: "Select a color to shoot with super powers!",
  },
  bomb: { icon: `${ICONS}Bomb_Colored.png`, name: "Demolish", line: "Tap an area to blow up pixels!" },
};

// The tutorial a level opens with, by level number. `id` is what the bot remembers once the player has done it, so it
// never shows again. A step has the `line` the mascot says, the `target` it spotlights ("queue": the first queue's front
// pig; "counter": the free-tray counter; "hand": the Hand's button) and `then`: "tap" waits for a press on the target
// pig, "button" for a press on the target button, "continue" for any press. A step with `pick` leaves the button's booster
// waiting for its pick, with the pick bubble showing until the pick lands or is cancelled.
// A tutorial with `hint` also shows the belt-full line (WAIT_LINE) for the rest of that level.
export const TUTORIALS = {
  1: {
    id: "tutorial-level-1",
    hint: true,
    steps: [{ line: "**Pick a kitty** and start clearing pixels!", target: "queue", then: "tap" }],
  },
  2: {
    id: "tutorial-level-2",
    steps: [{ line: "**Five kitties** can travel on the conveyor at once!", target: "counter", then: "continue" }],
  },
  8: {
    id: "tutorial-hand",
    steps: [{ line: "Tap your **powerup**!", target: "hand", then: "button", pick: true }],
  },
};

// The Hand's first use. Level 8 points at its button ("Tap your powerup!", the original's string); once it is pressed
// the pick bubble shows over the board (panels.js) until the first pick lands or is cancelled
export const HAND_PICK = { name: "HAND", line: BOOSTER_INTROS.hand.line };

// Tutorials that open when something happens in any level, the first time it does. `when(sim)` says it has happened.
// "slot" spotlights the first pig in a slot and waits for a press on it; "slots" the whole row and waits for a press
// on any pig in it.
export const LATER_TUTORIALS = [
  {
    id: "tutorial-slot-tap",
    when: (sim) => sim.slots.some((pig) => pig !== null),
    step: { line: "The kitty has remaining ammo. You can use it!", target: "slot", then: "tap" },
  },
  {
    id: "tutorial-slots-full",
    when: (sim) => sim.slots.every((pig) => pig !== null),
    step: {
      line: "**Slots are full!** Pick a kitty to send back to conveyor or lose!",
      target: "slots",
      then: "tap",
    },
  },
];

// Said, with no overlay, while the belt is full during the first level's tutorial
export const WAIT_LINE = "Wait for shooter to travel.";
