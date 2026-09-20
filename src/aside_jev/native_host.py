"""확장 요청 한 건을 처리하고 종료하는 Chrome Native Messaging 호스트."""
from __future__ import annotations

import json
import struct
import sys
from typing import Any, BinaryIO

from . import extension_control as control

MAX_MESSAGE_BYTES = 128 * 1024


def _read_exact(stream: BinaryIO, length: int) -> bytes:
    parts = bytearray()
    while len(parts) < length:
        block = stream.read(length - len(parts))
        if not block:
            break
        parts.extend(block)
    return bytes(parts)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite value")


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    header = _read_exact(stream, 4)
    if not header:
        return None
    if len(header) != 4:
        raise control.ControlError("protocol", "확장 메시지 헤더가 불완전합니다.")
    length = struct.unpack("=I", header)[0]
    if not 0 < length <= MAX_MESSAGE_BYTES:
        raise control.ControlError("message_size", "확장 메시지는 128 KiB 이하여야 합니다.")
    payload = _read_exact(stream, length)
    if len(payload) != length:
        raise control.ControlError("protocol", "확장 메시지가 불완전합니다.")
    try:
        message = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise control.ControlError("protocol", "확장 메시지의 JSON 형식이 올바르지 않습니다.") from None
    if not isinstance(message, dict):
        raise control.ControlError("protocol", "확장 메시지는 JSON 객체여야 합니다.")
    return message


def write_message(stream: BinaryIO, response: dict[str, Any]) -> None:
    payload = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        payload = b'{"ok":false,"error":{"code":"message_size","message":"Response exceeds limit"}}'
    stream.write(struct.pack("=I", len(payload)))
    stream.write(payload)
    stream.flush()


def dispatch(origin: str, message: dict[str, Any]) -> dict[str, Any]:
    control.validate_origin(origin)
    operation = message.get("op")
    if operation == "status":
        if set(message) != {"op"}:
            raise control.ControlError("input", "상태 요청에 지원하지 않는 항목이 있습니다.")
        status = control.get_status()
    elif operation == "set_enabled":
        if set(message) != {"op", "enabled"} or not isinstance(message["enabled"], bool):
            raise control.ControlError("input", "ON/OFF 요청은 enabled 값만 지정해 주세요.")
        status = control.set_enabled(message["enabled"])
    elif operation == "configure":
        if set(message) - {"op", "min_confidence", "timeout_s"} or len(message) == 1:
            raise control.ControlError("input", "최소 신뢰도와 HTTP 단계별 한도만 변경할 수 있습니다.")
        if any(value is None for name, value in message.items() if name != "op"):
            raise control.ControlError("input", "설정 값은 숫자여야 합니다.")
        status = control.configure(**{name: value for name, value in message.items() if name != "op"})
    else:
        raise control.ControlError("operation", "지원하지 않는 확장 요청입니다.")
    return {"ok": True, "status": status}


def serve(origin: str, *, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    """한 프레임만 처리한다. 감시 루프나 상주 프로세스를 만들지 않는다."""
    source = stdin if stdin is not None else sys.stdin.buffer
    destination = stdout if stdout is not None else sys.stdout.buffer
    try:
        message = read_message(source)
        if message is None:
            return 0
        response = dispatch(origin, message)
    except control.ControlError as error:
        response = {"ok": False, "error": {"code": error.code, "message": str(error)}}
    except Exception:
        # 파일 내용·키·예외 본문을 프로토콜 응답이나 로그에 출력하지 않는다.
        response = {"ok": False, "error": {"code": "internal", "message": "확장 요청을 처리하지 못했습니다. 설치 경로와 파일 권한을 확인해 주세요."}}
    try:
        write_message(destination, response)
    except (BrokenPipeError, OSError):
        return 1
    return 0


def main() -> None:
    origin = sys.argv[1] if len(sys.argv) == 2 else ""
    raise SystemExit(serve(origin))


if __name__ == "__main__":
    main()
