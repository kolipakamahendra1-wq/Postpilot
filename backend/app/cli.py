"""CLI: draft a post, approve it in the terminal, publish due posts. Needs no server."""
from __future__ import annotations

import argparse
import json

from . import service


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="postpilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft", help="run the agent and pause at approval")
    d.add_argument("brief")
    d.add_argument("--platform", default="x", choices=["x", "linkedin"])
    d.add_argument("--no-llm", action="store_true")
    a = sub.add_parser("decide")
    a.add_argument("post_id", type=int)
    a.add_argument("action", choices=["approve", "edit", "reject"])
    a.add_argument("--text")
    sub.add_parser("publish-due")
    sub.add_parser("list")
    args = p.parse_args(argv)

    if args.cmd == "draft":
        out = service.create_post(args.brief, args.platform, use_llm=not args.no_llm, actor="cli")
    elif args.cmd == "decide":
        out = service.decide(args.post_id, args.action, args.text, actor="cli")
    elif args.cmd == "publish-due":
        out = service.publish_due()
    else:
        out = service.list_posts()
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
