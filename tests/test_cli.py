import json

import pytest

from aside_jev.cli import main


def test_doctor_does_not_expose_key(monkeypatch, capsys):
    monkeypatch.setenv("TYPESAFE_API_KEY", "sentinel-private-key")
    with pytest.raises(SystemExit) as exc:
        main(["doctor", "--json"])
    assert exc.value.code == 0
    output = capsys.readouterr().out
    assert json.loads(output)["live_available"] is True
    assert "sentinel" not in output


def test_choose_outputs_json_and_timing(tmp_path, capsys):
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps([{"id": "next", "description": "Next action"}]))
    with pytest.raises(SystemExit) as exc:
        main(["choose", "--goal", "test", "--candidates", str(path)])
    assert exc.value.code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["choice_id"] == "next"
    assert result["provider"] == "mock"
    assert result["timing_ms"]["total"] >= 0


def test_bad_json_has_friendly_error_without_input(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("private-content is not json")
    with pytest.raises(SystemExit) as exc:
        main(["choose", "--goal", "test", "--candidates", str(path)])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "Invalid JSON" in output.err
    assert "private-content" not in output.err
    assert "Traceback" not in output.err


def test_dashboard_rejects_invalid_port(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["dashboard", "--port", "65536"])
    assert exc.value.code == 2
    assert "Port" in capsys.readouterr().err
