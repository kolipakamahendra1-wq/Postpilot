"""Slack approvals: Block Kit message out, signed button callback in."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

import httpx

from .config import get_settings

MAX_SKEW = 60 * 5


def verify_signature(secret: str, timestamp: str, body: bytes, signature: str, now: float | None = None) -> bool:
    """Slack v0 scheme: HMAC-SHA256 over `v0:{ts}:{body}`. Reject stale timestamps to stop replays."""
    if not secret:
        return False
    try:
        age = abs((now or time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > MAX_SKEW:
        return False
    base = f"v0:{timestamp}:".encode() + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Used by tests and the demo script to forge a valid request."""
    base = f"v0:{timestamp}:".encode() + body
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def build_message(post: dict) -> dict:
    pid = str(post["id"])
    flagged = [v["message"] for v in post["rule_report"].get("violations", [])]
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Post #{pid} awaiting approval ({post['platform']})"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": post["draft"]}},
    ]
    if flagged:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Rule flags: " + "; ".join(flagged)}]})
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {"type": "button", "action_id": "approve", "value": pid, "style": "primary", "text": {"type": "plain_text", "text": "Approve"}},
                {"type": "button", "action_id": "reject", "value": pid, "style": "danger", "text": {"type": "plain_text", "text": "Reject"}},
            ],
        }
    )
    return {"text": f"Post #{pid} awaiting approval", "blocks": blocks}


def notify(post: dict) -> str:
    """Send to the webhook, or report that Slack is not configured. Never raises."""
    url = get_settings().slack_webhook_url
    if not url:
        return "skipped: SLACK_WEBHOOK_URL not set"
    try:
        r = httpx.post(url, json=build_message(post), timeout=10)
        return "sent" if r.status_code == 200 else f"failed: HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return f"failed: {exc}"


def parse_action(body: bytes) -> tuple[str, int]:
    """Slack posts `payload=<json>` form-encoded. Return (action_id, post_id)."""
    payload = json.loads(parse_qs(body.decode())["payload"][0])
    action = payload["actions"][0]
    return action["action_id"], int(action["value"])
