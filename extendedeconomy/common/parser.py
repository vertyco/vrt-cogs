from redbot.core import commands
from redbot.core.i18n import Translator

_ = Translator("ExtendedEconomy", __file__)


class SetParser:
    def __init__(self, argument):
        allowed = ("+", "-")
        try:
            self.sum = int(argument)
        except ValueError:
            raise commands.BadArgument(
                _("Invalid value, the argument must be an integer, optionally preceded with a `+` or `-` sign.")
            )
        if argument and argument[0] in allowed:
            if self.sum < 0:
                self.operation = "withdraw"
            elif self.sum > 0:
                self.operation = "deposit"
            else:
                raise commands.BadArgument(
                    _(
                        "Invalid value, the amount of currency to increase or decrease"
                        " must be an integer different from zero."
                    )
                )
            self.sum = abs(self.sum)
        else:
            self.operation = "set"
