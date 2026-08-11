import re

SYMBOL_SUBSTITUTIONS = {
    "$": "s",
    "@": "a",
    "!": "i",
    "’": "'",
}
# Symbols that double as ordinary sentence punctuation. They only stand in for a
# letter when another alphanumeric follows them in the same token, so "sh!t" is
# caught while "damn!" keeps its trailing "!" and stays a closable whole word.
PUNCTUATION_LEET = {"!"}
DIGIT_SUBSTITUTIONS = {
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "9": "g",
}
# Separators allowed between the characters of one word: punctuation, never whitespace,
# and never an apostrophe, so contractions like "he'll" don't match "hell". The curly
# apostrophe never reaches this pattern: normalize() folds it to the straight form first.
TIGHT = r"(?:[^\w\s']|_)*"
# Separators allowed between the words of a multi-word entry: anything non-word.
LOOSE = r"[\W_]*"


def normalize(text: str) -> str:
    """Casefold and map leetspeak characters to letters.

    Symbol substitutions apply, including folding the curly apostrophe (’) to
    the straight one (') so "y'all" and "y’all" normalize identically. The
    characters in PUNCTUATION_LEET double as ordinary sentence punctuation, so
    they only stand in for a letter when another alphanumeric follows them in
    the same token: "sh!t" becomes "shit", while "damn!" keeps its "!" and
    stays a whole word the \\b boundary can still close on.
    Digit substitutions apply only inside a whitespace-token that already
    holds a letter, so "d4mn" becomes "damn" while a bare number like "455"
    is left alone.
    """
    out = []
    for token in re.split(r"(\s+)", text.casefold()):
        has_letter = any(char.isalpha() for char in token)
        for index, char in enumerate(token):
            following = token[index + 1] if index + 1 < len(token) else ""
            if char in PUNCTUATION_LEET and not following.isalnum():
                out.append(char)
            elif char in SYMBOL_SUBSTITUTIONS:
                out.append(SYMBOL_SUBSTITUTIONS[char])
            elif has_letter and char in DIGIT_SUBSTITUTIONS:
                out.append(DIGIT_SUBSTITUTIONS[char])
            else:
                out.append(char)
    return "".join(out)


def build_pattern(word: str, boundary: bool) -> str | None:
    """Build a separator-tolerant regex for a configured word.

    Each word part tolerates punctuation between its characters, so "ass" also
    catches "a.s.s" and "@$$". Multi-word entries additionally tolerate any
    separator between parts, so "son of a bitch" catches "sonofabitch".
    An interior apostrophe is kept as a literal required character rather
    than stripped, so a configured entry containing one (e.g. "y'all") still
    matches its literal form; it is not treated as a separator between other
    characters. Leading and trailing apostrophes are stripped instead, since
    a required apostrophe at either edge would need a word character right
    outside the \\b boundary, which real text essentially never provides;
    this lets entries like "fuckin'" or "'tis" build a pattern that can
    actually match. Returns None for entries holding no letters or digits.

    Digit-only entries such as "67" are allowed. normalize() leaves a bare
    number alone (its digit substitutions only fire inside a token that
    already holds a letter), so such an entry matches the literal digits.
    """
    if not re.sub(r"[^a-z0-9]+", "", word.casefold()):
        return None
    parts = []
    for part in normalize(word).split():
        chars = re.sub(r"[^\w']+", "", part).replace("_", "").strip("'")
        if any(char.isalnum() for char in chars):
            parts.append(TIGHT.join(re.escape(char) for char in chars))
    if not parts:
        return None
    core = LOOSE.join(parts)
    return rf"\b{core}\b" if boundary else core


def find_matches(content: str, words: dict[str, dict]) -> list[str]:
    """Return configured words found in content, each at most once.

    words maps word -> {"fine": int | None, "boundary": bool}.
    """
    norm = normalize(content)
    matched: list[str] = []
    for word, settings in words.items():
        pattern = build_pattern(word, settings.get("boundary", True))
        if pattern and re.search(pattern, norm):
            matched.append(word)
    return matched


def calculate_fine(matched: list[str], words: dict[str, dict], default_fine: int, stack: bool) -> int:
    """Total fine for the matched words.

    Stacking sums every matched word's fine; otherwise one fine is charged per
    message, the highest among the words that matched. A word whose configured
    fine is None uses the server default.
    """
    fines = []
    for word in matched:
        fine = words[word].get("fine")
        fines.append(default_fine if fine is None else fine)
    if not fines:
        return 0
    return sum(fines) if stack else max(fines)
