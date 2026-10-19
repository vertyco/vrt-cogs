// Every fixed number the simulation plays with, in ticks, beats and L units.
// A tick is 1/60 s. A beat is 1/1000 of a tick. L is 1/1200 of an original unit.
// Seconds became ticks once with secondsToTicks (floor(s * 60 + 0.5)); the seconds are in each comment.
// common/sim/numbers.py holds the same names with the same values.

export const TICKS_PER_SECOND = 60;
export const BEATS_PER_TICK = 1000;
export const L_PER_UNIT = 1200;

// The original's fire timer slack, 0.0001 s (ShootersOffenseController$$TickShooter, RVA 0x5451A88)
export const FIRE_SLACK_BEATS = 6;
// At most this many shots from one pig in one tick (same method)
export const MAX_SHOTS_PER_TICK = 16;

// Belt: 5.0 units a second, doubled while the auto-finisher runs (ConveyorController #990 speed)
export const BELT_SPEED = 100;
export const BELT_SPEED_FINISH = 200;
// Tray centers stay minSpacing 0.5 + baseItemLength 0.5 units apart (#990)
export const TRAY_SPACING = 1200;
// A pushed tray moves at most 0.595 units a tick (enforceLerpSpeed 1.0, ConveyorController$$EnforceSpacing)
export const TRAY_PUSH_MAX = 714;

// Shots: 15 units a second for pigs, 30 for the Super Shooter, 60 for the Super Unicorn (ShooterWeapon #11409)
export const SHOT_SPEED = 300;
export const SHOT_SPEED_SUPER = 600;
export const SHOT_SPEED_UNICORN = 1200;
// Hit radius 0.15 units (ProjectilesController$$MoveProjectiles)
export const HIT_RADIUS = 180;
// A line is in range within 0.15 units of the pig (#984 alignTolerance)
export const LINE_TOLERANCE = 180;
// A target's score is distance squared plus 0.01 x the line's offset from the pig, in units
// (ShootersOffenseController$$FindFrontTargetBest, RVA 0x5452184). Scaled by 1,440,000 to work in L: distance squared
// in L squared plus 12 x the offset in L
export const LINE_OFFSET_WEIGHT = 12;
// Each shot does 1 damage and costs 1 ammo (#984 damagePerShot)
export const SHOT_DAMAGE = 1;
// A Conveyor Wall checks a tray 0.25 units before the wall (rejectLeadWorldDistance)
export const CONVEYOR_WALL_LEAD = 300;

// Fire rate: 20.7 shots a second (#984 shotsPerSecond), in milli-shots a second
export const BASE_FIRE_RATE = 20700;
// Fire-speed multiplier in thousandths: 1.0 at 0.3125-unit cubes up to 2.5 at 0.1 (ShootSpeedMultiplier #425)
export const MULT_BASE = 1000;
export const MULT_SPAN = 1500;
export const MULT_FINISH = 2500;
// 0.3125 units and the 0.3125 - 0.1 unit span the multiplier ramps over
export const MULT_SLOW_SIZE = 375;
export const MULT_SIZE_SPAN = 255;
// Beats in a second times 1,000: divided by a rate in milli-shots a second it gives the beats between shots
export const FIRE_INTERVAL_SCALE = 60000000;

// The Demolish bomb's cross: 3 rows and 3 columns through the picked cell, 1 damage each
export const BOMB_SIZE = 3;
export const BOMB_DAMAGE = 1;

// The Super Unicorn's bar fills at FillPercent 90 of the level's cubes over ChargeCount 3 (MergedShooterSettings$$.ctor,
// RVA 0x514C20C)
export const UNICORN_FILL_PERCENT = 90;
export const UNICORN_CHARGE_COUNT = 3;

// Timers in ticks
export const HOP = 15; // 0.25 s hop onto the belt (#48058 jumpDuration)
export const HOP_GAP = 3; // 0.05 s between hops in one batch (#1052)
export const PLACE_WAIT = 1; // one frame between taking pigs out and their first hop (RVA 0x58D7C00)
export const TRAY_START_GAP = 1; // trays of one batch start one frame apart after the last hop (RVA 0x58D7C00)
export const SLOT_GRACE = 9; // 0.15 s before "Out of space" (#1022 gracePeriod)
export const WIN_DELAY = 12; // 0.2 s (object 914 checkCompleteDelay)
export const STUCK_DELAY = 6; // 0.1 s (MapFailController #913)
export const STUCK_INPUT_EXTRA = 12; // 0.2 s more for input-only blocks (#913)
export const REVIVE_DELAY = 12; // 0.2 s (MapRescueController #1051)
export const REVIVE_GAP = 3; // 0.05 s between pigs hopping out (#1051)
export const KEY_FLIGHT = 51; // 0.85 s
export const HAMMER_GAP = 9; // 0.15 s (#1041)
export const MALLET_GAP = 6; // 0.1 s (#1054)
export const STRIKE_LANDS = 51; // 0.85 s (RVA 0x5822274)
export const HAMMER_LIFT = 18; // 0.3 s lift, then a hammer leaves its queue (HammerFeature$$Hit, RVA 0x5822274)
export const HAMMER_DONE = 75; // 1.25 s: the swing and its joined 0.4 s shrink end, the hammer is gone
export const PIXEL_PIPE_REFILL = 4; // 0.07 s (PixelPipeFeature #12008)
export const CUBE_FLY_IN = 18; // 0.3 s (each feature's spawnJumpDuration)
export const DOOR_OPEN = 54; // 0.9 s: an opened Hungry Door's warm-up shake and swing, until it counts as finished
export const SHACKLE_BREAK = 18; // 0.3 s (ChainedShooterVisualizer breakDelay)
export const DUNGEON_WAIT = 24; // 0.4 s (ColoredShooterCageFeature #11609)
export const RESCUE_JUMP = 30; // 0.5 s (#11609)
export const ASTRO_PLACE_JUMP = 60; // 1.0 s (SpaceshipModel)
