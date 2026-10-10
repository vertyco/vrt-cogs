import discord
import pytest

from activityhub.common.setup_guide import README_URL, local_address, setup_pages


def pages(**changes) -> list[discord.Embed]:
    facts = dict(
        prefix="[p]",
        host="127.0.0.1",
        port=8742,
        running=True,
        has_secret=True,
        app_id=1000,
        color=discord.Color.blurple(),
    )
    facts.update(changes)
    return setup_pages(**facts)


@pytest.mark.parametrize(
    "host, expected",
    [("127.0.0.1", "127.0.0.1:9000"), ("0.0.0.0", "127.0.0.1:9000"), ("::", "127.0.0.1:9000"), ("::1", "[::1]:9000")],
)
def test_local_address_is_what_a_tunnel_on_the_same_machine_dials(host, expected):
    assert local_address(host, 9000) == expected


def test_every_page_fits_in_one_embed_and_links_the_readme():
    guide = pages()
    # More than 10 pages would turn on the menu's jump and search buttons, which a short guide doesn't need
    assert len(guide) <= 10
    for page in guide:
        assert page.title and page.url == README_URL
        assert len(str(page.description)) <= 4096
        assert len(page) <= 6000


def test_pages_use_this_bots_own_address():
    text = "\n".join(str(page.description) for page in pages(host="0.0.0.0", port=9000))
    assert "`0.0.0.0:9000` and is running" in text
    assert "cloudflared tunnel --url http://127.0.0.1:9000" in text
    assert "reverse_proxy 127.0.0.1:9000" in text
    assert "proxy_pass http://127.0.0.1:9000;" in text
    assert "Service URL: `http://127.0.0.1:9000`" in text
    assert "https://discord.com/developers/applications/1000" in text


def test_pages_say_what_is_missing():
    text = "\n".join(str(page.description) for page in pages(running=False, has_secret=False))
    assert "**isn't running**" in text
    assert "no client secret is saved" in text
