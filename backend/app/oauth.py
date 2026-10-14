"""OAuth2 authorization-code flow with PKCE. Tokens are encrypted at rest; `state` is single-use with a TTL."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings
from .db import connect, now_iso

STATE_TTL = 600

PROVIDERS = {
    "x": {
        "authorize": "https://twitter.com/i/oauth2/authorize",
        "token": "https://api.twitter.com/2/oauth2/token",
        "scopes": "tweet.read tweet.write users.read offline.access",
    },
    "linkedin": {
        "authorize": "https://www.linkedin.com/oauth/v2/authorization",
        "token": "https://www.linkedin.com/oauth/v2/accessToken",
        "scopes": "openid profile w_member_social",
    },
}


class OAuthError(Exception):
    pass


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().secret_key.encode()).digest())
    return Fernet(key)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def redirect_uri(provider: str) -> str:
    return f"{get_settings().public_url}/api/oauth/{provider}/callback"


def start(provider: str) -> str:
    if provider not in PROVIDERS:
        raise OAuthError("unknown provider")
    client_id = get_settings().oauth_client_ids.get(provider, "")
    if not client_id:
        raise OAuthError(f"{provider} client id is not configured")
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    with connect() as c:
        c.execute("DELETE FROM oauth_states WHERE expires_at < ?", (time.time(),))
        c.execute("INSERT INTO oauth_states VALUES (?,?,?,?)", (state, provider, verifier, time.time() + STATE_TTL))
    cfg = PROVIDERS[provider]
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri(provider),
            "scope": cfg["scopes"],
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{cfg['authorize']}?{query}"


def post_token(url: str, data: dict, auth: tuple[str, str] | None) -> dict:
    """Swapped out in tests."""
    r = httpx.post(url, data=data, auth=auth, timeout=15)
    if r.status_code != 200:
        raise OAuthError(f"token endpoint HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def finish(provider: str, code: str, state: str) -> None:
    with connect() as c:
        # DELETE ... RETURNING makes the state single-use even under concurrent callbacks.
        row = c.execute(
            "DELETE FROM oauth_states WHERE state=? RETURNING provider, verifier, expires_at", (state,)
        ).fetchone()
    if row is None or row["provider"] != provider or row["expires_at"] < time.time():
        raise OAuthError("invalid or expired state")
    s = get_settings()
    cid, csecret = s.oauth_client_ids[provider], s.oauth_client_secrets[provider]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(provider),
        "code_verifier": row["verifier"],
        "client_id": cid,
    }
    tokens = post_token(PROVIDERS[provider]["token"], data, (cid, csecret) if csecret else None)
    save_tokens(provider, tokens)


def save_tokens(provider: str, tokens: dict) -> None:
    blob = _fernet().encrypt(json.dumps(tokens).encode()).decode()
    with connect() as c:
        c.execute(
            "INSERT INTO oauth_tokens VALUES (?,?,?) ON CONFLICT(provider) DO UPDATE SET blob=excluded.blob, updated_at=excluded.updated_at",
            (provider, blob, now_iso()),
        )


def load_tokens(provider: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT blob FROM oauth_tokens WHERE provider=?", (provider,)).fetchone()
    if row is None:
        return None
    try:
        return json.loads(_fernet().decrypt(row["blob"].encode()))
    except InvalidToken:
        return None


def status() -> list[dict]:
    s = get_settings()
    out = []
    for p in PROVIDERS:
        with connect() as c:
            row = c.execute("SELECT updated_at FROM oauth_tokens WHERE provider=?", (p,)).fetchone()
        out.append({"provider": p, "configured": bool(s.oauth_client_ids.get(p)), "connected": row is not None, "updated_at": row["updated_at"] if row else None})
    return out
