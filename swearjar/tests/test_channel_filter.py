from swearjar.common.utils import channel_passes

CHANNEL = 100
CATEGORY = 200
PARENT = 300


def test_passes_with_no_lists():
    assert channel_passes([CHANNEL, CATEGORY], [], [])


def test_ignored_channel_blocks():
    assert not channel_passes([CHANNEL, CATEGORY], [], [CHANNEL])


def test_ignored_category_blocks_child_channel():
    assert not channel_passes([CHANNEL, CATEGORY], [], [CATEGORY])


def test_ignored_parent_blocks_thread():
    assert not channel_passes([CHANNEL, PARENT, CATEGORY], [], [PARENT])


def test_whitelist_overrides_blacklist():
    # Channel is on the ignore list, but a whitelist exists and holds it: it passes.
    assert channel_passes([CHANNEL], [CHANNEL], [CHANNEL])


def test_whitelist_blocks_everything_else():
    assert not channel_passes([CHANNEL, CATEGORY], [999], [])


def test_whitelisted_category_passes_child_channel():
    assert channel_passes([CHANNEL, CATEGORY], [CATEGORY], [])


def test_empty_whitelist_falls_back_to_blacklist():
    assert channel_passes([CHANNEL], [], [999])
    assert not channel_passes([CHANNEL], [], [CHANNEL])
