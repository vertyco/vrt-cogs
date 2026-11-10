import hashlib
import logging
import mimetypes
import os
import re
import typing as t
from pathlib import Path

from aiohttp import web

log = logging.getLogger("red.vrt.activityhub.files")

# Set here because Python's own table depends on the machine (Windows maps .mjs to text/plain),
# and browsers refuse module scripts and WebAssembly served with the wrong type
CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".mp3": "audio/mpeg",
}
# Engine builds ship files compressed ahead of time (game.wasm.br). They go out with Content-Encoding,
# so the browser unpacks them before the page's code sees them
COMPRESSED = {".gz": "gzip", ".br": "br"}
# For a file at an address that carries its folder's newest fingerprint. The file never changes at that address, so
# browsers and the caching services in between may keep it for a year and never ask the bot for it again
LASTING = "public, max-age=31536000, immutable"
HEAD_TAG = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
# What can come before the spot a page's <head> would start: a byte order mark, comments, the doctype and <html>
PAGE_START = re.compile(
    r"(?:\ufeff|\s|<!--.*?-->)*(?:<!doctype[^>]*>)?(?:\s|<!--.*?-->)*(?:<html\b[^>]*>)?", re.IGNORECASE | re.DOTALL
)


def hidden(relative: Path) -> bool:
    """Whether a path inside a web folder goes through a dot name (.git, .env). Those are never served or fingerprinted"""
    return any(part.startswith(".") for part in relative.parts)


def served_entries(folder: str | Path) -> t.Iterator[os.DirEntry]:
    """
    Every file under a folder the hub can serve, as its folder's listing describes it. A listing already holds what
    each file is and when it changed (on Windows, without asking about each file again), which keeps a look over a
    game of a thousand files quick. Hidden folders aren't even opened, since a .git folder can be huge, and neither
    are links to folders
    """
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir(follow_symlinks=False):
                yield from served_entries(entry.path)
            elif entry.is_file():
                yield entry


def served_files(root: Path) -> t.Iterator[Path]:
    """Every file under `root` the hub can serve"""
    return (Path(entry.path) for entry in served_entries(root))


# Each web folder's newest fingerprint, for knowing an address that carries it (is_current)
newest: dict[Path, str] = {}


def build_id(root: Path) -> str:
    """Short fingerprint of a folder's files, so their addresses change whenever any of them change"""
    parts = []
    start = len(str(root)) + 1
    for entry in served_entries(root):
        try:
            changed = entry.stat().st_mtime_ns
        except OSError as e:
            # A bundler rebuilding the folder can delete a file between the listing and this look at it
            log.debug("Left %s out of the fingerprint: %s", entry.path, e)
            continue
        parts.append(f"{entry.path[start:].replace(os.sep, '/')}{changed}")
    build = hashlib.sha1("".join(sorted(parts)).encode()).hexdigest()[:10]
    newest[root] = build
    return build


def is_current(root: Path, build: str) -> bool:
    """Whether a file address's code is the folder's newest fingerprint. An old page's addresses carry an older one"""
    return newest.get(root) == build


def resolve_inside(root: Path, relative: str) -> Path | None:
    """The file at `relative` under `root`, or None when it is missing, hidden, or the path leads outside `root`"""
    try:
        base = root.resolve()
        target = (base / relative).resolve()
        # Checked after following links, so a link can't lead to a hidden file either
        if target.is_relative_to(base) and not hidden(target.relative_to(base)) and target.is_file():
            return target
    except (OSError, ValueError) as e:
        log.debug("Refused file path %r: %s", relative, e)
    return None


def inject_head(html: str, tags: str) -> str:
    """Put tags right after <head>, so they come before any script or link that depends on them"""
    match = HEAD_TAG.search(html)
    if match is None:
        # No <head> tag (HTML allows that): the tags go after the doctype, so the page stays in standards mode
        match = PAGE_START.match(html)
    return html[: match.end()] + tags + html[match.end() :]


def file_response(path: Path, lasting: bool = False) -> web.FileResponse:
    """The file as a reply. `lasting` marks it as safe to keep for good (LASTING)"""
    encoding = COMPRESSED.get(path.suffix.lower())
    # A compressed file has the type of the file inside it: game.wasm.gz is WebAssembly
    name = path.stem if encoding else path.name
    content_type = CONTENT_TYPES.get(Path(name).suffix.lower())
    if content_type is None:
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    headers = {"Content-Type": content_type}
    if encoding is not None:
        headers["Content-Encoding"] = encoding
    if lasting:
        headers["Cache-Control"] = LASTING
    return web.FileResponse(path, headers=headers)
