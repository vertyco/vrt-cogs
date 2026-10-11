"""FarmCord's balance simulation. Simulated players play through the real rules in farmcord.game (nothing here copies
a rule: every outcome comes from the game's own functions), and the report shows how fast each one levels, when each
plot becomes affordable and where the FarmCoins go. test_balance.py checks the targets. Print the full report with:

    python -m farmcord.tests.simulate
"""

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from itertools import chain

from farmcord.catalog import ANIMALS, CANS, CARE_WINDOW, CROPS, HOES, PEN_SIZE, PLOTS, SPOTS, STORAGE
from farmcord.game import animals, crops, market
from farmcord.game import farm as actions
from farmcord.game.calendar import DAY, EPOCH, HOUR, WEEK
from farmcord.game.model import Animal, Farm, Spot, count, new_farm, pen_animals, storage_limit, waiting

SEED = 2026
# Monday 2026-01-05 00:00 UTC opens the first spring. Three weeks on, winter starts on a Monday too
SPRING = EPOCH
WINTER = EPOCH + 3 * WEEK
GOAL = 90
MILESTONES = (5, 10, 15, 25, 50, 75, GOAL)
LAST_PLOT = max(PLOTS)
# The plot the pen run turns into a pen once animals unlock
PEN_PLOT = 2
# The most one harvest gives
BIGGEST_HARVEST = 3
# A run still going by then never reaches the goal
LONGEST = 60 * DAY


@dataclass(frozen=True)
class Nonstop:
    """At the farm whenever something is ready, except asleep from 04:00 to 08:00 UTC. Plants only crops that ripen
    by bedtime"""

    name: str = "nonstop"
    bedtime: float = 4 * HOUR
    wake: float = 8 * HOUR

    def visit_at(self, t: float) -> float:
        """The first moment at or after `t` the player is at the farm"""
        clock = t % DAY
        return t - clock + self.wake if self.bedtime < clock < self.wake else t

    def deadline(self, t: float) -> float:
        """A crop planted at `t` must be ripe by then: the next bedtime"""
        bed = t - t % DAY + self.bedtime
        return bed if bed >= t else bed + DAY

    def next_visit(self, now: float, wanted: float) -> float:
        return self.visit_at(wanted)


@dataclass(frozen=True)
class Casual:
    """Three visits a day at fixed UTC hours, whatever is ready"""

    name: str = "casual"
    visits: tuple[float, ...] = (8 * HOUR, 14 * HOUR, 20 * HOUR)

    def visit_at(self, t: float) -> float:
        midnight = t - t % DAY
        return min(midnight + day + hour for day in (0.0, DAY) for hour in self.visits if midnight + day + hour >= t)

    def deadline(self, t: float) -> float:
        return math.inf

    def next_visit(self, now: float, wanted: float) -> float:
        return self.visit_at(now + 1)


@dataclass
class Sim:
    """One player's run: the farm, the seeded dice, and what the report needs"""

    player: Nonstop | Casual
    farm: Farm
    rng: random.Random
    start: float
    pen: bool = False
    # Level to the moment it was reached
    reached: dict[int, float] = field(default_factory=dict)
    # Plot number to the FarmCoins on hand at the first visit at its level, and when it was bought
    plots: dict[int, dict] = field(default_factory=dict)
    earned: Counter = field(default_factory=Counter)
    spent: Counter = field(default_factory=Counter)
    # (moment, plot, xp, coins) for every harvest, seed, animal and bag of feed, to compare a pen with a crop plot
    books: list[tuple[float, int, int, int]] = field(default_factory=list)
    # The crop plot being emptied to become a pen, and when the pen opened
    closing: int | None = None
    pen_since: float | None = None
    end: float = 0.0


# Bookkeeping


def note(sim: Sim, category: str, before: int, events: list[dict]) -> None:
    """File the FarmCoins an action moved: level and achievement rewards on their own, the rest under `category`"""
    rewards = 0
    for event in events:
        if event["kind"] == "level":
            sim.reached.setdefault(event["level"], event["at"])
        if event["kind"] in ("level", "achievement"):
            sim.earned[f"{event['kind']} rewards"] += event["coins"]
            rewards += event["coins"]
        if event["kind"] in ("grown", "born"):
            sim.books.append((event["at"], PEN_PLOT, event["xp"], 0))
    rest = sim.farm.coins - before - rewards
    if rest > 0:
        sim.earned[category] += rest
    elif rest < 0:
        sim.spent[category] -= rest


