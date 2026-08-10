from swearjar.common.utils import build_pattern, find_matches, normalize


def cfg(boundary: bool = True) -> dict:
    return {"fine": None, "boundary": boundary}


def test_normalize_casefold_and_symbol_leet():
    assert normalize("A$$HOLE") == "asshole"
    assert normalize("@$$") == "ass"


def test_normalize_substitutes_digits_only_inside_words():
    assert normalize("Sh!7") == "shit"
    assert normalize("d4mn") == "damn"
    assert normalize("we hit 455 damage") == "we hit 455 damage"


def test_build_pattern_substring_has_no_boundaries():
    pattern = build_pattern("ass", False)
    assert not pattern.startswith(r"\b")
    assert not pattern.endswith(r"\b")


def test_build_pattern_rejects_wordless_entries():
    assert build_pattern("", True) is None
    assert build_pattern("!!!", True) is None


def test_boundary_word_does_not_match_inside_other_word():
    words = {"ass": cfg(boundary=True)}
    assert find_matches("I have a class today", words) == []


def test_boundary_word_matches_plain():
    words = {"ass": cfg(boundary=True)}
    assert find_matches("what an ASS", words) == ["ass"]


def test_boundary_word_matches_obfuscated():
    words = {"ass": cfg(boundary=True)}
    assert find_matches("what an a.s.s move", words) == ["ass"]
    assert find_matches("what an @$$ move", words) == ["ass"]
    assert find_matches("what an a-s-s move", words) == ["ass"]


def test_single_word_match_does_not_span_whitespace():
    words = {"ass": cfg(boundary=True)}
    assert find_matches("send a ss of the error", words) == []


def test_plain_numbers_are_not_read_as_words():
    words = {"ass": cfg(boundary=True)}
    assert find_matches("we hit 455 damage", words) == []


def test_multi_word_phrase_matches_spaced_and_joined():
    words = {"son of a bitch": cfg(boundary=True)}
    assert find_matches("you son of a bitch", words) == ["son of a bitch"]
    assert find_matches("you sonofabitch", words) == ["son of a bitch"]


def test_substring_word_matches_inside_other_word():
    words = {"fuck": cfg(boundary=False)}
    assert find_matches("absofuckinglutely", words) == ["fuck"]


def test_substring_word_matches_obfuscated_inside_other_word():
    words = {"fuck": cfg(boundary=False)}
    assert find_matches("abso-f-u-c-k-ing-lutely", words) == ["fuck"]


def test_word_counted_once_per_message():
    words = {"damn": cfg()}
    assert find_matches("damn damn damn", words) == ["damn"]


def test_multiple_words_matched():
    words = {"damn": cfg(), "hell": cfg()}
    assert sorted(find_matches("damn this hell", words)) == ["damn", "hell"]


def test_empty_word_list():
    assert find_matches("damn", {}) == []


def test_clean_message():
    words = {"damn": cfg()}
    assert find_matches("what a lovely day", words) == []


def test_malformed_word_entry_is_skipped():
    words = {"!!!": cfg(), "damn": cfg()}
    assert find_matches("damn it", words) == ["damn"]


def test_apostrophe_contractions_are_not_false_positives():
    words = {"hell": cfg()}
    assert find_matches("he'll be here soon", words) == []
    assert find_matches("he’ll be here soon", words) == []
    assert find_matches("she'll do it", words) == []
    assert find_matches("I'll go", words) == []
    assert find_matches("we'll see", words) == []


def test_hell_still_matches_plain_and_obfuscated():
    words = {"hell": cfg()}
    assert find_matches("hell yeah", words) == ["hell"]
    assert find_matches("what the h-e-l-l", words) == ["hell"]


def test_configured_apostrophe_entry_matches_its_literal_form():
    words = {"y'all": cfg()}
    assert find_matches("y'all better run", words) == ["y'all"]
    assert find_matches("yall better run", words) == []


def test_leading_or_trailing_apostrophe_entry_still_matches():
    words = {"fuckin'": cfg()}
    assert find_matches("that is fuckin' great", words) == ["fuckin'"]
    assert find_matches("fuckin'", words) == ["fuckin'"]

    words = {"'tis": cfg()}
    assert find_matches("'tis the season", words) == ["'tis"]


def test_straight_and_curly_apostrophe_are_interchangeable():
    words = {"y'all": cfg()}
    assert find_matches("y'all better run", words) == ["y'all"]
    assert find_matches("y’all better run", words) == ["y'all"]

    words = {"y’all": cfg()}
    assert find_matches("y'all better run", words) == ["y’all"]
    assert find_matches("y’all better run", words) == ["y’all"]


def test_contraction_guard_still_holds_with_curly_apostrophe():
    words = {"hell": cfg()}
    assert find_matches("he'll be here", words) == []
    assert find_matches("he’ll be here", words) == []
    assert find_matches("hell yeah", words) == ["hell"]
