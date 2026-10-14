import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app import oauth, slack
from app.db import connect
from app.main import app

H = {"Authorization": "Bearer tok"}
BRIEF = "Announce our open source release of Postpilot, a human approved social agent"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def slack_request(client, secret, post_id, action, ts=None, tamper=False):
    body = ("payload=" + json.dumps({"actions": [{"action_id": action, "value": str(post_id)}]})).replace(" ", "%20").encode()
    ts = ts or str(int(time.time()))
    sig = slack.sign(secret, ts, body)
    if tamper:
        body += b"x"
    return client.post("/slack/actions", content=body, headers={"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": sig, "Content-Type": "application/x-www-form-urlencoded"})


# ---- API ----

def test_health_is_open_but_everything_else_needs_a_token(client):
    assert client.get("/api/health").json()["ok"]
    for path in ("/api/posts", "/api/campaigns", "/api/audit", "/api/connections"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.post("/api/posts", json={"brief": "hello world"}).status_code == 401


def test_full_flow_over_http(client):
    post = client.post("/api/posts", headers=H, json={"brief": BRIEF, "platform": "x", "use_llm": False}).json()
    assert post["status"] == "pending_approval"
    assert client.get("/api/posts?status=pending_approval", headers=H).json()[0]["id"] == post["id"]
    done = client.post(f"/api/posts/{post['id']}/decision", headers=H, json={"action": "approve"}).json()
    assert done["status"] == "scheduled"
    published = client.post("/api/scheduler/tick", headers=H).json()
    assert published[0]["status"] == "published"
    assert client.post(f"/api/posts/{post['id']}/decision", headers=H, json={"action": "reject"}).status_code == 409


def test_api_error_mapping(client):
    assert client.get("/api/posts/404", headers=H).status_code == 404
    assert client.post("/api/posts", headers=H, json={"brief": "hello there", "platform": "myspace"}).status_code == 422
    assert client.post("/api/posts", headers=H, json={"brief": "x"}).status_code == 422
    assert client.post("/api/campaigns", headers=H, json={"name": "n", "brief": "some brief", "cron": "bad"}).status_code == 422


# ---- Slack ----

def test_signature_rules():
    body, ts = b"payload=1", "1000"
    good = slack.sign("s", ts, body)
    assert slack.verify_signature("s", ts, body, good, now=1000)
    assert not slack.verify_signature("s", ts, body, good, now=1000 + 301)  # replay
    assert not slack.verify_signature("s", ts, body + b"!", good, now=1000)  # tamper
    assert not slack.verify_signature("other", ts, body, good, now=1000)
    assert not slack.verify_signature("", ts, body, good, now=1000)  # unconfigured secret never passes
    assert not slack.verify_signature("s", "abc", body, good, now=1000)


def test_slack_button_approves_a_post(client):
    post = client.post("/api/posts", headers=H, json={"brief": BRIEF, "use_llm": False}).json()
    r = slack_request(client, "shh", post["id"], "approve")
    assert r.status_code == 200 and "scheduled" in r.json()["text"]
    assert slack_request(client, "shh", post["id"], "reject").status_code == 409


def test_slack_rejects_bad_signature_and_stale_timestamp(client):
    post = client.post("/api/posts", headers=H, json={"brief": BRIEF, "use_llm": False}).json()
    assert slack_request(client, "wrong-secret", post["id"], "approve").status_code == 401
    assert slack_request(client, "shh", post["id"], "approve", tamper=True).status_code == 401
    assert slack_request(client, "shh", post["id"], "approve", ts="1000").status_code == 401
    assert client.get(f"/api/posts/{post['id']}", headers=H).json()["status"] == "pending_approval"


def test_slack_message_has_buttons_and_flags():
    post = {"id": 7, "platform": "x", "draft": "hello", "rule_report": {"violations": [{"message": "too long"}]}}
    msg = slack.build_message(post)
    ids = [e["action_id"] for b in msg["blocks"] if b["type"] == "actions" for e in b["elements"]]
    assert ids == ["approve", "reject"] and "too long" in json.dumps(msg)


# ---- OAuth ----

def test_oauth_start_builds_pkce_url(client):
    url = client.get("/api/oauth/x/start", headers=H).json()["url"]
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert q["code_challenge_method"] == "S256" and q["client_id"] == "x-client" and "tweet.write" in q["scope"]
    with connect() as c:
        verifier = c.execute("SELECT verifier FROM oauth_states WHERE state=?", (q["state"],)).fetchone()["verifier"]
    assert q["code_challenge"] == oauth.base64.urlsafe_b64encode(oauth.hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def test_oauth_unconfigured_or_unknown_provider(client, monkeypatch):
    monkeypatch.delenv("LINKEDIN_CLIENT_ID", raising=False)
    assert client.get("/api/oauth/linkedin/start", headers=H).status_code == 422
    assert client.get("/api/oauth/myspace/start", headers=H).status_code == 422


def _state(client):
    url = client.get("/api/oauth/x/start", headers=H).json()["url"]
    return parse_qs(urlparse(url).query)["state"][0]


def test_callback_exchanges_code_once_and_encrypts_tokens(client, monkeypatch):
    seen = {}

    def fake_post(url, data, auth):
        seen.update(url=url, data=data, auth=auth)
        return {"access_token": "SUPER-SECRET-ACCESS", "refresh_token": "r"}

    monkeypatch.setattr(oauth, "post_token", fake_post)
    state = _state(client)
    r = client.get(f"/api/oauth/x/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 307 and "connected=x" in r.headers["location"]
    assert seen["data"]["code_verifier"] and seen["data"]["code"] == "abc" and seen["auth"] == ("x-client", "x-secret")
    with connect() as c:
        raw = c.execute("SELECT blob FROM oauth_tokens").fetchone()["blob"]
    assert "SUPER-SECRET" not in raw
    assert oauth.load_tokens("x")["access_token"] == "SUPER-SECRET-ACCESS"
    assert [c for c in client.get("/api/connections", headers=H).json() if c["provider"] == "x"][0]["connected"]
    replay = client.get(f"/api/oauth/x/callback?code=abc&state={state}", follow_redirects=False)
    assert "error=" in replay.headers["location"]  # state is single use


def test_callback_rejects_forged_expired_and_cross_provider_state(client, monkeypatch):
    monkeypatch.setattr(oauth, "post_token", lambda *a, **k: pytest.fail("must not exchange"))
    assert "error=" in client.get("/api/oauth/x/callback?code=a&state=forged", follow_redirects=False).headers["location"]
    state = _state(client)
    assert "error=" in client.get(f"/api/oauth/linkedin/callback?code=a&state={state}", follow_redirects=False).headers["location"]
    state2 = _state(client)
    with connect() as c:
        c.execute("UPDATE oauth_states SET expires_at=0 WHERE state=?", (state2,))
    assert "error=" in client.get(f"/api/oauth/x/callback?code=a&state={state2}", follow_redirects=False).headers["location"]


def test_tokens_cannot_be_read_with_another_secret(monkeypatch):
    oauth.save_tokens("x", {"access_token": "a"})
    monkeypatch.setenv("POSTPILOT_SECRET_KEY", "different")
    assert oauth.load_tokens("x") is None


def test_live_publisher_without_connection_fails_cleanly(client, monkeypatch):
    monkeypatch.setenv("PUBLISHER", "live")
    post = client.post("/api/posts", headers=H, json={"brief": BRIEF, "use_llm": False}).json()
    client.post(f"/api/posts/{post['id']}/decision", headers=H, json={"action": "approve"})
    out = client.post("/api/scheduler/tick", headers=H).json()
    assert out[0]["status"] == "scheduled" and "not connected" in out[0]["error"]
