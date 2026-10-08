import hashlib
import logging
import mimetypes
import re
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
HEAD_TAG = re.compile(r"<head\b[^>]*>", re.IGNORECASE)


def build_id(root: Path) -> str:
    """Short fingerprint of a folder's files, so their addresses change whenever any of them change"""
    stamp = "".join(
        f"{p.relative_to(root).as_posix()}{p.stat().st_mtime_ns}" for p in sorted(root.rglob("*")) if p.is_file()
    )
    return hashlib.sha1(stamp.encode()).hexdigest()[:10]


def resolve_inside(root: Path, relative: str) -> Path | None:
    """The file at `relative` under `root`, or None when it is missing or the path leads outside `root`"""
    try:
        base = root.resolve()
        target = (base / relative).resolve()
        if target.is_relative_to(base) and target.is_file():
            return target
    except (OSError, ValueError) as e:
        log.debug("Refused file path %r: %s", relative, e)
    return None


def inject_head(html: str, tags: str) -> str:
    """Put tags right after <head>, so they come before any script or link that depends on them"""
    match = HEAD_TAG.search(html)
    if match is None:
        return tags + html
    return html[: match.end()] + tags + html[match.end() :]


def file_response(path: Path) -> web.FileResponse:
    content_type = CONTENT_TYPES.get(path.suffix.lower())
    if content_type is None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return web.FileResponse(path, headers={"Content-Type": content_type})
