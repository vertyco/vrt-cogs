import math
from datetime import datetime, timezone

import pytest

from activityhub.common.replies import dumps, loads


def test_dumps_is_compact_and_turns_number_keys_into_text():
    assert dumps({"a": [1, 2], 3: "x", "name": "Café"}) == '{"a":[1,2],"3":"x","name":"Café"}'


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_dumps_refuses_nan_and_infinity(value):
    # orjson would write them as null, which would hide a bug like a score that became NaN
    with pytest.raises(ValueError):
        dumps({"score": value})
    with pytest.raises(ValueError):
        dumps({"nothing": None, "score": value})


def test_dumps_keeps_null_and_text_that_says_null():
    assert dumps({"x": None, "word": "nullify"}) == '{"x":null,"word":"nullify"}'


def test_the_null_check_accepts_what_only_orjson_can_write():
    when = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert dumps({"when": when, "x": None}) == '{"when":"2026-01-02T00:00:00+00:00","x":null}'


def test_loads_reads_what_the_json_module_reads():
    assert loads('{"a": 1}') == {"a": 1}
    # Half of an emoji, which a page's JSON.stringify sends when it cuts a string in two, and orjson refuses
    assert loads('"\\ud83d"') == "\ud83d"
    with pytest.raises(ValueError):
        loads("not json")
