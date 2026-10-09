import re
import shutil
import subprocess
from pathlib import Path

import pytest

from marblemunch.common import rules

WEB = Path(__file__).resolve().parents[1] / "web"
# The page predicts the player's own hippo, and plays the preview, with the same numbers the bot uses
SHARED = [
    "TICK_RATE",
    "HOME_DEPTH",
    "MAX_REACH",
    "STRETCH_SECONDS",
    "RETRACT_SECONDS",
    "SNAP_COOLDOWN",
    "POOL_MIN",
    "POOL_MAX",
    "MARBLE_RADIUS",
]
SCRIPTS = sorted(path.name for path in WEB.glob("*.js"))


def test_the_page_uses_the_bots_numbers():
    scene = (WEB / "scene.js").read_text(encoding="utf-8")
    for name in SHARED:
        found = re.search(rf"^const {name} = ([0-9.]+);", scene, re.M)
        assert found, f"scene.js has no const {name}"
        assert float(found.group(1)) == getattr(rules, name), name


@pytest.mark.parametrize("name", SCRIPTS)
def test_page_scripts_parse(name, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js isn't installed, so the scripts can't be checked")
    # As a module, the way the browser loads it
    module = tmp_path / f"{name}.mjs"
    module.write_text((WEB / name).read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run([node, "--check", str(module)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
