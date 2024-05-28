"""Generate a full profile image with customizable parameters.

Args:
    background (t.Optional[bytes], optional): The background image as bytes. Defaults to None.
    avatar (t.Optional[bytes], optional): The avatar image as bytes. Defaults to None.
    username (t.Optional[str], optional): The username. Defaults to "Spartan117".
    status (t.Optional[str], optional): The status. Defaults to "online".
    level (t.Optional[int], optional): The level. Defaults to 1.
    messages (t.Optional[int], optional): The number of messages. Defaults to 0.
    voicetime (t.Optional[str], optional): The voicetime. Defaults to "None".
    stars (t.Optional[int], optional): The number of stars. Defaults to 0.
    prestige (t.Optional[int], optional): The prestige level. Defaults to 0.
    prestige_emoji (t.Optional[bytes], optional): The prestige emoji as bytes. Defaults to None.
    balance (t.Optional[int], optional): The balance. Defaults to 0.
    currency_name (t.Optional[str], optional): The name of the currency. Defaults to "Credits".
    previous_xp (t.Optional[int], optional): The previous XP. Defaults to 0.
    current_xp (t.Optional[int], optional): The current XP. Defaults to 0.
    next_xp (t.Optional[int], optional): The next XP. Defaults to 0.
    position (t.Optional[int], optional): The position. Defaults to 0.
    role_icon (t.Optional[bytes], optional): The role icon as bytes. Defaults to None.
    blur (t.Optional[bool], optional): Whether to blur the box behind the stats. Defaults to False.
    user_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the user. Defaults to None.
    base_color (t.Optional[t.Tuple[int, int, int]], optional): The base color. Defaults to None.
    stat_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the stats. Defaults to None.
    level_bar_color (t.Optional[t.Tuple[int, int, int]], optional): The color for the level bar. Defaults to None.
    render_gif (t.Optional[bool], optional): Whether to render as gif if profile or background is one. Defaults to False.
    debug (t.Optional[bool], optional): Whether to raise any errors rather than suppressing. Defaults to False.

Returns:
    bytes: The generated full profile image as bytes.
"""

import logging
import typing as t

from redbot.core.i18n import Translator

# try:
#     from . import imgtools
# except ImportError:
#     import imgtools

log = logging.getLogger("red.vrt.levelup.generator.levelalert")
_ = Translator("LevelUp", __file__)


def generate_full_profile(
    background: t.Optional[bytes] = None,
    avatar: t.Optional[bytes] = None,
    username: t.Optional[str] = "Spartan117",
    status: t.Optional[str] = "online",
    level: t.Optional[int] = 1,
    messages: t.Optional[int] = 0,
    voicetime: t.Optional[str] = "None",
    stars: t.Optional[int] = 0,
    prestige: t.Optional[int] = 0,
    prestige_emoji: t.Optional[bytes] = None,
    balance: t.Optional[int] = 0,
    currency_name: t.Optional[str] = "Credits",
    previous_xp: t.Optional[int] = 0,
    current_xp: t.Optional[int] = 0,
    next_xp: t.Optional[int] = 0,
    position: t.Optional[int] = 0,
    role_icon: t.Optional[bytes] = None,
    blur: t.Optional[bool] = False,
    user_color: t.Optional[t.Tuple[int, int, int]] = None,
    base_color: t.Optional[t.Tuple[int, int, int]] = None,
    stat_color: t.Optional[t.Tuple[int, int, int]] = None,
    level_bar_color: t.Optional[t.Tuple[int, int, int]] = None,
    render_gif: t.Optional[bool] = False,
    debug: t.Optional[bool] = False,
):
    # if background:
    #     card = Image.open(BytesIO(background))
    # else:
    #     card = imgtools.get_random_background()
    # if avatar:
    #     pfp = Image.open(BytesIO(avatar))
    # else:
    #     pfp = Image.open(imgtools.STOCK / "defaultpfp.png")
    pass
