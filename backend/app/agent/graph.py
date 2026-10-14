"""LangGraph workflow: research -> draft -> check (loop) -> human approval (interrupt) -> schedule.

The approval node calls `interrupt()`. State is saved by the SQLite checkpointer, so the run
survives a server restart and resumes with `Command(resume=...)` from the UI or a Slack button.
"""
from __future__ import annotations

import operator
import sqlite3
from dataclasses import dataclass, field
from typing import Annotated, Callable, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .. import rules
from ..llm import Client, LLMError
from . import tools

MAX_DRAFTS = 3


class State(TypedDict, total=False):
    brief: str
    platform: str
    tone: str
    urls: list[str]
    research: list[dict]
    draft: str
    report: dict
    attempts: int
    decision: dict
    outcome: str  # pending | rejected | scheduled
    scheduled_at: str | None
    trace: Annotated[list[dict], operator.add]


@dataclass
class Deps:
    client: Client | None = None
    banned: tuple[str, ...] = ()
    recent: Callable[[], list[str]] = field(default=lambda: [])


def _step(step: str, detail: str, **extra) -> list[dict]:
    return [{"step": step, "detail": detail, **extra}]


def template_draft(state: State) -> str:
    """No-model drafter: the brief itself plus hashtags. Research only informs the LLM prompt;
    keyword-matched headlines were too often unrelated to paste into a post."""
    brief = state["brief"].strip().rstrip(".")
    draft = brief + "."
    tags = tools.hashtag_suggest(brief, rules.MAX_HASHTAGS[state["platform"]])["hashtags"]
    return rules.trim_to_limit(draft + (" " + " ".join(tags) if tags else ""), state["platform"])


def build_graph(deps: Deps, checkpointer: SqliteSaver):
    def research(state: State):
        calls, planner = tools.plan_tools(deps.client, state["brief"], state.get("urls", []))
        results = tools.run_calls(calls)
        failed = sum(1 for r in results if "error" in r)
        return {"research": results, "trace": _step("research", f"{len(results)} tool calls, {failed} failed", planner=planner, calls=results)}

    def draft(state: State):
        attempts = state.get("attempts", 0) + 1
        feedback = ""
        if state.get("report") and not state["report"]["ok"]:
            feedback = "Fix these problems: " + "; ".join(v["message"] for v in state["report"]["violations"])
        text, mode = "", "template"
        if deps.client is not None:
            limit = rules.LIMITS[state["platform"]]
            notes = "\n".join(
                f"- {r['tool']}: {r.get('result') or r.get('error')}" for r in state.get("research", [])
            )
            system = (
                f"You write one {state['platform']} post in a {state.get('tone', 'friendly')} tone. "
                f"Maximum {limit} characters and {rules.MAX_HASHTAGS[state['platform']]} hashtags. "
                "Do not use these phrases: " + ", ".join(deps.banned) + ". Output only the post text."
            )
            try:
                text = deps.client.complete(system, f"Brief: {state['brief']}\nResearch:\n{notes}\n{feedback}").strip('"\' \n')
                mode = "llm"
            except LLMError as exc:
                mode = f"template (model failed: {str(exc)[:80]})"
        if not text:
            text = template_draft(state)
        return {"draft": text, "attempts": attempts, "trace": _step("draft", f"attempt {attempts} via {mode}", text=text)}

    def check(state: State):
        text = state["draft"]
        report = rules.check(text, state["platform"], deps.banned, deps.recent())
        if not report["ok"] and state["attempts"] >= MAX_DRAFTS:
            text = rules.trim_to_limit(text, state["platform"])
            report = rules.check(text, state["platform"], deps.banned, deps.recent())
        detail = "passed" if report["ok"] else f"{len(report['violations'])} violation(s)"
        return {"draft": text, "report": report, "trace": _step("check", detail, violations=report["violations"])}

    def after_check(state: State):
        return "approval" if state["report"]["ok"] or state["attempts"] >= MAX_DRAFTS else "draft"

    def approval(state: State):
        # No side effects before interrupt(): this node re-runs from the top on resume.
        decision = interrupt({"draft": state["draft"], "report": state["report"], "platform": state["platform"]})
        action = decision.get("action")
        update: dict = {"decision": decision}
        if action == "edit":
            text = decision.get("text", state["draft"])
            update["draft"] = text
            update["report"] = rules.check(text, state["platform"], deps.banned, deps.recent())
        update["trace"] = _step("approval", f"human chose {action}")
        return update

    def after_approval(state: State):
        return END if state["decision"].get("action") == "reject" else "schedule"

    def schedule(state: State):
        when = state["decision"].get("scheduled_at")
        return {"outcome": "scheduled", "scheduled_at": when, "trace": _step("schedule", f"queued for {when or 'next tick'}")}

    g = StateGraph(State)
    for name, fn in (("research", research), ("draft", draft), ("check", check), ("approval", approval), ("schedule", schedule)):
        g.add_node(name, fn)
    g.add_edge(START, "research")
    g.add_edge("research", "draft")
    g.add_edge("draft", "check")
    g.add_conditional_edges("check", after_check, {"draft": "draft", "approval": "approval"})
    g.add_conditional_edges("approval", after_approval, {END: END, "schedule": "schedule"})
    g.add_edge("schedule", END)
    return g.compile(checkpointer=checkpointer)


def make_checkpointer(path) -> SqliteSaver:
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False))
