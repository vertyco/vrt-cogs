class Script:
    """Stands in for random.Random, handing out queued rolls and choices in order"""

    def __init__(self, *rolls, choices=()):
        self.rolls = list(rolls)
        self.choices = list(choices)

    def random(self):
        return self.rolls.pop(0)

    def choice(self, options):
        pick = self.choices.pop(0)
        assert pick in options
        return pick

    def used_up(self):
        return not self.rolls and not self.choices
