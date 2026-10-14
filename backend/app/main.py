"""FastAPI app. Every /api route needs the bearer token; Slack and OAuth callbacks use their own proofs."""
from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import oauth, scheduler, service, slack
from .config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Postpilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_token(authorization: str = Header(default="")) -> None:
    expected = get_settings().api_token
    supplied = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "missing or invalid bearer token")


def translate(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NotFound):
        return HTTPException(404, str(exc))
    if isinstance(exc, service.Conflict):
        return HTTPException(409, str(exc))
    if isinstance(exc, (service.Invalid, oauth.OAuthError)):
        return HTTPException(422, str(exc))
    raise exc


class NewPost(BaseModel):
    brief: str = Field(min_length=3, max_length=1000)
    platform: str = "x"
    tone: str = "friendly"
    urls: list[str] = []
    use_llm: bool = True


class Decision(BaseModel):
    action: str
    text: str | None = None
    scheduled_at: str | None = None


class NewCampaign(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    brief: str = Field(min_length=3, max_length=1000)
    platform: str = "x"
    cron: str = "0 9 * * 1"


@app.get("/api/health")
def health():
    s = get_settings()
    return {"ok": True, "llm": s.llm_provider, "model": s.llm_model, "publisher": s.publisher,
            "slack": bool(s.slack_webhook_url), "slack_signing": bool(s.slack_signing_secret)}


api = [Depends(require_token)]


@app.post("/api/posts", dependencies=api)
def create_post(body: NewPost):
    try:
        return service.create_post(body.brief, body.platform, body.tone, body.urls, body.use_llm)
    except Exception as exc:
        raise translate(exc)


@app.get("/api/posts", dependencies=api)
def list_posts(status: str | None = None):
    return service.list_posts(status)


@app.get("/api/posts/{post_id}", dependencies=api)
def get_post(post_id: int):
    try:
        return service.get_post(post_id)
    except Exception as exc:
        raise translate(exc)


@app.post("/api/posts/{post_id}/decision", dependencies=api)
def decide(post_id: int, body: Decision):
    try:
        return service.decide(post_id, body.action, body.text, body.scheduled_at)
    except Exception as exc:
        raise translate(exc)


@app.post("/api/scheduler/tick", dependencies=api)
def tick():
    return service.publish_due()


@app.get("/api/campaigns", dependencies=api)
def list_campaigns():
    return service.list_campaigns()


@app.post("/api/campaigns", dependencies=api)
def add_campaign(body: NewCampaign):
    try:
        out = service.add_campaign(body.name, body.brief, body.platform, body.cron)
    except Exception as exc:
        raise translate(exc)
    scheduler.sync_campaigns()
    return out


@app.delete("/api/campaigns/{campaign_id}", dependencies=api)
def delete_campaign(campaign_id: int):
    try:
        service.delete_campaign(campaign_id)
    except Exception as exc:
        raise translate(exc)
    scheduler.sync_campaigns()
    return {"deleted": campaign_id}


@app.post("/api/campaigns/{campaign_id}/run", dependencies=api)
def run_campaign(campaign_id: int):
    try:
        return service.run_campaign(campaign_id)
    except Exception as exc:
        raise translate(exc)


@app.get("/api/audit", dependencies=api)
def audit():
    return service.audit_log()


@app.get("/api/connections", dependencies=api)
def connections():
    return oauth.status()


@app.get("/api/oauth/{provider}/start", dependencies=api)
def oauth_start(provider: str):
    try:
        return {"url": oauth.start(provider)}
    except Exception as exc:
        raise translate(exc)


@app.get("/api/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str = "", state: str = ""):
    """Browser redirect from the provider. Authenticated by the single-use `state`, not a bearer token."""
    base = get_settings().frontend_url + "/connections"
    try:
        oauth.finish(provider, code, state)
    except oauth.OAuthError as exc:
        return RedirectResponse(f"{base}?error={quote(str(exc)[:80])}")
    return RedirectResponse(f"{base}?connected={provider}")


@app.post("/slack/actions")
async def slack_actions(request: Request, x_slack_request_timestamp: str = Header(default=""),
                        x_slack_signature: str = Header(default="")):
    body = await request.body()
    if not slack.verify_signature(get_settings().slack_signing_secret, x_slack_request_timestamp, body, x_slack_signature):
        raise HTTPException(401, "bad slack signature")
    try:
        action, post_id = slack.parse_action(body)
        post = service.decide(post_id, "approve" if action == "approve" else "reject", actor="slack")
    except (KeyError, ValueError, IndexError) as exc:
        raise HTTPException(400, f"malformed slack payload: {exc}")
    except Exception as exc:
        raise translate(exc)
    return {"text": f"Post #{post_id} {post['status']}"}
