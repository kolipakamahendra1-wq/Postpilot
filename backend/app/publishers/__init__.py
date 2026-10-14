"""Publisher adapters. `publish(post)` returns a platform reference or raises PublishError."""
from __future__ import annotations

import httpx

from .. import oauth
from ..config import get_settings


class PublishError(Exception):
    pass


def _mock(post: dict) -> str:
    return f"mock-{post['platform']}-{post['id']}"


def _bearer(provider: str) -> str:
    tokens = oauth.load_tokens(provider)
    if not tokens:
        raise PublishError(f"{provider} is not connected")
    return tokens["access_token"]


def _x(post: dict) -> str:
    # Idempotency is enforced by the service claiming the post before calling us.
    r = httpx.post(
        "https://api.twitter.com/2/tweets",
        json={"text": post["draft"]},
        headers={"Authorization": f"Bearer {_bearer('x')}"},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise PublishError(f"x HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["data"]["id"]


def _linkedin(post: dict) -> str:
    headers = {"Authorization": f"Bearer {_bearer('linkedin')}"}
    me = httpx.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=15)
    if me.status_code != 200:
        raise PublishError(f"linkedin userinfo HTTP {me.status_code}")
    body = {
        "author": f"urn:li:person:{me.json()['sub']}",
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": post["draft"]},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    r = httpx.post("https://api.linkedin.com/v2/ugcPosts", json=body, headers=headers, timeout=15)
    if r.status_code not in (200, 201):
        raise PublishError(f"linkedin HTTP {r.status_code}: {r.text[:200]}")
    return r.headers.get("x-restli-id", "linkedin-post")


def publish(post: dict) -> str:
    if get_settings().publisher == "mock":
        return _mock(post)
    return {"x": _x, "linkedin": _linkedin}[post["platform"]](post)
