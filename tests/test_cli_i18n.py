import json

import pytest

from aside_jev.cli import main
from aside_jev.cli_i18n import MESSAGES, text


def test_cli_dictionaries_and_fallback():
    assert set(MESSAGES["en"]) == set(MESSAGES["ko"])
    assert text("demo_ready", "unsupported") == "Local demo: available"


@pytest.mark.parametrize("args, expected", [
    (["doctor"], "Local demo: available"),
    (["--lang", "ko", "doctor"], "로컬 데모: 사용 가능"),
    (["doctor", "--lang", "ko"], "로컬 데모: 사용 가능"),
])
def test_doctor_language(args, expected, capsys):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 0
    assert expected in capsys.readouterr().out


def test_machine_output_keys_do_not_depend_on_language(capsys):
    results = []
    for locale in ["en", "ko"]:
        with pytest.raises(SystemExit) as exc:
            main(["--lang", locale, "doctor", "--json"])
        assert exc.value.code == 0
        results.append(json.loads(capsys.readouterr().out))
    assert results[0] == results[1]


def test_localized_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "ko", "dashboard", "--help"])
    assert exc.value.code == 0
    assert "로컬 포트" in capsys.readouterr().out
