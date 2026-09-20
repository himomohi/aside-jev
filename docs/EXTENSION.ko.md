[English](EXTENSION.md) | **한국어**

# Aside Jev 설치

## 간편 설치

1. [Aside](https://aside.com/download)를 설치하고 로그인해 한 번 실행합니다. 설정을 적용하기 전에는 Aside를 종료하세요.
2. [프로젝트 ZIP](https://github.com/himomohi/aside-jev/archive/refs/heads/main.zip)을 내려받아 압축을 풀고 macOS는 **Install.command**, Windows는 **Install.cmd**를 실행합니다.
3. 계정을 선택하고 숨김 입력으로 Jev API 키를 입력한 뒤 표시된 경로를 확인해 적용합니다. Aside 다시 열기 → 확장 관리 → 개발자 모드 → **압축해제된 확장 로드**에서 설치기가 표시한 폴더를 선택하세요. Aside Jev를 고정하고 **ON**으로 켠 뒤 새 작업을 시작합니다.

Git, Python, uv를 미리 설치하지 않아도 됩니다. 설치기가 필요할 때 uv 0.12.17을 내려받아 압축 파일의 SHA-256을 검증하고, Python 3.11과 전용 실행 환경을 준비합니다. 의존성은 저장소의 `uv.lock`과 해시를 기준으로 설치합니다. 다운로드에는 인터넷이 필요합니다. PATH·실행 정책·로그인 항목·OS 서비스는 변경하지 않습니다. Native Messaging 도우미는 팝업 요청에 응답할 때만 실행되며 MCP 프로세스는 Aside가 관리합니다.

확장은 고정된 폴더에 복사하므로 설치 후 내려받은 ZIP 폴더를 삭제해도 연결을 유지합니다. 선택한 계정의 `settings.json`에서 `mcp.servers.aside-jev`만 병합하고 나머지 설정과 MCP는 보존합니다. 변경 파일은 백업하며 다른 설치가 소유한 `aside-jev` 항목은 덮어쓰지 않습니다. 실행 중인 Aside가 나중에 저장한 설정을 덮어쓸 수 있으므로 **설치 적용 시에는 Aside를 종료**하세요.

확장에는 고정 공개키와 ID `pendehmejnpgceflngbnbpagpodiiemg`가 포함됩니다. 공개키는 비밀값이 아니며 개인 서명키는 배포하지 않습니다. 새 간편 설치에서는 확장 ID를 복사할 필요가 없습니다.

### 영어 / 한국어

기본 언어는 영어입니다. 압축을 푼 폴더에서 아래 명령으로 한국어를 선택합니다.

| 플랫폼 | 한국어 설치 |
| --- | --- |
| macOS 터미널 | `bash scripts/install.sh --lang ko` |
| Windows 명령 프롬프트 | `.\Install.cmd --lang ko` |

macOS에서 다운로드한 `.command`가 열리지 않으면 터미널에서 `bash scripts/install.sh`를 사용하세요. OS 보안 정책은 유지합니다. 관리되는 Windows 기기의 다운로드·실행 제한은 정상적인 관리자 절차를 따라야 합니다.

<a id="windows"></a>

## Windows 등록

Aside는 [v1.0.914.1 변경 기록](https://docs.aside.com/changelog/native)에서 Windows 지원을 공식 발표했습니다. Native Messaging은 Windows에서 [브라우저별 레지스트리 키](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)를 사용하고 macOS에서는 manifest 폴더를 사용합니다.

HKCU 또는 HKLM에 Aside의 `NativeMessagingHosts` 부모가 **이미 있을 때만** `Software\Aside\NativeMessagingHosts\com.aside_jev.control`을 제안합니다. 제품·업데이터 등록 키만으로는 추정하지 않습니다. 부모가 없다면 설치한 Aside 빌드에서 확인한 Native Messaging 키를 `--windows-registry-key` 또는 설치 입력란에 지정해야 합니다. Chrome/Edge에 대신 등록하지 않습니다. 키를 확인할 수 없다면 해당 단계에서 중단하세요. Python 패키지 설치만으로 브라우저 연결이 성립하지는 않습니다.

관리자 권한 상승 없이 지정한 호스트만 **HKCU**에 등록합니다. 기존 등록 충돌을 감지하고 파일을 백업하며, 등록 실패 시 파일 변경도 원복합니다. Windows 실행기는 바이너리 메시지와 브라우저의 `--parent-window` 인자를 처리합니다. 파일 접근 권한은 Windows 상위 폴더의 ACL을 상속합니다.

**검증 범위:** macOS 초기 설치와 임시 계정 통합은 로컬에서 실행했습니다. Windows 분기와 레지스트리 원복은 자동 테스트했지만 실제 Windows PC의 `.cmd`·Win32 핸들·Aside 확장과 호스트 연결은 아직 실행 검증하지 않았습니다. [검증 기록](VALIDATION.ko.md)을 참고하세요.

## 설치 위치

| 항목 | macOS | Windows |
| --- | --- | --- |
| Python 환경·설치 파일 | `~/Library/Application Support/AsideJev` | `%LOCALAPPDATA%\AsideJev` |
| 설정·확장·키 파일·백업 | `~/.config/aside-jev` | `%USERPROFILE%\.config\aside-jev` |
| 계정 탐색 | 기존 `~/.aside/u/<숫자>/settings.json` | 기존 `%USERPROFILE%\.aside\u\<숫자>\settings.json` |
| Native host 등록 | 기존 Aside 데이터 폴더 → `NativeMessagingHosts` | 명시한 HKCU 호스트 키 → 설정 폴더의 manifest |

계정을 찾지 못하면 직접 경로를 지정할 수 있습니다. `ASIDE_JEV_INSTALL_DIR`은 실행 환경 위치, `--config-dir` 또는 `ASIDE_JEV_CONFIG_DIR`은 설정 위치를 바꿉니다. 연결 파일에는 실제 로컬 경로를 사용하세요. 심볼릭 링크·Windows junction·네트워크·장치 경로는 지원하지 않습니다.

## API 키와 설정

숨김 터미널 입력, `--env-file`로 지정한 기존 키 파일 또는 `TYPESAFE_API_KEY` / `TYPESAFEAI_API_KEY` 환경변수를 사용할 수 있습니다. 새 설치에서 터미널 환경변수만 존재하면 확인 후 로컬 키 파일에 보존해 이후 브라우저에서도 사용할 수 있게 합니다. 키는 **암호화되지 않은 로컬 파일**에 저장되며 출력하거나 팝업으로 보내지 않습니다. 키 파일은 위 두 이름의 단순 할당만 허용하고 셸 스크립트로 실행하지 않습니다.

키 입력을 건너뛰었다면 설치를 다시 실행해 입력할 수 있습니다. 키가 없으면 ON으로 켤 수 없습니다. 키 존재 여부는 인증 성공을 뜻하지 않습니다. 팝업은 MCP 설정 저장과 실제 MCP 연결 검증을 구분합니다.

## 미리보기·고급 설치

uv가 있는 개발자는 다음 명령을 사용할 수 있습니다.

```bash
uv run aside-jev setup --dry-run
uv run aside-jev setup --lang ko
```

`setup --dry-run`은 연결 파일과 레지스트리를 변경하지 않습니다. 바깥쪽 Install 실행 파일은 이 명령 전에 패키지 환경을 준비합니다. `setup --help`에서 `--profile-dir`, `--native-host-dir`, `--windows-registry-key`, `--env-file`, `--config-dir`, `--yes`(질문·키 입력 없는 명시적 적용)를 확인하세요.

기존 `scripts/setup_extension.py`도 수동 확장 ID와 명시 경로용으로 유지합니다. 기본은 미리보기이며 `--apply`는 로컬 연결만 등록하고 MCP 설정은 자동 병합하지 않습니다.

## 업데이트·비활성화·제거

- **간편 설치 업데이트:** 새 ZIP을 받아 같은 설치·설정 폴더로 다시 실행합니다. 업데이트 후 Aside에서 확장을 새로고침하세요. 백업과 다른 계정 설정은 보존합니다.
- **예전 수동 설치:** 새 고정 확장 ID나 키 파일 경로가 다를 수 있습니다. 설치기는 다른 연결로의 덮어쓰기를 거부합니다. 기존 팝업을 OFF로 바꾸고 MCP를 비활성화한 뒤 옛 확장을 제거하세요. 기존 미리보기에서 표시한 호스트 등록과 설정을 보관 이동한 뒤 새 간편 설치를 시작합니다. 새 연결 확인 전까지 백업을 보존하세요.
- **비활성화:** OFF로 바꾸고 새 작업을 시작합니다. 선택한 계정의 관리 지침만 제거하며 전용 MCP의 새 판단을 중단합니다. 이미 시작한 동작은 되돌리지 않습니다.
- **제거:** OFF로 바꾼 뒤 Aside의 Jev MCP와 확장을 제거합니다. 설치·설정 폴더와 미리보기에 나온 정확한 호스트 manifest를 보관 이동하세요. Windows에서는 이 설치가 소유한 `HKCU\…\com.aside_jev.control` 호스트 키만 제거하며 부모 키는 제거하지 않습니다. 필요하면 계정 문서를 백업에서 복구합니다.

ON은 새 작업 지침과 전용 Jev MCP 경로에 적용됩니다. 모든 Aside 내장 도구를 가로채지는 않습니다. 확장의 권한은 `nativeMessaging` 하나이며 전체 사이트 권한·content script·background service worker는 없습니다.