def act(sim: Sim, category: str, action, *args) -> dict:
    """One game action on the farm, its FarmCoins filed under `category`"""
    before = sim.farm.coins
    result, events = action(sim.farm, *args)
    note(sim, category, before, events)
    return result


def crop_spots(farm: Farm) -> list[tuple[int, Spot]]:
    """(plot number, spot) for every spot of every open crop plot"""
    return [
        (plot.number, spot)
        for plot in farm.plots.values()
        if plot.unlocked and plot.kind == "crops"
        for spot in plot.spots
    ]


# Crops


def outlook(player: Nonstop | Casual, key: str, now: float) -> float:
    """XP per spot-hour of planting `key` now, counted until the visit that picks it: its harvest XP after the stages
    the player won't be there to water and any spoiling before that visit. 0 when it won't ripen by the deadline"""
    spot = Spot(0, state="growing", crop=key)
    crops.start_cycle(spot, now)
    ripe = crops.ripe_at(spot)
    if ripe > player.deadline(now):
        return 0.0
    for k in range(crops.STAGES):
        if player.visit_at(crops.stage_start(spot, k)) < crops.stage_start(spot, k + 1):
            spot.watered |= 1 << k
    picked = player.visit_at(ripe)
    return CROPS[key].xp * crops.value_multiplier(spot, picked) / (picked - now)


def rank(player: Nonstop | Casual, farm: Farm, now: float) -> list[str]:
    """The crops open at the player's level, best outlook first (the newer crop on a tie), leaving out any worth
    nothing"""
    scores = {key: outlook(player, key, now) for key, crop in CROPS.items() if crop.level <= farm.level}
    best = sorted(scores, key=lambda key: (scores[key], CROPS[key].level), reverse=True)
    return [key for key in best if scores[key] > 0]


def harvest_all(sim: Sim, now: float) -> None:
    """Pick every ripe crop. A stack that might not take the next harvest is sold first"""
    farm = sim.farm
    for number, spot in crop_spots(farm):
        if crops.harvest_refusal(spot, now):
            continue
        key = f"crop:{spot.crop}"
        if max(count(farm, key), count(farm, f"{key}:x")) + BIGGEST_HARVEST > storage_limit(farm):
            sell_crops(sim, now)
        result = act(sim, "harvests", actions.harvest, number, spot.index, now, sim.rng)
        sim.books.append((now, number, result["xp"], result["worth"]))


def sell_crops(sim: Sim, now: float) -> None:
    for key, item in list(sim.farm.items.items()):
        if key in market.CROP_ITEMS:
            act(sim, "crop sales", market.sell_crops, key, item.quantity, now)


def till_all(sim: Sim, now: float) -> None:
    """Clear rotted spots and till bare ones. A wider hoe tills the rest of its row or plot in the same tap"""
    for number, spot in crop_spots(sim.farm):
        while spot.state in ("untilled", "rotted"):
            act(sim, "tilling", actions.till, number, spot.index, now)


def plant_all(sim: Sim, now: float) -> None:
    """Sow every tilled spot with the best crop the player has a seed for or can pay for"""
    farm = sim.farm
    ranking = rank(sim.player, farm, now)
    for number, spot in crop_spots(farm):
        if spot.state != "tilled" or number == sim.closing:
            continue
        key = next((key for key in ranking if count(farm, f"seed:{key}") or farm.coins >= CROPS[key].seed_price), None)
        if key is None:
            return
        paid = 0
        if not count(farm, f"seed:{key}"):
            paid = act(sim, "seeds", market.buy_seeds, key, 1)["cost"]
        act(sim, "planting", actions.plant, number, spot.index, key, now)
        sim.books.append((now, number, 0, -paid))


def water_all(sim: Sim, now: float) -> None:
    """Water every crop whose stage still needs it, refilling the can at the Pond whenever it runs dry"""
    for number, spot in crop_spots(sim.farm):
        if crops.water_refusal(spot, now) is None:
            if sim.farm.water < 1:
                act(sim, "pond", actions.refill)
            act(sim, "watering", actions.water, number, spot.index, now)


# Plots, tools and storage


