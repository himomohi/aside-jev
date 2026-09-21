import json
import os
from pathlib import Path
import sys
import time

import pytest

from aside_jev import connection_check as probe


def script(tmp_path, text):
    path = tmp_path / 'probe.py'
    path.write_text(text)
    return str(path)


def test_failure_details_never_escape(tmp_path):
    path = script(tmp_path, 'import sys\nprint("private-provider-body")\nprint("private-secret", file=sys.stderr)\n')
    result = probe.run(sys.executable, [path], str(tmp_path))
    assert result['code'] == 'probe_failed'
    assert 'private' not in json.dumps(result)


def test_timeout_kills_child(tmp_path):
    pidfile = tmp_path / 'pid'
    path = script(tmp_path, f'import os,time\nopen({str(pidfile)!r}, "w").write(str(os.getpid()))\ntime.sleep(60)\n')
    started = time.monotonic()
    result = probe.run(sys.executable, [path], str(tmp_path), timeout_s=0.5)
    assert result['code'] == 'probe_timeout'
    assert time.monotonic() - started < 4
    if os.name != 'nt':
        with pytest.raises(ProcessLookupError):
            os.kill(int(pidfile.read_text()), 0)


def test_missing_launcher(tmp_path):
    assert probe.run(str(tmp_path / 'missing'), [], str(tmp_path))['code'] == 'launcher_missing'


def test_environment_omits_credentials_and_python_injection(monkeypatch):
    for name in ('TYPESAFE_API_KEY', 'TYPESAFEAI_API_KEY', 'OTHER_API_KEY', 'PYTHONPATH', 'PYTHONSTARTUP'):
        monkeypatch.setenv(name, 'fixture-private')
    assert 'fixture-private' not in json.dumps(probe.clean_environment())


def test_oversize_response_is_bounded(tmp_path):
    path = script(tmp_path, 'import sys\nsys.stdout.write("x" * 1000000)\nsys.stdout.flush()\n')
    assert probe.run(sys.executable, [path], str(tmp_path), timeout_s=1)['state'] == 'failed'


@pytest.mark.parametrize('listing', [
    {'tools': []}, {'tools': [{'name': 'jev_step'}]},
    {'tools': None}, {'tools': [{'name': None}]},
    {'tools': [{'name': name} for name in probe.REQUIRED_TOOLS], 'nextCursor': 'more'},
])
def test_missing_or_incomplete_tools_never_report_ready(tmp_path, listing):
    path = script(tmp_path, f'''import json,sys
json.loads(sys.stdin.readline())
print(json.dumps({{"jsonrpc":"2.0","id":1,"result":{{"protocolVersion":"2024-11-05","capabilities":{{}}}}}}),flush=True)
json.loads(sys.stdin.readline())
json.loads(sys.stdin.readline())
print(json.dumps({{"jsonrpc":"2.0","id":2,"result":{listing!r}}}),flush=True)
''')
    assert probe.run(sys.executable, [path], str(tmp_path))['state'] == 'failed'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX process groups')
def test_timeout_terminates_spawned_child_group(tmp_path):
    pidfile = tmp_path / 'child-pid'
    path = script(tmp_path, f'''import subprocess,sys,time
child=subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
open({str(pidfile)!r}, 'w').write(str(child.pid))
time.sleep(60)
''')
    assert probe.run(sys.executable, [path], str(tmp_path), timeout_s=0.5)['code'] == 'probe_timeout'
    child_pid = int(pidfile.read_text())
    # 운영체제의 zombie 수거 시점은 다르므로 실행 중 상태만 검사한다.
    import subprocess
    state = subprocess.run(['ps', '-o', 'stat=', '-p', str(child_pid)], capture_output=True, text=True).stdout.strip()
    assert not state or state.startswith('Z')
