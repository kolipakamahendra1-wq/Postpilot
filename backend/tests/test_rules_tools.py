import json

from app import rules
from app.agent import tools
from app.llm import LLMError
from conftest import REAL_IS_PUBLIC_URL, FakeClient


def test_x_length_limit():
    assert rules.check("a" * 280, "x")["ok"]
    report = rules.check("a" * 281, "x")
    assert not report["ok"] and report["violations"][0]["rule"] == "length"


def test_x_counts_links_as_23_chars():
    text = "Read this " + "https://example.com/" + "a" * 200
    assert rules.weighted_length(text, "x") == len("Read this ") + 23
    assert rules.check(text, "x")["ok"]


def test_linkedin_allows_long_posts():
    assert rules.check("a" * 2900, "linkedin")["ok"]


def test_hashtag_cap_differs_per_platform():
    text = "hi #a #b #c"
    assert not rules.check(text, "x")["ok"]
    assert rules.check(text, "linkedin")["ok"]


def test_banned_phrase_matches_whole_words_only():
    assert not rules.check("This is guaranteed to work", "x", banned=("guaranteed",))["ok"]
    assert rules.check("Unguaranteedly fine", "x", banned=("guaranteed",))["ok"]


def test_duplicate_detection():
    old = ["We just shipped version two of our agent today"]
    assert not rules.check("We just shipped version two of our agent today!", "x", recent=old)["ok"]
    assert rules.check("Totally different words appear here now", "x", recent=old)["ok"]


def test_empty_and_unknown_platform():
    assert not rules.check("  ", "x")["ok"]
    assert rules.check("hi", "mastodon")["violations"][0]["rule"] == "platform"


def test_trim_stays_under_limit_on_word_boundary():
    out = rules.trim_to_limit("word " * 100, "x")
    assert rules.weighted_length(out, "x") <= 280 and out.endswith("…")


def test_ssrf_guard_blocks_internal_addresses():
    for url in ("http://127.0.0.1/", "http://169.254.169.254/latest", "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "ftp://example.com"):
        assert not REAL_IS_PUBLIC_URL(url), url


def test_ssrf_guard_unwraps_nat64(monkeypatch):
    import socket

    def resolve(ip):
        return lambda host, port: [(socket.AF_INET6, 0, 0, "", (ip, port, 0, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve("64:ff9b::7f00:1"))  # embeds 127.0.0.1
    assert not REAL_IS_PUBLIC_URL("https://sneaky.example")
    monkeypatch.setattr(socket, "getaddrinfo", resolve("64:ff9b::9f59:f3f2"))  # embeds a public address
    assert REAL_IS_PUBLIC_URL("https://fine.example")


def test_fetch_url_extracts_title_and_text():
    out = tools.fetch_url("https://example.com")
    assert out["title"] == "Page" and "Hello world" in out["summary"]


def test_fetch_url_refuses_private(monkeypatch):
    monkeypatch.setattr(tools, "is_public_url", lambda u: False)
    out = tools.run_calls([{"tool": "fetch_url", "args": {"url": "http://127.0.0.1"}}])
    assert "error" in out[0]


def test_trending_filters_by_keyword_and_falls_back_to_top():
    assert tools.trending_topics("rust async")["topics"] == ["Rust async runtimes compared"]
    miss = tools.trending_topics("zzzz")
    assert miss["matched"] is False and len(miss["topics"]) == 3


def test_failing_tool_does_not_abort_the_batch():
    out = tools.run_calls([
        {"tool": "nope", "args": {}},
        {"tool": "char_limit", "args": {"text": "abc", "platform": "x"}},
        {"tool": "char_limit", "args": {"wrong": 1}},
    ])
    assert "error" in out[0] and out[1]["result"]["remaining"] == 277 and "error" in out[2]


def test_plan_uses_valid_llm_choice():
    reply = json.dumps({"calls": [{"tool": "trending_topics", "args": {"keyword": "rust"}}, {"tool": "rm_rf", "args": {}}]})
    calls, planner = tools.plan_tools(FakeClient(reply), "brief", [])
    assert planner == "llm" and [c["tool"] for c in calls] == ["trending_topics"]


def test_plan_drops_urls_the_model_invented():
    reply = json.dumps({"calls": [{"tool": "fetch_url", "args": {"url": "https://made-up.example"}},
                                  {"tool": "fetch_url", "args": {"url": "https://real.example"}}]})
    calls, _ = tools.plan_tools(FakeClient(reply), "brief", ["https://real.example"])
    assert [c["args"]["url"] for c in calls] == ["https://real.example"]


def test_plan_falls_back_on_garbage_or_error():
    for bad in ("not json", '{"calls": "x"}', '{"nope": 1}', LLMError("down")):
        calls, planner = tools.plan_tools(FakeClient(bad), "Launching our new agent", ["https://a.com"])
        assert planner == "default" and calls[0]["tool"] == "fetch_url"


def test_hashtags_skip_stopwords():
    assert tools.hashtag_suggest("about this launching agent")["hashtags"] == ["#Launching", "#Agent"]
