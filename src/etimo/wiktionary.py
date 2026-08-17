"""Access to Wiktionary wikitext.

`WikitextSource` is a Protocol: the rest of the program does not know whether
the wikitext comes from the network, from a fixture, or from the on-disk cache.
That is what lets the parser be tested without a connection and the caching
layer be added without touching anything else.

The client is a deliberate minimum — one endpoint (`action=parse`), one
property (`wikitext`) — plus the courtesies a public API deserves: a minimum
interval between requests, an identifying User-Agent as the Wikimedia terms
require, and a retry that honours the delay the server asks for.
"""

from __future__ import annotations

import gzip
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Protocol

from .version import __version__

_ENDPOINT = "https://en.wiktionary.org/w/api.php"

# The Wikimedia terms of use ask every client to identify itself with a means
# of contact. The project URL is the least a default can carry; ETIMO_USER_AGENT
# lets whoever runs it put their own address in.
_DEFAULT_USER_AGENT = (
    f"etimo/{__version__} (etymological reconstruction CLI; "
    "https://github.com/6MicheleStingo9/etimo)"
)

# Starting delay between attempts, and the longest we will ever wait: past this
# the right answer is to fail with a message, not to sleep.
_INITIAL_BACKOFF = 2.0
_MAX_BACKOFF = 60.0


class SourceError(Exception):
    """The source is unreachable or answers with something unusable."""


def _body(response) -> bytes:
    """Read the response body, decompressing it when needed."""
    data = response.read()
    if response.headers.get("Content-Encoding", "").lower() == "gzip":
        return gzip.decompress(data)
    return data


def _requested_delay(error: urllib.error.HTTPError) -> float | None:
    """The wait asked for by `Retry-After`, when expressed in seconds."""
    value = error.headers.get("Retry-After") if error.headers else None
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        # It may be an HTTP date: we do not parse it, knowing the server wants
        # patience is enough, and the backoff decides how much.
        return None


class WikitextSource(Protocol):
    """Anything that can return the wikitext of a page."""

    def wikitext(self, title: str) -> str | None:
        """The raw wikitext, or None when the page does not exist."""
        ...


class WiktionaryClient:
    """Client for the en.wiktionary.org API.

    Fetching the source rather than the rendered HTML is essential: the
    structured information lives in the templates.
    """

    def __init__(
        self,
        endpoint: str = _ENDPOINT,
        *,
        min_interval: float = 0.5,
        timeout: float = 15.0,
        attempts: int = 4,
        max_backoff: float = _MAX_BACKOFF,
        user_agent: str | None = None,
        warn: Callable[[str], None] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.min_interval = min_interval
        self.timeout = timeout
        self.attempts = attempts
        self.max_backoff = max_backoff
        self.user_agent = (
            user_agent or os.environ.get("ETIMO_USER_AGENT") or _DEFAULT_USER_AGENT
        )
        # Courtesy waits are frequent enough that whoever is watching the
        # terminal should know we are waiting, and why, instead of seeing the
        # program apparently stuck.
        self.warn = warn or (lambda _message: None)
        self.requests_made = 0
        self._last_request = 0.0

    def wikitext(self, title: str) -> str | None:
        """Download a page's wikitext, following redirects.

        Returns None when the page does not exist: that is an expected outcome,
        not an error — many forms cited in etymologies have no entry of their
        own.
        """
        params = {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "redirects": "1",
            "format": "json",
            "formatversion": "2",
        }
        response = self._request(params)

        if not isinstance(response, dict):
            raise SourceError(
                f"Wiktionary answered with {type(response).__name__}, not an object"
            )

        error = response.get("error")
        if error is not None:
            code = error.get("code", "") if isinstance(error, dict) else str(error)
            if code in ("missingtitle", "invalidtitle", "nosuchsection"):
                return None
            raise SourceError(f"Wiktionary rejected the request for «{title}»: {code}")

        parsed = response.get("parse")
        if not isinstance(parsed, dict) or "wikitext" not in parsed:
            # A well-formed answer that carries no page is not the same as "the
            # page does not exist": returning None here would let a passing
            # glitch be stored as a settled absence.
            raise SourceError(
                f"Wiktionary returned no wikitext for «{title}» and did not say why"
            )

        text = parsed["wikitext"]
        return text if isinstance(text, str) else None

    def _request(self, params: dict[str, str]) -> dict:
        """Perform the call, keeping the pace and retrying when it makes sense."""
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
                # Wiktionary entries are large and compress very well: asking
                # for gzip markedly reduces the traffic we impose on public
                # servers that are serving us for free.
                "Accept-Encoding": "gzip",
            },
        )

        delay = _INITIAL_BACKOFF
        last_error: Exception | None = None

        for attempt in range(self.attempts):
            self._respect_interval()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self.requests_made += 1
                    return json.loads(_body(response).decode("utf-8"))
            except urllib.error.HTTPError as error:
                last_error = error
                # 429 and 5xx are transient and worth retrying. Others are not.
                if error.code != 429 and error.code < 500:
                    raise SourceError(
                        f"Wiktionary answered {error.code} ({error.reason})"
                    ) from error
                # On 429 the server states how long to wait: its instruction is
                # worth more than any backoff we could guess. It is taken as
                # given, not doubled — doubling an explicit instruction is
                # arbitrary — and capped, because a CLI that sleeps for hours
                # without a word is indistinguishable from one that has hung.
                asked = _requested_delay(error)
                if asked is not None and asked > 0:
                    delay = min(asked, self.max_backoff)
                    if asked > self.max_backoff:
                        self.warn(
                            f"Wiktionary asks for {asked:.0f}s; waiting {delay:.0f}s "
                            "and giving up if it insists"
                        )
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                UnicodeDecodeError,
                http.client.HTTPException,
                gzip.BadGzipFile,
                OSError,
            ) as error:
                # Everything the transport can throw once a connection is open:
                # a truncated read, a body that is not the gzip it claims to be,
                # bytes that are not UTF-8. Each of these used to escape as a
                # traceback.
                last_error = error

            if attempt < self.attempts - 1:
                self.warn(
                    f"Wiktionary did not respond ({last_error}); "
                    f"retrying in {delay:.0f}s"
                )
                time.sleep(delay)
                delay = min(delay * 2, self.max_backoff)

        raise SourceError(
            f"Could not reach Wiktionary after {self.attempts} attempts: {last_error}"
        )

    def _respect_interval(self) -> None:
        """No more than one request every `min_interval` seconds."""
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()


class SessionMemory:
    """Avoid requesting the same page twice within one run.

    This is not a cache: nothing is written to disk and nothing outlives the
    process. It exists because different languages can share a page title —
    Italian "patria" and Latin "patria" sit in the same document, in two
    sections — and without this memory the document would be downloaded once
    per section.
    """

    def __init__(self, source: WikitextSource) -> None:
        self.source = source
        self._pages: dict[str, str | None] = {}

    def wikitext(self, title: str) -> str | None:
        if title not in self._pages:
            self._pages[title] = self.source.wikitext(title)
        return self._pages[title]

    @property
    def requests_made(self) -> int:
        """Requests that actually went out to the network, not the saved ones."""
        return getattr(self.source, "requests_made", 0)

    @property
    def cache_hits(self) -> int:
        """Reads served by a cache further down, if there is one."""
        return getattr(self.source, "cache_hits", 0)


class DictSource:
    """In-memory source for tests: title -> wikitext.

    It exists so the parser can be exercised against fixed text, without a
    network and without depending on the current state of Wiktionary.
    """

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.requests_made = 0

    def wikitext(self, title: str) -> str | None:
        self.requests_made += 1
        return self.pages.get(title)
