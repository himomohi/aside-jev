"""수동 ON 요청의 준비 검사. 검사 실패 시 실행을 허용하지 않는다."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from . import extension_control as control

MAX_AGE = 3600


def fingerprint(config: dict[str, Any]) -> str:
    return hashlib.sha256(control._json_bytes(config)).hexdigest()


def status(root, config) -> dict[str, Any]:
    try:
        value = json.loads(control._text(root / 'activation.json', limit=4096) or '{}')
        if not isinstance(value, dict):
            return {'state': 'unverified', 'stage': 'not_checked'}
        stamp = value.get('checked_at')
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not 0 < stamp <= time.time():
            return {'state': 'unverified', 'stage': 'not_checked'}
        if value.get('fingerprint') != fingerprint(config):
            return {'state': 'unverified', 'stage': 'settings_changed'}
        if value.get('state') == 'ready' and time.time() - value.get('checked_at', 0) > MAX_AGE:
            return {'state': 'unverified', 'stage': 'expired'}
        return {key: value[key] for key in ('state', 'stage', 'checked_at') if key in value}
    except (ValueError, OSError, control.ControlError):
        return {'state': 'unverified', 'stage': 'not_checked'}


def invalidate() -> None:
    root = control.config_root()
    with control._lock(root):
        control._atomic_write(root / 'activation.json', b'{}')


async def check_aside(expected_entry: dict[str, Any]) -> None:
    from .browser_runtime import connect_aside
    async with asyncio.timeout(10):
        async with connect_aside() as runtime:
            # 실제 Aside 계정 설정과 브라우저 RPC를 읽는다. URL/탭 내용은 반환하지 않는다.
            value = await runtime._call(
                "var activationMcp=aside.settings.get('mcp');"
                "var activationTabs=await listBrowserTabs();"
                "console.log(JSON.stringify({marker:'aside-jev-runtime-v1',"
                "tools:activationMcp?.inventories?.['aside-jev']?.tools?.map(t=>t.name),entry:activationMcp?.servers?.['aside-jev'],browserReady:Array.isArray(activationTabs)}));")
            from .connection_check import REQUIRED_TOOLS
            if (value.get('entry') != expected_entry or value.get('browserReady') is not True
                    or not isinstance(value.get('tools'), list) or not REQUIRED_TOOLS.issubset(value['tools'])):
                raise RuntimeError('aside_connection_mismatch')


def check_api(config: dict[str, Any]) -> None:
    from .jev import system_one
    values = control._key_values(config)
    key = next((values[name] for name in control.KEY_NAMES if values.get(name)), None)
    if not key:
        raise RuntimeError('key_missing')
    # 개인 화면 대신 고정 합성 데이터로 인증과 응답 계약만 검사한다.
    result = system_one({'connection_test': True}, {'ready': {
        'type': 'noul', 'criteria': {'true': 'connection_test is true', 'false': 'connection_test is false'}}},
        api_key=key, model=config['model'], timeout_s=3)
    if result['answers']['ready']['type'] != 'noul':
        raise RuntimeError('invalid_api_response')


def activate() -> dict[str, Any]:
    from .connection_check import run
    root = control.config_root()
    # 긴 검사 중 lock을 유지하지 않는다. OFF/설정 변경은 마지막 fingerprint로 감지한다.
    with control._lock(root):
        config = control._load_config(root)
        current = status(root, config)
        if current.get('state') == 'checking' and time.time() - current.get('checked_at', 0) < 60:
            raise control.ControlError('busy', 'Connection verification is already running.')
        control._atomic_write(root / 'activation.json', b'{}')
        control._apply(root, config, True)
        config = control._load_config(root)
        identity = fingerprint(config)
        stamp = time.time()
        def save(state, stage):
            control._atomic_write(root / 'activation.json', control._json_bytes({
                'state': state, 'stage': stage, 'checked_at': stamp, 'fingerprint': identity}))
        save('checking', 'mcp')
    stage = 'mcp'
    try:
        entry = control._mcp_entry(config)
        checked = run(entry['command'], entry['args'], str(root))
        if checked['state'] != 'ready':
            raise RuntimeError('mcp_unavailable')
        stage = 'api'
        check_api(config)
        stage = 'aside'
        asyncio.run(check_aside(entry))
        state, stage = 'ready', 'complete'
    except Exception:
        state = 'failed'
    with control._lock(root):
        fresh = control._load_config(root)
        if fingerprint(fresh) != identity or status(root, fresh).get('checked_at') != stamp:
            return control._status(root, fresh)
        save(state, stage)
        return control._status(root, fresh)
