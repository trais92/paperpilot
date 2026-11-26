"""Vertragstest für den Port `StorageTarget`.

Jeder Adapter (heute `LocalStore` und `MemoryStore`, später Google Drive) muss diese Tests bestehen.
Ein neuer Adapter wird in `store_factory` eingetragen, sonst nichts.
"""

from datetime import datetime

import pytest

from paperpilot_ops.ports import StorageTarget
from paperpilot_ops.store import LocalStore, MemoryStore, sha256


@pytest.fixture(params=["local", "memory"])
def store_factory(request, tmp_path):
    """Liefert eine Funktion, die das Ablageziel neu öffnet (wie ein späterer Lauf)."""
    if request.param == "local":
        return lambda: LocalStore(tmp_path)
    memory = MemoryStore()
    return lambda: memory


def test_satisfies_protocol(store_factory):
    store: StorageTarget = store_factory()
    assert isinstance(store.location, str) and store.location


def test_write_file_never_overwrites(store_factory):
    store = store_factory()
    first = store.write_file("x/a.txt", b"1")
    second = store.write_file("x/a.txt", b"2")
    third = store.write_file("x/a.txt", b"3")
    assert (first, second, third) == ("x/a.txt", "x/a-2.txt", "x/a-3.txt")


def test_written_content_is_known_as_duplicate(store_factory):
    store = store_factory()
    assert not store.has(sha256(b"inhalt"))
    store.write_file("doc.pdf", b"inhalt")
    assert store.has(sha256(b"inhalt"))


def test_duplicate_index_survives_reopen_after_save(store_factory):
    store = store_factory()
    store.write_file("doc.pdf", b"inhalt")
    store.save(None)
    assert store_factory().has(sha256(b"inhalt"))


def test_read_text_missing_is_none(store_factory):
    assert store_factory().read_text("gibt/es/nicht.csv") is None


def test_write_text_replaces_and_keeps_line_endings(store_factory):
    store = store_factory()
    store.write_text("Fristen/fristen.ics", "A\r\nB\r\n")
    store.write_text("Fristen/fristen.ics", "C\r\nD\r\n")
    assert store_factory().read_text("Fristen/fristen.ics") == "C\r\nD\r\n"


def test_last_run_never_goes_back(store_factory):
    store = store_factory()
    assert store.last_run() is None
    store.save(datetime(2026, 11, 20, 10, 0))
    store_factory().save(datetime(2026, 11, 1, 10, 0))  # älterer Lauf darf den Stand nicht zurücksetzen
    store_factory().save(None)
    assert store_factory().last_run() == datetime(2026, 11, 20, 10, 0)
