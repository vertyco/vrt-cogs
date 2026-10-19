// The original's tables, converted to JSON by the converters in the game's tools folder. The page never hard-codes a
// table the original keeps as data: it reads it from here, under the file's name (data.items, data.actors ...).
import { download } from "./art.js";

export const data = {};

// One name per file in data/. A task that adds a converted file adds its name here
const FILES = ["items", "actors", "world", "rooms", "loadscripts", "story"];

let loading = null;

// Fetches every data file once and fills `data`. The world starts only after dataLoaded() resolves
export function loadData() {
  loading ??= Promise.all(
    FILES.map(async (name) => {
      data[name] = await (await download(`data/${name}.json`)).json();
    }),
  );
  return loading;
}

export function dataLoaded() {
  return loadData();
}
