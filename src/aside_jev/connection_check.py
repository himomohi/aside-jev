"""비밀이나 도구 실행 없이 설치된 MCP의 stdio 연결만 수동 검사한다."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import signal
from typing import Any

TIMEOUT_S = 6.0
MAX_RESPONSE = 262144
REQUIRED_TOOLS = {"jev_step", "jev_system_one", "jev_extension_status", "jev_browser_run"}


def result(state: str = "unverified", code: str = "not_checked", count: int = 0) -> dict[str, Any]:
    return {"state": state, "code": code, "checked_at": None if state == "unverified" else datetime.now(timezone.utc).isoformat(),
            "tool_count": count, "scope": "local_mcp_probe"}


def clean_environment() -> dict[str, str]:
    # Python 주입 변수와 API 키는 전달하지 않는다. 셸을 실행하지 않는다.
    names = ("HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "LANG")
    return {name: os.environ[name] for name in names if name in os.environ}


async def _probe(command: str, args: list[str], cwd: str, timeout_s: float) -> int:
    process = None
    try:
        async with asyncio.timeout(timeout_s):
            process = await asyncio.create_subprocess_exec(
                command, *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=clean_environment(), cwd=cwd,
                limit=MAX_RESPONSE, start_new_session=os.name != "nt")

            async def send(payload: dict[str, Any]) -> None:
                process.stdin.write((json.dumps({"jsonrpc": "2.0", **payload}) + "\n").encode())
                await process.stdin.drain()

            async def receive(identity: int) -> dict[str, Any]:
                # 서버 알림을 무제한으로 수용하지 않는다.
                for _ in range(16):
                    line = await process.stdout.readline()
                    if not line or len(line) > MAX_RESPONSE:
                        raise ValueError()
                    message = json.loads(line)
                    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                        raise ValueError()
                    if message.get("id") == identity:
                        if "error" in message or not isinstance(message.get("result"), dict):
                            raise ValueError()
                        return message["result"]
                raise ValueError()

            await send({"id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "aside-jev-local-probe", "version": "1"}}})
            initialized = await receive(1)
            if not isinstance(initialized.get("capabilities"), dict) or not initialized.get("protocolVersion"):
                raise ValueError()
            await send({"method": "notifications/initialized"})
            await send({"id": 2, "method": "tools/list", "params": {}})
            listed = await receive(2)
            tools = listed.get("tools")
            if not isinstance(tools, list) or listed.get("nextCursor"):
                raise ValueError()
            names = [tool.get("name") if isinstance(tool, dict) else None for tool in tools]
            if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names) or not REQUIRED_TOOLS.issubset(names):
                raise ValueError()
            return len(tools)
    finally:
        if process is not None:
            # 검사 전용 자식은 성공/실패/시간 초과 모두 즉시 정리한다.
            if process.stdin:
                process.stdin.close()
            try:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                elif process.returncode is None:
                    process.kill()
            except ProcessLookupError:
                pass
            # Windows에서는 가득 찬 stdout 파이프가 wait() 완료를 막을 수 있다.
            # 종료된 자식의 남은 출력을 버리면서 파이프를 닫고 정리 시간도 제한한다.
            try:
                await asyncio.wait_for(process.communicate(), timeout=2)
            except TimeoutError:
                process._transport.close()
                raise


def run(command: str, args: list[str], cwd: str, *, timeout_s: float = TIMEOUT_S) -> dict[str, Any]:
    try:
        count = asyncio.run(_probe(command, args, cwd, timeout_s))
        return result("ready", "local_probe_ready", count)
    except TimeoutError:
        return result("failed", "probe_timeout")
    except FileNotFoundError:
        return result("failed", "launcher_missing")
    except PermissionError:
        return result("failed", "launcher_denied")
    except Exception:
        # 오류 본문과 서버 stdout/stderr는 응답이나 로그에 복제하지 않는다.
        return result("failed", "probe_failed")
