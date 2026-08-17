"""The HTTP layer: retries, pacing, and what happens when answers go wrong.

`urlopen` is replaced by a stub, so these tests exercise the real retry and
error-handling code without a connection. This is the layer where a mistake is
invisible until it reaches a user, which is why it deserves tests of its own.
"""

import email.message
import gzip
import http.client
import json
import urllib.error
import urllib.request

import pytest

from etimo.wiktionary import SourceError, WiktionaryClient, _requested_delay


class Answer:
    """A stand-in for the object `urlopen` returns."""

    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}

    def read(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def page(wikitext="W"):
    return Answer(json.dumps({"parse": {"wikitext": wikitext}}).encode())


def serving(monkeypatch, *answers):
    """Make `urlopen` return the given answers in turn, then repeat the last."""
    calls = []

    def fake(_request, timeout=None):
        calls.append(timeout)
        answer = answers[min(len(calls) - 1, len(answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return calls


def http_error(code, retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("u", code, "reason", headers, None)


def client(**kwargs):
    kwargs.setdefault("min_interval", 0)
    kwargs.setdefault("warn", lambda _message: None)
    return WiktionaryClient(**kwargs)


class TestNormalAnswers:
    def test_returns_the_wikitext(self, monkeypatch):
        serving(monkeypatch, page("=={{it}}=="))
        assert client().wikitext("x") == "=={{it}}=="

    def test_missing_page_is_not_an_error(self, monkeypatch):
        # Many forms cited in etymologies have no entry: expected, not a fault.
        missing = json.dumps({"error": {"code": "missingtitle"}}).encode()
        serving(monkeypatch, Answer(missing))
        assert client().wikitext("x") is None

    def test_gzip_is_decompressed(self, monkeypatch):
        body = gzip.compress(json.dumps({"parse": {"wikitext": "G"}}).encode())
        serving(monkeypatch, Answer(body, {"Content-Encoding": "gzip"}))
        assert client().wikitext("x") == "G"

    def test_the_timeout_is_passed_down(self, monkeypatch):
        calls = serving(monkeypatch, page())
        client(timeout=7.5).wikitext("x")
        assert calls == [7.5]


class TestMalformedAnswers:
    """None of these may reach the user as a traceback."""

    @pytest.mark.parametrize(
        "answer",
        [
            Answer(b"not gzip at all", {"Content-Encoding": "gzip"}),
            Answer(bytes([0xFF, 0xFE]) + b"{}"),
            Answer(http.client.IncompleteRead(b"half", 100)),
            Answer(b"{not json"),
            Answer(json.dumps({"error": "a string, not an object"}).encode()),
            Answer(json.dumps([1, 2, 3]).encode()),
        ],
        ids=["bad-gzip", "bad-utf8", "truncated", "bad-json", "error-not-a-dict",
             "payload-not-an-object"],
    )
    def test_every_malformed_answer_becomes_a_SourceError(self, monkeypatch, answer):
        serving(monkeypatch, answer)
        with pytest.raises(SourceError):
            client(attempts=1).wikitext("x")

    def test_an_answer_without_a_page_is_not_an_absence(self, monkeypatch):
        # Returning None here would let a passing glitch be cached for thirty
        # days as "this word does not exist".
        warning = json.dumps({"warnings": {"main": "maxlag"}}).encode()
        serving(monkeypatch, Answer(warning))
        with pytest.raises(SourceError):
            client(attempts=1).wikitext("x")


class TestRetrying:
    def test_client_errors_fail_at_once(self, monkeypatch):
        calls = serving(monkeypatch, http_error(404))
        with pytest.raises(SourceError):
            client(attempts=4).wikitext("x")
        assert len(calls) == 1, "a 404 will not become a 200 by asking again"

    def test_server_errors_are_retried(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _s: None)
        calls = serving(monkeypatch, http_error(503))
        with pytest.raises(SourceError):
            client(attempts=3).wikitext("x")
        assert len(calls) == 3

    def test_a_retry_can_succeed(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _s: None)
        serving(monkeypatch, http_error(500), page("recovered"))
        assert client(attempts=3).wikitext("x") == "recovered"

    def test_retry_after_is_honoured_but_capped(self, monkeypatch):
        # A day-long Retry-After must not put the command to sleep for a day:
        # the server's instruction is respected up to a limit, then we give up
        # with a message.
        slept = []
        monkeypatch.setattr("time.sleep", slept.append)
        serving(monkeypatch, http_error(429, retry_after=86400))
        with pytest.raises(SourceError):
            client(attempts=4, max_backoff=60).wikitext("x")
        assert slept and max(slept) <= 60

    def test_retry_after_is_not_doubled(self, monkeypatch):
        # Doubling an explicit instruction from the server is arbitrary.
        slept = []
        monkeypatch.setattr("time.sleep", slept.append)
        serving(monkeypatch, http_error(429, retry_after=5))
        with pytest.raises(SourceError):
            client(attempts=2, max_backoff=60).wikitext("x")
        assert slept == [5]

    def test_an_http_date_is_not_parsed_but_does_not_break(self, monkeypatch):
        assert _requested_delay(http_error(429, "Wed, 21 Oct 2026 07:28:00 GMT")) is None

    def test_the_user_is_told_we_are_waiting(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _s: None)
        said = []
        serving(monkeypatch, http_error(503))
        with pytest.raises(SourceError):
            WiktionaryClient(min_interval=0, attempts=2, warn=said.append).wikitext("x")
        assert said, "a silent wait is indistinguishable from a hang"


class TestCourtesy:
    def test_the_user_agent_identifies_the_client(self, monkeypatch):
        monkeypatch.delenv("ETIMO_USER_AGENT", raising=False)
        agent = client().user_agent
        assert "etimo" in agent
        # Wikimedia asks for a means of contact, not just a name.
        assert "http" in agent or "@" in agent

    def test_the_user_agent_can_be_overridden_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("ETIMO_USER_AGENT", "mine/1.0 (me@example.com)")
        assert client().user_agent == "mine/1.0 (me@example.com)"

    def test_requests_are_spaced_out(self, monkeypatch):
        slept = []
        monkeypatch.setattr("time.sleep", slept.append)
        serving(monkeypatch, page())
        c = WiktionaryClient(min_interval=0.5, warn=lambda _m: None)
        c.wikitext("a")
        c.wikitext("b")
        assert slept, "the second request must wait for the courtesy interval"
