import json
import pytest
from aside_jev import activation, extension_control as control, connection_check, extension_gate
from test_extension_control import installation, isolated_global_rules


def ready_fakes(monkeypatch, installation):
    root, profile, _ = installation
    monkeypatch.setenv('TYPESAFE_API_KEY','fixture-only')
    config=control._load_config(root)
    (profile/'settings.json').write_text(json.dumps({'mcp':{'servers':{'aside-jev':control._mcp_entry(config)}}}))
    monkeypatch.setattr(connection_check,'run',lambda *a,**kw:{'state':'ready'})
    monkeypatch.setattr(activation,'check_api',lambda config:None)
    async def aside(entry): pass
    monkeypatch.setattr(activation,'check_aside',aside)
    return root


def test_activation_all_checks_and_settings_change_invalidate(monkeypatch, installation):
    ready_fakes(monkeypatch,installation)
    assert not control.get_status()['execution_ready']
    assert activation.activate()['execution_ready']
    assert not control.configure(min_confidence=.9)['execution_ready']


@pytest.mark.parametrize('failed', ['mcp','api','aside'])
def test_failed_check_never_unlocks_execution(monkeypatch,installation,failed):
    ready_fakes(monkeypatch,installation)
    if failed=='mcp': monkeypatch.setattr(connection_check,'run',lambda *a,**kw:{'state':'failed'})
    if failed=='api':
        def api(config): raise RuntimeError('private secret must not leak')
        monkeypatch.setattr(activation,'check_api',api)
    if failed=='aside':
        async def aside(entry): raise RuntimeError('private secret must not leak')
        monkeypatch.setattr(activation,'check_aside',aside)
    value=activation.activate()
    assert not value['execution_ready']
    assert value['activation']['state']=='failed'
    assert value['activation']['stage']==failed
    assert 'private secret' not in str(value)


def test_off_during_check_cannot_be_reenabled(monkeypatch,installation):
    ready_fakes(monkeypatch,installation)
    def cancel(config): control.set_enabled(False)
    monkeypatch.setattr(activation,'check_api',cancel)
    value=activation.activate()
    assert not value['enabled'] and not value['execution_ready']


def test_unverified_policy_blocks_before_credentials(monkeypatch):
    monkeypatch.setenv('ASIDE_JEV_EXTENSION_MODE','1')
    monkeypatch.setattr(control,'load_runtime_policy',lambda:{'enabled':True,'execution_ready':False})
    def forbidden(): raise AssertionError('must not access provider')
    monkeypatch.setattr(control,'load_key_environment',forbidden)
    with pytest.raises(RuntimeError,match='not verified'): extension_gate.active_policy()


def test_expired_verification_and_off_invalidate(monkeypatch,installation):
    ready_fakes(monkeypatch,installation)
    assert activation.activate()['execution_ready']
    now=activation.time.time()
    monkeypatch.setattr(activation.time,'time',lambda:now+activation.MAX_AGE+1)
    assert not control.get_status()['execution_ready']
    control.set_enabled(False)
    control.set_enabled(True)
    assert not control.get_status()['execution_ready']


@pytest.mark.parametrize('value', [[], None, 1, {'checked_at': 'invalid'}, {'checked_at': True}, {'checked_at': float('nan')}, {'checked_at': float('inf')}])
def test_malformed_activation_state_stays_locked(installation, value):
    root, _, _ = installation
    (root / 'activation.json').write_text(json.dumps(value))
    assert activation.status(root, control._load_config(root))['state'] == 'unverified'
