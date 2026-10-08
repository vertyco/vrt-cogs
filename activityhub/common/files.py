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
HEAD_TAG = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
# What can come before the spot a page's <head> would start: a byte order mark, comments, the doctype and <html>
PAGE_START = re.compile(
    r"(?:\ufeff|\s|<!--.*?-->)*(?:<!doctype[^>]*>)?(?:\s|<!--.*?-->)*(?:<html\b[^>]*>)?", re.IGNORECASE | re.DOTALL
)


def hidden(relative: Path) -> bool:
    """Whether a path inside a web folder goes through a dot name (.git, .env). Those are never served or fingerprinted"""
    return any(part.startswith(".") for part in relative.parts)


def served_files(root: Path) -> t.Iterator[Path]:
    """Every file under `root` the hub can serve. Hidden folders aren't even walked, since a .git folder can be huge"""
    for folder, folders, files in os.walk(root):
        folders[:] = [name for name in folders if not hidden(Path(name))]
        for name in files:
            path = Path(folder, name)
            if not hidden(Path(name)) and path.is_file():
                yield path


def build_id(root: Path) -> str:
    """Short fingerprint of a folder's files, so their addresses change whenever any of them change"""
    stamp = "".join(f"{p.relative_to(root).as_posix()}{p.stat().st_mtime_ns}" for p in sorted(served_files(root)))
    return hashlib.sha1(stamp.encode()).hexdigest()[:10]


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


def file_response(path: Path) -> web.FileResponse:
    encoding = COMPRESSED.get(path.suffix.lower())
    # A compressed file has the type of the file inside it: game.wasm.gz is WebAssembly
    name = path.stem if encoding else path.name
    content_type = CONTENT_TYPES.get(Path(name).suffix.lower())
    if content_type is None:
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    headers = {"Content-Type": content_type}
    if encoding is not None:
        headers["Content-Encoding"] = encoding
    return web.FileResponse(path, headers=headers)
