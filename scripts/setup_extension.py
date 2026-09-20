#!/usr/bin/env python3
"""Aside Jev Native Messaging 연결 설치를 미리 보거나 명시적으로 적용한다."""
from __future__ import annotations

import argparse
import json
import sys

from aside_jev.extension_control import ControlError, setup_installation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension-id", required=True, help="Aside 확장 관리 화면에 표시된 32자리 ID")
    parser.add_argument("--profile-dir", required=True, help="대상 Aside accountRoot의 실제 절대 경로")
    parser.add_argument("--native-host-dir", required=True, help="Aside가 사용하는 NativeMessagingHosts 폴더의 실제 경로")
    parser.add_argument("--env-file", help="허용된 TypeSafe 키의 단순 할당만 포함한 UTF-8 파일")
    parser.add_argument("--profile-label", help="확장 팝업에 표시할 프로필 이름")
    parser.add_argument("--config-dir", help="확장 전용 설정 폴더 (기본 ASIDE_JEV_CONFIG_DIR 또는 사용자 .config/aside-jev)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="설치 계획만 출력 (기본)")
    mode.add_argument("--apply", action="store_true", help="명시적 승인 후 연결 파일을 실제 등록")
    args = parser.parse_args()
    try:
        result = setup_installation(extension_id=args.extension_id, profile_dir=args.profile_dir, native_host_dir=args.native_host_dir,
                                    env_file=args.env_file, profile_label=args.profile_label, apply=args.apply, root=args.config_dir)
    except ControlError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError:
        print(json.dumps({"ok": False, "error": {"code": "file_access", "message": "설치 경로와 파일 권한을 확인해 주세요."}}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "plan": result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
