// Every number Starhold plays with, and the map. Times are in steps (30 a second), distances and ranges in map
// units, speeds in hundredths of a map unit a step. Tuning happens here and nowhere else.

export const STEPS = 30;

// Move kinds, as the page sends them and the bot stores them: [step, kind, ...details]
export const BUILD = 0; // [step, 0, spot, tower]
export const UPGRADE = 1; // [step, 1, spot]
export const FORM = 2; // [step, 2, spot, which]
export const SELL = 3; // [step, 3, spot]
export const PARK = 4; // [step, 4, spot, road distance in map units]
export const CALL = 5; // [step, 5]
export const STRIKE = 6; // [step, 6, x, y]
export const STASIS = 7; // [step, 7, x, y]

export const START = { money: 250, lives: 20, countdown: 600 };

export const WAVES = {
  countdown: 370, // after a wave's last entry
  callBonus: 4, // money per whole second left on the countdown
  base: 6, // wave N has base + N robots
  most: 60,
  growth: 111, // percent: health grows 11% a wave, compounding
  entryGap: 18, // 0.6 s between entries
  bunchGap: 4, // between the Skitters of one bunch
  bossEvery: 10,
};

// Robot types, by index
export const SCRAPPER = 0;
export const SKITTER = 1;
export const BUZZER = 2;
export const BRUTE = 3;
export const SPLITTER = 4;
export const COLOSSUS = 5;

// hp is at wave 1. bite is damage to a Drone bay's drones while it stands in their pile, every DRONE.every steps.
// from is the first wave it comes in
export const ROBOTS = [
  {
    key: "scrapper",
    name: "Scrapper",
    hp: 40,
    speed: 120,
    lives: 1,
    points: 1,
    bounty: 6,
    from: 1,
    weight: 1,
    bite: 8,
  },
  {
    key: "skitter",
    name: "Skitter",
    hp: 15,
    speed: 240,
    lives: 1,
    points: 1,
    bounty: 3,
    from: 3,
    weight: 1,
    bite: 4,
    bunch: 3,
  },
  {
    key: "buzzer",
    name: "Buzzer",
    hp: 50,
    speed: 160,
    lives: 1,
    points: 2,
    bounty: 10,
    from: 6,
    weight: 1,
    bite: 0,
    flies: true,
  },
  {
    key: "brute",
    name: "Brute",
    hp: 200,
    speed: 60,
    lives: 2,
    points: 4,
    bounty: 20,
    from: 9,
    weight: 1,
    bite: 25,
    armored: true,
  },
  {
    key: "splitter",
    name: "Splitter",
    hp: 90,
    speed: 100,
    lives: 1,
    points: 2,
    bounty: 12,
    from: 12,
    weight: 1,
    bite: 10,
    splits: 3,
  },
  {
    key: "colossus",
    name: "Scrap Colossus",
    hp: 3000,
    speed: 40,
    lives: 5,
    points: 50,
    bounty: 200,
    from: 0, // never drawn for a mix: it comes every WAVES.bossEvery waves
    weight: 0,
    bite: 100,
    armored: true,
    boss: true,
    drops: 90, // a Skitter every 3 s while it walks
  },
];

// Tower kinds, by index
export const BLASTER = 0;
export const MISSILE = 1;
export const TESLA = 2;
export const DRONES = 3;

