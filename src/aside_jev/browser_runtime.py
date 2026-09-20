"""작업 동안 하나의 Aside MCP/REPL 세션을 유지하는 고정 실행기."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import re
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .aside_bridge import resolve_aside_bin

REF = re.compile(r"\[ref=(?:f\d+)?e\d+\]")
MAX_SNAPSHOT_CHARS = 500_000


@dataclass(frozen=True)
class Observation:
    url: str
    tree: str

    @property
    def identity(self) -> str:
        return self.url + "\n" + REF.sub("[ref]", self.tree)


class BrowserRuntimeError(RuntimeError):
    pass


class AsideRuntime:
    def __init__(self, session: ClientSession):
        self.session = session

    async def _call(self, code: str) -> dict[str, Any]:
        response = await self.session.call_tool("repl", {"code": code, "title": "Jev 브라우저 단계"})
        if response.isError:
            raise BrowserRuntimeError("Aside REPL 호출에 실패했습니다. 실행 결과를 확인한 뒤 수동으로 재개해 주세요.")
        for block in response.content:
            if getattr(block, "type", None) != "text":
                continue
            for line in reversed(block.text.splitlines()):
                try:
                    value = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict) and value.get("marker") == "aside-jev-runtime-v1":
                    return value
        raise BrowserRuntimeError("Aside REPL 응답 형식을 확인할 수 없습니다.")

    @staticmethod
    def _observation(value: dict[str, Any]) -> Observation:
        if not isinstance(value.get("url"), str) or not isinstance(value.get("tree"), str):
            raise BrowserRuntimeError("Aside 화면 관찰이 누락되었습니다.")
        if len(value["tree"]) > MAX_SNAPSHOT_CHARS:
            raise BrowserRuntimeError("페이지가 관찰 한도를 초과했습니다. 작업 범위를 좁혀 주세요.")
        return Observation(value["url"], value["tree"])

    async def attach(self, target_id: str) -> Observation:
        value = await self._call(
            "var __asideJevPage = await attachBrowserTab(" + json.dumps(target_id) + ");"
            "console.log(JSON.stringify({marker:'aside-jev-runtime-v1',url:__asideJevPage.url(),"
            "tree:(await snapshot(__asideJevPage)).tree}));"
        )
        return self._observation(value)

    async def execute(self, action: dict[str, Any], expected: Observation, *, timeout_ms: int) -> Observation | None:
        # 실행할 코드는 아래 세 종류로 한정한다. 모델 출력은 코드로 평가하지 않는다.
        operation = action["action"]
        if operation not in ("click", "focus", "fill"):
            raise ValueError("Unsupported browser action")
        argument = json.dumps(action.get("value", ""), ensure_ascii=False) + "," if operation == "fill" else ""
        expression = f"await __asideJevPage.locator(ref).{operation}({argument}{{timeout:{timeout_ms}}});"
        value = await self._call(
            "console.log(JSON.stringify(await (async()=>{"
            "const before=await snapshot(__asideJevPage);"
            "const normalized=__asideJevPage.url()+'\\n'+before.tree.replace(/\\[ref=(?:f\\d+)?e\\d+\\]/g,'[ref]');"
            f"if(normalized!=={json.dumps(expected.identity, ensure_ascii=False)})"
            "return {marker:'aside-jev-runtime-v1',stale:true};"
            "const lines=before.tree.split('\\n').filter(line=>line.replace(/\\[ref=(?:f\\d+)?e\\d+\\]/g,'[ref]')==="
            + json.dumps(action["line"], ensure_ascii=False) + ");"
            "if(lines.length!==1) return {marker:'aside-jev-runtime-v1',stale:true};"
            "const ref=lines[0].match(/\\[ref=((?:f\\d+)?e\\d+)\\]/)?.[1];"
            "if(!ref) return {marker:'aside-jev-runtime-v1',stale:true};"
            + expression +
            "return {marker:'aside-jev-runtime-v1',url:__asideJevPage.url(),tree:(await snapshot(__asideJevPage)).tree};"
            "})()));"
        )
        return None if value.get("stale") else self._observation(value)


@asynccontextmanager
async def connect_aside() -> AsyncIterator[AsideRuntime]:
    parameters = StdioServerParameters(command=resolve_aside_bin(), args=["mcp"])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield AsideRuntime(session)
