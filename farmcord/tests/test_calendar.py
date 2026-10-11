from datetime import date, datetime, timezone

from farmcord.catalog import CROPS
from farmcord.game.calendar import (
    DAY,
    EPOCH,
    HOUR,
    SEASONS,
    day_ends_at,
    in_season,
    is_rainy,
    rained_between,
    season_at,
    season_ends_at,
    weather_at,
)


def at(year, month, day, hour=0):
    return datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp()


def test_constants():
    assert HOUR == 3600.0
    assert DAY == 86400.0
    assert EPOCH == at(2026, 1, 5)
    assert isinstance(EPOCH, float)


def test_seasons_run_a_week_each_from_the_epoch():
    assert season_at(EPOCH) == "spring"
    assert season_at(EPOCH + 6 * DAY + 23 * HOUR) == "spring"
    assert season_at(EPOCH + 7 * DAY) == "summer"
    assert season_at(EPOCH + 14 * DAY) == "autumn"
    assert season_at(EPOCH + 21 * DAY) == "winter"
    assert season_at(EPOCH + 28 * DAY) == "spring"
    assert season_at(EPOCH + 4 * 7 * DAY * 13 + 8 * DAY) == "summer"


def test_seasons_before_the_epoch_keep_counting_backwards():
    assert season_at(EPOCH - 1) == "winter"
    assert season_at(EPOCH - 7 * DAY) == "winter"
    assert season_at(EPOCH - 7 * DAY - 1) == "autumn"
    assert season_at(EPOCH - 28 * DAY) == "spring"


def test_season_ends_at_the_next_weekly_boundary():
    assert season_ends_at(EPOCH) == EPOCH + 7 * DAY
    assert season_ends_at(EPOCH + 3 * DAY) == EPOCH + 7 * DAY
    assert season_ends_at(EPOCH + 7 * DAY - 1) == EPOCH + 7 * DAY
    assert season_ends_at(EPOCH + 7 * DAY) == EPOCH + 14 * DAY
    assert season_ends_at(EPOCH - 1) == EPOCH
    assert season_ends_at(EPOCH - 8 * DAY) == EPOCH - 7 * DAY


def test_the_season_changes_at_the_moment_it_ends():
    for start in (EPOCH, EPOCH + 9 * DAY, EPOCH - 3 * DAY):
        ends = season_ends_at(start)
        assert season_at(ends - 1) == season_at(start)
        assert season_at(ends) != season_at(start)


def test_known_days_are_rainy_or_dry():
    assert is_rainy(date(2026, 1, 5)) is False
    assert is_rainy(date(2026, 1, 6)) is True
    assert is_rainy(date(2026, 10, 10)) is True


def test_about_a_quarter_of_the_year_is_rainy():
    first = date(2026, 1, 1).toordinal()
    rainy = sum(is_rainy(date.fromordinal(first + i)) for i in range(365))
    assert rainy == 95
    assert 70 <= rainy <= 115


def test_weather_is_rain_snow_or_sun():
    assert weather_at(at(2026, 1, 6, 12)) == "rain"
    assert weather_at(at(2026, 1, 5, 12)) == "sun"
    # 2026-01-31 is in the winter week
    assert season_at(at(2026, 1, 31)) == "winter"
    assert weather_at(at(2026, 1, 31, 12)) == "snow"
    assert weather_at(at(2026, 1, 29, 12)) == "sun"


def test_weather_follows_the_utc_day():
    assert weather_at(at(2026, 1, 6)) == "rain"
    assert weather_at(at(2026, 1, 6, 23) + 3599) == "rain"
    assert weather_at(at(2026, 1, 7)) == "rain"
    assert weather_at(at(2026, 1, 9)) == "sun"


def test_day_ends_at_the_next_utc_midnight():
    assert day_ends_at(at(2026, 3, 4, 13)) == at(2026, 3, 5)
    assert day_ends_at(at(2026, 3, 4)) == at(2026, 3, 5)
    assert day_ends_at(at(2026, 3, 5) - 1) == at(2026, 3, 5)


def test_rained_between_over_a_rainy_day():
    assert rained_between(at(2026, 1, 6), at(2026, 1, 7)) is True
    assert rained_between(at(2026, 1, 6, 10), at(2026, 1, 6, 11)) is True


def test_rained_between_over_a_dry_day():
    assert rained_between(at(2026, 1, 5), at(2026, 1, 6)) is False
    assert rained_between(at(2026, 1, 5, 3), at(2026, 1, 5, 20)) is False


def test_rained_between_crossing_midnight_into_a_rainy_day():
    assert rained_between(at(2026, 1, 5, 23), at(2026, 1, 6, 1)) is True


def test_rained_between_does_not_count_the_end_moment():
    assert rained_between(at(2026, 1, 5, 23), at(2026, 1, 6)) is False


def test_rained_between_an_empty_or_reversed_span_is_dry():
    rainy_noon = at(2026, 1, 6, 12)
    assert rained_between(rainy_noon, rainy_noon) is False
    assert rained_between(rainy_noon + HOUR, rainy_noon) is False


def test_rained_between_a_long_span_finds_any_rainy_day():
    assert rained_between(at(2026, 1, 5), at(2026, 1, 12)) is True


def test_in_season_uses_the_crops_seasons():
    # wildflowers: spring, summer, autumn. tulips: winter, spring
    assert in_season("wildflowers", EPOCH) is True
    assert in_season("wildflowers", EPOCH + 21 * DAY) is False
    assert in_season("tulips", EPOCH + 21 * DAY) is True
    assert in_season("tulips", EPOCH + 7 * DAY) is False


def test_every_crop_grows_in_real_seasons():
    for crop in CROPS.values():
        assert 2 <= len(crop.seasons) <= 3
        assert set(crop.seasons) <= set(SEASONS)
