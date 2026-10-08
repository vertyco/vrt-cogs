import gzip
import os

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from activityhub.common.files import build_id, file_response, inject_head, resolve_inside


def write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_build_id_is_short_and_stable(tmp_path):
    write(tmp_path / "game.js")
    first = build_id(tmp_path)
    assert len(first) == 10
    assert build_id(tmp_path) == first


def test_build_id_changes_when_a_file_changes(tmp_path):
    target = write(tmp_path / "game.js")
    before = build_id(tmp_path)
    stamp = target.stat().st_mtime_ns + 5_000_000_000
    os.utime(target, ns=(stamp, stamp))
    assert build_id(tmp_path) != before


def test_build_id_changes_when_a_file_is_added(tmp_path):
    write(tmp_path / "a.js")
    before = build_id(tmp_path)
    write(tmp_path / "sub" / "b.js")
    assert build_id(tmp_path) != before


def test_build_id_ignores_hidden_files(tmp_path):
    write(tmp_path / "game.js")
    git_file = write(tmp_path / ".git" / "objects" / "ab")
    before = build_id(tmp_path)
    stamp = git_file.stat().st_mtime_ns + 5_000_000_000
    os.utime(git_file, ns=(stamp, stamp))
    write(tmp_path / ".DS_Store")
    write(tmp_path / "sub" / ".env")
    assert build_id(tmp_path) == before


def test_build_id_skips_broken_links(tmp_path):
    write(tmp_path / "game.js")
    before = build_id(tmp_path)
    (tmp_path / "gone.js").symlink_to(tmp_path / "missing.js")
    assert build_id(tmp_path) == before


def test_resolve_inside_finds_nested_files(tmp_path):
    target = write(tmp_path / "web" / "levels" / "one.json")
    assert resolve_inside(tmp_path / "web", "levels/one.json") == target.resolve()


def test_resolve_inside_refuses_escapes_and_missing_files(tmp_path):
    secret = write(tmp_path / "secret.txt")
    web = tmp_path / "web"
    write(web / "index.html")
    assert resolve_inside(web, "../secret.txt") is None
    assert resolve_inside(web, "..\\secret.txt") is None
    assert resolve_inside(web, str(secret.resolve())) is None
    assert resolve_inside(web, "missing.js") is None
    assert resolve_inside(web, "") is None
    assert resolve_inside(web, "bad\x00name") is None


def test_resolve_inside_never_finds_hidden_files(tmp_path):
    web = tmp_path / ".local" / "web"
    game = write(web / "game.js")
    for name in (".env", ".git/config", "sub/.hidden/x.js"):
        write(web / name)
        assert resolve_inside(web, name) is None
    # Checked where a link leads, so a plainly named link to a hidden file is refused too
    (web / "config").symlink_to(web / ".env")
    assert resolve_inside(web, "config") is None
    # Only the part inside the web folder counts: the web folder itself may sit in a hidden one
    assert resolve_inside(web, "game.js") == game.resolve()


def test_inject_head_puts_tags_first_in_head():
    html = '<!doctype html><html><HEAD lang="x"><script src="a.js"></script></HEAD></html>'
    out = inject_head(html, "<base>")
    assert out == '<!doctype html><html><HEAD lang="x"><base><script src="a.js"></script></HEAD></html>'


def test_inject_head_skips_header_tags():
    assert inject_head("<header>hi</header><head></head>", "<b>") == "<header>hi</header><head><b></head>"


@pytest.mark.parametrize(
    "page, expected",
    [
        ("<!DOCTYPE html>\n<p>hi</p>", "<!DOCTYPE html>\n<b><p>hi</p>"),
        ('<!doctype html> <html lang="en"><p>hi</p>', '<!doctype html> <html lang="en"><b><p>hi</p>'),
        ("\ufeff<!-- built -->\n<!doctype html><p>hi</p>", "\ufeff<!-- built -->\n<!doctype html><b><p>hi</p>"),
        ("<html><p>hi</p>", "<html><b><p>hi</p>"),
        ("<p>hi</p>", "<b><p>hi</p>"),
    ],
)
def test_inject_head_without_a_head_goes_after_the_doctype(page, expected):
    # Anything before the doctype would switch the page to quirks mode
    assert inject_head(page, "<b>") == expected


def test_file_response_sets_types_browsers_need(tmp_path):
    expected = {
        "a.js": "text/javascript",
        "a.mjs": "text/javascript",
        "a.wasm": "application/wasm",
        "a.css": "text/css",
        "a.svg": "image/svg+xml",
        "a.json": "application/json",
        "a.html": "text/html",
        "a.png": "image/png",
        "a.woff2": "font/woff2",
        "a.mp3": "audio/mpeg",
    }
    for name, content_type in expected.items():
        assert file_response(write(tmp_path / name)).headers["Content-Type"] == content_type


def test_compressed_files_get_the_inner_type_and_an_encoding(tmp_path):
    expected = {
        "game.wasm.gz": ("application/wasm", "gzip"),
        "game.framework.js.br": ("text/javascript", "br"),
        "game.data.gz": ("application/octet-stream", "gzip"),
        "level.JSON.GZ": ("application/json", "gzip"),
    }
    for name, (content_type, encoding) in expected.items():
        headers = file_response(write(tmp_path / name)).headers
        assert (headers["Content-Type"], headers["Content-Encoding"]) == (content_type, encoding)
    assert "Content-Encoding" not in file_response(write(tmp_path / "game.js")).headers


@pytest.mark.asyncio
async def test_compressed_files_reach_the_page_unpacked(tmp_path):
    # The browser unpacks them before the page's code sees them, so a page that unpacks a file itself
    # must give it another extension
    packed = tmp_path / "game.js.gz"
    packed.write_bytes(gzip.compress(b"export const level = 1;"))

    async def serve(request):
        return file_response(packed)

    app = web.Application()
    app.router.add_get("/game.js.gz", serve)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.get("/game.js.gz")
        assert resp.headers["Content-Type"].startswith("text/javascript")
        assert resp.headers["Content-Encoding"] == "gzip"
        assert await resp.text() == "export const level = 1;"
    finally:
        await client.close()
