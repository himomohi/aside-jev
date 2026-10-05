"""Execute the actual generated REPL JavaScript against deterministic snapshots."""
import asyncio
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from aside_jev.browser_runtime import AsideRuntime, Observation

TREE = '- link "Continue" [ref=e1]\n' + '- text "Large page"\n' * 20000
URL = "https://example.test/"
ACTION = {"action": "click", "line": '- link "Continue" [ref]', "role": "link", "name": "Continue"}


def snippets():
    class Session:
        codes = []
        async def call_tool(self, name, args):
            self.codes.append(args["code"])
            value = {"marker": "aside-jev-runtime-v1", "url": URL, "tree": TREE}
            return SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text=json.dumps(value))])
    session = Session()
    runtime = AsideRuntime(session)
    async def run():
        expected = await runtime.attach("tab1")
        await runtime.execute(ACTION, expected, timeout_ms=1000)
    asyncio.run(run())
    return session.codes


def test_execution_request_does_not_resend_large_tree():
    attach, execute = snippets()
    assert len(TREE) > 300000
    assert len(execute) < 2000
    assert "Large page" not in execute
    assert "normalized!==__asideJevIdentity" in execute


@pytest.mark.parametrize("changed,duplicate,expected", [(False, False, 1), (True, False, 0), (False, True, 0)])
def test_generated_js_checks_fresh_page_and_unique_target(changed, duplicate, expected):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node required to execute REPL fixture")
    attach, execute = snippets()
    before = TREE + ('\n- title "changed"' if changed else '')
    if duplicate:
        # The attach sees the same duplicate tree; only the uniqueness guard blocks.
        before = TREE + '\n- link "Continue" [ref=e2]'
    snapshots = [before if duplicate else TREE, before, '- heading "Done"']
    script = """
const assert = require('node:assert/strict');
let count = 0;
let trees = SNAPSHOTS;
async function attachBrowserTab() { return {url: () => URL, locator: () => ({click: async () => {count++;}})}; }
async function snapshot() { return {tree: trees.shift()}; }
(async () => { ATTACH EXECUTE assert.equal(count, EXPECTED); })().catch(e => {console.error(e); process.exit(1);});
""".replace("SNAPSHOTS", json.dumps(snapshots)).replace("URL", json.dumps(URL)).replace("ATTACH", attach).replace("EXECUTE", execute).replace("EXPECTED", str(expected))
    subprocess.run([node, "-"], input=script, text=True, capture_output=True, check=True, timeout=10)


def test_wrong_expected_observation_never_calls_browser():
    class Session:
        async def call_tool(self, *args):
            raise AssertionError("Must not read or execute with an unattached observation")
    runtime = AsideRuntime(Session())
    assert asyncio.run(runtime.execute(ACTION, Observation(URL, TREE), timeout_ms=1000)) is None


@pytest.mark.parametrize("failure", [RuntimeError("disconnected"), asyncio.CancelledError()])
def test_failed_or_cancelled_call_invalidates_confirmed_observation(failure):
    class Session:
        calls = 0
        async def call_tool(self, *args):
            self.calls += 1
            if self.calls > 1:
                raise failure
            value = {"marker": "aside-jev-runtime-v1", "url": URL, "tree": TREE}
            return SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text=json.dumps(value))])
    session = Session()
    runtime = AsideRuntime(session)
    async def run():
        expected = await runtime.attach("tab1")
        with pytest.raises(type(failure)):
            await runtime.execute(ACTION, expected, timeout_ms=1000)
        assert await runtime.execute(ACTION, expected, timeout_ms=1000) is None
        assert session.calls == 2
    asyncio.run(run())