def upgrades(farm: Farm) -> list[tuple[int, str, object, tuple]]:
    """The tool and storage upgrades a player would want now, cheapest first, as (price, category, action, args). The
    next can once the crop spots outnumber what the can holds, the wide hoe once there are 2 crop plots and the plow at
    3, and storage once a full harvest at 2 a spot wouldn't fit"""
    spots = len(crop_spots(farm))
    can, hoe, store = farm.can_tier + 1, farm.hoe_tier + 1, farm.storage_tier + 1
    wanted = []
    if can < len(CANS) and spots > CANS[farm.can_tier].capacity:
        wanted.append((CANS[can].level, CANS[can].price, "tools", market.buy_tool, ("can", can)))
    if hoe < len(HOES) and spots > hoe * SPOTS:
        wanted.append((HOES[hoe].level, HOES[hoe].price, "tools", market.buy_tool, ("hoe", hoe)))
    if store < len(STORAGE) and 2 * spots > storage_limit(farm):
        wanted.append((STORAGE[store].level, STORAGE[store].price, "storage", market.buy_storage, (store,)))
    open_now = [option[1:] for option in wanted if option[0] <= farm.level]
    return sorted(open_now, key=lambda option: option[0])


def shop(sim: Sim, now: float) -> None:
    """Plots first, each bought the first visit it is affordable. While one waits for FarmCoins nothing else is bought.
    Then every wanted upgrade the player can pay for while keeping a plot's worth of its dearest seeds"""
    farm = sim.farm
    for number, info in PLOTS.items():
        if farm.plots[number].unlocked or info.level > farm.level:
            continue
        log = sim.plots.setdefault(number, {"coins": farm.coins, "bought": None})
        if farm.coins < info.price:
            return
        act(sim, "plots", market.unlock_plot, number, "crops")
        log["bought"] = now
    reserve = SPOTS * max(crop.seed_price for crop in CROPS.values() if crop.level <= farm.level and not crop.bush)
    for price, category, action, args in upgrades(farm):
        if farm.coins - price >= reserve:
            act(sim, category, action, *args)


# The pen


def best_animal(farm: Farm) -> str | None:
    """The animal the pen raises: the latest one the player's level opens"""
    open_now = [animal for animal in ANIMALS.values() if animal.level <= farm.level]
    return max(open_now, key=lambda animal: animal.level).key if open_now else None


def open_pen(sim: Sim, now: float) -> None:
    """Once animals unlock, stop planting on the pen plot, and switch it as soon as its last crop is picked"""
    farm = sim.farm
    plot = farm.plots[PEN_PLOT]
    if sim.pen_since is not None or not plot.unlocked or best_animal(farm) is None:
        return
    sim.closing = PEN_PLOT
    if market.switch_refusal(farm, plot, "animals") is None and farm.coins >= market.switch_fee(farm):
        fee = act(sim, "plot switches", market.switch_plot, PEN_PLOT, "animals")["fee"]
        sim.books.append((now, PEN_PLOT, 0, -fee))
        sim.pen_since = now
        sim.closing = None


def done(animal: Animal, kind: str, stud: Animal | None, crowded: bool, now: float) -> bool:
    """Whether a grown-up has nothing more to give the pen: an older kind, an ill one, a mother whose litter came (or
    one who can't try while babies wait for her spot), or a male that isn't the pen's stud"""
    if animal.kind != kind or animals.condition(animal, now) != "healthy":
        return True
    return animal.bred or crowded if animal.sex == "female" else animal is not stud


def sell_animals(sim: Sim, now: float) -> None:
    """Sell every grown-up the pen is done with. The first healthy grown-up male of the pen's kind stays as its stud"""
    farm = sim.farm
    kind = best_animal(farm)
    herd = pen_animals(farm, PEN_PLOT)
    males = [a for a in herd if a.kind == kind and a.sex == "male" and a.adult]
    stud = next((a for a in males if animals.condition(a, now) == "healthy"), None)
    crowded = bool(waiting(farm))
    for animal in herd:
        if animal.adult and not animal.pregnant_until and done(animal, kind, stud, crowded, now):
            coins = act(sim, "animal sales", market.sell_animal, animal.id, now)["coins"]
            sim.books.append((now, PEN_PLOT, 0, coins))


def stock_pen(sim: Sim, now: float) -> None:
    """Bring waiting babies in, let every ready mother try for babies, then fill the pen with bought babies: a male when
    the pen has none of the kind, females otherwise"""
    farm = sim.farm
    if sim.pen_since is None:
        return
    for baby in waiting(farm):
        if len(pen_animals(farm, PEN_PLOT)) < PEN_SIZE:
            act(sim, "pen", actions.move_baby, baby.id, PEN_PLOT, now)
    for animal in pen_animals(farm, PEN_PLOT):
        if animals.breed_refusal(farm, animal, now) is None:
            act(sim, "pen", actions.breed, animal.id, now, sim.rng)
    info = ANIMALS[best_animal(farm)]
    while len(pen_animals(farm, PEN_PLOT)) < PEN_SIZE and farm.coins >= info.baby_price:
        males = any(a.kind == info.key and a.sex == "male" for a in pen_animals(farm, PEN_PLOT))
        act(sim, "animals", market.buy_animal, info.key, "female" if males else "male", PEN_PLOT, now)
        sim.books.append((now, PEN_PLOT, 0, -info.baby_price))


