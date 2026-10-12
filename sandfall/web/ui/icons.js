// Small line icons, drawn on a 24 x 24 grid. Each entry is the markup inside the <svg>.
const SVG = "http://www.w3.org/2000/svg";

const GEAR =
  "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 " +
  "1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 " +
  "1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-" +
  ".06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 " +
  "1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 " +
  "1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z";

const PATHS = {
  back: '<path d="M15 5 L8 12 L15 19" />',
  world: '<circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" />',
  pause: '<path d="M8 5v14M16 5v14" />',
  play: '<path d="M7 4.5v15l12-7.5z" />',
  step: '<path d="M6 5v14M10 5l9 7-9 7z" />',
  undo: '<path d="M9 14 4 9l5-5" /><path d="M4 9h10a6 6 0 0 1 0 12h-3" />',
  save: '<path d="M5 3h11l4 4v14H5z" /><path d="M8 3v6h7V3M8 21v-7h8v7" />',
  gallery:
    '<rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="m3 17 5-4 4 3 3-2 6 4" />',
  music: '<path d="M9 18V5l11-2v13" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="17.5" cy="16" r="2.5" />',
  musicOff:
    '<path d="M9 18V5l11-2v13" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="17.5" cy="16" r="2.5" /><path d="M3 3l18 18" />',
  sound: '<path d="M4 9v6h4l5 4V5L8 9z" /><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12" />',
  mute: '<path d="M4 9v6h4l5 4V5L8 9z" /><path d="m17 9 5 6M22 9l-5 6" />',
  gear: `<circle cx="12" cy="12" r="3" /><path d="${GEAR}" />`,
  help: '<circle cx="12" cy="12" r="9" /><path d="M9.5 9.2a2.6 2.6 0 1 1 3.6 2.4c-.8.4-1.1.9-1.1 1.9M12 17h.01" />',
  heart: '<path d="M12 20.5S3.5 15 3.5 8.9A4.4 4.4 0 0 1 12 7a4.4 4.4 0 0 1 8.5 1.9C20.5 15 12 20.5 12 20.5z" />',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6" />',
  close: '<path d="M6 6l12 12M18 6 6 18" />',
  chevron: '<path d="m6 9 6 6 6-6" />',
  brush: '<path d="M18.5 3.5 21 6l-9 9-2.5-2.5z" /><path d="M9.5 12.5C7 12.5 5.5 14 5.5 16.2c0 1.5-.9 2.8-2 3.8 3.2.6 6.8-.6 6.8-3.6" />',
  line: '<path d="M5 19 19 5" /><circle cx="5" cy="19" r="1.7" /><circle cx="19" cy="5" r="1.7" />',
  box: '<rect x="4" y="5" width="16" height="14" rx="1.5" stroke-dasharray="3.5 2.5" />',
  fill: '<path d="M5 12.5 12 5.5l7 7-6.2 6.2a2 2 0 0 1-2.8 0z" /><path d="M5 12.5h14M12 5.5 9 2.5" /><path d="M20.5 16c1.2 1.6 1.6 2.6 0 3.2-1.6-.6-1.2-1.6 0-3.2z" />',
  eraser: '<path d="m7 20-3.5-3.5a1.6 1.6 0 0 1 0-2.2L13.6 4.2a1.6 1.6 0 0 1 2.2 0l4 4a1.6 1.6 0 0 1 0 2.2L10.5 20z" /><path d="m8 11.5 5.5 5.5M10.5 20H20" />',
  heat: '<path d="M12 3c.6 3.4 5 5.4 5 10a5 5 0 0 1-10 0c0-2 1-3.4 2.2-4.4.2 1.4.8 2.2 1.6 2.6C10.6 8.4 11.2 5.6 12 3z" />',
  cool: '<path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9" /><path d="m9.5 4.5 2.5 2 2.5-2M9.5 19.5l2.5-2 2.5 2" />',
  shove: '<path d="M3 5v14M7 12h12M14 7l5 5-5 5" />',
  hand: '<path d="M8 12V5.5a1.5 1.5 0 0 1 3 0V11M11 10.5V4.5a1.5 1.5 0 0 1 3 0V11M14 10.5V6a1.5 1.5 0 0 1 3 0v8c0 4-2.5 7-6 7-2.5 0-4-1.3-5.2-3.2L3.5 14a1.5 1.5 0 0 1 2.5-1.6L8 15" />',
  bolt: '<path d="M13 2 5 13.5h6L10 22l8-11.5h-6z" />',
  picker: '<path d="M15 5.5 18.5 9M19.6 4.4a2.1 2.1 0 0 1 0 3L17 10l-3-3 2.6-2.6a2.1 2.1 0 0 1 3 0z" /><path d="m14 7-9.5 9.5V20H8l9.5-9.5" />',
  round: '<circle cx="12" cy="12" r="7" />',
  square: '<rect x="5" y="5" width="14" height="14" rx="1" />',
  spray: '<circle cx="12" cy="12" r="8" stroke-dasharray="1 4.2" /><circle cx="12" cy="12" r=".7" /><circle cx="9" cy="14.5" r=".7" /><circle cx="15" cy="9.5" r=".7" /><circle cx="14.5" cy="14.5" r=".7" />',
  empty: '<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="3.5 3" /><path d="M12 8.5v7M8.5 12h7" />',
  mirror: '<path d="M12 3v18" stroke-dasharray="2 3" /><path d="M9 7 4 12l5 5zM15 7l5 5-5 5z" />',
  search: '<circle cx="11" cy="11" r="6.5" /><path d="m16 16 5 5" />',
  more: '<circle cx="5.5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="18.5" cy="12" r="1.2" />',
  less: '<path d="m6 9 6 6 6-6" />',
};

/** A fresh <svg> for the named icon. The icon takes the text color of the button it sits in */
export function icon(name) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = PATHS[name] ?? "";
  return svg;
}
