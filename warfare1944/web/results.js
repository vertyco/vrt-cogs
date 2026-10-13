// How a battle ends on the page: the line and the music when the bot says it ended (endBattle, F6:6804-6932), the
// results screen when it says the battle is over (postBattleScreen, F6:6952-7195), and after the last mission's win
// the newspaper and the campaign stats (showEnding, F6:9858-9910).
//
// The bot decides who won, how, every count and where Continue goes; this page only words and draws them. The results
// are the loading screen's clip (sprite 1528) on its postBattle or endGame frame, over the field, and they stay over
// the next screen while they fade away.
import { clockText } from "./hud.js";
import * as sound from "./sound.js";
import * as tweens from "./tween.js";

const SIDES = ["british", "german"];
const DEPTH_BLACKOUT = 1500000;
const EASE = "easeOutSine";
const LINEAR = "linear";
const CLICK = "sound_interface_click";
const ROLL_OVER = "sound_interface_rollOver";
const CHEER = "sound_cheer";
// The music that plays over the end, once, rising over 10 seconds
const MUSIC_ID = "endBattleMusic";
const WIN_MUSIC = "music_winMusic";
const LOSS_MUSIC = "music_lossMusic";
const MUSIC_LOOPS = 1;
const MUSIC_FADE_IN = 10;
const MUSIC_FADE_OUT = 5;
// The screen fades in over 2 seconds, and the battle under it is taken away once it has (unloadBattle). Continue
// fades it out over 1.2 seconds, and the ending's Main Menu over 1
const FADE_IN = 2;
const FADE_OUT = 1.2;
const ENDING_FADE_OUT = 1;
// The ending's newspaper fades out over 2 seconds when the stats come up
const PAPER_FADE = 2;
// Flash color transforms for a button under the pointer: everything 220 % bright, and back
const BRIGHT = [220, 0, 220, 0, 220, 0, 100, 0];
const NORMAL = [100, 0, 100, 0, 100, 0, 100, 0];
// The numbers' colors on the results screen: the better side's green, the worse side's red (F6:7094-7195)
const GOOD = 10667612;
const BAD = 9323331;
// Each row of the results: the field's name after the side's prefix, the bot's count, and which way is better. A
// higher count is good (1) or bad (-1)
const ROWS = [
  ["enemiesKilled", "kills", 1],
  ["unitsLost", "lost", -1],
  ["unitsDeployed", "deployed", 1],
  ["trenchesTaken", "covers", 1],
  ["supportUsed", "support", -1],
];
const PREFIX = { british: "brit_", german: "german_" };
// What the screen calls each side (the American side is "british" in code and data)
const NAMES = { british: "U.S", german: "GERMAN" };
// The line for each way a battle ends, for the side that won and the side that lost (endBattle, F6:6873-6909). A
// Quit Battle ("surrender") and a versus player leaving ("left") end as a morale loss
const LINES = {
  conquer: { win: "ENEMY GROUND TAKEN, YOU WIN!", loss: "GROUND LOST, YOU HAVE BEEN DEFEATED." },
  objective: { win: "OBJECTIVE COMPLETED! VICTORY!", loss: "OBJECTIVE DESTROYED! YOU HAVE FAILED!" },
  defend: { win: "DEFENCE HELD! YOU WIN!", loss: "WE FAILED TO BREAK THEIR RANKS! OUR ATTACK HAS BEEN DELAYED!" },
  morale: { win: "THE ENEMY HAS SURRENDERED, YOU WIN!", loss: "OUR MEN SURRENDERED, YOU HAVE BEEN DEFEATED." },
};
// The ending's headlines, after the side's name (showEnding, F6:9868-9889)
const HEADLINES = [
  "ARMY LED TO GLORIOUS VICTORY",
  "ARMY CONQUERS ALL",
  "FORCES VICTORIOUS",
  "ARMED FORCES SURGE TO VICTORY",
  "MEN LED TO VICTORY IN EUROPE",
];
// The campaign stats' fields and the career counts they show (F6:9890-9909)
const CAREER = {
  end_soldiersKilled: "soldiersKilled",
  end_soldiersLost: "soldiersLost",
  end_trenchesTaken: "trenchesTaken",
  end_supportUsed: "supportUsed",
  end_wins: "wins",
  end_losses: "losses",
  end_moraleWins: "moraleWins",
  end_moraleLosses: "moraleLosses",
  end_conquerWins: "conquerWins",
  end_conquerLosses: "conquerLosses",
  end_xpGained: "experienceGained",
  end_bonusXPGained: "bonusExpGained",
  end_riflemen: "riflemenDeployed",
  end_assault: "assaultDeployed",
  end_machineGun: "machineGunDeployed",
  end_sniper: "sniperDeployed",
  end_officer: "officerDeployed",
  end_mortarTeam: "mortarTeamDeployed",
  end_bazooka: "bazookaDeployed",
  end_tank: "tankDeployed",
};
// The unnamed buttons of the campaign stats (sprite 1514): Play More Games and Play Warfare 1917, which the port
// removes, and Main Menu
const STATS_PLAY_MORE_DEPTH = 6;
const STATS_PLAY_1917_DEPTH = 54;
const STATS_MAIN_MENU_DEPTH = 47;
// The newspaper's Campaign Stats button (sprite 1526), unnamed in the newspaper's timeline (sprite 1527), which
// brings it up 4 seconds in (the load script on its placement)
const NEWSPAPER_BUTTON_DEPTH = 10;
const NEWSPAPER_BUTTON_FADE = 0.5;
const NEWSPAPER_BUTTON_DELAY = 4;
// Where Continue goes for each of the bot's words. The Watch list and the versus lobby come with the screens that
// show them
const SCREENS = { menu: "main" };

