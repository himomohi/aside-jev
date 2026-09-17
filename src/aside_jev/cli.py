from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .core import Candidate, build_abstain
from .loop import decide


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_choose(args: argparse.Namespace) -> int:
    data = _load_json(args.candidates)
    observation = (
        _load_json(args.observation) if args.observation else {"note": "no observation file"}
    )
    candidates = [
        Candidate(
            id=str(item["id"]),
            description=str(item.get("description") or item["id"]),
            tool=item.get("tool"),
            arguments=dict(item.get("arguments") or {}),
        )
        for item in data
    ]
    if not any(c.id == "abstain" for c in candidates):
        candidates.append(build_abstain())
    candidate, confidence, probs = decide(
        candidates,
        goal=args.goal,
        observation=observation,
        provider=args.provider,
        model=args.model,
        prefer=args.prefer,
    )
    print(
        json.dumps(
            {
                "choice_id": candidate.id,
                "confidence": confidence,
                "probabilities": probs,
                "candidate": candidate.to_dict(),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_serve(_args: argparse.Namespace) -> int:
    from .mcp_server import main as mcp_main

    mcp_main()
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="aside-jev",
        description="Bounded TypeSafe Jev decisions for Aside agents",
    )
    parser.add_argument("--version", action="version", version=f"aside-jev {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Run the aside-jev MCP server on stdio")
    p_serve.set_defaults(func=cmd_serve)

    p_choose = sub.add_parser("choose", help="Choose one candidate id (mock or live)")
    p_choose.add_argument("--goal", required=True)
    p_choose.add_argument("--candidates", required=True, help="JSON array of candidates")
    p_choose.add_argument("--observation", help="JSON observation file")
    p_choose.add_argument("--provider", choices=["mock", "live"], default="mock")
    p_choose.add_argument("--model", default=None)
    p_choose.add_argument("--prefer", default=None, help="mock-only preferred id")
    p_choose.set_defaults(func=cmd_choose)

    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
