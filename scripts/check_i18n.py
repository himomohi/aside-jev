"""언어별 공개 산출물 연결·문서 링크·영상 사전의 누락을 검사한다."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    mapping = json.loads((ROOT / "README.i18n.json").read_text())
    assert mapping["default_locale"] == "en"
    for locale, artifacts in mapping["locales"].items():
        readme = (ROOT / artifacts["readme"]).read_text()
        for kind, relative in artifacts.items():
            assert (ROOT / relative).is_file(), f"{locale}: missing {kind}: {relative}"
            if kind != "readme":
                assert relative in readme, f"{locale}: README does not link {relative}"
    en = json.loads((ROOT / "video/src/locales/en.json").read_text())
    ko = json.loads((ROOT / "video/src/locales/ko.json").read_text())
    assert en.keys() == ko.keys(), "Video locale keys differ"
    docs = [ROOT / "README.md", ROOT / "README.ko.md", ROOT / "CHANGELOG.md", ROOT / "CHANGELOG.ko.md"]
    docs += list((ROOT / "docs").rglob("*.md")) + list((ROOT / "video").glob("README*.md"))
    count = 0
    for path in docs:
        source = path.read_text()
        links = re.findall(r'(?:src|href)="([^\"]+)"', source)
        links += re.findall(r'\]\(([^) ]+)\)', source)
        for link in links:
            if re.match(r"^(?:https?://|#)", link):
                continue
            target = unquote(link.split("#", 1)[0])
            assert (path.parent / target).exists(), f"Broken link in {path.relative_to(ROOT)}: {link}"
            count += 1
    print(f"PASS: 2 locales, mapped artifacts, video keys, {count} local documentation links")


if __name__ == "__main__":
    main()
