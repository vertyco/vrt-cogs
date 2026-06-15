import threading

from assistant.common.conversation_store import ConversationStore
from assistant.common.models import Conversation


def test_save_and_load_roundtrip(tmp_path):
    store = ConversationStore(tmp_path)
    store.save("1-2-3", {"messages": [{"role": "user", "content": "hi"}]})
    store.save("4-5-6", {"messages": []})

    loaded = store.load_all()

    assert loaded == {
        "1-2-3": {"messages": [{"role": "user", "content": "hi"}]},
        "4-5-6": {"messages": []},
    }


def test_save_overwrites_existing_key(tmp_path):
    store = ConversationStore(tmp_path)
    store.save("1-2-3", {"messages": [{"role": "user", "content": "first"}]})
    store.save("1-2-3", {"messages": [{"role": "user", "content": "second"}]})

    loaded = store.load_all()

    assert loaded["1-2-3"]["messages"][0]["content"] == "second"


def test_delete_removes_one_key(tmp_path):
    store = ConversationStore(tmp_path)
    store.save("1-2-3", {"messages": []})
    store.save("4-5-6", {"messages": []})

    store.delete("1-2-3")

    assert set(store.load_all()) == {"4-5-6"}


def test_delete_missing_key_is_silent(tmp_path):
    store = ConversationStore(tmp_path)
    store.delete("9-9-9")  # must not raise


def test_clear_removes_everything(tmp_path):
    store = ConversationStore(tmp_path)
    store.save("1-2-3", {"messages": []})
    store.save("4-5-6", {"messages": []})

    store.clear()

    assert store.load_all() == {}


def test_load_all_on_empty_dir_returns_empty(tmp_path):
    store = ConversationStore(tmp_path)
    assert store.load_all() == {}


def test_corrupt_file_is_skipped_not_fatal(tmp_path):
    store = ConversationStore(tmp_path)
    store.save("1-2-3", {"messages": []})
    (store.dir / "bad-bad-bad.json").write_text("{not json", encoding="utf-8")

    loaded = store.load_all()

    assert set(loaded) == {"1-2-3"}  # good file loads, corrupt one skipped


def test_concurrent_saves_same_key_do_not_raise(tmp_path):
    store = ConversationStore(tmp_path)
    errors = []

    def writer(n):
        try:
            for _ in range(20):
                store.save("1-2-3", {"messages": [{"role": "user", "content": str(n)}]})
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    loaded = store.load_all()
    assert "1-2-3" in loaded  # a valid final file survives, no orphans break load


def test_conversation_roundtrips_through_store(tmp_path):
    # Mirrors save_conversation's real path: Conversation.model_dump() (the override already
    # forces mode="json"; passing mode= again is a TypeError) -> store.save -> load_all -> validate.
    store = ConversationStore(tmp_path)
    convo = Conversation(messages=[{"role": "user", "content": "hi"}])

    store.save("1-2-3", convo.model_dump())
    restored = Conversation.model_validate(store.load_all()["1-2-3"])

    assert restored.messages == [{"role": "user", "content": "hi"}]
