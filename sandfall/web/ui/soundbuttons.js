// The bar's music and sound-effects buttons (M toggles the music), and the volume slider in settings.
import { onKey } from "../keys.js";
import { addBarButton } from "./bar.js";
import { icon } from "./icons.js";
import { addSlider } from "./settings.js";

/** Adds the music button (bar order 50), the effects button (55) and the volume row. Returns { refresh } */
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
  }

  function flipMusic() {
    sound.setMusic(!sound.musicOn);
    refresh();
  }

  music.addEventListener("click", flipMusic);
  effects.addEventListener("click", () => {
    sound.setSfx(!sound.sfxOn);
    refresh();
  });
  onKey("m", flipMusic);
  onKey("M", flipMusic);
  addSlider("Volume", 0, 100, () => sound.volume, (value) => sound.setVolume(value));
  refresh();
  return { refresh };
}
