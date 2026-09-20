#!/usr/bin/env python3
"""실제 Aside에서 localhost fixture를 6번 이동한다. Jev API 호출은 하지 않는다."""
from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from urllib.parse import parse_qs, urlparse

from aside_jev.browser_flow import run_browser_flow
from aside_jev.browser_runtime import connect_aside


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        step = int(parse_qs(urlparse(self.path).query).get("step", ["0"])[0])
        body = f'<!doctype html><html><meta charset="utf-8"><title>Aside Jev 로컬 검증</title><h1>단계 {step}</h1>'
        body += f'<a href="?step={step + 1}">Continue</a>' if step < 6 else '<h2>Journey complete</h2>'
        body += "</html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_args):
        pass


def fixture_decision(**kwargs):
    ids = [item.id for item in kwargs["candidates"]]
    return ("finish" if "finish" in ids else "action-0", 1.0, {})


async def verify(url: str):
    async with connect_aside() as runtime:
        opened = await runtime._call(
            f"var fixtureTab=await openTab({json.dumps(url)});"
            "console.log(JSON.stringify({marker:'aside-jev-runtime-v1',targetId:(await listBrowserTabs()).find(t=>t.url===fixtureTab.url()).targetId}));"
        )
        try:
            result = await run_browser_flow(
                runtime, goal="Follow Continue until Journey complete", target_id=opened["targetId"],
                action_rules=[{"role": "link", "name": "Continue", "action": "click"}],
                completion_text="Journey complete", completion_url=url + "?step=6",
                decision=fixture_decision,
            )
            result["provider"] = "fixture_stub"
            result["live_jev_verified"] = False
            print(json.dumps(result, ensure_ascii=False, indent=2))
            assert result["verified"] and sum(step["executed"] for step in result["steps"]) == 6
        finally:
            await runtime._call("await closeTab(fixtureTab); console.log(JSON.stringify({marker:'aside-jev-runtime-v1',closed:true}));")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        asyncio.run(verify(f"http://127.0.0.1:{server.server_port}/"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
