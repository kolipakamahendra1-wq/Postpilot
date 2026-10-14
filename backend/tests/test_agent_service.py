from datetime import datetime, timedelta, timezone

import pytest

from app import publishers, service
from app.llm import LLMError

BRIEF = "Announce our open source release of Postpilot, a human approved social agent"


def test_graph_pauses_at_approval_without_a_model():
    post = service.create_post(BRIEF, "x", use_llm=False)
    assert post["status"] == "pending_approval"
    assert post["draft"] and post["rule_report"]["ok"]
    assert [t["step"] for t in post["trace"]] == ["research", "draft", "check"]


def test_llm_draft_is_used_when_valid(fake_llm):
    client = fake_llm('{"calls": []}', "Postpilot is out. Humans approve every post.")
    post = service.create_post(BRIEF, "x")
    assert post["draft"] == "Postpilot is out. Humans approve every post."
    assert len(client.calls) == 2


def test_too_long_draft_is_revised_with_feedback(fake_llm):
    client = fake_llm("{}", "x" * 400, "Short and fine.")
    post = service.create_post(BRIEF, "x")
    assert post["draft"] == "Short and fine."
    assert "limit 280" in client.calls[-1]["user"]
    assert sum(1 for t in post["trace"] if t["step"] == "draft") == 2


def test_gives_up_after_three_drafts_and_trims(fake_llm):
    fake_llm("{}", "word " * 100, "word " * 100, "word " * 100)
    post = service.create_post(BRIEF, "x")
    assert post["status"] == "pending_approval" and post["rule_report"]["ok"] and post["draft"].endswith("…")


def test_model_failure_degrades_to_template(fake_llm):
    fake_llm("{}", LLMError("ollama HTTP 500: token repeat limit reached"))
    post = service.create_post(BRIEF, "x")
    assert post["status"] == "pending_approval" and post["draft"]
    assert any("model failed" in t["detail"] for t in post["trace"])


def test_approval_survives_restart_and_schedules():
    post = service.create_post(BRIEF, "linkedin", use_llm=False)
    service._checkpointer.cache_clear()  # new sqlite connection, like a server restart
    done = service.decide(post["id"], "approve", scheduled_at="2030-01-01T09:00:00Z")
    assert done["status"] == "scheduled" and done["scheduled_at"] == "2030-01-01T09:00:00+00:00"
    assert done["trace"][-1]["step"] == "schedule"


def test_edit_replaces_text():
    post = service.create_post(BRIEF, "x", use_llm=False)
    done = service.decide(post["id"], "edit", text="Hand written final copy.")
    assert done["draft"] == "Hand written final copy." and done["status"] == "scheduled"


def test_reject_ends_the_run():
    post = service.create_post(BRIEF, "x", use_llm=False)
    assert service.decide(post["id"], "reject")["status"] == "rejected"
    assert service.publish_due() == []


def test_hard_violation_blocks_approval_and_keeps_post_pending():
    post = service.create_post(BRIEF, "x", use_llm=False)
    with pytest.raises(service.Invalid):
        service.decide(post["id"], "edit", text="x" * 400)
    assert service.get_post(post["id"])["status"] == "pending_approval"


def test_second_decision_conflicts():
    post = service.create_post(BRIEF, "x", use_llm=False)
    service.decide(post["id"], "approve")
    with pytest.raises(service.Conflict):
        service.decide(post["id"], "reject")


def test_unknown_post_and_bad_input():
    with pytest.raises(service.NotFound):
        service.decide(999, "approve")
    with pytest.raises(service.Invalid):
        service.create_post("  ", "x")
    with pytest.raises(service.Invalid):
        service.create_post("hello there", "myspace")
    post = service.create_post(BRIEF, "x", use_llm=False)
    with pytest.raises(service.Invalid):
        service.decide(post["id"], "approve", scheduled_at="tomorrow-ish")


def test_publish_only_due_posts_and_only_once():
    now = datetime.now(timezone.utc)
    due = service.create_post(BRIEF, "x", use_llm=False)
    later = service.create_post("Another distinct announcement about quarterly roadmap planning", "x", use_llm=False)
    service.decide(due["id"], "approve", scheduled_at=(now - timedelta(minutes=1)).isoformat())
    service.decide(later["id"], "approve", scheduled_at=(now + timedelta(days=1)).isoformat())
    first = service.publish_due(now)
    assert [p["id"] for p in first] == [due["id"]] and first[0]["status"] == "published"
    assert first[0]["publish_ref"] == f"mock-x-{due['id']}"
    assert service.publish_due(now) == []
    assert service.get_post(later["id"])["status"] == "scheduled"


def test_failed_publish_retries_then_gives_up(monkeypatch):
    calls = []

    def boom(post):
        calls.append(post["id"])
        raise publishers.PublishError("HTTP 503")

    monkeypatch.setattr(publishers, "publish", boom)
    post = service.create_post(BRIEF, "x", use_llm=False)
    service.decide(post["id"], "approve")
    clock = datetime.now(timezone.utc) + timedelta(seconds=5)
    for _ in range(5):
        service.publish_due(clock)
        clock += timedelta(hours=1)
    final = service.get_post(post["id"])
    assert final["status"] == "failed" and final["attempts"] == 3 and len(calls) == 3
    assert "503" in final["error"]


def test_audit_trail_records_actors():
    post = service.create_post(BRIEF, "x", use_llm=False)
    service.decide(post["id"], "approve", actor="slack")
    events = [(a["actor"], a["event"]) for a in service.audit_log()]
    assert ("slack", "approve") in events and ("user", "created") in events


def test_campaign_validation_and_cron_run():
    with pytest.raises(service.Invalid):
        service.add_campaign("bad", "brief text", "x", "not a cron")
    camp = service.add_campaign("Weekly", "Share a tip about local LLM agents", "x", "0 9 * * 1")
    run = service.run_campaign(camp["id"])
    assert run["campaign_id"] == camp["id"] and run["status"] in ("pending_approval", "failed")
    assert ("cron", "created") in [(a["actor"], a["event"]) for a in service.audit_log()]
    service.delete_campaign(camp["id"])
    with pytest.raises(service.NotFound):
        service.run_campaign(camp["id"])