// levels[0..2] are levels 1 to 3; forms[0..1] are the two final forms. cost is the price of that step.
// every is steps between shots; air is whether it can hit flying robots; armor is whether armored robots halve it
export const TOWERS = [
  {
    key: "blaster",
    name: "Blaster",
    air: true,
    armor: true,
    levels: [
      { cost: 70, damage: 8, every: 12, range: 160 },
      { cost: 90, damage: 14, every: 12, range: 180 },
      { cost: 130, damage: 22, every: 12, range: 200 },
    ],
    forms: [
      { key: "gatling", name: "Gatling", cost: 200, damage: 18, every: 4, range: 200 },
      { key: "railgun", name: "Railgun", cost: 200, damage: 120, every: 45, range: 300, beam: 12 },
    ],
  },
  {
    key: "missile",
    name: "Missile pod",
    air: false,
    armor: true,
    levels: [
      { cost: 120, damage: 30, blast: 60, every: 60, range: 200 },
      { cost: 160, damage: 50, blast: 60, every: 60, range: 220 },
      { cost: 220, damage: 80, blast: 70, every: 60, range: 240 },
    ],
    forms: [
      { key: "swarm", name: "Swarm", cost: 300, damage: 25, missiles: 6, blast: 40, every: 60, range: 240 },
      { key: "mortar", name: "Mortar", cost: 300, damage: 220, blast: 100, every: 90, range: 340, flight: 36 },
    ],
  },
  {
    key: "tesla",
    name: "Tesla coil",
    air: true,
    armor: false,
    levels: [
      { cost: 100, damage: 20, chain: 2, every: 30, range: 130 },
      { cost: 140, damage: 34, chain: 3, every: 30, range: 145 },
      { cost: 200, damage: 52, chain: 4, every: 30, range: 160 },
    ],
    forms: [
      { key: "storm", name: "Storm", cost: 280, damage: 60, chain: 8, every: 30, range: 170 },
      {
        key: "disruptor",
        name: "Disruptor",
        cost: 280,
        damage: 55,
        chain: 4,
        slow: 40,
        slowFor: 60,
        every: 30,
        range: 170,
      },
    ],
  },
  {
    key: "drones",
    name: "Drone bay",
    air: false,
    armor: false,
    levels: [
      { cost: 90, hp: 60, damage: 6 },
      { cost: 120, hp: 110, damage: 10 },
      { cost: 170, hp: 170, damage: 15 },
    ],
    forms: [
      { key: "guardians", name: "Guardians", cost: 250, hp: 400, damage: 15, heal: 20 },
      { key: "strikers", name: "Strikers", cost: 250, hp: 220, damage: 40 },
    ],
  },
];

export const SELL_BACK = 70; // percent of everything spent
export const CHAIN_JUMP = 80; // a Tesla zap jumps to robots this close to the last one
export const MISSILE_SPEED = 600; // hundredths a step: 180 map units a second
export const MIN_FLIGHT = 4;

// count drones per bay; every steps between blows; back is the wait after a drone is destroyed; reach is how far
// from the bay its parking point may be; grab is how far short of the parking point the wall stops robots, and how
// close to it a robot must stand to be in the pile; drain is the steps between robots leaving a pile that was let go,
// so they walk on one by one rather than as one heap
export const DRONE = { count: 3, every: 30, back: 300, reach: 160, grab: 20, drain: 15 };

export const POWERS = {
  strike: { delay: 30, radius: 90, base: 150, perWave: 30, cooldown: 1350 },
  stasis: { radius: 110, length: 120, cooldown: 1800, bossSpeed: 50 },
};

// Every road segment runs straight across or straight up or down, so every length is a whole number. The road
// starts above the top edge so robots walk in: a long straight, a tight hairpin back up, down the right side, a loop
// round the crater in the middle, and a last run to the reactor core. The pads sit about 95 map units off the road at
// its bends, so most reach two stretches of road; the one inside the loop (260, 740) reaches three
export const MAP = {
  width: 720,
  height: 1280,
  road: [
    [100, -40],
    [100, 310],
    [290, 310],
    [290, 120],
    [480, 120],
    [480, 420],
    [620, 420],
    [620, 640],
    [110, 640],
    [110, 840],
    [600, 840],
    [600, 1000],
    [240, 1000],
    [240, 1110],
  ],
  core: [240, 1110],
  spots: [
    [195, 215],
    [385, 215],
    [575, 270],
    [380, 370],
    [525, 530],
    [600, 740],
    [260, 740],
    [450, 740],
    [150, 930],
    [300, 920],
    [500, 920],
    [380, 1110],
  ],
  backdrop: "art/moon.webp",
};
