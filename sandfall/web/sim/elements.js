// Every element, by id. Saved worlds store these ids, so an id never changes meaning: new elements go on the end.

/** The element tabs, in rail order */
export const TABS = [
  { key: "powders", name: "Powders" },
  { key: "liquids", name: "Liquids" },
  { key: "gases", name: "Gases" },
  { key: "solids", name: "Solids" },
  { key: "energy", name: "Energy" },
  { key: "special", name: "Special" },
  { key: "life", name: "Life" },
  { key: "machines", name: "Machines" },
];

const KINDS = new Map([
  ["powders", "powder"],
  ["liquids", "liquid"],
  ["gases", "gas"],
  ["solids", "solid"],
  ["energy", "energy"],
  ["special", "special"],
  ["life", "life"],
  ["machines", "machine"],
]);

// Made elements (paint: false) only appear as the result of a rule: they are not in the tabs or the spigot lists.
// cond is heat conductivity 0..64. start is the heat a new cell gets (null: 20 when painted, kept when converted).
const MADE = { paint: false };
const THERMITE_BURNS_FOR = 90;
const ACID_FUMES_LAST = 100;
const GAS = { cond: 8 };

// [key, name, tab, color, fields that differ from the defaults]. Colors are the originals' where they read well on the
// dark backdrops, tuned in lightness (same hue) where they looked harsh or vanished into the dark. They are drawing only:
// no rule reads them and they are not part of a saved world or its fingerprint.
const ROWS = [
  ["empty", "Empty", null, [0, 0, 0], { paint: false, cond: 8 }],
  // Powders
  [
    "sand",
    "Sand",
    "powders",
    [238, 204, 128],
    { blurb: "Falls and piles up in cones. Sinks slowly through water." },
  ],
  ["salt", "Salt", "powders", [255, 255, 255], { blurb: "Turns water into salt water. Kills plants and melts ice." }],
  [
    "coloredSand",
    "Colored sand",
    "powders",
    [230, 110, 170],
    { blurb: "Sand in a color you pick. Falls and piles up like sand." },
  ],
  [
    "gunpowder",
    "Gunpowder",
    "powders",
    [157, 134, 110],
    { burns: true, blurb: "Pops in a ring of fire when lit, and the pops chain down a trail of it." },
  ],
  [
    "snow",
    "Snow",
    "powders",
    [240, 248, 255],
    { start: -5, blurb: "Drifts down slowly. Melts into water when it warms up." },
  ],
  ["ash", "Ash", "powders", [90, 90, 95], { blurb: "Left behind by burnt wood and plants. Light and dusty." }],
  [
    "soil",
    "Soil",
    "powders",
    [120, 75, 33],
    { blurb: "Falls straight down and drinks water from above. Wet soil grows trees." },
  ],
  [
    "wetSoil",
    "Wet soil",
    "powders",
    [88, 50, 22],
    { ...MADE, blurb: "Soil that drank water. It dries out again, or sometimes grows a tree." },
  ],
  [
    "thermite",
    "Thermite",
    "powders",
    [150, 80, 80],
    { burns: true, blurb: "Burns white hot once lit and melts straight down through almost anything." },
  ],
  [
    "burningThermite",
    "Burning thermite",
    "powders",
    [255, 240, 200],
    {
      ...MADE,
      start: 2500,
      glow: 255,
      init: () => THERMITE_BURNS_FOR,
      blurb: "Lit thermite. Burns at 2,500 degrees for a moment, then turns to ash.",
    },
  ],
  [
    "concrete",
    "Concrete",
    "powders",
    [139, 162, 162],
    { blurb: "Pours like sand, sinks in water, and slowly sets into wall, fastest next to a wall." },
  ],
  [
    "stone",
    "Stone",
    "powders",
    [100, 68, 32],
    { ...MADE, cond: 10, blurb: "Heavy rock that sinks through water and oil. Melts into lava when very hot." },
  ],
  ["rust", "Rust", "powders", [150, 75, 40], { ...MADE, blurb: "Flaky crumbs left when metal rusts." }],
  ["pollen", "Pollen", "powders", [230, 235, 110], { ...MADE, blurb: "Yellow dust shaken off leaves." }],
  // Liquids
  [
    "water",
    "Water",
    "liquids",
    [40, 110, 230],
    { cond: 20, blurb: "Flows and spreads flat. Boils into steam when hot and freezes into ice when cold." },
  ],
  [
    "saltWater",
    "Salt water",
    "liquids",
    [90, 160, 240],
    { cond: 20, blurb: "Heavier than water, so it sinks under it. Boils into steam and leaves salt behind." },
  ],
  [
    "oil",
    "Oil",
    "liquids",
    [128, 64, 64],
    { burns: true, blurb: "Floats on water. Flashes into a cross of flames when fire touches it." },
  ],
  [
    "lava",
    "Lava",
    "liquids",
    [245, 110, 40],
    {
      start: 1200,
      cond: 16,
      glow: 220,
      blurb: "Oozes slowly and glows. Lights what burns, and sets into stone in water or as it cools.",
    },
  ],
  [
    "acid",
    "Acid",
    "liquids",
    [120, 255, 60],
    { blurb: "Eats most things it touches and wears itself away doing it. Glass holds it." },
  ],
  [
    "honey",
    "Honey",
    "liquids",
    [255, 180, 30],
    { burns: true, blurb: "Thick and slow, a quarter as fast as water. Burns very slowly." },
  ],
  [
    "nitro",
    "Nitro",
    "liquids",
    [52, 118, 6],
    { burns: true, blurb: "Heavy liquid that blows up near fire and throws sparks. Soil next to it charges it." },
  ],
  [
    "chargedNitro",
    "Charged nitro",
    "liquids",
    [245, 98, 78],
    { ...MADE, blurb: "Nitro that met soil. Fire sets it off in a beam straight up." },
  ],
  [
    "napalm",
    "Napalm",
    "liquids",
    [232, 162, 30],
    { burns: true, blurb: "Sticky fuel. Fire makes it throw rising fireballs." },
  ],
  [
    "cryo",
    "Cryo",
    "liquids",
    [0, 213, 255],
    { start: -200, blurb: "Liquid cold. Freezes water and ice into chilled ice, and sets lava into stone." },
  ],
  [
    "moltenGlass",
    "Molten glass",
    "liquids",
    [255, 170, 90],
    { ...MADE, glow: 160, blurb: "Glowing liquid glass. Cools into glass." },
  ],
  [
    "moltenMetal",
    "Molten metal",
    "liquids",
    [255, 200, 150],
    { ...MADE, glow: 180, blurb: "Glowing liquid metal. Cools back into metal." },
  ],
  [
    "liquidWax",
    "Liquid wax",
    "liquids",
    [238, 221, 205],
    { ...MADE, cond: 2, blurb: "Melted wax. Sets again where it lands." },
  ],
  // Gases
  [
    "steam",
    "Steam",
    "gases",
    [195, 214, 235],
    { ...GAS, start: 110, blurb: "Rises fast. Cools back into water, or rains out under a ceiling." },
  ],
  [
    "smoke",
    "Smoke",
    "gases",
    [112, 112, 112],
    { ...GAS, blurb: "Drifts up from burning wood and plants, then fades.", init: (w, i, d) => 60 + d.roll(141) },
  ],
  [
    "methane",
    "Methane",
    "gases",
    [140, 150, 140],
    { ...GAS, burns: true, blurb: "A faint gas that drifts up through anything. Burns in a quick fireball." },
  ],
  [
    "acidFumes",
    "Acid fumes",
    "gases",
    [170, 255, 120],
    {
      ...GAS,
      ...MADE,
      init: () => ACID_FUMES_LAST,
      blurb: "A puff from acid. Fades fast and kills the plants and leaves it touches.",
    },
  ],
  // Solids
  [
    "wall",
    "Wall",
    "solids",
    [128, 128, 128],
    { cond: 4, blurb: "Stays where you put it. Build cups, floors and dams with it." },
  ],
  [
    "wood",
    "Wood",
    "solids",
    [130, 90, 50],
    { cond: 4, burns: true, blurb: "Burns for a while when fire touches it, leaving ash and smoke." },
  ],
  [
    "metal",
    "Metal",
    "solids",
    [160, 165, 175],
    {
      cond: 60,
      blurb: "Carries heat and electricity. Melts when very hot, and slowly rusts in water, faster in salt water.",
    },
  ],
  [
    "glass",
    "Glass",
    "solids",
    [200, 230, 240],
    { blurb: "See-through. Acid cannot eat it. Melts back into liquid glass when very hot." },
  ],
  [
    "ice",
    "Ice",
    "solids",
    [161, 232, 255],
    { start: -20, cond: 16, blurb: "Melts into water when warm, or next to fire, steam or salt." },
  ],
  [
    "chilledIce",
    "Chilled ice",
    "solids",
    [20, 153, 220],
    { ...MADE, cond: 16, blurb: "Made by cryo. Creeps through nearby water, then thaws into ice." },
  ],
  [
    "wax",
    "Wax",
    "solids",
    [238, 221, 204],
    {
      burns: true,
      cond: 2,
      blurb: "Burns slowly and drips. A flame on a block of wax never goes out, so it makes a candle.",
    },
  ],
  [
    "c4",
    "C-4",
    "solids",
    [250, 242, 156],
    { burns: true, blurb: "Hangs in the air until fire touches it, then goes off in a huge fireball." },
  ],
  [
    "fuse",
    "Fuse",
    "solids",
    [128, 2, 1],
    { burns: true, blurb: "Fire races along a line of it in a flash. Use it to light things from far away." },
  ],
  [
    "plant",
    "Plant",
    "solids",
    [56, 186, 64],
    { burns: true, blurb: "Grows through water, and only water. Burns. The ??? wave cannot touch it." },
  ],
  [
    "branch",
    "Branch",
    "solids",
    [166, 128, 100],
    { ...MADE, burns: true, blurb: "The woody part of a tree. Burns slowly into ash." },
  ],
  [
    "leaf",
    "Leaf",
    "solids",
    [82, 107, 45],
    { ...MADE, burns: true, blurb: "The green part of a tree, sometimes in pink or white blossom. Burns, dies in salt, and drops pollen." },
  ],
  // Energy
  [
    "fire",
    "Fire",
    "energy",
    [255, 64, 64],
    { start: 600, cond: 24, glow: 200, blurb: "Climbs and flickers. Burns anything that burns, and boils water." },
  ],
  [
    "torch",
    "Torch",
    "energy",
    [245, 75, 15],
    { glow: 180, blurb: "Never goes out. Sets fire to everything next to it, even walls." },
  ],
  [
    "spark",
    "Spark",
    "energy",
    [255, 240, 120],
    { glow: 255, blurb: "Paint it on metal to send a pulse of electricity along it. Anywhere else it is just a flash of fire." },
  ],
  [
    "battery",
    "Battery",
    "energy",
    [230, 200, 60],
    { blurb: "Never moves. Every moment it sends a pulse of electricity into the metal touching it." },
  ],
  // Special
  [
    "wave",
    "???",
    "special",
    [255, 0, 255],
    { blurb: "A wave that eats everything, walls too, but never plants. It leaves a trail of red dust." },
  ],
  ["redDust", "Red dust", "special", [220, 40, 40], { ...MADE, blurb: "The trail the ??? wave leaves. Fades away." }],
  [
    "mystery",
    "Mystery",
    "special",
    [162, 232, 196],
    {
      blurb:
        "Falls like sand. Next to sand it paints a star across the world, next to salt a spiral, next to fire it scrambles everything, and next to pollen it goes off like a nuke.",
    },
  ],
  // Life
  [
    "seed",
    "Seed",
    "life",
    [150, 110, 60],
    { blurb: "Falls and waits. On wet soil it grows a tree. Dropped in water it becomes a plant." },
  ],
  [
    "bug",
    "Bug",
    "life",
    [82, 62, 42],
    {
      burns: true,
      // Heading is a random 0 or 1 (walking right): the layout is described at the top of rules/life.js
      init: (w, i, d) => d.roll(2),
      blurb: "Crawls over any surface and eats plants, leaves and honey. Fed enough, it lays more. Drowns in water.",
    },
  ],
  [
    "fish",
    "Fish",
    "life",
    [255, 150, 60],
    { blurb: "Darts about in water and eats bugs that fall in. On dry land it flops for a while, then dies." },
  ],
  [
    "firefly",
    "Firefly",
    "life",
    [230, 255, 120],
    {
      burns: true,
      glow: 140,
      // A random heading, a random turning side and a 1 in 3 chance of being able to lay (rules/life.js)
      init: (w, i, d) => d.roll(8) | (d.roll(2) << 3) | (d.roll(3) === 0 ? 16 : 0),
      blurb: "Drifts through the air in loops and glows. Lays more near plants. Gone in water or fire.",
    },
  ],
  // Machines
  [
    "spout",
    "Spout",
    "machines",
    [112, 160, 255],
    { blurb: "Weeps water on every free side, forever. A grain of sand slowly turns it into sand." },
  ],
  ["well", "Well", "machines", [100, 34, 34], { blurb: "Seeps oil on every free side, forever." }],
  ["gasVent", "Gas vent", "machines", [84, 104, 88], { blurb: "Leaks methane on every free side, forever." }],
  [
    "cloner",
    "Cloner",
    "machines",
    [200, 180, 40],
    { blurb: "Copies the first thing that touches it, then pours out more of it. Erase it to reset." },
  ],
  ["drain", "Drain", "machines", [46, 46, 64], { blurb: "Swallows anything that touches it, except walls and other machines." }],
  [
    "heater",
    "Heater",
    "machines",
    [200, 60, 40],
    { start: 400, cond: 64, blurb: "Always 400 degrees. Boils water and lights wood." },
  ],
  [
    "cooler",
    "Cooler",
    "machines",
    [60, 120, 200],
    { start: -100, cond: 64, blurb: "Always -100 degrees. Freezes water into ice." },
  ],
];

/**
 * Indexed by id: { id, key, name, tab, kind, color, start, cond, burns, paint, glow, blurb, init }.
 * init(w, i, d), when set, gives a new cell its life value.
 */
export const ELEMENTS = ROWS.map(([key, name, tab, color, fields], id) => ({
  id,
  key,
  name,
  tab,
  kind: tab === null ? "empty" : KINDS.get(tab),
  color,
  start: null,
  cond: 6,
  burns: false,
  paint: true,
  glow: 0,
  blurb: "",
  init: null,
  ...fields,
}));

export const ELEMENT_COUNT = ELEMENTS.length;

/** Element id by key: EL.sand === 1 */
export const EL = Object.freeze(Object.fromEntries(ELEMENTS.map((e) => [e.key, e.id])));
