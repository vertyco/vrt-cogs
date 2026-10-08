"""DEVELOPERS.md checked against the code: the messages it quotes, and its code samples"""

import ast
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

HUB = Path(__file__).resolve().parents[1]
GUIDE = (HUB / "DEVELOPERS.md").read_text(encoding="utf-8")
# Where the hub's own messages live. The vendored Discord SDK is left out, since its text isn't the hub's
PYTHON_SOURCES = [*sorted((HUB / "common").glob("*.py")), *sorted((HUB / "commands").glob("*.py")), HUB / "main.py"]
JS_SOURCES = [HUB / "web" / name for name in ("sdk.js", "host.js", "menu.js")]

# In a message from the code, FIELD is a part filled in when it runs: an f-string or template literal field, or a
# %s log argument. In the guide's text, ANY stands for ..., and OPEN and CLOSE mark an example value like 'x' or <key>
FIELD = "\x00"
ANY = "\x01"
OPEN = "\x02"
CLOSE = "\x03"
EXAMPLE = re.compile(r"<[^<>]*>|(?<![\w'])'[^']+'(?!\w)")
MARKED_EXAMPLE = re.compile(f"{OPEN}[^{CLOSE}]*{CLOSE}")
FORMAT_FIELD = re.compile(r"%[-#0-9.]*[sdrfx]|\{[^{}]*\}")
JS_STRING = re.compile(r"""'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`""")
BACKTICKED = re.compile(r"`([^`]+)`")
# What a row is about rather than what the developer sees: a command, a call or an address
SUBJECT = re.compile(r"\[p\].*|[\w.]+\(\)|/.*")
# Text the guide quotes from the browser or from Python itself, which the hub never prints
NOT_THE_HUBS = (
    "Uncaught",
    "does not provide",
    "coroutine",
    "hub.api is not",
    "ValueError: Out of range",
    '"activityhub"',
)
# How much of the guide's own text has to be the code's own text. Shorter quotes say too little to check
MIN_MATCHED = 12
# How much of the guide's own text one field can stand for: a name or a number, like OtherCog or 413
FIELD_VALUE = 12
FENCE = re.compile(r"^( *)```(\w*)\n(.*?)^\1```$", re.S | re.M)


