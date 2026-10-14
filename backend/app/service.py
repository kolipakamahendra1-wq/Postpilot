"""Application logic shared by the API, the scheduler and the CLI."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from langgraph.types import Command

from . import db, publishers, rules, slack
from .agent.graph import Deps, build_graph, make_checkpointer
from .config import get_settings
from .llm import get_client

MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 60


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


def client_factory():
    """Overridden in tests with a fake model."""
    return get_client()


@lru_cache(maxsize=4)
def _checkpointer(path: str):
    from pathlib import Path

    return make_checkpointer(Path(path))


def _graph(use_llm: bool):
    s = get_settings()

    def recent() -> list[str]:
        with db.connect() as c:
            rows = c.execute(
                "SELECT draft FROM posts WHERE status IN ('pending_approval','scheduled','publishing','published') "
                "ORDER BY id DESC LIMIT 20"
            ).fetchall()
        return [r["draft"] for r in rows]

    deps = Deps(client=client_factory() if use_llm else None, banned=s.banned_words, recent=recent)
    return build_graph(deps, _checkpointer(str(s.checkpoint_path)))


def get_post(post_id: int) -> dict:
    with db.connect() as c:
        row = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if row is None:
        raise NotFound(f"post {post_id} not found")
    return db.row_to_dict(row)


def list_posts(status: str | None = None) -> list[dict]:
    with db.connect() as c:
        if status:
            rows = c.execute("SELECT * FROM posts WHERE status=? ORDER BY id DESC", (status,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM posts ORDER BY id DESC LIMIT 200").fetchall()
    return [db.row_to_dict(r) for r in rows]


def _save_run(post_id: int, values: dict, trace: list[dict]) -> None:
    import json

    with db.connect() as c:
        c.execute(
            "UPDATE posts SET draft=?, rule_report=?, trace=?, status=? WHERE id=?",
            (values.get("draft", ""), json.dumps(values.get("report", {})), json.dumps(trace), "pending_approval", post_id),
        )


def create_post(brief: str, platform: str, tone: str = "friendly", urls: list[str] | None = None,
                use_llm: bool = True, campaign_id: int | None = None, actor: str = "user") -> dict:
    if platform not in rules.LIMITS:
        raise Invalid(f"platform must be one of {sorted(rules.LIMITS)}")
    if not brief.strip():
        raise Invalid("brief is empty")
    thread_id = uuid.uuid4().hex
    with db.connect() as c:
        cur = c.execute(
            "INSERT INTO posts (thread_id, platform, brief, status, campaign_id, created_at) VALUES (?,?,?,?,?,?)",
            (thread_id, platform, brief.strip(), "drafting", campaign_id, db.now_iso()),
        )
        post_id = cur.lastrowid
    db.audit(actor, "created", post_id, brief[:120])
    config = {"configurable": {"thread_id": thread_id}}
    try:
        graph = _graph(use_llm)
        graph.invoke({"brief": brief.strip(), "platform": platform, "tone": tone, "urls": urls or [], "trace": []}, config)
        snap = graph.get_state(config)
        _save_run(post_id, snap.values, snap.values.get("trace", []))
    except Exception as exc:  # a failed run is recorded, not raised, so the queue shows it
        with db.connect() as c:
            c.execute("UPDATE posts SET status='failed', error=? WHERE id=?", (str(exc)[:300], post_id))
        db.audit("system", "run_failed", post_id, str(exc))
        return get_post(post_id)
    post = get_post(post_id)
    note = slack.notify(post)
    db.audit("system", "awaiting_approval", post_id, f"slack: {note}")
    return post


def _parse_when(value: str | None) -> str:
    if not value:
        return db.now_iso()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid("scheduled_at must be ISO 8601") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def decide(post_id: int, action: str, text: str | None = None, scheduled_at: str | None = None, actor: str = "user") -> dict:
    if action not in ("approve", "edit", "reject"):
        raise Invalid("action must be approve, edit or reject")
    post = get_post(post_id)
    final_text = text if action == "edit" and text is not None else post["draft"]
    if action != "reject":
        report = rules.check(final_text, post["platform"], get_settings().banned_words)
        hard = [v for v in report["violations"] if v["rule"] in ("empty", "length", "platform")]
        if hard:
            raise Invalid("; ".join(v["message"] for v in hard))
    when = _parse_when(scheduled_at) if action != "reject" else None
    # Atomic claim: two clicks (web + Slack) cannot both resume the same run.
    with db.connect() as c:
        claimed = c.execute("UPDATE posts SET status='deciding' WHERE id=? AND status='pending_approval'", (post_id,)).rowcount
    if claimed != 1:
        raise Conflict(f"post {post_id} is {post['status']}, not pending_approval")
    config = {"configurable": {"thread_id": post["thread_id"]}}
    try:
        graph = _graph(False)
        graph.invoke(Command(resume={"action": action, "text": final_text, "scheduled_at": when}), config)
        snap = graph.get_state(config)
    except Exception:
        with db.connect() as c:
            c.execute("UPDATE posts SET status='pending_approval' WHERE id=?", (post_id,))
        raise
    import json

    status = "rejected" if action == "reject" else "scheduled"
    with db.connect() as c:
        c.execute(
            "UPDATE posts SET status=?, draft=?, rule_report=?, trace=?, scheduled_at=? WHERE id=?",
            (status, snap.values.get("draft", post["draft"]), json.dumps(snap.values.get("report", post["rule_report"])),
             json.dumps(snap.values.get("trace", [])), when, post_id),
        )
    db.audit(actor, action, post_id, f"scheduled_at={when}" if when else "")
    return get_post(post_id)


def publish_due(now: datetime | None = None) -> list[dict]:
    """Publish every scheduled post that is due. Safe to call concurrently and after a restart."""
    now_s = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
    with db.connect() as c:
        due = [r["id"] for r in c.execute("SELECT id FROM posts WHERE status='scheduled' AND scheduled_at <= ? ORDER BY scheduled_at", (now_s,))]
    results = []
    for post_id in due:
        with db.connect() as c:
            claimed = c.execute(
                "UPDATE posts SET status='publishing', attempts=attempts+1 WHERE id=? AND status='scheduled'", (post_id,)
            ).rowcount
        if claimed != 1:
            continue  # another worker has it
        post = get_post(post_id)
        try:
            ref = publishers.publish(post)
        except Exception as exc:
            if post["attempts"] >= MAX_ATTEMPTS:
                status, retry_at = "failed", post["scheduled_at"]
            else:
                status = "scheduled"
                retry_at = (datetime.fromisoformat(now_s) + timedelta(seconds=RETRY_BASE_SECONDS * post["attempts"])).isoformat(timespec="seconds")
            with db.connect() as c:
                c.execute("UPDATE posts SET status=?, error=?, scheduled_at=? WHERE id=?", (status, str(exc)[:300], retry_at, post_id))
            db.audit("scheduler", "publish_failed", post_id, f"{status}: {exc}")
        else:
            with db.connect() as c:
                c.execute("UPDATE posts SET status='published', publish_ref=?, published_at=?, error=NULL WHERE id=?", (ref, db.now_iso(), post_id))
            db.audit("scheduler", "published", post_id, ref)
        results.append(get_post(post_id))
    return results


# ---- campaigns (cron-driven drafting) ----

def list_campaigns() -> list[dict]:
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM campaigns ORDER BY id")]


def add_campaign(name: str, brief: str, platform: str, cron: str) -> dict:
    from apscheduler.triggers.cron import CronTrigger

    if platform not in rules.LIMITS:
        raise Invalid(f"platform must be one of {sorted(rules.LIMITS)}")
    try:
        CronTrigger.from_crontab(cron)
    except ValueError as exc:
        raise Invalid(f"bad cron expression: {exc}") from exc
    with db.connect() as c:
        cur = c.execute("INSERT INTO campaigns (name, brief, platform, cron) VALUES (?,?,?,?)", (name, brief, platform, cron))
        row = c.execute("SELECT * FROM campaigns WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


def delete_campaign(campaign_id: int) -> None:
    with db.connect() as c:
        if c.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,)).rowcount != 1:
            raise NotFound(f"campaign {campaign_id} not found")


def run_campaign(campaign_id: int) -> dict:
    with db.connect() as c:
        row = c.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
    if row is None:
        raise NotFound(f"campaign {campaign_id} not found")
    return create_post(row["brief"], row["platform"], campaign_id=campaign_id, actor="cron")


def audit_log(limit: int = 100) -> list[dict]:
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]
