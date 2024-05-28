from pathlib import Path

LEVELUP_ROOT = Path(__file__).parent.parent
LEVELUP_DATA = LEVELUP_ROOT / "data"
FONTS = LEVELUP_DATA / "fonts"
BACKGROUNDS = LEVELUP_DATA / "backgrounds"
STOCK = LEVELUP_DATA / "stock"
DEFAULT_FONT = STOCK / "font.ttf"

PROFILE_TYPES = {
    1: "full",
    2: "slim",
}
LOADING = "https://i.imgur.com/l3p6EMX.gif"
