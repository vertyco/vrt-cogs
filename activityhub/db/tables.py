from piccolo.columns import BigInt, Real, Varchar
from piccolo.table import Table


class Play(Table):
    """One person's stretch inside one game, written when it ends"""

    guild_id = BigInt(null=True, default=None, index=True, help_text="Empty for an Activity outside a server")
    user_id = BigInt(index=True)
    game = Varchar(length=32)
    platform = Varchar(length=8, default="", help_text='"mobile" or "desktop" as Discord says, empty when unknown')
    started_at = Real(index=True, help_text="Unix time the play started")
    seconds = Real(default=0.0, help_text="How long the play's clock ran, with hidden time left out")


TABLES: list[type[Table]] = [Play]