def overdue(sim: Sim, now: float, due: float) -> bool:
    """Whether a care window closing at `due` needs tending now: it closes within the hour, or the player won't be
    back before it does"""
    return due - HOUR <= now or sim.player.next_visit(now, due - HOUR) >= due


def feed_bag(sim: Sim, kind: str, now: float) -> bool:
    """A bag of the kind's feed in storage, bought if need be. False when the player can't pay for one"""
    farm = sim.farm
    if count(farm, f"feed:{kind}"):
        return True
    if farm.coins < ANIMALS[kind].feed_price:
        return False
    act(sim, "feed", market.buy_feed, kind, 1)
    sim.books.append((now, PEN_PLOT, 0, -ANIMALS[kind].feed_price))
    return True


def care(sim: Sim, now: float) -> None:
    """Feed (a bag of the animal's own feed) and water every animal that needs it before the player is back"""
    farm = sim.farm
    for animal in pen_animals(farm, PEN_PLOT):
        if overdue(sim, now, animal.fed_at + CARE_WINDOW) and feed_bag(sim, animal.kind, now):
            act(sim, "pen", actions.feed, animal.id, f"feed:{animal.kind}", now)
        if overdue(sim, now, animal.watered_at + CARE_WINDOW):
            if farm.water < 1:
                act(sim, "pond", actions.refill)
            act(sim, "pen", actions.water_animal, animal.id, now)


# Playing


def crop_moments(sim: Sim, now: float):
    """Each stage start (to water it) and ripening. An empty spot waits for the player's next bedtime to pass"""
    for number, spot in crop_spots(sim.farm):
        if spot.state == "growing":
            yield from (crops.stage_start(spot, k) for k in range(1, crops.STAGES + 1))
        elif number != sim.closing:
            yield sim.player.deadline(now) + 1


def pen_moments(farm: Farm):
    """An hour before each care window closes, growing up, births and the next breeding try"""
    for animal in farm.animals:
        if animal.plot is None:
            continue
        yield min(animal.fed_at, animal.watered_at) + CARE_WINDOW - HOUR
        if not animal.adult:
            yield animals.grown_at(animal)
        if animal.pregnant_until:
            yield animal.pregnant_until
        elif animal.adult and animal.sex == "female" and not animal.bred:
            yield animal.tried_at + animals.BREED_REST


def next_event(sim: Sim, now: float) -> float:
    times = [t for t in chain(crop_moments(sim, now), pen_moments(sim.farm)) if t > now]
    return min(times, default=now + DAY)


def visit(sim: Sim, now: float) -> None:
    """Everything the player does at the farm at `now`, in the order a player would"""
    before = sim.farm.coins
    note(sim, "settle", before, actions.settle(sim.farm, now, sim.rng))
    harvest_all(sim, now)
    sell_crops(sim, now)
    if sim.pen:
        sell_animals(sim, now)
    shop(sim, now)
    if market.can_have_free_packet(sim.farm):
        act(sim, "free packet", market.free_packet)
    if sim.pen:
        open_pen(sim, now)
        care(sim, now)
    till_all(sim, now)
    plant_all(sim, now)
    water_all(sim, now)
    # New babies get what the seeds leave
    if sim.pen:
        stock_pen(sim, now)


def finished(sim: Sim, now: float) -> bool:
    """The goal level is reached and the last plot is bought, or a day has passed since the goal without it"""
    reached = sim.reached.get(GOAL)
    if reached is None:
        return now - sim.start > LONGEST
    return sim.farm.plots[LAST_PLOT].unlocked or now > reached + DAY


def play(player: Nonstop | Casual, monday: float, pen: bool = False, seed: int = SEED) -> Sim:
    """A new farm made at the player's first visit from `monday` on, played until the goal"""
    start = player.visit_at(monday)
    sim = Sim(player, new_farm(1, player.name, start), random.Random(seed), start, pen)
    now = start
    while not finished(sim, now):
        visit(sim, now)
        now = player.next_visit(now, next_event(sim, now))
    sim.end = now
    return sim


# The report


def day_of(sim: Sim, level: int) -> float | None:
    """Days from the farm's first moment until `level`, None if never reached"""
    return (sim.reached[level] - sim.start) / DAY if level in sim.reached else None