def python_messages(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Docstrings describe messages rather than send them. The text between an f-string's fields is only part of a
    # message, and on its own it would let a field in another message stand for it
    skip = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Expr)}
    skip |= {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = (FORMAT_FIELD.sub(FIELD, p.value) if isinstance(p, ast.Constant) else FIELD for p in node.values)
            yield "".join(parts)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield FORMAT_FIELD.sub(FIELD, node.value)


def js_messages(path: Path):
    for match in JS_STRING.finditer(path.read_text(encoding="utf-8")):
        text = re.sub(r"\$\{[^}]*\}", FIELD, match[0][1:-1])
        yield text.replace('\\"', '"').replace("\\'", "'")


MESSAGES = {text for path in PYTHON_SOURCES for text in python_messages(path)} | {
    text for path in JS_SOURCES for text in js_messages(path)
}


def guide_pattern(text: str) -> str:
    """The guide's text with ... as ANY, and each example value between OPEN and CLOSE"""
    return EXAMPLE.sub(lambda match: OPEN + match[0] + CLOSE, text.replace("...", ANY))


def own_text(pattern: str) -> str:
    """What the guide wrote itself, without its placeholders and example values"""
    return MARKED_EXAMPLE.sub("", pattern).replace(ANY, "")


def field_value(text: str, at_edge: bool) -> int | None:
    """
    How many characters of the guide's own text a field stands for when it holds this text, or None when it can't.
    A field can hold another of the code's own strings (a part added to the message), example values and
    placeholders on their own, or a short value of the guide's with no space at either end, since the message has
    its own spaces around the field. At the start or end of the quote that value is one word, so a field can't
    swallow the quote's last words while the message's own words after it go unquoted
    """
    held = MARKED_EXAMPLE.sub(FIELD, text).replace(ANY, FIELD)
    if OPEN in held or CLOSE in held:
        # Half an example value
        return None
    value = held.strip(FIELD)
    size = len(held.replace(FIELD, ""))
    if value in MESSAGES or size == 0:
        return size
    if FIELD in held or size > FIELD_VALUE or value != value.strip() or (at_edge and len(value.split()) > 1):
        return None
    return size


def fields_fill_in(pattern: str, message: str) -> float:
    """
    The fewest characters of the guide's own text that the message's fields have to stand for, so that the guide's
    text is part of the message, or infinity when it can't be. ANY stands for any text, an example value for a field
    or for the same text, and each FIELD for a value (see field_value)
    """
    pattern = ANY + pattern + ANY
    rows, cols = len(pattern), len(message)
    # How much of the guide's own text comes before each position
    before = [len(own_text(pattern[:i])) for i in range(rows + 1)]
    # best[i][j]: the fewest characters filled in to line up pattern[i:] with message[j:]
    best = [[float("inf")] * (cols + 1) for _ in range(rows + 1)]
    best[rows][cols] = 0
    for i in range(rows, -1, -1):
        for j in range(cols, -1, -1):
            options = [best[i][j]]
            here = pattern[i] if i < rows else None
            if here == ANY:
                # The placeholder ends here, or it also covers the message's next character
                options.append(best[i + 1][j])
                if j < cols:
                    options.append(best[i][j + 1])
            elif here in (OPEN, CLOSE):
                options.append(best[i + 1][j])
            elif here is not None and j < cols and message[j] == here:
                options.append(best[i + 1][j + 1])
            if j < cols and message[j] == FIELD:
                for end in range(i, rows + 1):
                    size = field_value(pattern[i:end], before[i] == 0 or before[end] == before[rows])
                    if size is not None:
                        options.append(best[end][j + 1] + size)
            best[i][j] = min(options)
    return best[0][0]


def reads_like(text: str, message: str) -> bool:
    pattern = guide_pattern(text)
    return len(own_text(pattern)) - fields_fill_in(pattern, message) >= MIN_MATCHED


def code_says(text: str) -> bool:
    """Whether some message in the code reads like this text from the guide"""
    # Only messages sharing a run of 8 characters with the text are checked in full, most shared first. A text with
    # no run that long between its placeholders, like `Action <key>.<name> failed`, is checked against every message
    pieces = re.split(f"[{ANY}{OPEN}{CLOSE}]", guide_pattern(text))
    runs = {piece[k : k + 8] for piece in pieces for k in range(len(piece) - 7)}
    shared = sorted(((sum(run in message for run in runs), message) for message in MESSAGES), reverse=True)
    return any(reads_like(text, message) for count, message in shared if count or not runs)


def common_problems():
    """The 'What you see' cell of every row in the guide's Common problems tables"""
    section = GUIDE[GUIDE.index("## 16. Common problems") : GUIDE.index("## 17. ")]
    for line in section.splitlines():
        if line.startswith("| ") and not line.startswith("| What you see"):
            yield line.split(" | ")[0][2:]


def quoted(cell: str):
    """Each backticked text in a cell, plus the message in double quotes when there is one ("Bad request.", say)"""
    yield from BACKTICKED.findall(cell)
    outside = BACKTICKED.sub("", cell)
    if outside.count('"') >= 2:
        yield outside[outside.index('"') + 1 : outside.rindex('"')]


def log_lines():
    """The bot log lines the guide's Testing and debugging section says to look for, with each ending it lists"""
    start = GUIDE.index("**Python errors**")
    paragraph = GUIDE[start : GUIDE.index("\n", start)]
    for line, endings in re.findall(r"`([^`]+)`(?: \(followed by ([^)]*)\))?", paragraph):
        yield line
        # `Action <key>.<name>` alone is too short to check, but with "failed" after it, it's a whole log line
        yield from (f"{line} {ending}" for ending in re.findall(r'"([^"]+)"', endings))


def guide_messages():
    texts = [text for cell in common_problems() for text in quoted(cell)] + list(log_lines())
    for text in texts:
        if SUBJECT.fullmatch(text) or text.startswith(NOT_THE_HUBS):
            continue
        if len(own_text(guide_pattern(text))) >= MIN_MATCHED:
            yield pytest.param(text, id=text[:50])


def code_blocks(language: str):
    for match in FENCE.finditer(GUIDE):
        if match[2] == language:
            line = GUIDE.count("\n", 0, match.start()) + 1
            yield pytest.param(textwrap.dedent(match[3]), id=f"DEVELOPERS.md:{line}")


def test_the_guide_still_has_what_these_tests_read():
    # A change to the tables or the fences would otherwise leave the tests below checking nothing
    assert len(list(guide_messages())) >= 40
    assert len(list(log_lines())) >= 8
    assert len(list(code_blocks("python"))) >= 10
    assert len(list(code_blocks("js"))) >= 6
    assert len(list(code_blocks("json"))) >= 1


def test_a_changed_message_no_longer_reads_like_the_code():
    message = f"{FIELD} handler {FIELD} must be an async def"
    assert reads_like("actions handler 'x' must be an async def", message)
    assert not reads_like("actions handler 'x' must be an async function", message)
    # A field stands for a value, not for the words around it
    message = f'routes key {FIELD} must be "METHOD path": GET or POST'
    assert reads_like("routes key 'x' must be \"METHOD path\": ...", message)
    assert not reads_like("routes key 'x' must be \"METHOD path\" ...", message)
    message = f"{FIELD} {FIELD} is a coroutine, not a method: write self.{FIELD} without ()"
    assert not reads_like("actions 'x' is a coroutine, not a method: write self.x with no ()", message)
    # An example value stands for a field, or for the same text
    assert not reads_like("actions handler 'x' takes (ctx)", f"{FIELD} handler {FIELD} gets {FIELD}")
    assert reads_like("The 'activityhub' field is reserved", "The 'activityhub' field is reserved for the hub")
    assert not reads_like("Something went wrong somewhere.", f"{FIELD}: {FIELD}")
    # A field at the end of the quote holds one word, so the message's own words after it are quoted too
    message = f"Unknown field {FIELD} (did you mean {FIELD}?)"
    assert reads_like("Unknown field 'action' (did you mean 'actions'?)", message)
    assert not reads_like("Unknown field 'action' (did you mean an 'actions'?)", message)
    assert reads_like("The key 'x' is already used by OtherCog", f"The key {FIELD} is already used by {FIELD}")
    # A field holds an example value, or a value of its own, not both
    message = f"actions key {FIELD} must be 1-64 letters"
    assert reads_like("actions key 'x' must be ...", message)
    assert not reads_like("actions key named 'x' must be ...", message)


def test_only_whole_messages_are_read_from_the_code(tmp_path):
    # A docstring isn't a message, and neither is the text between an f-string's fields
    source = tmp_path / "source.py"
    source.write_text('"""About this file"""\nlog.error(f"Raw route {path} returned {kind}, not a response")\n')
    assert list(python_messages(source)) == [f"Raw route {FIELD} returned {FIELD}, not a response"]


@pytest.mark.parametrize("text", guide_messages())
def test_the_guide_quotes_the_hubs_own_messages(text):
    assert code_says(text), f"DEVELOPERS.md quotes {text!r}, but no message in the code reads like that"


@pytest.mark.parametrize("code", code_blocks("python"))
def test_python_samples_parse(code):
    ast.parse(code)


@pytest.mark.parametrize("code", code_blocks("json"))
def test_json_samples_parse(code):
    json.loads(code)


@pytest.mark.parametrize("code", code_blocks("js"))
def test_js_samples_parse(code, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the samples can't be checked")
    # The samples use import and top-level await, so they are checked as modules
    sample = tmp_path / "sample.mjs"
    sample.write_text(code, encoding="utf-8")
    result = subprocess.run([node, "--check", str(sample)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
