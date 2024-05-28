import logging

from redbot.core.i18n import Translator

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.levelup.api.leaderboards")
_ = Translator("LevelUp", __file__)


class LeaderBoards(MixinMeta):
    pass
