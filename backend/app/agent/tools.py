"""Tools the agent can call. Each is a plain function with a JSON-able result; the registry doubles as the schema."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urlparse

import httpx

from .. import rules
from ..config import get_settings
from ..llm import Client, LLMError

MAX_BYTES = 200_000
NAT64 = ipaddress.ip_network("64:ff9b::/96")
STOPWORDS = set("this that with from your about have will into more than what when where which their there been some".split())


class ToolError(Exception):
    pass


def is_public_url(url: str) -> bool:
    """SSRF guard: http(s) only, and every resolved address must be public."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip in NAT64:  # IPv6-only networks: judge the embedded IPv4 address instead
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def http_get(url: str) -> tuple[int, str]:
    """Swapped out in tests. No redirects, so a public URL cannot bounce us to an internal one."""
    with httpx.stream("GET", url, timeout=10, follow_redirects=False) as r:
        data = b""
        for chunk in r.iter_bytes():
            data += chunk
            if len(data) > MAX_BYTES:
                break
        return r.status_code, data.decode("utf-8", errors="replace")


def fetch_url(url: str) -> dict:
    if not is_public_url(url):
        raise ToolError("url is not a public http(s) address")
    status, body = http_get(url)
    if status != 200:
        raise ToolError(f"HTTP {status}")
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.I | re.S)
    text = unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return {"title": unescape(title.group(1)).strip() if title else "", "summary": text[:600]}


def trending_topics(keyword: str) -> dict:
    feed = get_settings().trending_feed
    if not is_public_url(feed):
        raise ToolError("trending feed is not a public address")
    status, body = http_get(feed)
    if status != 200:
        raise ToolError(f"feed HTTP {status}")
    try:
        titles = [(el.findtext("title") or "").strip() for el in ET.fromstring(body).iter("item")]
    except ET.ParseError as exc:
        raise ToolError(f"feed is not valid XML: {exc}") from exc
    words = {w for w in re.findall(r"[a-z0-9]+", keyword.lower()) if len(w) > 2}
    hits = [t for t in titles if words & set(re.findall(r"[a-z0-9]+", t.lower()))]
    return {"topics": (hits or titles)[:5], "matched": bool(hits)}


def hashtag_suggest(text: str, limit: int = 2) -> dict:
    seen: list[str] = []
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]{4,}", text):
        lw = w.lower()
        if lw not in STOPWORDS and lw not in seen:
            seen.append(lw)
    top = sorted(seen, key=len, reverse=True)[:limit]
    return {"hashtags": ["#" + w.capitalize() for w in top]}


def char_limit(text: str, platform: str) -> dict:
    length = rules.weighted_length(text, platform)
    limit = rules.LIMITS.get(platform, 280)
    return {"length": length, "limit": limit, "remaining": limit - length}


REGISTRY = {
    "fetch_url": {"fn": fetch_url, "args": {"url": "string"}, "doc": "Read a web page the post should reference."},
    "trending_topics": {"fn": trending_topics, "args": {"keyword": "string"}, "doc": "Current headlines related to a keyword."},
    "hashtag_suggest": {"fn": hashtag_suggest, "args": {"text": "string"}, "doc": "Suggest hashtags for text."},
    "char_limit": {"fn": char_limit, "args": {"text": "string", "platform": "x|linkedin"}, "doc": "Measure text against a platform limit."},
}


def keywords(brief: str, n: int = 3) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", brief) if len(w) > 3 and w.lower() not in STOPWORDS]
    return " ".join(words[:n])


def default_plan(brief: str, urls: list[str]) -> list[dict]:
    plan = [{"tool": "fetch_url", "args": {"url": u}} for u in urls[:2]]
    plan.append({"tool": "trending_topics", "args": {"keyword": keywords(brief)}})
    return plan


def plan_tools(client: Client | None, brief: str, urls: list[str]) -> tuple[list[dict], str]:
    """Ask the model which tools to call. Any malformed answer falls back to the deterministic plan."""
    if client is None:
        return default_plan(brief, urls), "default"
    catalog = {k: {"args": v["args"], "doc": v["doc"]} for k, v in REGISTRY.items() if k in ("fetch_url", "trending_topics")}
    system = (
        "You choose tools for a social media research step. Reply with JSON only: "
        '{"calls":[{"tool":"<name>","args":{...}}]}. At most 3 calls. Tools: ' + json.dumps(catalog)
    )
    try:
        raw = client.complete(system, f"Brief: {brief}\nURLs given: {urls}", json_mode=True)
        calls = json.loads(raw)["calls"]
        valid = [c for c in calls if c.get("tool") in catalog and isinstance(c.get("args"), dict)]
        # A small model invents plausible URLs. Only fetch pages the user actually supplied.
        valid = [c for c in valid if c["tool"] != "fetch_url" or c["args"].get("url") in urls][:3]
        if valid:
            return valid, "llm"
    except (LLMError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return default_plan(brief, urls), "default"


def run_calls(calls: list[dict]) -> list[dict]:
    """Execute tool calls. One failing tool is recorded, never fatal."""
    out = []
    for call in calls:
        entry = REGISTRY.get(call["tool"])
        try:
            if entry is None:
                raise ToolError(f"unknown tool {call['tool']}")
            out.append({"tool": call["tool"], "args": call["args"], "result": entry["fn"](**call["args"])})
        except (ToolError, httpx.HTTPError, TypeError) as exc:
            out.append({"tool": call["tool"], "args": call["args"], "error": str(exc)})
    return out
