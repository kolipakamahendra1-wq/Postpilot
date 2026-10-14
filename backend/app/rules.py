"""Deterministic brand and platform rules. Runs next to the LLM because a 3B model misses obvious problems."""
from __future__ import annotations

import re

LIMITS = {"x": 280, "linkedin": 3000}
MAX_HASHTAGS = {"x": 2, "linkedin": 5}
URL_RE = re.compile(r"https?://\S+")
HASHTAG_RE = re.compile(r"(?<!\w)#\w+")
X_URL_WEIGHT = 23  # X counts every link as 23 characters


def weighted_length(text: str, platform: str) -> int:
    if platform == "x":
        return len(URL_RE.sub("x" * X_URL_WEIGHT, text))
    return len(text)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def check(text: str, platform: str, banned: tuple[str, ...] = (), recent: list[str] | None = None) -> dict:
    """Return {"ok": bool, "violations": [{"rule", "message"}]}. Never raises."""
    violations: list[dict] = []
    if platform not in LIMITS:
        return {"ok": False, "violations": [{"rule": "platform", "message": f"unknown platform '{platform}'"}]}
    if not text.strip():
        violations.append({"rule": "empty", "message": "draft is empty"})
    length = weighted_length(text, platform)
    if length > LIMITS[platform]:
        violations.append({"rule": "length", "message": f"{length} chars, limit {LIMITS[platform]} on {platform}"})
    tags = HASHTAG_RE.findall(text)
    if len(tags) > MAX_HASHTAGS[platform]:
        violations.append({"rule": "hashtags", "message": f"{len(tags)} hashtags, max {MAX_HASHTAGS[platform]}"})
    lowered = text.lower()
    for word in banned:
        if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", lowered):
            violations.append({"rule": "banned_word", "message": f"contains banned phrase '{word}'"})
    for old in recent or []:
        if similarity(text, old) >= 0.8:
            violations.append({"rule": "duplicate", "message": "near-duplicate of a recent post"})
            break
    return {"ok": not violations, "violations": violations, "length": length, "limit": LIMITS[platform]}


def trim_to_limit(text: str, platform: str) -> str:
    """Last-resort repair: cut at a word boundary under the limit and add an ellipsis."""
    limit = LIMITS.get(platform, 280)
    if weighted_length(text, platform) <= limit:
        return text
    words = text.split()
    while words and weighted_length(" ".join(words) + "…", platform) > limit:
        words.pop()
    return " ".join(words) + "…"
