"""
The side program that checks a Starhold run, and the loader it shares with the tests.

The bot never runs a game. To check a score, it starts this file as its own short-lived Python program, hands it the
run's seed and moves on stdin, and reads the result it prints. This file loads the page's own rules files from
web/sim/ into V8 (mini-racer) and replays the run with them, so the check uses exactly the code the player played.

The page loads web/sim/ as ES modules. V8 inside mini-racer runs plain scripts, so the loader wraps each file in a
function and turns its import and export lines into plain variables, without changing the files on disk. The rules
files keep to the shapes it reads: `import { a, b } from "./file.js";` and
`export function|const|class name`, one name per statement. Anything else (`export let`, generators, `export default`,
`export {`, `import *`, imports from outside the folder) stops the load with a ValueError naming the file, as does
importing a name the other file doesn't export. The bundle runs in strict mode, as ES modules always do.

This program must stay importable on its own: the bot starts it in isolated mode, where nothing of the cog is on the
path. It is never imported by the cog itself, so V8 is never loaded into the bot's process.
"""

import json
import re
import sys
from pathlib import Path

from py_mini_racer import MiniRacer

SIM = Path(__file__).resolve().parents[1] / "web" / "sim"
IMPORT = re.compile(r'^import \{([^}]*)\} from "\./([\w-]+)\.js";[ \t]*$', re.M)
EXPORT = re.compile(r"^export (?=(?:async )?(?:function|const|class) +[A-Za-z_$])", re.M)
EXPORTED = re.compile(r"^export (?:async )?(?:function|const|class) +([A-Za-z_$][\w$]*)", re.M)
LEFTOVER = re.compile(r"^[ \t]*(?:import|export)\b.*$", re.M)


def module_name(stem: str) -> str:
    return "m_" + stem.replace("-", "_")


def read_folder(sim: Path) -> dict[str, str]:
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(sim.glob("*.js"))}


def order(texts: dict[str, str], sim: Path) -> list[str]:
    """Every file, each after the files it imports. A loop of imports can't be ordered"""
    done: list[str] = []
    visiting: set[str] = set()

    def visit(stem: str, importer: str) -> None:
        if stem in done:
            return
        if stem == importer:
            raise ValueError(f"{stem}.js imports itself")
        if stem in visiting:
            raise ValueError(f"{stem}.js imports itself through other files")
        if stem not in texts:
            raise ValueError(f"{importer}.js imports {stem}.js, which isn't in {sim}")
        visiting.add(stem)
        for _, needed in IMPORT.findall(texts[stem]):
            visit(needed, stem)
        visiting.discard(stem)
        done.append(stem)

    for stem in texts:
        visit(stem, "")
    return done


def check_imports(texts: dict[str, str]) -> None:
    """A real module refuses to load when it imports a name the other file doesn't export; so does the loader"""
    exports = {stem: set(EXPORTED.findall(text)) for stem, text in texts.items()}
    for stem, text in texts.items():
        for names, needed in IMPORT.findall(text):
            for name in (part.strip().split(" as ")[0].strip() for part in names.split(",")):
                if name and name not in exports[needed]:
                    raise ValueError(f"{stem}.js imports {name} from {needed}.js, which doesn't export it")


def plain_import(match: re.Match) -> str:
    names = [part.strip().replace(" as ", ": ") for part in match.group(1).split(",") if part.strip()]
    return f"const {{ {', '.join(names)} }} = {module_name(match.group(2))};"


def wrap(stem: str, text: str) -> str:
    """One file as a plain script: its imports read from the files before it, its exports returned"""
    exported = EXPORTED.findall(text)
    body = EXPORT.sub("", IMPORT.sub(plain_import, text))
    leftover = LEFTOVER.search(body)
    if leftover:
        raise ValueError(f"{stem}.js: the loader can't read {leftover.group(0).strip()!r}")
    return f"const {module_name(stem)} = (() => {{\n{body}\nreturn {{ {', '.join(exported)} }};\n}})();\n"


def bundle(sim: Path = SIM) -> str:
    """The whole folder as one script that leaves every file's exports on globalThis.sim"""
    texts = read_folder(sim)
    stems = order(texts, sim)
    check_imports(texts)
    parts = [wrap(stem, texts[stem]) for stem in stems]
    exposed = ", ".join(f"{stem.replace('-', '_')}: {module_name(stem)}" for stem in texts)
    return '"use strict";\n' + "".join(parts) + f"globalThis.sim = {{ {exposed} }};\n"


def load(sim: Path = SIM) -> MiniRacer:
    ctx = MiniRacer()
    ctx.eval(bundle(sim))
    return ctx


def check(ctx: MiniRacer, data: dict) -> dict:
    """Replay a run: the rules' own check(), given the seed, the moves and the step to stop at"""
    return json.loads(ctx.eval(f"JSON.stringify(sim.replay.check({json.dumps(data)}))"))


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
        result = check(load(), {"seed": data["seed"], "moves": data["moves"], "end": data["end"]})
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