function random(n) {
  return Math.floor(Math.random() * n);
}

// The side a viewer sees the battle from: their own, and a watcher's the one the field and HUD show them
function viewSide(battle) {
  return battle.you ?? battle.map.side;
}

export class Results {
  constructor(field) {
    this.field = field;
    // The clip on show, and the id of the battle it shows the results of
    this.clip = null;
    this.shownId = null;
    this.leaving = false;
    field.onEvent("end", (event, quiet) => this.ended(event, quiet));
    field.onLoad((battle) => this.load(battle));
    field.onClear(() => this.reset());
  }

  get page() {
    return this.field.page;
  }

  // ---------- The end of the fighting ----------

  // endBattle (F6:6804-6932): the cheer, the line in the middle of the screen and the win or loss music. A line that comes after the
  // drawing leapt over its moment still shows, as it lasts for seconds, but its cheer has passed
  ended(event, quiet) {
    const battle = this.field.battle;
    if (!battle) {
      return;
    }
    const won = SIDES[event[2]] === viewSide(battle);
    const lines = LINES[event[3]] ?? LINES.morale;
    if (!quiet) {
      sound.play(CHEER);
    }
    this.page.quickMessage(lines[won ? "win" : "loss"], "center").catch((e) => {
      console.warn("Warfare 1944: couldn't show the end line", e);
    });
    sound.playMusic(won ? WIN_MUSIC : LOSS_MUSIC, MUSIC_ID, MUSIC_LOOPS, MUSIC_FADE_IN);
  }

  // ---------- The battle being over ----------

  // A battle joined after it ended comes with its result, shown at once
  load(battle) {
    if (battle.result && !this.leaving) {
      this.show(battle.result);
    }
  }

  // The bot's word that the battle is over. With no result (the battle was stopped) there is nothing to show, and the
  // player goes to the main menu and a watcher back to the Watch list
  over(over) {
    if (!over.result) {
      this.page.show(this.field.battle?.you === null ? "watch" : "main");
      return;
    }
    this.show(over.result);
  }

  reset() {
    this.shownId = null;
    if (!this.leaving) {
      this.clip?.destroy({ children: true });
      this.clip = null;
    }
  }

  show(result) {
    const battle = this.field.battle;
    if (!battle || this.shownId === battle.id) {
      return;
    }
    this.shownId = battle.id;
    this.leaving = false;
    const clip = this.page.attach("loadScreen", DEPTH_BLACKOUT, "results");
    this.clip = clip;
    clip.alpha = 0;
    const side = viewSide(battle);
    if (result.next === "ending") {
      this.buildEnding(clip, side);
    } else {
      this.buildResults(clip, battle, result, side);
    }
    // The picture covers the battle, and takes the presses so nothing under it hears them
    const bg = clip.child("bg");
    bg.gotoAndStop(side);
    bg.useHandCursor = false;
    bg.setHandler("onRelease", () => {});
    tweens.alphaTo(clip, 100, FADE_IN, EASE, 0, () => this.field.unload());
  }

  // ---------- The results screen ----------

