"""Local storage of already downloaded pages.

Etymological chains converge: thousands of Italian words go back to a few
hundred Indo-European roots, and the upper entries — `pater`, `*patēr`,
`*ph₂tḗr` — are requested by every word of the family. Keeping them locally
avoids repeatedly asking a public service for data that rarely changes.

Three choices deserve a word.

**Missing entries are stored too.** Many forms cited in etymologies have no
page of their own. Without recording the absence, every run would go back to
ask for them, which is precisely the most useless traffic there is.

**Entries expire.** Wiktionary is corrected over time, and a perpetual local
copy would give stale answers without saying so. The default lifetime is thirty
days: long enough to silence the traffic during a working session, short enough
not to fossilise the data.

**A cache failure does not stop the tool.** If the file is not writable or the
database unreadable, the walk continues over the network with a warning: the
cache is an optimisation, not a dependency.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

from .wiktionary import WikitextSource

DEFAULT_TTL_DAYS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    title      TEXT PRIMARY KEY,
    wikitext   TEXT,
    found      INTEGER NOT NULL,
    fetched_at REAL    NOT NULL
);
"""


def default_path() -> Path:
    """The cache file, following the XDG conventions."""
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "etimo" / "pages.sqlite"


class DiskCache:
    """Wraps a source, keeping its answers in a local database."""

    def __init__(
        self,
        source: WikitextSource,
        *,
        path: Path | None = None,
        ttl_days: float = DEFAULT_TTL_DAYS,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self.source = source
        self.path = Path(path) if path else default_path()
        self.ttl = ttl_days * 86_400
        self.warn = warn or (lambda _message: None)
        self.cache_hits = 0
        self._db: sqlite3.Connection | None = self._open()

    # -- Lifecycle -----------------------------------------------------------

    def _open(self) -> sqlite3.Connection | None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path, timeout=5.0)
            # Write-ahead logging lets a second etimo read while the first
            # writes. Without it two runs in parallel meet "database is locked"
            # and one of them silently gives up its cache.
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(_SCHEMA)
            db.commit()
            return db
        except (sqlite3.Error, OSError) as error:
            self.warn(f"cache unavailable ({error}); continuing over the network")
            return None

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def __enter__(self) -> DiskCache:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _give_up(self, error: Exception) -> None:
        """Disable the cache after a failure, without interrupting the walk."""
        self.warn(f"cache disabled ({error}); continuing over the network")
        try:
            if self._db is not None:
                self._db.close()
        except sqlite3.Error:
            pass
        self._db = None

    # -- WikitextSource interface -------------------------------------------

    def wikitext(self, title: str) -> str | None:
        stored = self._read(title)
        if stored is not None:
            self.cache_hits += 1
            found, text = stored
            return text if found else None

        text = self.source.wikitext(title)
        self._write(title, text)
        return text

    @property
    def requests_made(self) -> int:
        """Requests that actually went out to the network."""
        return getattr(self.source, "requests_made", 0)

    # -- Database access -----------------------------------------------------

    def _read(self, title: str) -> tuple[bool, str | None] | None:
        """The stored entry, if present and not expired."""
        if self._db is None:
            return None
        try:
            row = self._db.execute(
                "SELECT wikitext, found, fetched_at FROM pages WHERE title = ?",
                (title,),
            ).fetchone()
        except sqlite3.Error as error:
            self._give_up(error)
            return None

        if row is None:
            return None

        text, found, fetched_at = row
        if time.time() - fetched_at > self.ttl:
            # Drop it now rather than wait for a rewrite that may never come:
            # a page looked up once and never again would otherwise sit in the
            # file for good, and the file would only ever grow.
            self._forget(title)
            return None
        return bool(found), text

    def _forget(self, title: str) -> None:
        if self._db is None:
            return
        try:
            self._db.execute("DELETE FROM pages WHERE title = ?", (title,))
            self._db.commit()
        except sqlite3.Error as error:
            self._give_up(error)

    def _write(self, title: str, text: str | None) -> None:
        if self._db is None:
            return
        try:
            self._db.execute(
                "INSERT OR REPLACE INTO pages "
                "(title, wikitext, found, fetched_at) VALUES (?, ?, ?, ?)",
                (title, text, int(text is not None), time.time()),
            )
            self._db.commit()
        except sqlite3.Error as error:
            self._give_up(error)

    # -- Maintenance ---------------------------------------------------------

    def prune(self) -> tuple[int, float]:
        """Drop every expired entry and reclaim the space.

        Expiry alone never shrinks the file: an entry is only dropped when it
        is read again, so pages looked up once and never revisited stay for
        good. `VACUUM` is what actually returns the space — without it SQLite
        keeps the freed pages for its own reuse and the file never gets
        smaller.

        Returns how many entries were removed and how many MB were reclaimed.
        """
        if self._db is None:
            return 0, 0.0

        before = self.path.stat().st_size if self.path.exists() else 0
        try:
            cursor = self._db.execute(
                "DELETE FROM pages WHERE fetched_at < ?", (time.time() - self.ttl,)
            )
            removed = cursor.rowcount
            self._db.commit()
            # VACUUM cannot run inside a transaction, and sqlite3 opens one for
            # us on every statement unless isolation is off for the call.
            self._db.isolation_level = None
            self._db.execute("VACUUM")
            self._db.isolation_level = "DEFERRED"
        except sqlite3.Error as error:
            self._give_up(error)
            return 0, 0.0

        after = self.path.stat().st_size if self.path.exists() else 0
        return removed, (before - after) / 1_048_576

    def stats(self) -> tuple[int, float]:
        """Number of stored entries and file size in MB."""
        if self._db is None:
            return 0, 0.0
        try:
            (entries,) = self._db.execute("SELECT COUNT(*) FROM pages").fetchone()
        except sqlite3.Error:
            return 0, 0.0
        size = self.path.stat().st_size / 1_048_576 if self.path.exists() else 0.0
        return entries, size


def clear(path: Path | None = None) -> tuple[bool, str]:
    """Delete the cache file. Returns (succeeded, message)."""
    target = Path(path) if path else default_path()

    if not target.exists():
        return True, f"No cache to clear at {target}."

    size = target.stat().st_size / 1_048_576
    try:
        target.unlink()
    except OSError as error:
        return False, f"Could not remove {target}: {error}"
    return True, f"Cache cleared: {target} ({size:.1f} MB)."
