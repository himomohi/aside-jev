from concurrent.futures import ThreadPoolExecutor
import json
import threading

import httpx2
import pytest
from typesafe_sdk import RetryPolicy, TypeSafeClient

from aside_jev import jev
from aside_jev.core import Candidate

CANDIDATES = [Candidate("a", "A", tool="click", arguments={"ref": "a"})]


def choice_response(choice="a", confidence=0.9):
    return {
        "model": "jev-test", "usage": {"input_tokens": 12, "output_tokens": 1},
        "answers": {"aside_action": {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": {choice: confidence}}},
    }


@pytest.fixture
def fake_provider(monkeypatch):
    jev.close_clients()
    created = []
    requests = []
    handler = {"call": lambda request: httpx2.Response(200, json=choice_response())}
    original = jev._new_client

    def build(key, base_url):
        def handle(request):
            requests.append(request)
            return handler["call"](request)
        # 실제 factory의 timeout/retry 설정과 SDK 직렬화 경로를 그대로 검증한다.
        real_constructor = TypeSafeClient
        def constructor(**kwargs):
            kwargs["transport"] = httpx2.MockTransport(handle)
            client = real_constructor(**kwargs)
            created.append(client)
            return client
        import typesafe_sdk
        with monkeypatch.context() as scope:
            scope.setattr(typesafe_sdk, "TypeSafeClient", constructor)
            return original(key, base_url)
    monkeypatch.setattr(jev, "_new_client", build)
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    yield created, requests, handler
    jev.close_clients()


def choose(**kwargs):
    return jev.choose_live(CANDIDATES, goal="Goal", observation={"safe": "value"}, **kwargs)


def test_reuses_client_across_requests_but_never_caches_decisions(fake_provider):
    created, requests, handler = fake_provider
    assert choose()[1] == 0.9
    handler["call"] = lambda request: httpx2.Response(200, json=choice_response(confidence=0.6))
    assert choose(timeout_s=3)[1] == 0.6
    assert len(created) == 1
    assert len(requests) == 2
    assert requests[0].extensions["timeout"]["read"] == 15.0
    assert requests[1].extensions["timeout"]["read"] == 3.0
    jev.close_clients()
    assert created[0]._http_client.is_closed


def test_shared_client_handles_concurrent_requests(fake_provider):
    created, requests, handler = fake_provider
    barrier = threading.Barrier(4)
    def respond(request):
        barrier.wait(timeout=3)
        return httpx2.Response(200, json=choice_response())
    handler["call"] = respond
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: choose(), range(4)))
    assert len(results) == 4
    assert len(created) == 1
    assert len(requests) == 4


def test_timeout_has_no_retry_and_no_secret_details(fake_provider):
    _, requests, handler = fake_provider
    def timeout(request):
        raise httpx2.ReadTimeout("sensitive-response", request=request)
    handler["call"] = timeout
    with pytest.raises(jev.JevProviderError) as error:
        choose(timeout_s=1)
    assert error.value.code == "timeout"
    assert "sensitive-response" not in str(error.value)
    assert len(requests) == 1


@pytest.mark.parametrize("status,code", [(401, "authentication"), (403, "authentication"), (429, "rate_limit"), (503, "unavailable")])
def test_provider_errors_are_actionable_and_redacted(fake_provider, status, code):
    _, requests, handler = fake_provider
    handler["call"] = lambda request: httpx2.Response(status, json={"message": "secret server body fake-key"})
    with pytest.raises(jev.JevProviderError) as error:
        choose()
    assert error.value.code == code
    assert "secret" not in str(error.value)
    assert "fake-key" not in str(error.value)
    assert len(requests) == 1


@pytest.mark.parametrize("confidence", [-0.1, 1.1, None])
def test_invalid_confidence_never_returns_an_action(fake_provider, confidence):
    _, _, handler = fake_provider
    handler["call"] = lambda request: httpx2.Response(200, json=choice_response(confidence=confidence))
    with pytest.raises(jev.JevProviderError) as error:
        choose()
    assert error.value.code == "invalid_response"


