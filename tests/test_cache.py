"""Local storage of downloaded pages."""

import sqlite3
import time

import pytest

from etimo.cache import DiskCache, clear
from etimo.wiktionary import DictSource

PAGES = {"fuoco": "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|focus}}.\n"}


@pytest.fixture
def path(tmp_path):
    return tmp_path / "pages.sqlite"


class TestStorage:
    def test_second_read_does_not_touch_the_source(self, path):
        source = DictSource(PAGES)
        cache = DiskCache(source, path=path)

        first = cache.wikitext("fuoco")
        second = cache.wikitext("fuoco")

        assert first == second
        assert source.requests_made == 1
        assert cache.cache_hits == 1

    def test_survives_being_closed(self, path):
        source = DictSource(PAGES)
        first = DiskCache(source, path=path)
        first.wikitext("fuoco")
        first.close()

        # An empty source: if the data arrives, it comes from disk.
        second = DiskCache(DictSource({}), path=path)
        assert second.wikitext("fuoco") == PAGES["fuoco"]

    def test_missing_entry_is_stored(self, path):
        # Forms cited without an entry of their own are common: asking for them
        # on every run would be the most useless traffic of all.
        source = DictSource({})
        cache = DiskCache(source, path=path)

        assert cache.wikitext("missing-entry") is None
        assert cache.wikitext("missing-entry") is None
        assert source.requests_made == 1
        assert cache.cache_hits == 1

    def test_missing_entry_distinguished_from_empty_page(self, path):
        cache = DiskCache(DictSource({"empty": ""}), path=path)
        assert cache.wikitext("empty") == ""
        assert cache.wikitext("empty") == ""
        assert cache.wikitext("absent") is None


class TestExpiry:
    def test_expired_entry_is_fetched_again(self, path):
        source = DictSource(PAGES)
        DiskCache(source, path=path).wikitext("fuoco")

        # Backdate the entry beyond its lifetime.
        with sqlite3.connect(path) as db:
            db.execute("UPDATE pages SET fetched_at = ?", (time.time() - 31 * 86_400,))

        DiskCache(source, path=path, ttl_days=30).wikitext("fuoco")
        assert source.requests_made == 2

    def test_fresh_entry_is_not_fetched(self, path):
        source = DictSource(PAGES)
        DiskCache(source, path=path).wikitext("fuoco")
        DiskCache(source, path=path, ttl_days=30).wikitext("fuoco")
        assert source.requests_made == 1


class TestRobustness:
    def test_unwritable_path_does_not_interrupt(self, tmp_path):
        # The cache is an optimisation: its failure must not prevent the walk,
        # which works over the network regardless.
        obstacle = tmp_path / "file"
        obstacle.write_text("not a directory")
        warnings = []

        cache = DiskCache(
            DictSource(PAGES), path=obstacle / "pages.sqlite", warn=warnings.append
        )

        assert cache.wikitext("fuoco") == PAGES["fuoco"]
        assert warnings and "cache" in warnings[0]

    def test_unreadable_database_degrades_to_the_network(self, path):
        path.write_bytes(b"this is not an sqlite database")
        warnings = []
        source = DictSource(PAGES)

        cache = DiskCache(source, path=path, warn=warnings.append)
        assert cache.wikitext("fuoco") == PAGES["fuoco"]
        assert warnings


class TestClearing:
    def test_removes_the_file(self, path):
        DiskCache(DictSource(PAGES), path=path).wikitext("fuoco")
        assert path.exists()

        succeeded, message = clear(path)
        assert succeeded
        assert not path.exists()
        assert "cleared" in message

    def test_clearing_a_missing_cache_is_not_an_error(self, tmp_path):
        succeeded, message = clear(tmp_path / "never-created.sqlite")
        assert succeeded
        assert "No cache" in message


class TestPruning:
    """Expiry alone never shrinks the file."""

    def test_expired_entries_are_dropped(self, path):
        source = DictSource({f"w{i}": f"==Italian==\n\n===Etymology===\nx{i}\n"
                             for i in range(20)})
        cache = DiskCache(source, path=path)
        for i in range(20):
            cache.wikitext(f"w{i}")
        cache.close()

        with sqlite3.connect(path) as db:
            db.execute("UPDATE pages SET fetched_at = ?", (time.time() - 40 * 86_400,))

        cache = DiskCache(source, path=path)
        removed, _ = cache.prune()
        assert removed == 20
        assert cache.stats()[0] == 0

    def test_fresh_entries_survive_pruning(self, path):
        source = DictSource({"fuoco": PAGES["fuoco"]})
        cache = DiskCache(source, path=path)
        cache.wikitext("fuoco")
        removed, _ = cache.prune()
        assert removed == 0
        assert cache.stats()[0] == 1

    def test_pruning_a_broken_cache_is_harmless(self, path):
        path.write_bytes(b"not a database")
        cache = DiskCache(DictSource({}), path=path, warn=lambda _m: None)
        assert cache.prune() == (0, 0.0)
