// The bar's music and sound-effects buttons (M toggles the music), and the same two switches in settings, each with
// its own volume slider under it.
import { onKey } from "../keys.js";
import { addBarButton } from "./bar.js";
import { icon } from "./icons.js";
import { addSlider, addToggle, refreshSettings } from "./settings.js";

/** Adds the music button (bar order 50), the effects button (55) and their settings rows. Returns { refresh } */
export function buildSoundControls(sound) {
  const music = addBarButton({ id: "music", label: "Music", icon: icon("music"), order: 50 });
  const effects = addBarButton({ id: "sound", label: "Sound effects", icon: icon("sound"), order: 55 });

  function show(button, on, label, onIcon, offIcon, key = "") {
    button.replaceChildren(icon(on ? onIcon : offIcon));
    button.setAttribute("aria-pressed", String(on));
    button.setAttribute("aria-label", `${label} ${on ? "on" : "off"}`);
    button.title = `${label}: ${on ? "on" : "off"}${key}`;
  }

  function refresh() {
    show(music, sound.musicOn, "Music", "music", "musicOff", " (M)");
    show(effects, sound.sfxOn, "Sound effects", "sound", "mute");
    refreshSettings();
  }

  function setMusic(on) {
    sound.setMusic(on);
    refresh();
  }

  function setSfx(on) {
    sound.setSfx(on);
    refresh();
  }

  music.addEventListener("click", () => setMusic(!sound.musicOn));
  effects.addEventListener("click", () => setSfx(!sound.sfxOn));
  onKey("m", () => setMusic(!sound.musicOn));
  onKey("M", () => setMusic(!sound.musicOn));
  addToggle("Music", () => sound.musicOn, setMusic);
  addSlider("Music volume", 0, 100, () => sound.musicVolume, (value) => sound.setMusicVolume(value), true);
  addToggle("Sound effects", () => sound.sfxOn, setSfx);
  addSlider("Sound effects volume", 0, 100, () => sound.sfxVolume, (value) => sound.setSfxVolume(value), true);
  refresh();
  return { refresh };
}
