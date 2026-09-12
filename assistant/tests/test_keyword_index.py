import pytest

from assistant.common.embedding_store import EmbeddingStore
from assistant.common.keyword_index import KeywordIndex, tokenize

DOCS = {
    "ark rates": "Harvest rates are 3x on weekdays and 5x on weekends across all ARK servers.",
    "discord rules": "Be respectful in the Discord. No spam, no advertising other servers.",
    "tickets": "Open a support ticket in the tickets channel and a staff member will help.",
}


def test_tokenize_lowercases_and_strips_punctuation():
    assert tokenize("Hello, World! 3x-rates") == ["hello", "world", "3x", "rates"]


def test_search_ranks_term_overlap_and_normalises_scores():
    index = KeywordIndex()
    index.build(DOCS)
    hits = index.search("what are the harvest rates on weekends", top_n=3)
    assert hits[0][0] == "ark rates"
    assert hits[0][1] == 1.0
    assert all(0 < score <= 1.0 for _, score in hits)


def test_search_drops_documents_with_no_overlap():
    index = KeywordIndex()
    index.build(DOCS)
    hits = index.search("staff ticket", top_n=3)
    assert [name for name, _ in hits] == ["tickets"]


def test_search_empty_cases():
    index = KeywordIndex()
    assert index.search("anything", top_n=3) == []
    index.build(DOCS)
    assert index.search("", top_n=3) == []
    assert index.search("rates", top_n=0) == []
    assert index.search("zzz qqq", top_n=3) == []


def test_top_n_caps_results():
    index = KeywordIndex()
    index.build(DOCS)
    assert len(index.search("servers", top_n=1)) == 1


@pytest.mark.asyncio
async def test_store_keyword_search_and_cache_invalidation(tmp_path):
    store = EmbeddingStore(tmp_path)
    await store.initialize()
    guild = 1
    await store.add(guild, "ark rates", DOCS["ark rates"], [0.1, 0.2], "fake")
    await store.add(guild, "tickets", DOCS["tickets"], [0.3, 0.4], "fake")

    hits = await store.keyword_search(guild, "harvest rates weekend", top_n=3)
    assert hits[0][0] == "ark rates"
    assert hits[0][1] == DOCS["ark rates"]
    assert hits[0][2] == 1.0
    assert hits[0][3] == 2
    assert guild in store.keyword_indexes

    await store.add(guild, "discord rules", DOCS["discord rules"], [0.5, 0.6], "fake")
    assert guild not in store.keyword_indexes
    hits = await store.keyword_search(guild, "spam advertising", top_n=3)
    assert hits[0][0] == "discord rules"

    await store.delete(guild, "discord rules")
    assert guild not in store.keyword_indexes
    assert await store.keyword_search(guild, "spam advertising", top_n=3) == []

    await store.delete_all(guild)
    assert await store.keyword_search(guild, "harvest", top_n=3) == []
    assert await store.keyword_search(guild, "", top_n=3) == []