def plot_waits(sim: Sim) -> dict[int, float | None]:
    """Hours from reaching each plot's level until it was bought. None when it never was"""
    waits = {}
    for number, info in PLOTS.items():
        log = sim.plots.get(number)
        if number != 1 and info.level <= GOAL:
            bought = log and log["bought"]
            waits[number] = (bought - sim.reached[info.level]) / HOUR if bought else None
    return waits


def per_day(sim: Sim, plot: int, since: float, until: float) -> tuple[float, float]:
    """XP and FarmCoins (harvest worth or sales, less seeds, babies and feed) one plot made a day in [since, until)"""
    rows = [(xp, coins) for at, number, xp, coins in sim.books if number == plot and since <= at < until]
    span = (until - since) / DAY
    return sum(row[0] for row in rows) / span, sum(row[1] for row in rows) / span


def cell(value: float | None, digits: int = 1) -> str:
    return "never" if value is None else f"{value:,.{digits}f}"


def level_table(runs: dict[str, Sim]) -> list[str]:
    lines = ["| Level | " + " | ".join(runs) + " |", "|---" * (len(runs) + 1) + "|"]
    for level in MILESTONES:
        lines.append(f"| {level} | " + " | ".join(cell(day_of(sim, level), 2) for sim in runs.values()) + " |")
    firsts = [cell((sim.reached[2] - sim.start) / HOUR * 60, 0) + " min" for sim in runs.values()]
    lines.append("| First level-up | " + " | ".join(firsts) + " |")
    return lines


def plot_table(name: str, sim: Sim) -> list[str]:
    lines = [f"{name}:", ""]
    lines.append("| Plot | Level | Price | Day level reached | FarmCoins on hand then | Hours until bought |")
    lines.append("|---" * 6 + "|")
    for number, wait in plot_waits(sim).items():
        info = PLOTS[number]
        reached = cell(day_of(sim, info.level), 2)
        coins = cell(sim.plots.get(number, {}).get("coins"), 0)
        lines.append(f"| {number} | {info.level} | {info.price:,} | {reached} | {coins} | {cell(wait)} |")
    return lines


def coin_table(runs: dict[str, Sim]) -> list[str]:
    lines = ["| FarmCoins | " + " | ".join(runs) + " |", "|---" * (len(runs) + 1) + "|"]
    for side in ("earned", "spent"):
        books = [getattr(sim, side) for sim in runs.values()]
        for key in sorted({key for book in books for key in book}):
            lines.append(f"| {side}: {key} | " + " | ".join(f"{book[key]:,}" for book in books) + " |")
        totals = [f"**{sum(book.values()):,}**" for book in books]
        lines.append(f"| **{side} in all** | " + " | ".join(totals) + " |")
    return lines


def pen_table(sim: Sim) -> list[str]:
    """The pen beside Plot 1 (crops all along), per day, in stretches between milestone levels"""
    marks = [sim.pen_since, *(sim.reached[level] for level in (25, 50, 75) if level in sim.reached), sim.end]
    lines = ["| Stretch (days) | Pen XP/day | Plot 1 XP/day | Pen FarmCoins/day | Plot 1 FarmCoins/day |"]
    lines.append("|---|---|---|---|---|")
    for since, until in zip(marks, marks[1:]):
        pen_xp, pen_coins = per_day(sim, PEN_PLOT, since, until)
        crop_xp, crop_coins = per_day(sim, 1, since, until)
        span = f"{(since - sim.start) / DAY:.1f} to {(until - sim.start) / DAY:.1f}"
        lines.append(f"| {span} | {pen_xp:,.0f} | {crop_xp:,.0f} | {pen_coins:,.0f} | {crop_coins:,.0f} |")
    return lines


def report(runs: dict[str, Sim], pen_run: Sim) -> str:
    lines = ["Day each level is reached (days since the farm was made):", "", *level_table(runs), ""]
    for name, sim in runs.items():
        lines += [*plot_table(name, sim), ""]
    lines += ["FarmCoins earned and spent:", "", *coin_table({**runs, "Nonstop with a pen": pen_run}), ""]
    lines += ["Nonstop with a pen on Plot 2 against Plot 1:", "", *pen_table(pen_run), ""]
    lines.append(f"Nonstop with a pen reached level {GOAL} on day {cell(day_of(pen_run, GOAL), 2)}")
    return "\n".join(lines)


def main() -> None:
    runs = {
        "Nonstop": play(Nonstop(), SPRING),
        "Casual": play(Casual(), SPRING),
        "Casual, winter start": play(Casual(), WINTER),
    }
    print(report(runs, play(Nonstop(), SPRING, pen=True)))


if __name__ == "__main__":
    main()
