import pytest

from app import service
from app.agent import tools
from app.llm import LLMError

REAL_IS_PUBLIC_URL = tools.is_public_url

RSS = """<rss><channel>
<item><title>Rust async runtimes compared</title></item>
<item><title>Postgres 18 released</title></item>
<item><title>Why local LLMs are catching up</title></item>
</channel></rss>"""


class FakeClient:
    """Scripted model. Items are returned in order; an Exception item is raised."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, user, json_mode=False):
        self.calls.append({"system": system, "user": user, "json": json_mode})
        reply = self.replies.pop(0) if self.replies else "fallback reply"
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for k, v in {
        "POSTPILOT_DATA_DIR": str(tmp_path),
        "POSTPILOT_TOKEN": "tok",
        "POSTPILOT_SECRET_KEY": "test-secret",
        "SCHEDULER_ENABLED": "0",
        "LLM_PROVIDER": "none",
        "PUBLISHER": "mock",
        "SLACK_SIGNING_SECRET": "shh",
        "X_CLIENT_ID": "x-client",
        "X_CLIENT_SECRET": "x-secret",
    }.items():
        monkeypatch.setenv(k, v)
    service._checkpointer.cache_clear()
    monkeypatch.setattr(tools, "is_public_url", lambda url: True)
    monkeypatch.setattr(tools, "http_get", lambda url: (200, RSS if "feed" in url or "hnrss" in url else "<html><title>Page</title><body>Hello <b>world</b></body></html>"))
    yield
    service._checkpointer.cache_clear()


@pytest.fixture
def fake_llm(monkeypatch):
    def install(*replies):
        client = FakeClient(*replies)
        monkeypatch.setattr(service, "client_factory", lambda: client)
        return client

    return install


__all__ = ["FakeClient", "LLMError"]
