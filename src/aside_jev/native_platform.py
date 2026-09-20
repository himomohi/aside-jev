"""Native Messaging의 플랫폼별 파일 보호와 실행 파일 생성을 담당한다."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path, PureWindowsPath
import re
import sys
from typing import Iterator
import uuid


class ControlError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def platform_name() -> str:
    return "windows" if sys.platform == "win32" else "posix"


def is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def validate_windows_path(path: str | Path) -> None:
    """장치 경로·공유 경로·대체 스트림과 Win32 별칭은 설치 대상으로 받지 않는다."""
    parsed = PureWindowsPath(path)
    if not re.fullmatch(r"[A-Za-z]:", parsed.drive) or not parsed.root:
        raise ControlError("unsafe_path", "Windows 설치에는 로컬 드라이브의 절대 경로를 지정해 주세요.")
    for part in parsed.parts[1:]:
        if any(character in part for character in '<>:"|?*\x00\r\n') or part.endswith((".", " ")):
            raise ControlError("unsafe_path", "Windows에서 안전하게 사용할 수 없는 파일 경로입니다.")
        if re.fullmatch(r"(?i)(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?", part):
            raise ControlError("unsafe_path", "Windows 장치 이름은 파일 경로로 사용할 수 없습니다.")


def _windows_api():
    # Windows에서만 시스템 DLL을 열어 다른 플랫폼의 import를 유지한다.
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    return kernel


def _open_windows_handle(path: Path, *, directory: bool, write: bool = False, create: bool = False) -> int:
    import ctypes
    from ctypes import wintypes

    class FileInformation(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("created", wintypes.FILETIME),
                    ("accessed", wintypes.FILETIME), ("written", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                    ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    kernel = _windows_api()
    access = 0 if directory else (0x80000000 | (0x40000000 if write else 0))
    flags = 0x00200000 | (0x02000000 if directory else 0)  # 링크 자체를 열고 부모 교체를 막는다.
    handle = kernel.CreateFileW(str(path), access, 0x1 | 0x2, None, 4 if create else 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = FileInformation()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & 0x400 or bool(info.attributes & 0x10) != directory or (not directory and info.links != 1):
            raise ControlError("unsafe_path", "링크·재분석 지점 또는 일반 파일이 아닌 설정 대상은 사용할 수 없습니다.")
        return handle
    except Exception:
        kernel.CloseHandle(handle)
        raise


@contextmanager
def windows_directory(path: Path, *, create: bool = False) -> Iterator[None]:
    """조상 디렉터리 핸들을 유지해 파일 작업 도중 경로가 교체되지 않게 한다."""
    validate_windows_path(path)
    handles = []
    try:
        current = Path(path.anchor)
        handles.append(_open_windows_handle(current, directory=True))
        for component in path.parts[1:]:
            current = current / component
            try:
                handle = _open_windows_handle(current, directory=True)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    current.mkdir()
                except FileExistsError:
                    pass
                handle = _open_windows_handle(current, directory=True)
            handles.append(handle)
        yield
    finally:
        for handle in reversed(handles):
            _windows_api().CloseHandle(handle)


def _windows_fd(path: Path, *, write: bool = False, create: bool = False) -> int:
    import msvcrt
    validate_windows_path(path)
    handle = _open_windows_handle(path, directory=False, write=write, create=create)
    try:
        return msvcrt.open_osfhandle(handle, (os.O_RDWR if write else os.O_RDONLY) | os.O_BINARY)
    except Exception:
        _windows_api().CloseHandle(handle)
        raise


def windows_read(path: Path, limit: int) -> bytes | None:
    try:
        with windows_directory(path.parent):
            fd = _windows_fd(path)
            with os.fdopen(fd, "rb") as stream:
                if os.fstat(stream.fileno()).st_size > limit:
                    raise ControlError("file_size", "설정 파일이 허용 크기를 초과했습니다.")
                data = stream.read(limit + 1)
                if len(data) > limit:
                    raise ControlError("file_size", "설정 파일이 허용 크기를 초과했습니다.")
                return data
    except FileNotFoundError:
        return None
    except OSError:
        raise ControlError("file_access", "설정 파일에 접근할 수 없습니다. 경로와 권한을 확인해 주세요.") from None


def windows_atomic_write(path: Path, data: bytes) -> None:
    validate_windows_path(path)
    with windows_directory(path.parent, create=True):
        # 기존 대상을 열어 링크와 하드링크를 확인한 뒤 닫아 교체를 허용한다.
        windows_read(path, 262144)
        temporary = path.parent / (".aside-jev-" + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_BINARY, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            windows_read(path, 262144)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def windows_unlink(path: Path) -> None:
    with windows_directory(path.parent):
        windows_read(path, 262144)
        path.unlink()


@contextmanager
def windows_lock(path: Path) -> Iterator[None]:
    import msvcrt
    with windows_directory(path.parent):
        fd = _windows_fd(path, write=True, create=True)
        locked = False
        try:
            # Windows 바이트 범위 잠금은 파일 끝 너머의 한 바이트에도 적용할 수 있다.
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError:
                raise ControlError("busy", "다른 설정 변경이 진행 중입니다. 잠시 후 다시 시도해 주세요.") from None
            yield
        finally:
            try:
                if locked:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(fd)


def cmd_quote_literal(value: str) -> str:
    if any(character in value for character in ('"', "\r", "\n", "\x00")):
        raise ControlError("unsafe_path", "실행 파일 경로에 지원하지 않는 문자가 있습니다.")
    # 배치 파일의 퍼센트 확장을 막고 지연 확장은 호출 스크립트에서 끈다.
    return '"' + value.replace("%", "%%") + '"'


def windows_launcher(python: str, *, native: bool) -> bytes:
    entry = "native-entry.py" if native else "mcp-entry.py"
    argument = ' "%~1"' if native else ""
    script = ("@echo off\r\nsetlocal DisableDelayedExpansion\r\n"
              "chcp 65001 >nul\r\n"
              f'{cmd_quote_literal(python)} -I "%~dp0{entry}"{argument}\r\n'
              "exit /b %errorlevel%\r\n")
    return script.encode("utf-8")


def windows_entry(*, native: bool) -> bytes:
    # 인수나 환경 파일은 셸로 평가하지 않는다. 설치 당시 폴더가 설정의 기준이다.
    ending = ("from aside_jev.native_host import main\nmain()\n" if native else
              "from aside_jev.cli import main\nsys.argv = [sys.argv[0], 'serve', '--extension']\nmain()\n")
    return ("# aside-jev가 관리하는 고정 진입점\nimport os\nimport sys\nfrom pathlib import Path\n"
            "os.environ['ASIDE_JEV_CONFIG_DIR'] = str(Path(__file__).parent)\n" + ending).encode("utf-8")


def windows_status_launcher(python: str) -> bytes:
    return windows_launcher(python, native=False).replace(b"mcp-entry.py", b"status-entry.py")


def windows_status_entry() -> bytes:
    return windows_entry(native=False).replace(b"'serve', '--extension'", b"'extension-status'")
