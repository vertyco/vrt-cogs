import os

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


def test_inject_head_puts_tags_first_in_head():
    html = '<!doctype html><html><HEAD lang="x"><script src="a.js"></script></HEAD></html>'
    out = inject_head(html, "<base>")
    assert out == '<!doctype html><html><HEAD lang="x"><base><script src="a.js"></script></HEAD></html>'


def test_inject_head_skips_header_tags():
    assert inject_head("<header>hi</header><head></head>", "<b>") == "<header>hi</header><head><b></head>"


def test_inject_head_without_a_head_prepends():
    assert inject_head("<p>hi</p>", "<b>") == "<b><p>hi</p>"


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
