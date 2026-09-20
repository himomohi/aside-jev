from __future__ import annotations

import argparse
import json
import os
import sys
from time import perf_counter
from typing import Any

from . import __version__
from .core import parse_candidates
from .cli_i18n import text
from .jev import system_one
from .loop import decide


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_choose(args: argparse.Namespace) -> int:
    started = perf_counter()
    data = _load_json(args.candidates)
    observation = (
        _load_json(args.observation) if args.observation else {"note": "no observation file"}
    )
    candidates = parse_candidates(data)
    prepared = perf_counter()
    candidate, confidence, probs = decide(
        candidates,
        goal=args.goal,
        observation=observation,
        provider=args.provider,
        model=args.model,
        prefer=args.prefer,
        timeout_s=args.timeout,
    )
    finished = perf_counter()
    print(
        json.dumps(
            {
                "choice_id": candidate.id,
                "confidence": confidence,
                "probabilities": probs,
                "candidate": candidate.to_dict(),
                "provider": args.provider,
                "model": args.model if args.provider == "live" else None,
                "timing_ms": {
                    "preparation": round((prepared - started) * 1000, 3),
                    "decision": round((finished - prepared) * 1000, 3),
                    "total": round((finished - started) * 1000, 3),
                },
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_system_one(args: argparse.Namespace) -> int:
    state = _load_json(args.state)
    questions = _load_json(args.questions)
    out = system_one(state, questions, model=args.model, timeout_s=args.timeout)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .mcp_server import main as mcp_main

    if args.extension:
        os.environ["ASIDE_JEV_EXTENSION_MODE"] = "1"
    mcp_main()
    return 0


def cmd_native_host(args: argparse.Namespace) -> int:
    from .native_host import serve

    serve(args.origin)
    return 0


def cmd_extension_status(_args: argparse.Namespace) -> int:
    from .extension_control import get_status

    print(json.dumps(get_status(), ensure_ascii=False, indent=2))
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    from .dashboard import serve_dashboard

    serve_dashboard(args.port, open_browser=args.open, locale=getattr(args, "lang", "en"))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .dashboard import runtime_status

    status = runtime_status()
    if args.json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        print(f"Aside Jev {status['version']}")
        locale = getattr(args, "lang", "en")
        print(text("demo_ready", locale))
        print(text("key_label", locale) + text("key_present" if status["live_available"] else "key_missing", locale))
        print(text("aside_label", locale) + text("aside_present" if status["aside_available"] else "aside_missing", locale))
        print(text("workspace", locale))
        print(text("limit", locale))
    return 0


def main(argv: list[str] | None = None) -> None:
    # --lang를 하위 명령 앞뒤 모두 허용하며 시스템 언어는 자동 적용하지 않는다.
    language_parser = argparse.ArgumentParser(add_help=False)
    language_parser.add_argument("--lang", choices=["en", "ko"], default="en")
    language, remaining = language_parser.parse_known_args(argv)
    locale = language.lang
    def t(key: str) -> str:
        return text(key, locale)

    parser = argparse.ArgumentParser(
        prog="aside-jev",
        description=t("description"),
    )
    parser.add_argument("--version", action="version", version=f"aside-jev {__version__}")
    parser.add_argument("--lang", choices=["en", "ko"], default=locale, help=t("language"))
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help=t("serve"))
    p_serve.add_argument("--extension", action="store_true", help=t("extension"))
    p_serve.set_defaults(func=cmd_serve)

    p_native = sub.add_parser("native-host", help=t("native"))
    p_native.add_argument("origin")
    p_native.set_defaults(func=cmd_native_host)

    p_extension_status = sub.add_parser("extension-status", help=t("status"))
    p_extension_status.set_defaults(func=cmd_extension_status)

    p_dashboard = sub.add_parser("dashboard", help=t("dashboard"))
    p_dashboard.add_argument("--port", type=int, default=8766, help=t("port"))
    p_dashboard.add_argument("--open", action="store_true", help=t("open"))
    p_dashboard.set_defaults(func=cmd_dashboard)

    p_doctor = sub.add_parser("doctor", help=t("doctor"))
    p_doctor.add_argument("--json", action="store_true", help=t("json"))
    p_doctor.set_defaults(func=cmd_doctor)

    p_choose = sub.add_parser("choose", help=t("choose"))
    p_choose.add_argument("--goal", required=True)
    p_choose.add_argument("--candidates", required=True, help=t("candidates"))
    p_choose.add_argument("--observation", help=t("observation"))
    p_choose.add_argument("--provider", choices=["mock", "live"], default="mock")
    p_choose.add_argument("--model", default="jev-latest")
    p_choose.add_argument("--prefer", default=None, help=t("prefer"))
    p_choose.add_argument("--timeout", type=float, default=15, help=t("timeout"))
    p_choose.set_defaults(func=cmd_choose)

    p_so = sub.add_parser("system-one", help=t("system_one"))
    p_so.add_argument("--state", required=True, help=t("state"))
    p_so.add_argument("--questions", required=True, help=t("questions"))
    p_so.add_argument("--model", default="jev-latest")
    p_so.add_argument("--timeout", type=float, default=15, help=t("timeout"))
    p_so.set_defaults(func=cmd_system_one)

    args = parser.parse_args(remaining)
    try:
        if args.command == "dashboard" and not 0 <= args.port <= 65535:
            raise ValueError(t("port_error"))
        code = args.func(args)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        # provider 오류는 Jev 계층에서 비밀정보 없이 정규화한다.
        message = text("json_error", locale, detail=exc.msg) if isinstance(exc, json.JSONDecodeError) else str(exc)
        print(json.dumps({"error": message, "code": getattr(exc, "code", "input")}, ensure_ascii=False), file=sys.stderr)
        code = 2
    finally:
        from .jev import close_clients
        close_clients()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