  // postBattleScreen: the heading, both sides' numbers, the bonus XP and Continue
  buildResults(clip, battle, result, side) {
    clip.gotoAndStop("postBattle");
    const won = result.winner === side;
    clip.child("teamVictory").text = `${NAMES[side]} ${won ? "VICTORY!" : "DEFEAT!"}`;
    // The link to the original site's guide is gone
    clip.child("hints").visible = false;
    clip.child("missionTime").text = clockText(result.seconds);
    // Only a campaign player's win or loss counts toward XP, so Custom Battle, versus and a watcher see no bonus
    if (battle.kind === "campaign" && battle.you) {
      clip.child("bonusXP").text = `BONUS XP: ${result.bonus_xp}`;
    } else {
      clip.child("bonusXP").text = "";
      clip.child("XPnote").visible = false;
    }
    this.fillNumbers(clip, result.stats);
    const button = clip.child("continueButton");
    button.child("buttonText").text = "CONTINUE";
    this.wireButton(button, () => this.proceed(result.next));
  }

  fillNumbers(clip, stats) {
    for (const [name, key, direction] of ROWS) {
      const [british, german] = SIDES.map((side) => stats[side][key]);
      for (const side of SIDES) {
        clip.child(PREFIX[side] + name).text = stats[side][key];
      }
      if (british === german) {
        continue;
      }
      const higher = british > german ? "british" : "german";
      const lower = higher === "british" ? "german" : "british";
      tweens.colorTo(clip.child(PREFIX[higher] + name), direction > 0 ? GOOD : BAD);
      tweens.colorTo(clip.child(PREFIX[lower] + name), direction > 0 ? BAD : GOOD);
    }
  }

  // The button's brightening under the pointer (continueButton's rollover in postBattleScreen)
  wireButton(button, press) {
    button.setHandler("onRollOver", () => {
      sound.play(ROLL_OVER);
      tweens.colorTransformTo(button, ...BRIGHT, 0.4, EASE);
    });
    button.setHandler("onRollOut", () => tweens.colorTransformTo(button, ...NORMAL, 0.6, EASE));
    button.setHandler("onRelease", press);
  }

  // Continue (postBattleScreen): the music fades, the screen fades away over the next screen, and the bot's word says
  // which screen that is
  proceed(next) {
    if (this.leaving) {
      return;
    }
    sound.play(CLICK);
    sound.stopMusic(MUSIC_ID, MUSIC_FADE_OUT);
    this.leaveFor(SCREENS[next] ?? next, FADE_OUT, EASE);
  }

  // The screen goes to the next one at once and fades away over it
  leaveFor(name, seconds, ease) {
    this.leaving = true;
    const page = this.page;
    const clip = this.clip;
    page.battle = null;
    page.show(page.screens[name] ? name : "main");
    tweens.alphaTo(clip, 0, seconds, ease, 0, () => {
      clip.destroy({ children: true });
      if (this.clip === clip) {
        this.clip = null;
        this.leaving = false;
      }
    });
  }

  // ---------- The ending ----------

  // showEnding: a newspaper with a headline, then the campaign stats
  buildEnding(clip, side) {
    clip.gotoAndStop("endGame");
    const ending = clip.child("ending");
    const stats = clip.child("campaignStats");
    stats.visible = false;
    ending.child("paper").child("headLine").text = `${NAMES[side]} ${HEADLINES[random(HEADLINES.length)]}`;
    this.fillStats(stats);
    const view = ending.at(NEWSPAPER_BUTTON_DEPTH);
    view.alpha = 0;
    tweens.alphaTo(view, 100, NEWSPAPER_BUTTON_FADE, LINEAR, NEWSPAPER_BUTTON_DELAY);
    view.child("viewStats").child("buttonText").text = "CAMPAIGN STATS";
    view.child("viewStats").setHandler("onRelease", () => this.showStats(ending, stats));
    stats.at(STATS_PLAY_MORE_DEPTH).visible = false;
    stats.at(STATS_PLAY_1917_DEPTH).visible = false;
    const menu = stats.at(STATS_MAIN_MENU_DEPTH);
    menu.child("buttonText").text = "MAIN MENU";
    menu.setHandler("onRelease", () => {
      if (this.leaving) {
        return;
      }
      // The save the original makes here shows its saving icon (saveGame, F6:46-90)
      this.page.savedIcon().catch((e) => {
        console.warn("Warfare 1944: couldn't show the saving icon", e);
      });
      this.leaveFor("main", ENDING_FADE_OUT, LINEAR);
    });
  }

  fillStats(stats) {
    const career = this.page.save?.career ?? {};
    for (const [name, key] of Object.entries(CAREER)) {
      stats.child(name).text = career[key] ?? 0;
    }
  }

  // The newspaper's Campaign Stats button: the music fades, the stats come up under the paper, and the paper fades
  showStats(ending, stats) {
    sound.stopMusic(MUSIC_ID, MUSIC_FADE_OUT);
    this.fillStats(stats);
    stats.visible = true;
    tweens.alphaTo(ending, 0, PAPER_FADE, EASE, 0, () => {
      ending.visible = false;
    });
  }
}