def test_observation_history_and_goal_are_redacted_on_the_wire(fake_provider):
    _, requests, _ = fake_provider
    jev.choose_live(
        CANDIDATES, goal="password=goal-secret",
        observation={"nested": {"apiKey": "observation-secret"}},
        history=[{"step": i, "token": "history-secret"} for i in range(40)],
    )
    body = json.loads(requests[0].content)
    assert "secret" not in requests[0].content.decode()
    assert len(body["state"]["history"]) == 12
    assert body["state"]["history"][-1]["step"] == 39


def test_key_rotation_does_not_reuse_authenticated_client(fake_provider):
    created, requests, _ = fake_provider
    choose(api_key="first")
    choose(api_key="second")
    assert len(created) == 2
    assert requests[0].headers["authorization"] != requests[1].headers["authorization"]


def test_pool_evicts_only_idle_clients(fake_provider):
    created, _, _ = fake_provider
    for i in range(7):
        choose(api_key=f"key-{i}")
    assert len(jev._clients) == 4
    assert all(client._http_client.is_closed for client in created[:3])


def test_close_does_not_interrupt_in_flight_request(fake_provider):
    created, _, handler = fake_provider
    started, release = threading.Event(), threading.Event()
    def respond(request):
        started.set()
        assert release.wait(3)
        return httpx2.Response(200, json=choice_response())
    handler["call"] = respond
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(choose)
        assert started.wait(3)
        jev.close_clients()
        assert not created[0]._http_client.is_closed
        release.set()
        assert pending.result()[0] == "a"
    assert created[0]._http_client.is_closed


def test_general_questions_preserve_score_scale_and_noul_criteria(fake_provider):
    created, requests, handler = fake_provider
    handler["call"] = lambda request: httpx2.Response(200, json={
        "model": "jev-test", "usage": {}, "answers": {
            "risk": {"type": "score", "score": 1.7, "confidence": 0.8, "probabilities": {"0": 0.0, "1": 0.3, "2": 0.7}, "legend": {"0": "low", "1": "mid", "2": "high"}},
            "done": {"type": "noul", "noul": 0.1},
        },
    })
    result = jev.system_one(
        {"secret": "hidden"}, {
            "risk": {"type": "score", "criteria": ["low", "mid", "high"]},
            "done": {"type": "noul", "criteria": {"true": "Finished", "false": "Incomplete"}},
        },
    )
    assert result["answers"]["risk"]["score"] == 1.7
    assert result["answers"]["done"]["noul"] == 0.1
    assert "hidden" not in requests[0].content.decode()


@pytest.mark.parametrize("timeout", [0, 61, float("nan"), True, "15"])
def test_invalid_timeout_never_calls_provider(fake_provider, timeout):
    created, requests, _ = fake_provider
    with pytest.raises(ValueError, match="timeout_s"):
        choose(timeout_s=timeout)
    assert not created and not requests


def test_general_questions_reject_wrong_answer_kind(fake_provider):
    _, _, handler = fake_provider
    handler["call"] = lambda request: httpx2.Response(200, json={
        "model": "jev-test", "usage": {}, "answers": {"answer": {"type": "noul", "noul": 0.9}},
    })
    with pytest.raises(jev.JevProviderError) as error:
        jev.system_one("state", {"answer": {"type": "choice", "criteria": {"yes": "Yes"}}})
    assert error.value.code == "invalid_response"


def test_busy_requests_fail_without_waiting_or_extra_provider_calls(fake_provider):
    _, requests, handler = fake_provider
    condition = threading.Condition()
    release = threading.Event()
    active = 0
    def respond(request):
        nonlocal active
        with condition:
            active += 1
            condition.notify_all()
        assert release.wait(3)
        return httpx2.Response(200, json=choice_response())
    handler["call"] = respond
    with ThreadPoolExecutor(max_workers=jev.MAX_IN_FLIGHT) as executor:
        pending = [executor.submit(choose) for _ in range(jev.MAX_IN_FLIGHT)]
        try:
            with condition:
                assert condition.wait_for(lambda: active == jev.MAX_IN_FLIGHT, timeout=3)
            with pytest.raises(jev.JevBusyError):
                choose()
            assert len(requests) == jev.MAX_IN_FLIGHT
        finally:
            release.set()
        assert all(task.result()[0] == "a" for task in pending)
